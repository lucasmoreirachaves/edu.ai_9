"""Painel do administrador da instituição (gestor): estrutura acadêmica, usuários, políticas, uso e privacidade."""
import csv
import io
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import correio, ia, scoring
from ..auth import gestor_only, hash_password
from ..db import CommitRoute, audit, get_db, jdump, jload, notify, one, rows
from ..ia_providers import ProvedorIndisponivel, usar_config
from ..ia_providers.nuvem import ProvedorNuvem
from ..util import PLANS, code, delete_material, institution_settings, mask_key
from .common import send_invite_email

router = APIRouter(prefix="/api/gestor", route_class=CommitRoute)

DEFAULT_SETTINGS = {
    "ai_model": ia.DEFAULT_MODEL, "ai_enabled": True, "publish_requires_review": False, "allow_class_code": True,
    "notify_new_activity": True, "notify_grades": True, "notify_weekly_report": True,
    "retention_days": 365, "privacy_admins": [], "welcome": "", "ticket_sla_days": 5,
    "menu_text": "auto",   # cor do texto do menu lateral: auto | branco | preto
}


def _settings(conn, iid) -> dict:
    return {**DEFAULT_SETTINGS, **institution_settings(conn, iid)}


def privacy_admin(user=Depends(gestor_only), conn=Depends(get_db)) -> dict:
    """Auditoria e dados pessoais: só gestores autorizados (lista vazia = todos os gestores)."""
    allowed = _settings(conn, user["institution_id"]).get("privacy_admins") or []
    if allowed and user["id"] not in allowed:
        raise HTTPException(403, "Acesso restrito ao responsável por privacidade da instituição")
    return user


# ================================================================== dashboard

@router.get("/dashboard")
def dashboard(user=Depends(gestor_only), conn=Depends(get_db)):
    iid = user["institution_id"]
    q = lambda sql, *p: conn.execute(sql, (iid, *p)).fetchone()[0]  # noqa: E731
    by_class = rows(conn.execute(
        """SELECT c.id, c.name, (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS students,
             (SELECT ROUND(AVG(s.score*10.0/a.points),1) FROM submissions s JOIN activities a ON a.id=s.activity_id WHERE a.class_id=c.id AND s.status='corrigida') AS avg
           FROM classes c WHERE c.institution_id=? ORDER BY c.name""", (iid,)))
    weekly = rows(conn.execute(
        """SELECT strftime('%Y-%W', created_at) AS week, COUNT(DISTINCT user_id) AS users FROM audit_log
           WHERE institution_id=? AND action='login' AND created_at >= date('now','-56 day') GROUP BY week ORDER BY week""", (iid,)))
    return {
        "kpis": {
            "students": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='aluno' AND status='ativo'"),
            "teachers": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='professor' AND status='ativo'"),
            "classes": q("SELECT COUNT(*) FROM classes WHERE institution_id=?"),
            "activities": q("SELECT COUNT(*) FROM activities a JOIN subjects s ON s.id=a.subject_id WHERE s.institution_id=? AND a.status<>'rascunho'"),
            "materials": q("SELECT COUNT(*) FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE s.institution_id=? AND m.status='publicado'"),
            "ai_month": q("SELECT COUNT(*) FROM ai_usage WHERE institution_id=? AND created_at >= date('now','start of month')"),
            "active_week": q("SELECT COUNT(DISTINCT user_id) FROM audit_log WHERE institution_id=? AND action='login' AND created_at >= date('now','-7 day')"),
            "pending_invites": q("SELECT COUNT(*) FROM invites WHERE institution_id=? AND status='pendente'"),
        },
        "by_class": by_class, "weekly": weekly,
        "recent": rows(conn.execute("SELECT a.action, a.detail, a.created_at, u.name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id WHERE a.institution_id=? ORDER BY a.id DESC LIMIT 8", (iid,))),
        "plan": plan_info(conn, iid),
    }


# ================================================================== instituição, unidades e cursos

class InstitutionIn(BaseModel):
    name: str
    cnpj: str = ""
    type: str = "Escola"
    color: str = "#172033"
    logo: str | None = None


@router.get("/institution")
def institution(user=Depends(gestor_only), conn=Depends(get_db)):
    iid = user["institution_id"]
    inst = one(conn.execute("SELECT id, name, slug, cnpj, type, color, logo, plan, created_at FROM institutions WHERE id=?", (iid,)))
    inst["units"] = rows(conn.execute(
        "SELECT u.*, (SELECT COUNT(*) FROM classes c WHERE c.unit_id=u.id) AS classes FROM units u WHERE u.institution_id=?", (iid,)))
    inst["courses"] = rows(conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM classes k WHERE k.course_id=c.id) AS classes FROM courses c WHERE c.institution_id=?", (iid,)))
    return inst


@router.put("/institution")
def update_institution(body: InstitutionIn, user=Depends(gestor_only), conn=Depends(get_db)):
    if body.logo and len(body.logo) > 400_000:
        raise HTTPException(400, "Logotipo muito grande (máx. 300 KB)")
    if body.logo and not re.match(r"^data:image/(png|jpe?g|gif|webp|svg\+xml);base64,", body.logo):
        raise HTTPException(400, "Logotipo em formato inválido")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", body.color or ""):
        raise HTTPException(400, "Cor inválida")
    if not body.name.strip():
        raise HTTPException(400, "Informe o nome da instituição")
    conn.execute("UPDATE institutions SET name=?, cnpj=?, type=?, color=?, logo=? WHERE id=?",
                 (body.name.strip(), body.cnpj, body.type, body.color, body.logo, user["institution_id"]))
    audit(conn, user, "instituicao.editada", body.name)
    return {"ok": True}


class NamedIn(BaseModel):
    name: str
    extra: str = ""   # cidade (unidade) ou nível (curso)


@router.post("/units")
def add_unit(body: NamedIn, user=Depends(gestor_only), conn=Depends(get_db)):
    return {"id": conn.execute("INSERT INTO units (institution_id, name, city) VALUES (?,?,?)", (user["institution_id"], body.name, body.extra)).lastrowid}


@router.delete("/units/{uid}")
def del_unit(uid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    conn.execute("UPDATE classes SET unit_id=NULL WHERE unit_id=? AND institution_id=?", (uid, user["institution_id"]))
    conn.execute("DELETE FROM units WHERE id=? AND institution_id=?", (uid, user["institution_id"]))
    return {"ok": True}


@router.post("/courses")
def add_course(body: NamedIn, user=Depends(gestor_only), conn=Depends(get_db)):
    return {"id": conn.execute("INSERT INTO courses (institution_id, name, level) VALUES (?,?,?)", (user["institution_id"], body.name, body.extra)).lastrowid}


@router.delete("/courses/{cid}")
def del_course(cid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    conn.execute("UPDATE classes SET course_id=NULL WHERE course_id=? AND institution_id=?", (cid, user["institution_id"]))
    conn.execute("DELETE FROM courses WHERE id=? AND institution_id=?", (cid, user["institution_id"]))
    return {"ok": True}


# ================================================================== usuários e convites

@router.get("/users")
def users(role: str | None = None, q: str | None = None, user=Depends(gestor_only), conn=Depends(get_db)):
    sql = """SELECT u.id, u.name, u.email, u.role, u.status, u.grade, u.last_login, u.created_at,
               (SELECT GROUP_CONCAT(c.name, ', ') FROM class_students cs JOIN classes c ON c.id=cs.class_id WHERE cs.user_id=u.id) AS classes,
               (SELECT GROUP_CONCAT(s.name || ' (' || c.name || ')', ', ') FROM subjects s JOIN classes c ON c.id=s.class_id WHERE s.teacher_id=u.id) AS subjects
             FROM users u WHERE u.institution_id=?"""
    params: list = [user["institution_id"]]
    if role:
        sql += " AND u.role=?"
        params.append(role)
    if q:
        sql += " AND (u.name LIKE ? OR u.email LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    return rows(conn.execute(sql + " ORDER BY u.name", params))


class UserUpdate(BaseModel):
    name: str
    role: str
    status: str
    grade: str | None = None


@router.put("/users/{uid}")
def update_user(uid: int, body: UserUpdate, user=Depends(gestor_only), conn=Depends(get_db)):
    u = one(conn.execute("SELECT * FROM users WHERE id=? AND institution_id=?", (uid, user["institution_id"])))
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    if body.role not in ("gestor", "professor", "aluno", "secretaria") or body.status not in ("ativo", "inativo"):
        raise HTTPException(400, "Papel ou status inválido")
    if uid == user["id"] and (body.role != "gestor" or body.status != "ativo"):
        raise HTTPException(400, "Você não pode remover o seu próprio acesso de gestor")
    if u.get("is_superadmin") and not user.get("is_superadmin"):
        raise HTTPException(403, "Esta conta é do administrador geral da plataforma")
    changed_access = u["role"] != body.role or u["status"] != body.status
    conn.execute("UPDATE users SET name=?, role=?, status=?, grade=?, token_version=token_version+? WHERE id=?",
                 (body.name, body.role, body.status, body.grade, int(changed_access), uid))
    if u["role"] == "professor" and body.role != "professor":
        n = conn.execute("SELECT COUNT(*) FROM subjects WHERE teacher_id=? AND active=1", (uid,)).fetchone()[0]
        if n:
            raise HTTPException(409, f"Este professor tem {n} disciplina(s) ativa(s). Transfira as disciplinas para outro professor antes.")
    if u["role"] != body.role:
        audit(conn, user, "permissao.alterada", f"{u['email']}: {u['role']} → {body.role}")
    if u["status"] != body.status:
        audit(conn, user, "usuario.desativado" if body.status == "inativo" else "usuario.reativado", u["email"])
    return {"ok": True}


@router.post("/users/{uid}/reset-password")
def reset_password(uid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    u = one(conn.execute("SELECT * FROM users WHERE id=? AND institution_id=?", (uid, user["institution_id"])))
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    if u.get("is_superadmin") and not user.get("is_superadmin"):
        raise HTTPException(403, "Esta conta é do administrador geral da plataforma")
    temp = "Edu-" + secrets.token_urlsafe(6)
    conn.execute("UPDATE users SET password_hash=?, token_version=token_version+1 WHERE id=?", (hash_password(temp), uid))
    audit(conn, user, "senha.redefinida", u["email"])
    return {"password": temp}


class InviteIn(BaseModel):
    emails: list[str]
    role: str
    class_id: int | None = None


def _create_invite(conn, user, email: str, role: str, class_id=None, name=None) -> dict:
    email = email.strip().lower()
    if "@" not in email or len(email) > 200:
        raise HTTPException(400, f"E-mail inválido: {email}")
    if class_id and not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?", (class_id, user["institution_id"]))):
        raise HTTPException(400, "Turma inválida")
    if one(conn.execute("SELECT id FROM users WHERE institution_id=? AND email=? AND status='ativo'", (user["institution_id"], email))):
        return {"email": email, "status": "já cadastrado"}
    token = secrets.token_urlsafe(16)
    conn.execute("UPDATE invites SET status='substituido' WHERE institution_id=? AND email=? AND status='pendente'", (user["institution_id"], email))
    conn.execute("INSERT INTO invites (institution_id, email, name, role, class_id, token) VALUES (?,?,?,?,?,?)",
                 (user["institution_id"], email, name, role, class_id if role == "aluno" else None, token))
    inst = one(conn.execute("SELECT name FROM institutions WHERE id=?", (user["institution_id"],)))
    send_invite_email(conn, user["institution_id"], inst["name"], email, role, token)
    return {"email": email, "status": "convidado", "token": token}


@router.post("/invites")
def invite(body: InviteIn, user=Depends(gestor_only), conn=Depends(get_db)):
    if body.role not in ("gestor", "professor", "aluno", "secretaria"):
        raise HTTPException(400, "Papel inválido")
    if len(body.emails) > 500:
        raise HTTPException(400, "Envie no máximo 500 convites por vez")
    out = [_create_invite(conn, user, e, body.role, body.class_id) for e in body.emails if e.strip()]
    audit(conn, user, "convites.enviados", f"{len(out)} {body.role}(s)")
    return out


@router.get("/invites")
def invites(user=Depends(gestor_only), conn=Depends(get_db)):
    return rows(conn.execute(
        "SELECT i.id, i.email, i.name, i.role, i.status, i.token, i.created_at, c.name AS class_name FROM invites i"
        " LEFT JOIN classes c ON c.id=i.class_id WHERE i.institution_id=? AND i.status='pendente' ORDER BY i.id DESC", (user["institution_id"],)))


@router.delete("/invites/{iid}")
def cancel_invite(iid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    conn.execute("UPDATE invites SET status='cancelado' WHERE id=? AND institution_id=?", (iid, user["institution_id"]))
    return {"ok": True}


class ImportIn(BaseModel):
    csv: str


@router.post("/import")
def import_csv(body: ImportIn, user=Depends(gestor_only), conn=Depends(get_db)):
    """CSV com colunas: nome;email;papel;turma (turma opcional, pelo nome)."""
    classes = {r["name"].lower(): r["id"] for r in rows(conn.execute("SELECT id, name FROM classes WHERE institution_id=?", (user["institution_id"],)))}
    text = body.csv.strip()
    delim = ";" if text.count(";") >= text.count(",") else ","
    out = []
    if text.count("\n") > 2000:
        raise HTTPException(400, "Importe no máximo 2.000 linhas por vez")
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
        if not row or (i == 0 and "mail" in ",".join(row).lower()):
            continue
        row = [c.strip() for c in row] + ["", "", "", ""]
        name, email, role, cls = row[:4]
        role = {"professora": "professor", "aluna": "aluno", "estudante": "aluno", "admin": "gestor", "secretario": "secretaria",
                "secretário": "secretaria", "secretária": "secretaria"}.get(role.lower(), role.lower() or "aluno")
        if role not in ("gestor", "professor", "aluno", "secretaria"):
            out.append({"email": email, "status": f"papel inválido: {role}"})
            continue
        try:
            out.append(_create_invite(conn, user, email, role, classes.get(cls.lower()), name or None))
        except HTTPException as e:
            out.append({"email": email, "status": e.detail})
    audit(conn, user, "usuarios.importados", f"{sum(1 for o in out if o['status'] == 'convidado')} convites")
    return out


# ================================================================== turmas e matrículas

class ClassIn(BaseModel):
    name: str
    grade: str = ""
    year: int = 2026
    unit_id: int | None = None
    course_id: int | None = None


@router.get("/classes")
def classes(user=Depends(gestor_only), conn=Depends(get_db)):
    out = rows(conn.execute(
        """SELECT c.*, u.name AS unit_name, k.name AS course_name,
             (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS students
           FROM classes c LEFT JOIN units u ON u.id=c.unit_id LEFT JOIN courses k ON k.id=c.course_id
           WHERE c.institution_id=? ORDER BY c.name""", (user["institution_id"],)))
    for c in out:
        c["subjects"] = rows(conn.execute(
            "SELECT s.id, s.name, s.active, u.id AS teacher_id, u.name AS teacher FROM subjects s JOIN users u ON u.id=s.teacher_id WHERE s.class_id=?", (c["id"],)))
    return out


def _check_class_refs(conn, user, body: ClassIn):
    iid = user["institution_id"]
    if not body.name.strip():
        raise HTTPException(400, "Informe o nome da turma")
    if body.unit_id and not one(conn.execute("SELECT id FROM units WHERE id=? AND institution_id=?", (body.unit_id, iid))):
        raise HTTPException(400, "Unidade inválida")
    if body.course_id and not one(conn.execute("SELECT id FROM courses WHERE id=? AND institution_id=?", (body.course_id, iid))):
        raise HTTPException(400, "Curso inválido")


def _new_class_code(conn) -> str:
    c = code(6, False)
    while one(conn.execute("SELECT id FROM classes WHERE code=?", (c,))):
        c = code(6, False)
    return c


@router.post("/classes")
def create_class(body: ClassIn, user=Depends(gestor_only), conn=Depends(get_db)):
    _check_class_refs(conn, user, body)
    cid = conn.execute("INSERT INTO classes (institution_id, unit_id, course_id, name, grade, year, code) VALUES (?,?,?,?,?,?,?)",
                       (user["institution_id"], body.unit_id, body.course_id, body.name.strip(), body.grade, body.year, _new_class_code(conn))).lastrowid
    audit(conn, user, "turma.criada", body.name)
    return {"id": cid}


@router.put("/classes/{cid}")
def update_class(cid: int, body: ClassIn, user=Depends(gestor_only), conn=Depends(get_db)):
    _check_class_refs(conn, user, body)
    conn.execute("UPDATE classes SET name=?, grade=?, year=?, unit_id=?, course_id=? WHERE id=? AND institution_id=?",
                 (body.name, body.grade, body.year, body.unit_id, body.course_id, cid, user["institution_id"]))
    return {"ok": True}


@router.delete("/classes/{cid}")
def delete_class(cid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    c = one(conn.execute("SELECT * FROM classes WHERE id=? AND institution_id=?", (cid, user["institution_id"])))
    if not c:
        raise HTTPException(404, "Turma não encontrada")
    if conn.execute("SELECT COUNT(*) FROM subjects WHERE class_id=?", (cid,)).fetchone()[0]:
        raise HTTPException(409, "A turma tem disciplinas vinculadas; remova-as antes")
    conn.execute("DELETE FROM class_students WHERE class_id=?", (cid,))
    conn.execute("DELETE FROM calendar_events WHERE class_id=?", (cid,))
    conn.execute("DELETE FROM classes WHERE id=?", (cid,))
    audit(conn, user, "turma.excluida", c["name"])
    return {"ok": True}


@router.get("/classes/{cid}")
def class_detail(cid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    c = one(conn.execute("SELECT * FROM classes WHERE id=? AND institution_id=?", (cid, user["institution_id"])))
    if not c:
        raise HTTPException(404, "Turma não encontrada")
    c["students"] = rows(conn.execute("SELECT u.id, u.name, u.email, u.status FROM users u JOIN class_students cs ON cs.user_id=u.id WHERE cs.class_id=? ORDER BY u.name", (cid,)))
    c["subjects"] = rows(conn.execute(
        """SELECT s.id, s.name, s.active, s.teacher_id, u.name AS teacher,
             (SELECT COUNT(*) FROM materials m WHERE m.subject_id=s.id) + (SELECT COUNT(*) FROM activities a WHERE a.subject_id=s.id)
             + (SELECT COUNT(*) FROM documents d WHERE d.subject_id=s.id) AS content
           FROM subjects s JOIN users u ON u.id=s.teacher_id WHERE s.class_id=? ORDER BY s.name""", (cid,)))
    return c


class EnrollIn(BaseModel):
    user_ids: list[int]


@router.post("/classes/{cid}/students")
def enroll(cid: int, body: EnrollIn, user=Depends(gestor_only), conn=Depends(get_db)):
    if not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?", (cid, user["institution_id"]))):
        raise HTTPException(404, "Turma não encontrada")
    n = 0
    for uid in body.user_ids:
        if one(conn.execute("SELECT id FROM users WHERE id=? AND institution_id=? AND role='aluno'", (uid, user["institution_id"]))):
            n += conn.execute("INSERT OR IGNORE INTO class_students (class_id, user_id) VALUES (?,?)", (cid, uid)).rowcount
    audit(conn, user, "matriculas", f"{n} aluno(s) na turma {cid}")
    return {"added": n}


@router.delete("/classes/{cid}/students/{uid}")
def unenroll(cid: int, uid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    if not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?", (cid, user["institution_id"]))):
        raise HTTPException(404, "Turma não encontrada")
    conn.execute("DELETE FROM class_students WHERE class_id=? AND user_id=?", (cid, uid))
    audit(conn, user, "matricula.removida", f"aluno {uid} da turma {cid}")
    return {"ok": True}


class SubjectLinkIn(BaseModel):
    class_id: int
    teacher_id: int
    name: str
    active: bool = True


def _check_link(conn, user, body: SubjectLinkIn):
    iid = user["institution_id"]
    if not body.name.strip():
        raise HTTPException(400, "Informe o nome da disciplina")
    if not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?", (body.class_id, iid))):
        raise HTTPException(400, "Turma inválida")
    if not one(conn.execute("SELECT id FROM users WHERE id=? AND institution_id=? AND role='professor' AND status='ativo'",
                            (body.teacher_id, iid))):
        raise HTTPException(400, "Professor inválido ou desativado")


@router.get("/subjects")
def list_subjects(user=Depends(gestor_only), conn=Depends(get_db)):
    """Grade de disciplinas da instituição: turma, professor responsável e uso."""
    return rows(conn.execute(
        """SELECT s.id, s.name, s.active, s.class_id, s.teacher_id, c.name AS class_name, u.name AS teacher,
             (SELECT COUNT(*) FROM materials m WHERE m.subject_id=s.id AND m.status='publicado') AS published,
             (SELECT COUNT(*) FROM activities a WHERE a.subject_id=s.id) AS activities
           FROM subjects s JOIN classes c ON c.id=s.class_id JOIN users u ON u.id=s.teacher_id
           WHERE s.institution_id=? ORDER BY c.name, s.name""", (user["institution_id"],)))


@router.post("/subjects")
def link_teacher(body: SubjectLinkIn, user=Depends(gestor_only), conn=Depends(get_db)):
    """Cria a disciplina na turma e define o professor responsável."""
    _check_link(conn, user, body)
    if one(conn.execute("SELECT id FROM subjects WHERE class_id=? AND lower(name)=lower(?) AND active=1", (body.class_id, body.name.strip()))):
        raise HTTPException(409, "Esta turma já tem uma disciplina ativa com esse nome")
    sid = conn.execute("INSERT INTO subjects (institution_id, teacher_id, class_id, name) VALUES (?,?,?,?)",
                       (user["institution_id"], body.teacher_id, body.class_id, body.name.strip())).lastrowid
    notify(conn, body.teacher_id, f"Você foi vinculado(a) à disciplina {body.name.strip()}", "Disciplinas", f"#/p/disciplina/{sid}")
    audit(conn, user, "disciplina.vinculada", body.name.strip())
    return {"id": sid}


@router.put("/subjects/{sid}")
def update_link(sid: int, body: SubjectLinkIn, user=Depends(gestor_only), conn=Depends(get_db)):
    """Troca professor, turma, nome ou situação. Materiais e atividades continuam com a disciplina."""
    s = one(conn.execute("SELECT * FROM subjects WHERE id=? AND institution_id=?", (sid, user["institution_id"])))
    if not s:
        raise HTTPException(404, "Disciplina não encontrada")
    _check_link(conn, user, body)
    if body.class_id != s["class_id"] and conn.execute("SELECT COUNT(*) FROM activities WHERE subject_id=?", (sid,)).fetchone()[0]:
        raise HTTPException(409, "A disciplina já tem atividades nesta turma. Para outra turma, crie uma disciplina nova.")
    conn.execute("UPDATE subjects SET teacher_id=?, class_id=?, name=?, active=? WHERE id=?",
                 (body.teacher_id, body.class_id, body.name.strip(), int(body.active), sid))
    if body.teacher_id != s["teacher_id"]:
        # jogos e materiais seguem a disciplina; o novo professor passa a vê-los
        conn.execute("UPDATE games SET teacher_id=? WHERE subject_id=? AND status IN ('rascunho','finalizado')", (body.teacher_id, sid))
        notify(conn, body.teacher_id, f"Você assumiu a disciplina {body.name.strip()}", "Disciplinas", f"#/p/disciplina/{sid}")
        notify(conn, s["teacher_id"], f"A disciplina {s['name']} foi transferida para outro professor", "Disciplinas", "#/p/disciplinas")
        audit(conn, user, "disciplina.transferida", f"{s['name']}: professor {s['teacher_id']} → {body.teacher_id}")
    audit(conn, user, "disciplina.editada", body.name.strip())
    return {"ok": True}


@router.delete("/subjects/{sid}")
def delete_link(sid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    """Exclui só disciplina sem conteúdo; com conteúdo, desative (mantém o histórico)."""
    s = one(conn.execute("SELECT * FROM subjects WHERE id=? AND institution_id=?", (sid, user["institution_id"])))
    if not s:
        raise HTTPException(404, "Disciplina não encontrada")
    used = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE subject_id=?", (sid,)).fetchone()[0]
               for t in ("materials", "activities", "documents", "questions", "games"))
    if used:
        raise HTTPException(409, "A disciplina já tem conteúdos ou atividades. Desative-a em vez de excluir, para manter o histórico.")
    conn.execute("DELETE FROM topics WHERE subject_id=?", (sid,))
    conn.execute("DELETE FROM subjects WHERE id=?", (sid,))
    audit(conn, user, "disciplina.excluida", s["name"])
    return {"ok": True}


# ================================================================== conteúdos e políticas

@router.get("/contents")
def contents(user=Depends(gestor_only), conn=Depends(get_db)):
    iid = user["institution_id"]
    mats = rows(conn.execute(
        """SELECT m.id, m.title, m.type, m.status, m.updated_at, m.ai_source, s.name AS subject_name, u.name AS teacher,
             (SELECT GROUP_CONCAT(c.name, ', ') FROM material_classes mc JOIN classes c ON c.id=mc.class_id WHERE mc.material_id=m.id) AS classes
           FROM materials m JOIN subjects s ON s.id=m.subject_id JOIN users u ON u.id=s.teacher_id
           WHERE s.institution_id=? AND m.status<>'arquivado' ORDER BY m.updated_at DESC LIMIT 200""", (iid,)))
    by_type = rows(conn.execute(
        "SELECT m.type, COUNT(*) AS n, SUM(m.status='publicado') AS published FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE s.institution_id=? GROUP BY m.type", (iid,)))
    docs = one(conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM documents WHERE institution_id=?", (iid,)))
    return {"materials": mats, "by_type": by_type, "documents": docs, "settings": _settings(conn, iid)}


@router.delete("/materials/{mid}")
def delete_material_gestor(mid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    m = one(conn.execute("SELECT m.title, s.teacher_id FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE m.id=? AND s.institution_id=?", (mid, user["institution_id"])))
    if not m:
        raise HTTPException(404, "Material não encontrado")
    delete_material(conn, mid)
    notify(conn, m["teacher_id"], f"O material “{m['title']}” foi excluído pela coordenação", "Materiais", "#/p/materiais")
    audit(conn, user, "material.excluido_gestor", m["title"])
    return {"ok": True}


@router.post("/materials/{mid}/archive")
def archive_material(mid: int, user=Depends(gestor_only), conn=Depends(get_db)):
    m = one(conn.execute("SELECT m.title, s.teacher_id FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE m.id=? AND s.institution_id=?", (mid, user["institution_id"])))
    if not m:
        raise HTTPException(404, "Material não encontrado")
    conn.execute("UPDATE materials SET status='arquivado' WHERE id=?", (mid,))
    conn.execute("DELETE FROM material_classes WHERE material_id=?", (mid,))
    notify(conn, m["teacher_id"], f"O material “{m['title']}” foi arquivado pela coordenação", "Materiais", f"#/p/material/{mid}")
    audit(conn, user, "material.arquivado_gestor", m["title"])
    return {"ok": True}


# ================================================================== relatórios institucionais

def _reports(conn, iid):
    by_class = rows(conn.execute(
        """SELECT c.name, (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS students,
             ROUND(AVG(s.score*10.0/a.points),1) AS avg, COUNT(s.id) AS submissions,
             (SELECT COUNT(*) FROM activities a2 WHERE a2.class_id=c.id AND a2.status<>'rascunho') AS activities
           FROM classes c LEFT JOIN activities a ON a.class_id=c.id LEFT JOIN submissions s ON s.activity_id=a.id AND s.status='corrigida'
           WHERE c.institution_id=? GROUP BY c.id ORDER BY c.name""", (iid,)))
    for c in by_class:
        exp = c["students"] * c["activities"]
        c["completion"] = round(100 * c["submissions"] / exp) if exp else None
    by_subject = rows(conn.execute(
        """SELECT s.name, COUNT(DISTINCT s.id) AS classes, ROUND(AVG(x.score*10.0/a.points),1) AS avg
           FROM subjects s LEFT JOIN activities a ON a.subject_id=s.id LEFT JOIN submissions x ON x.activity_id=a.id AND x.status='corrigida'
           WHERE s.institution_id=? GROUP BY s.name ORDER BY s.name""", (iid,)))
    teachers = rows(conn.execute(
        """SELECT u.name, (SELECT COUNT(*) FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE s.teacher_id=u.id) AS materials,
             (SELECT COUNT(*) FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE s.teacher_id=u.id AND m.status='publicado') AS published,
             (SELECT COUNT(*) FROM activities a WHERE a.created_by=u.id) AS activities,
             (SELECT COUNT(*) FROM games g WHERE g.teacher_id=u.id) AS games
           FROM users u WHERE u.institution_id=? AND u.role='professor' AND u.status='ativo' ORDER BY u.name""", (iid,)))
    results = scoring.question_results(conn, "a.subject_id IN (SELECT id FROM subjects WHERE institution_id=?)", (iid,))
    weekly = rows(conn.execute(
        """SELECT strftime('%Y-%W', s.submitted_at) AS week, COUNT(*) AS submissions, ROUND(AVG(s.score*10.0/a.points),1) AS avg
           FROM submissions s JOIN activities a ON a.id=s.activity_id JOIN subjects sub ON sub.id=a.subject_id
           WHERE sub.institution_id=? AND s.submitted_at >= date('now','-84 day') GROUP BY week ORDER BY week""", (iid,)))
    return {"by_class": by_class, "by_subject": by_subject, "teachers": teachers,
            "topics": scoring.by_topic(conn, results)[:10], "weekly": weekly}


@router.get("/reports")
def reports(user=Depends(gestor_only), conn=Depends(get_db)):
    return _reports(conn, user["institution_id"])


@router.get("/reports/export.csv")
def reports_csv(user=Depends(gestor_only), conn=Depends(get_db)):
    r = _reports(conn, user["institution_id"])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Turma", "Alunos", "Média (0-10)", "Conclusão (%)"])
    for c in r["by_class"]:
        w.writerow([c["name"], c["students"], c["avg"], c["completion"]])
    w.writerow([])
    w.writerow(["Disciplina", "Média (0-10)"])
    for s in r["by_subject"]:
        w.writerow([s["name"], s["avg"]])
    w.writerow([])
    w.writerow(["Professor", "Materiais", "Publicados", "Atividades", "Jogos"])
    for t in r["teachers"]:
        w.writerow([t["name"], t["materials"], t["published"], t["activities"], t["games"]])
    audit(conn, user, "relatorio.exportado", "institucional")
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=relatorio-institucional.csv"})


# ================================================================== planos e uso

def plan_info(conn, iid) -> dict:
    inst = one(conn.execute("SELECT plan FROM institutions WHERE id=?", (iid,)))
    limits = PLANS.get(inst["plan"], PLANS["Escola Pro"])
    q = lambda sql: conn.execute(sql, (iid,)).fetchone()[0]  # noqa: E731
    storage = q("SELECT COALESCE(SUM(size),0) FROM documents WHERE institution_id=?")
    return {"plan": inst["plan"], "limits": limits,
            "usage": {"teachers": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='professor' AND status='ativo'"),
                      "students": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='aluno' AND status='ativo'"),
                      "storage_mb": round(storage / 1024 / 1024, 2),
                      "ai_month": q("SELECT COUNT(*) FROM ai_usage WHERE institution_id=? AND created_at >= date('now','start of month')")}}


@router.get("/plan")
def plan(user=Depends(gestor_only), conn=Depends(get_db)):
    iid = user["institution_id"]
    info = plan_info(conn, iid)
    info["plans"] = PLANS
    info["request"] = one(conn.execute("SELECT plan, created_at FROM plan_requests WHERE institution_id=? AND status='pendente'", (iid,)))
    info["daily"] = rows(conn.execute(
        "SELECT date(created_at) AS day, COUNT(*) AS n, SUM(chars_in+chars_out) AS chars FROM ai_usage WHERE institution_id=? AND created_at >= date('now','-30 day') GROUP BY day ORDER BY day", (iid,)))
    info["by_kind"] = rows(conn.execute(
        "SELECT kind, COUNT(*) AS n FROM ai_usage WHERE institution_id=? AND created_at >= date('now','start of month') GROUP BY kind ORDER BY n DESC", (iid,)))
    info["by_provider"] = rows(conn.execute(
        "SELECT provider, model, COUNT(*) AS n, ROUND(AVG(ms)/1000.0,1) AS avg_s FROM ai_usage WHERE institution_id=? GROUP BY provider, model ORDER BY n DESC", (iid,)))
    info["history"] = rows(conn.execute(
        "SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS n FROM ai_usage WHERE institution_id=? GROUP BY month ORDER BY month DESC LIMIT 12", (iid,)))
    return info


class PlanIn(BaseModel):
    plan: str


@router.put("/plan")
def change_plan(body: PlanIn, user=Depends(gestor_only), conn=Depends(get_db)):
    """O gestor PEDE a troca; quem aprova (após contrato/pagamento) é o administrador geral da plataforma."""
    if body.plan not in PLANS:
        raise HTTPException(400, "Plano inválido")
    iid = user["institution_id"]
    if one(conn.execute("SELECT id FROM plan_requests WHERE institution_id=? AND status='pendente'", (iid,))):
        conn.execute("UPDATE plan_requests SET plan=?, user_id=?, created_at=CURRENT_TIMESTAMP WHERE institution_id=? AND status='pendente'",
                     (body.plan, user["id"], iid))
    else:
        conn.execute("INSERT INTO plan_requests (institution_id, user_id, plan) VALUES (?,?,?)", (iid, user["id"], body.plan))
    inst = one(conn.execute("SELECT name FROM institutions WHERE id=?", (iid,)))
    for a in rows(conn.execute("SELECT id FROM users WHERE is_superadmin=1 AND status='ativo'")):
        notify(conn, a["id"], f"{inst['name']} pediu o plano {body.plan}", "Planos", "#/admin/instituicoes")
    audit(conn, user, "plano.solicitado", body.plan)
    return {"ok": True, "requested": True}


# ================================================================== configurações

def _public_settings(s: dict) -> dict:
    """A chave da API nunca volta para o navegador."""
    return {k: v for k, v in s.items() if k != "ai_cloud"}


@router.get("/settings")
def get_settings(user=Depends(gestor_only), conn=Depends(get_db)):
    s = _settings(conn, user["institution_id"])
    usar_config({"mode": "local", "model": s["ai_model"]})   # esta aba mostra a IA local (Ollama)
    return {"settings": _public_settings(s), "ia": ia.status(s["ai_model"]), "email_configured": correio.configurado(),
            "gestores": rows(conn.execute("SELECT id, name FROM users WHERE institution_id=? AND role='gestor' AND status='ativo'", (user["institution_id"],)))}


@router.put("/settings")
def put_settings(body: dict, user=Depends(gestor_only), conn=Depends(get_db)):
    current = _settings(conn, user["institution_id"])
    if "privacy_admins" in body and body["privacy_admins"] != current["privacy_admins"]:
        privacy_admin(user, conn)  # só quem já é responsável muda a lista
    clean = {k: body[k] for k in DEFAULT_SETTINGS if k in body}
    for k, v in clean.items():  # cada configuração precisa ter o tipo certo
        default = DEFAULT_SETTINGS[k]
        if isinstance(default, bool) and not isinstance(v, bool):
            raise HTTPException(400, f"Valor inválido para {k}")
        if k == "ticket_sla_days" and (not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 60):
            raise HTTPException(400, "O prazo de resposta do atendimento deve ficar entre 1 e 60 dias")
        if k == "retention_days" and (not isinstance(v, int) or isinstance(v, bool) or not 30 <= v <= 3650):
            raise HTTPException(400, "O prazo de retenção deve ficar entre 30 e 3.650 dias")
        if k == "menu_text" and v not in ("auto", "branco", "preto"):
            raise HTTPException(400, "Cor do texto inválida: use auto, branco ou preto")
        if k in ("ai_model", "welcome") and (not isinstance(v, str) or len(v) > 300):
            raise HTTPException(400, f"Valor inválido para {k}")
    if "privacy_admins" in clean:
        ids = clean["privacy_admins"]
        gestores = {r[0] for r in conn.execute("SELECT id FROM users WHERE institution_id=? AND role='gestor'", (user["institution_id"],))}
        if not isinstance(ids, list) or any(i not in gestores for i in ids):
            raise HTTPException(400, "Responsáveis inválidos")
    current.update(clean)
    conn.execute("UPDATE institutions SET settings=? WHERE id=?", (jdump(current), user["institution_id"]))
    audit(conn, user, "configuracoes.alteradas", ", ".join(clean.keys()))
    return _public_settings(current)


# ================================================================== IA em nuvem da instituição (link e chave da API)

def _cloud_view(s: dict) -> dict:
    c = s.get("ai_cloud") or {}
    ready = bool(c.get("url") and c.get("key"))
    return {"url": c.get("url") or "", "key_masked": mask_key(c.get("key")), "has_key": bool(c.get("key")),
            "model": c.get("model") or "", "default_mode": s.get("ai_default_mode") or ("nuvem" if ready else "local"),
            "ready": ready, "local_model": s.get("ai_model") or ia.DEFAULT_MODEL, "tested_at": c.get("tested_at"),
            "test_ok": c.get("test_ok")}


@router.get("/ia-nuvem")
def get_cloud(user=Depends(gestor_only), conn=Depends(get_db)):
    return _cloud_view(_settings(conn, user["institution_id"]))


class CloudIn(BaseModel):
    url: str | None = None
    key: str | None = None            # vazio = mantém a chave atual; "-" apaga
    model: str | None = None
    default_mode: str | None = None   # nuvem | local


@router.put("/ia-nuvem")
def put_cloud(body: CloudIn, user=Depends(gestor_only), conn=Depends(get_db)):
    """Link e chave da API da IA contratada pela instituição: vale para todos os usuários dela."""
    s = _settings(conn, user["institution_id"])
    c = dict(s.get("ai_cloud") or {})
    changed = []
    if body.url is not None:
        url = body.url.strip()
        if url and not re.match(r"^https?://[^\s/$.?#].[^\s]*$", url, re.I):
            raise HTTPException(400, "O link da API precisa ser um endereço http:// ou https:// válido")
        c["url"] = url[:500]
        changed.append("link")
    if body.key == "-":
        c.pop("key", None)
        changed.append("chave removida")
    elif body.key:
        if len(body.key.strip()) < 8:
            raise HTTPException(400, "Chave da API muito curta")
        c["key"] = body.key.strip()[:500]
        changed.append("chave")
    if body.model is not None:
        c["model"] = body.model.strip()[:120]
        changed.append("modelo")
    if changed:
        c.pop("test_ok", None)
        c.pop("tested_at", None)
    s["ai_cloud"] = c
    if body.default_mode is not None:
        if body.default_mode not in ("nuvem", "local"):
            raise HTTPException(400, "Modo padrão inválido")
        s["ai_default_mode"] = body.default_mode
        changed.append(f"modo padrão {body.default_mode}")
    conn.execute("UPDATE institutions SET settings=? WHERE id=?", (jdump(s), user["institution_id"]))
    audit(conn, user, "ia.nuvem_configurada", ", ".join(changed) or "sem mudanças")   # a chave nunca vai para a auditoria
    return _cloud_view(s)


@router.post("/ia-nuvem/testar")
def test_cloud(user=Depends(gestor_only), conn=Depends(get_db)):
    """Faz uma pergunta curta à IA em nuvem para conferir o link, a chave e o modelo."""
    s = _settings(conn, user["institution_id"])
    c = s.get("ai_cloud") or {}
    if not (c.get("url") and c.get("key")):
        raise HTTPException(400, "Cadastre o link e a chave da API antes de testar")
    p = ProvedorNuvem(c["url"], c["key"], c.get("model") or "")
    try:
        out = p.conversar([{"role": "user", "content": "Responda apenas: OK"}], c.get("model") or "", 0, 30)
        ok, msg = True, (out or "").strip()[:200] or "(resposta vazia)"
    except (ProvedorIndisponivel, RuntimeError) as e:
        ok, msg = False, str(e)[:300]
    c.update(test_ok=ok, tested_at=datetime.utcnow().isoformat(timespec="seconds"))
    s["ai_cloud"] = c
    conn.execute("UPDATE institutions SET settings=? WHERE id=?", (jdump(s), user["institution_id"]))
    return {"ok": ok, "message": msg, "url": p.url}


# ================================================================== faturas da plataforma (somente leitura)

@router.get("/faturas")
def minhas_faturas(user=Depends(gestor_only), conn=Depends(get_db)):
    today = datetime.utcnow().date().isoformat()
    out = rows(conn.execute("SELECT id, reference, description, amount, due_date, status, paid_at, payment_method FROM invoices"
                            " WHERE institution_id=? AND status<>'cancelada' ORDER BY due_date DESC", (user["institution_id"],)))
    for f in out:
        f["overdue"] = f["status"] == "aberta" and f["due_date"] < today
        f["situacao"] = "vencida" if f["overdue"] else f["status"]
    return out


# ================================================================== auditoria e privacidade

@router.get("/audit")
def audit_log(q: str | None = None, action: str | None = None, limit: int = 200, user=Depends(privacy_admin), conn=Depends(get_db)):
    sql = "SELECT a.*, u.name AS user_name, u.role FROM audit_log a LEFT JOIN users u ON u.id=a.user_id WHERE a.institution_id=?"
    params: list = [user["institution_id"]]
    if q:
        sql += " AND (a.detail LIKE ? OR u.name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if action:
        sql += " AND a.action LIKE ?"
        params.append(f"{action}%")
    return rows(conn.execute(sql + " ORDER BY a.id DESC LIMIT ?", (*params, min(limit, 1000))))


@router.get("/data-requests")
def data_requests(user=Depends(privacy_admin), conn=Depends(get_db)):
    return rows(conn.execute(
        "SELECT d.*, u.name, u.email, u.role FROM data_requests d JOIN users u ON u.id=d.user_id WHERE d.institution_id=? ORDER BY d.status, d.id DESC",
        (user["institution_id"],)))


class ResolveIn(BaseModel):
    status: str   # concluida | recusada


@router.post("/data-requests/{rid}/resolve")
def resolve_request(rid: int, body: ResolveIn, user=Depends(privacy_admin), conn=Depends(get_db)):
    r = one(conn.execute("SELECT * FROM data_requests WHERE id=? AND institution_id=?", (rid, user["institution_id"])))
    if not r:
        raise HTTPException(404, "Solicitação não encontrada")
    if r["kind"] == "exclusao" and body.status == "concluida":
        _anonymize(conn, r["user_id"])
    conn.execute("UPDATE data_requests SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE id=?", (body.status, rid))
    notify(conn, r["user_id"], f"Sua solicitação de {r['kind']} de dados foi {body.status}", "Privacidade", "#/perfil")
    audit(conn, user, "lgpd.resolvida", f"{r['kind']} #{rid}: {body.status}")
    return {"ok": True}


def _anonymize(conn, uid: int):
    """Remove o que identifica a pessoa. Notas e entregas ficam (sem nome), pois a escola pode ter
    obrigação legal de guardar o histórico escolar; respostas discursivas (texto livre) são apagadas."""
    u = one(conn.execute("SELECT email, name FROM users WHERE id=?", (uid,)))
    conn.execute("UPDATE users SET name='Usuário removido', email=?, password_hash=NULL, status='inativo', grade=NULL,"
                 " totp_secret=NULL, two_factor=0, token_version=token_version+1 WHERE id=?", (f"removido-{uid}@anonimo.local", uid))
    conn.execute("UPDATE game_players SET name='Anônimo' WHERE user_id=?", (uid,))
    for t in ("notifications", "password_resets", "material_progress", "flashcard_reviews"):
        conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    for s in rows(conn.execute("SELECT id, answers, grading FROM submissions WHERE student_id=?", (uid,))):
        answers = {k: (v if isinstance(v, int) else "[removido]") for k, v in (jload(s["answers"], {}) or {}).items()}
        grading = {k: {**g, "ai_feedback": None} for k, g in (jload(s["grading"], {}) or {}).items()}
        conn.execute("UPDATE submissions SET answers=?, grading=? WHERE id=?", (jdump(answers), jdump(grading), s["id"]))
    conn.execute("UPDATE ticket_messages SET body='[mensagem removida a pedido do titular]', attachment=NULL WHERE user_id=?", (uid,))
    if u:
        for col in ("detail",):
            conn.execute(f"UPDATE audit_log SET {col}=REPLACE({col}, ?, '[removido]') WHERE {col} LIKE ?", (u["email"], f"%{u['email']}%"))
            conn.execute(f"UPDATE audit_log SET {col}=REPLACE({col}, ?, '[removido]') WHERE {col} LIKE ?", (u["name"], f"%{u['name']}%"))
        conn.execute("UPDATE invites SET email=?, name=NULL WHERE lower(email)=lower(?)", (f"removido-{uid}@anonimo.local", u["email"]))
        conn.execute("UPDATE outbox SET to_email='[removido]', body='[removido]' WHERE lower(to_email)=lower(?)", (u["email"],))


@router.get("/users/{uid}/export")
def export_user(uid: int, user=Depends(privacy_admin), conn=Depends(get_db)):
    u = one(conn.execute("SELECT id, name, email, role, status, grade, created_at, last_login, consent_at FROM users WHERE id=? AND institution_id=?",
                         (uid, user["institution_id"])))
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    data = {"usuario": u,
            "turmas": rows(conn.execute("SELECT c.name FROM class_students cs JOIN classes c ON c.id=cs.class_id WHERE cs.user_id=?", (uid,))),
            "entregas": [{**s, "answers": jload(s["answers"], {}), "grading": jload(s["grading"], {})} for s in
                         rows(conn.execute("SELECT a.title, s.answers, s.grading, s.score, s.submitted_at FROM submissions s JOIN activities a ON a.id=s.activity_id WHERE s.student_id=?", (uid,)))],
            "progresso": rows(conn.execute("SELECT m.title, p.pct, p.updated_at FROM material_progress p JOIN materials m ON m.id=p.material_id WHERE p.user_id=?", (uid,))),
            "jogos": rows(conn.execute("SELECT g.title, p.score FROM game_players p JOIN games g ON g.id=p.game_id WHERE p.user_id=?", (uid,))),
            "chamados": [{**t, "mensagens": rows(conn.execute("SELECT body, created_at FROM ticket_messages WHERE ticket_id=? AND internal=0", (t["id"],)))}
                         for t in rows(conn.execute("SELECT id, protocol, category, subject, status, created_at FROM tickets WHERE user_id=?", (uid,)))],
            "registros": rows(conn.execute("SELECT action, detail, created_at FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT 500", (uid,)))}
    audit(conn, user, "lgpd.exportacao", u["email"])
    return data


@router.post("/retention/apply")
def apply_retention(user=Depends(privacy_admin), conn=Depends(get_db)):
    days = int(_settings(conn, user["institution_id"]).get("retention_days") or 365)
    n = conn.execute("DELETE FROM audit_log WHERE institution_id=? AND created_at < date('now', ?)",
                     (user["institution_id"], f"-{days} day")).rowcount
    n2 = conn.execute("DELETE FROM notifications WHERE read=1 AND created_at < date('now', ?) AND user_id IN (SELECT id FROM users WHERE institution_id=?)",
                      (f"-{days} day", user["institution_id"])).rowcount
    audit(conn, user, "retencao.aplicada", f"{n} registros de auditoria e {n2} notificações removidos (>{days} dias)")
    return {"audit_removed": n, "notifications_removed": n2}
