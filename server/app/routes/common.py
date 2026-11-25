"""Acesso e recursos compartilhados: login, onboarding, convites, perfil, notificações, busca."""
import re
import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import correio, ia
from ..auth import check_password, current_user, hash_password, make_2fa_ticket, make_token, read_2fa_ticket
from ..db import CommitRoute, audit, get_db, jdump, jload, one, rows
from ..seguranca import client_ip, hash_token, limitar, limpar, novo_segredo, otpauth_uri, verificar_totp
from ..util import ai_config, ai_model, institution_settings, mask_key, student_class_ids, teacher_subject_ids

PLANO_INICIAL = "Essencial"  # cadastro público começa no plano básico; upgrade passa pelo admin geral

router = APIRouter(prefix="/api", route_class=CommitRoute)


def _public_user(conn, u: dict) -> dict:
    inst = one(conn.execute("SELECT id, name, slug, color, logo, plan, settings FROM institutions WHERE id=?",
                            (u["institution_id"],)))
    settings = jload(inst.pop("settings"), {}) or {}
    inst["settings"] = {k: settings.get(k) for k in ("ai_model", "welcome", "menu_text")}
    prefs = jload(u.get("ai_prefs"), {}) or {}
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "grade": u.get("grade"),
            "two_factor": bool(u.get("two_factor")), "weekly_email": u.get("weekly_email"), "institution": inst,
            "is_superadmin": bool(u.get("is_superadmin")), "impersonated_by": u.get("impersonated_by"),
            "ai_mode": prefs.get("mode") or "", "has_photo": bool(u.get("photo"))}


# ------------------------------------------------------------------ login

class LoginIn(BaseModel):
    institution: str
    email: str
    password: str


def _finish_login(conn, u: dict) -> dict:
    conn.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (u["id"],))
    audit(conn, u, "login", u["email"])
    return {"token": make_token(u), "user": _public_user(conn, u)}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, conn=Depends(get_db)):
    chave = f"login:{body.institution.strip().lower()}:{body.email.strip().lower()}"
    limitar(f"login-ip:{client_ip(request)}", 30, 600)   # um mesmo IP tentando muitas contas
    limitar(chave, 8, 900, "Muitas tentativas para esta conta. Aguarde 15 minutos ou use “Esqueci minha senha”.")
    inst = one(conn.execute("SELECT * FROM institutions WHERE slug=?", (body.institution.strip().lower(),)))
    u = inst and one(conn.execute("SELECT * FROM users WHERE institution_id=? AND lower(email)=lower(?)",
                                  (inst["id"], body.email.strip())))
    if not u or not check_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Instituição, e-mail ou senha incorretos")
    if u["is_superadmin"]:
        raise HTTPException(403, "Administradores gerais entram pelo acesso administrativo da plataforma.")
    if u["status"] != "ativo":
        raise HTTPException(403, "Conta desativada. Fale com o administrador da instituição.")
    if not inst["active"] and not u["is_superadmin"]:
        raise HTTPException(403, "Instituição suspensa. Fale com o suporte da plataforma.")
    limpar(chave)
    if u["two_factor"] and u["totp_secret"]:
        return {"needs_2fa": True, "ticket": make_2fa_ticket(u)}
    return _finish_login(conn, u)


class AdminLoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/admin-login")
def admin_login(body: AdminLoginIn, request: Request, conn=Depends(get_db)):
    """Login exclusivo do administrador geral da plataforma (sem código de instituição)."""
    limitar(f"login-ip:{client_ip(request)}", 30, 600)
    chave = f"admin-login:{body.email.strip().lower()}"
    limitar(chave, 6, 900, "Muitas tentativas. Aguarde 15 minutos.")
    u = one(conn.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND is_superadmin=1", (body.email.strip(),)))
    if not u or not check_password(body.password, u["password_hash"]):
        raise HTTPException(401, "E-mail ou senha incorretos")
    if u["status"] != "ativo":
        raise HTTPException(403, "Conta de administrador desativada")
    limpar(chave)
    if u["two_factor"] and u["totp_secret"]:
        return {"needs_2fa": True, "ticket": make_2fa_ticket(u)}
    return _finish_login(conn, u)


class TwoFactorIn(BaseModel):
    ticket: str
    code: str


@router.post("/auth/2fa")
def login_2fa(body: TwoFactorIn, conn=Depends(get_db)):
    uid = read_2fa_ticket(body.ticket)
    limitar(f"2fa:{uid}", 6, 300, "Muitos códigos incorretos. Aguarde 5 minutos.")
    u = one(conn.execute("SELECT * FROM users WHERE id=? AND status='ativo'", (uid,)))
    if not u or not verificar_totp(u["totp_secret"], body.code):
        raise HTTPException(401, "Código incorreto")
    limpar(f"2fa:{uid}")
    return _finish_login(conn, u)


# ------------------------------------------------------------------ esqueci minha senha

class ForgotIn(BaseModel):
    institution: str
    email: str


@router.post("/auth/forgot")
def forgot(body: ForgotIn, request: Request, conn=Depends(get_db)):
    """Sempre responde igual (não revela se o e-mail existe). O link vale 1 hora."""
    limitar(f"forgot-ip:{client_ip(request)}", 10, 3600)
    limitar(f"forgot:{body.email.strip().lower()}", 3, 3600)
    inst = one(conn.execute("SELECT id, name FROM institutions WHERE slug=?", (body.institution.strip().lower(),)))
    u = inst and one(conn.execute("SELECT * FROM users WHERE institution_id=? AND lower(email)=lower(?) AND status='ativo'",
                                  (inst["id"], body.email.strip())))
    if u:
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?,?,?)",
                     (u["id"], hash_token(token), time.time() + 3600))
        correio.enviar(conn, u["email"], "Redefinição de senha — EDU.AI",
                       f"Olá, {u['name']}.\n\nRecebemos um pedido para redefinir a sua senha em {inst['name']}.\n"
                       f"Para criar uma nova senha, abra o link abaixo (válido por 1 hora):\n\n"
                       f"{correio.link('#/redefinir-senha/' + token)}\n\n"
                       "Se você não pediu, ignore este e-mail: a sua senha continua a mesma.", inst["id"])
        audit(conn, u, "senha.recuperacao_pedida", u["email"])
    return {"ok": True, "email_configured": correio.configurado()}


class ResetIn(BaseModel):
    token: str
    password: str


@router.post("/auth/reset")
def reset(body: ResetIn, request: Request, conn=Depends(get_db)):
    limitar(f"reset-ip:{client_ip(request)}", 20, 3600)
    r = one(conn.execute("SELECT * FROM password_resets WHERE token_hash=? AND used=0", (hash_token(body.token),)))
    if not r or r["expires_at"] < time.time():
        raise HTTPException(400, "Link inválido ou expirado. Peça um novo em “Esqueci minha senha”.")
    if len(body.password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    conn.execute("UPDATE password_resets SET used=1 WHERE user_id=?", (r["user_id"],))
    conn.execute("UPDATE users SET password_hash=?, token_version=token_version+1 WHERE id=?",
                 (hash_password(body.password), r["user_id"]))
    u = one(conn.execute("SELECT * FROM users WHERE id=?", (r["user_id"],)))
    audit(conn, u, "senha.redefinida_por_link", u["email"])
    return {"ok": True}


@router.get("/institutions/{slug}")
def institution_public(slug: str, conn=Depends(get_db)):
    inst = one(conn.execute("SELECT name, slug, color, logo FROM institutions WHERE slug=?", (slug.lower(),)))
    if not inst:
        raise HTTPException(404, "Instituição não encontrada")
    return inst


# ------------------------------------------------------------------ onboarding (nova instituição)

class OnboardingIn(BaseModel):
    name: str
    cnpj: str = ""
    type: str = "Escola"
    color: str = "#172033"
    units: list[str] = []
    courses: list[str] = []
    admin_name: str
    admin_email: str
    admin_password: str
    invites: list[dict] = []          # [{email, role}]
    plan: str = PLANO_INICIAL   # ignorado: toda instituição nova começa no plano inicial


def _slugify(name: str) -> str:
    s = name.lower()
    for a, b in zip("áàâãéêíóôõúüç", "aaaaeeiooouuc"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "instituicao"


@router.post("/onboarding")
def onboarding(body: OnboardingIn, request: Request, conn=Depends(get_db)):
    limitar(f"onboarding:{client_ip(request)}", 5, 3600, "Muitos cadastros a partir desta rede. Tente mais tarde.")
    if not body.name.strip() or "@" not in body.admin_email:
        raise HTTPException(400, "Informe o nome da instituição e um e-mail válido")
    if len(body.admin_password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    slug, base, n = _slugify(body.name), _slugify(body.name), 1
    while one(conn.execute("SELECT id FROM institutions WHERE slug=?", (slug,))):
        n += 1
        slug = f"{base}-{n}"
    iid = conn.execute("INSERT INTO institutions (name, slug, cnpj, type, color, plan) VALUES (?,?,?,?,?,?)",
                       (body.name.strip(), slug, body.cnpj, body.type, _color(body.color), PLANO_INICIAL)).lastrowid
    for u in body.units or ["Unidade principal"]:
        conn.execute("INSERT INTO units (institution_id, name) VALUES (?,?)", (iid, u))
    for c in body.courses:
        conn.execute("INSERT INTO courses (institution_id, name) VALUES (?,?)", (iid, c))
    uid = conn.execute(
        "INSERT INTO users (institution_id, name, email, password_hash, role, consent_at) VALUES (?,?,?,?,'gestor',CURRENT_TIMESTAMP)",
        (iid, body.admin_name, body.admin_email.lower(), hash_password(body.admin_password))).lastrowid
    u = one(conn.execute("SELECT * FROM users WHERE id=?", (uid,)))
    for inv in body.invites[:200]:
        if inv.get("email") and "@" in inv["email"] and inv.get("role") in ("professor", "aluno", "gestor", "secretaria"):
            token = secrets.token_urlsafe(16)
            conn.execute("INSERT INTO invites (institution_id, email, role, token) VALUES (?,?,?,?)",
                         (iid, inv["email"].strip().lower(), inv["role"], token))
            send_invite_email(conn, iid, body.name, inv["email"].strip().lower(), inv["role"], token)
    audit(conn, u, "instituicao.criada", body.name)
    return {"token": make_token(u), "user": _public_user(conn, u), "slug": slug}


def _color(c: str) -> str:
    return c if re.fullmatch(r"#[0-9A-Fa-f]{6}", c or "") else "#172033"


PAPEL = {"professor": "professor(a)", "aluno": "aluno(a)", "gestor": "gestor(a)", "secretaria": "secretário(a)"}


def send_invite_email(conn, institution_id: int, institution_name: str, email: str, role: str, token: str):
    correio.enviar(conn, email, f"Convite para a plataforma de {institution_name}",
                   f"Olá!\n\nVocê foi convidado(a) como {PAPEL.get(role, role)} na plataforma EDU.AI de {institution_name}.\n"
                   f"Para ativar a sua conta e criar a sua senha, abra:\n\n{correio.link('#/convite/' + token)}\n",
                   institution_id)


# ------------------------------------------------------------------ convites

@router.get("/invites/{token}")
def invite_info(token: str, conn=Depends(get_db)):
    inv = one(conn.execute(
        "SELECT i.email, i.name, i.role, i.status, n.name AS institution, n.slug FROM invites i"
        " JOIN institutions n ON n.id=i.institution_id WHERE i.token=?", (token,)))
    if not inv:
        raise HTTPException(404, "Convite inválido")
    if inv["status"] != "pendente":
        raise HTTPException(410, "Este convite já foi utilizado")
    return inv


class AcceptIn(BaseModel):
    name: str
    password: str
    accept_terms: bool


@router.post("/invites/{token}/accept")
def invite_accept(token: str, body: AcceptIn, request: Request, conn=Depends(get_db)):
    limitar(f"invite-ip:{client_ip(request)}", 20, 3600)
    inv = one(conn.execute("SELECT * FROM invites WHERE token=? AND status='pendente'", (token,)))
    if not inv:
        raise HTTPException(404, "Convite inválido ou já utilizado")
    if not body.accept_terms:
        raise HTTPException(400, "É preciso aceitar os Termos de Uso e a Política de Privacidade")
    if len(body.password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    existing = one(conn.execute("SELECT id FROM users WHERE institution_id=? AND email=?",
                                (inv["institution_id"], inv["email"])))
    if existing:
        conn.execute("UPDATE users SET name=?, password_hash=?, status='ativo', consent_at=CURRENT_TIMESTAMP, token_version=token_version+1 WHERE id=?",
                     (body.name, hash_password(body.password), existing["id"]))
        uid = existing["id"]
    else:
        uid = conn.execute(
            "INSERT INTO users (institution_id, name, email, password_hash, role, consent_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
            (inv["institution_id"], body.name, inv["email"], hash_password(body.password), inv["role"])).lastrowid
    if inv["class_id"]:
        conn.execute("INSERT OR IGNORE INTO class_students (class_id, user_id) VALUES (?,?)", (inv["class_id"], uid))
    conn.execute("UPDATE invites SET status='aceito' WHERE id=?", (inv["id"],))
    u = one(conn.execute("SELECT * FROM users WHERE id=?", (uid,)))
    audit(conn, u, "convite.aceito", u["email"])
    for g in rows(conn.execute("SELECT id FROM users WHERE institution_id=? AND role='gestor'", (u["institution_id"],))):
        conn.execute("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)",
                     (g["id"], f"{u['name']} aceitou o convite", "Usuários", "#/g/usuarios"))
    return {"token": make_token(u), "user": _public_user(conn, u)}


class JoinIn(BaseModel):
    institution: str
    class_code: str
    name: str
    email: str
    password: str
    accept_terms: bool


@router.post("/auth/join-class")
def join_class(body: JoinIn, request: Request, conn=Depends(get_db)):
    """Aluno cria a conta com o código da turma informado pelo professor."""
    limitar(f"join-ip:{client_ip(request)}", 10, 3600, "Muitas tentativas de código de turma. Aguarde e tente de novo.")
    inst = one(conn.execute("SELECT * FROM institutions WHERE slug=?", (body.institution.strip().lower(),)))
    if not inst or not institution_settings(conn, inst["id"]).get("allow_class_code", True):
        raise HTTPException(404, "Instituição não encontrada ou cadastro por código desativado")
    cls = one(conn.execute("SELECT * FROM classes WHERE institution_id=? AND upper(code)=upper(?)",
                           (inst["id"], body.class_code.strip())))
    if not cls:
        raise HTTPException(404, "Código de turma inválido")
    if not body.accept_terms:
        raise HTTPException(400, "É preciso aceitar os termos")
    if len(body.password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    if "@" not in body.email or not body.name.strip():
        raise HTTPException(400, "Informe nome e e-mail válidos")
    if one(conn.execute("SELECT id FROM users WHERE institution_id=? AND lower(email)=lower(?)", (inst["id"], body.email))):
        raise HTTPException(409, "Já existe uma conta com este e-mail. Entre com a sua senha.")
    uid = conn.execute(
        "INSERT INTO users (institution_id, name, email, password_hash, role, grade, consent_at) VALUES (?,?,?,?,'aluno',?,CURRENT_TIMESTAMP)",
        (inst["id"], body.name, body.email.lower(), hash_password(body.password), cls["grade"])).lastrowid
    conn.execute("INSERT INTO class_students (class_id, user_id) VALUES (?,?)", (cls["id"], uid))
    u = one(conn.execute("SELECT * FROM users WHERE id=?", (uid,)))
    audit(conn, u, "aluno.cadastro_codigo", cls["name"])
    return {"token": make_token(u), "user": _public_user(conn, u)}


# ------------------------------------------------------------------ perfil

@router.get("/me")
def me(user=Depends(current_user), conn=Depends(get_db)):
    return _public_user(conn, user)


class ProfileIn(BaseModel):
    name: str
    email: str
    weekly_email: bool = True


@router.put("/me")
def update_me(body: ProfileIn, user=Depends(current_user), conn=Depends(get_db)):
    if not body.name.strip() or "@" not in body.email:
        raise HTTPException(400, "Informe nome e e-mail válidos")
    clash = one(conn.execute("SELECT id FROM users WHERE institution_id=? AND lower(email)=lower(?) AND id<>?",
                             (user["institution_id"], body.email, user["id"])))
    if clash:
        raise HTTPException(409, "E-mail já usado por outro usuário")
    if body.email.strip().lower() != user["email"].lower():
        audit(conn, user, "email.alterado", f"{user['email']} → {body.email.strip().lower()}")
        correio.enviar(conn, user["email"], "Seu e-mail foi alterado — EDU.AI",
                       f"O e-mail da sua conta foi trocado para {body.email.strip().lower()}. Se não foi você, avise a escola.",
                       user["institution_id"])
    conn.execute("UPDATE users SET name=?, email=?, weekly_email=? WHERE id=?",
                 (body.name.strip(), body.email.strip().lower(), int(body.weekly_email), user["id"]))
    return _public_user(conn, one(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],))))


# ------------------------------------------------------------------ verificação em duas etapas

@router.post("/me/2fa/setup")
def twofa_setup(user=Depends(current_user), conn=Depends(get_db)):
    """Gera um segredo novo (ainda inativo) para cadastrar no app autenticador."""
    if user["impersonated_by"]:
        raise HTTPException(403, "Não disponível ao acessar como outro usuário")
    secret = novo_segredo()
    conn.execute("UPDATE users SET totp_secret=?, two_factor=0 WHERE id=?", (secret, user["id"]))
    inst = one(conn.execute("SELECT name FROM institutions WHERE id=?", (user["institution_id"],)))
    return {"secret": secret, "uri": otpauth_uri(secret, user["email"], f"EDU.AI {inst['name']}")}


class CodeIn(BaseModel):
    code: str


@router.post("/me/2fa/enable")
def twofa_enable(body: CodeIn, user=Depends(current_user), conn=Depends(get_db)):
    limitar(f"2fa-setup:{user['id']}", 10, 600)
    u = one(conn.execute("SELECT totp_secret FROM users WHERE id=?", (user["id"],)))
    if not verificar_totp(u["totp_secret"], body.code):
        raise HTTPException(400, "Código incorreto. Confira se o relógio do celular está certo e tente de novo.")
    conn.execute("UPDATE users SET two_factor=1 WHERE id=?", (user["id"],))
    audit(conn, user, "2fa.ativada")
    return {"ok": True}


class DisableIn(BaseModel):
    password: str


@router.post("/me/2fa/disable")
def twofa_disable(body: DisableIn, user=Depends(current_user), conn=Depends(get_db)):
    limitar(f"senha:{user['id']}", 10, 900)
    u = one(conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)))
    if not check_password(body.password, u["password_hash"]):
        raise HTTPException(400, "Senha incorreta")
    conn.execute("UPDATE users SET two_factor=0, totp_secret=NULL WHERE id=?", (user["id"],))
    audit(conn, user, "2fa.desativada")
    return {"ok": True}


class PasswordIn(BaseModel):
    current: str
    new: str


@router.post("/me/password")
def change_password(body: PasswordIn, user=Depends(current_user), conn=Depends(get_db)):
    limitar(f"senha:{user['id']}", 10, 900)
    u = one(conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)))
    if not check_password(body.current, u["password_hash"]):
        raise HTTPException(400, "Senha atual incorreta")
    if len(body.new) < 8:
        raise HTTPException(400, "A nova senha precisa ter pelo menos 8 caracteres")
    conn.execute("UPDATE users SET password_hash=?, token_version=token_version+1 WHERE id=?",
                 (hash_password(body.new), user["id"]))
    audit(conn, user, "senha.alterada")
    # as sessões em outros aparelhos são encerradas; esta recebe um token novo
    return {"ok": True, "token": make_token(one(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],))))}


class DataRequestIn(BaseModel):
    kind: str
    detail: str = ""


@router.post("/me/data-request")
def data_request(body: DataRequestIn, user=Depends(current_user), conn=Depends(get_db)):
    if body.kind not in ("exportacao", "correcao", "exclusao"):
        raise HTTPException(400, "Tipo inválido")
    conn.execute("INSERT INTO data_requests (institution_id, user_id, kind, detail) VALUES (?,?,?,?)",
                 (user["institution_id"], user["id"], body.kind, body.detail))
    audit(conn, user, "lgpd.solicitacao", body.kind)
    return {"ok": True}


# ------------------------------------------------------------------ notificações

@router.get("/notifications")
def notifications(limit: int = 30, user=Depends(current_user), conn=Depends(get_db)):
    items = rows(conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?", (user["id"], limit)))
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (user["id"],)).fetchone()[0]
    return {"items": items, "unread": unread}


@router.post("/notifications/read-all")
def notifications_read_all(user=Depends(current_user), conn=Depends(get_db)):
    conn.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user["id"],))
    return {"ok": True}


@router.post("/notifications/{nid}/read")
def notification_read(nid: int, user=Depends(current_user), conn=Depends(get_db)):
    conn.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?", (nid, user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------ busca global

@router.get("/search")
def search(q: str, user=Depends(current_user), conn=Depends(get_db)):
    like = f"%{q.strip()}%"
    out: list[dict] = []
    if len(q.strip()) < 2:
        return out
    if user["role"] == "professor":
        sids = teacher_subject_ids(conn, user) or [0]
        ph = ",".join("?" * len(sids))
        for r in rows(conn.execute(f"SELECT id, name FROM subjects WHERE id IN ({ph}) AND name LIKE ?", (*sids, like))):
            out.append({"kind": "Disciplina", "title": r["name"], "link": f"#/p/disciplina/{r['id']}"})
        for r in rows(conn.execute(f"SELECT id, title FROM documents WHERE subject_id IN ({ph}) AND title LIKE ? LIMIT 8", (*sids, like))):
            out.append({"kind": "Documento", "title": r["title"], "link": f"#/p/documento/{r['id']}"})
        for r in rows(conn.execute(f"SELECT id, title, type FROM materials WHERE subject_id IN ({ph}) AND title LIKE ? LIMIT 8", (*sids, like))):
            out.append({"kind": ia.TYPE_LABEL.get(r["type"], "Material"), "title": r["title"], "link": f"#/p/material/{r['id']}"})
        for r in rows(conn.execute(f"SELECT id, statement FROM questions WHERE subject_id IN ({ph}) AND statement LIKE ? LIMIT 8", (*sids, like))):
            out.append({"kind": "Questão", "title": r["statement"][:90], "link": f"#/p/questoes?q={quote(q)}"})
        for r in rows(conn.execute(f"SELECT id, title FROM activities WHERE subject_id IN ({ph}) AND title LIKE ? LIMIT 8", (*sids, like))):
            out.append({"kind": "Atividade", "title": r["title"], "link": f"#/p/atividade/{r['id']}"})
    elif user["role"] == "aluno":
        cids = student_class_ids(conn, user) or [0]
        ph = ",".join("?" * len(cids))
        for r in rows(conn.execute(
                f"SELECT DISTINCT m.id, m.title, m.type FROM materials m JOIN material_classes mc ON mc.material_id=m.id"
                f" WHERE mc.class_id IN ({ph}) AND m.status='publicado' AND m.title LIKE ? LIMIT 10", (*cids, like))):
            out.append({"kind": ia.TYPE_LABEL.get(r["type"], "Material"), "title": r["title"], "link": f"#/a/estudar/{r['id']}"})
        for r in rows(conn.execute(
                f"SELECT id, title FROM activities WHERE class_id IN ({ph}) AND status<>'rascunho' AND title LIKE ? LIMIT 8", (*cids, like))):
            out.append({"kind": "Atividade", "title": r["title"], "link": f"#/a/atividade/{r['id']}"})
    elif user["role"] == "secretaria":
        iid = user["institution_id"]
        for r in rows(conn.execute("SELECT id, name FROM users WHERE institution_id=? AND role='aluno'"
                                   " AND (name LIKE ? OR email LIKE ? OR registration LIKE ?) LIMIT 10", (iid, like, like, like))):
            out.append({"kind": "Aluno", "title": r["name"], "link": f"#/s/aluno/{r['id']}"})
    else:
        iid = user["institution_id"]
        for r in rows(conn.execute("SELECT id, name, role FROM users WHERE institution_id=? AND (name LIKE ? OR email LIKE ?) LIMIT 10", (iid, like, like))):
            out.append({"kind": r["role"].capitalize(), "title": r["name"], "link": "#/g/usuarios"})
        for r in rows(conn.execute("SELECT id, name FROM classes WHERE institution_id=? AND name LIKE ? LIMIT 8", (iid, like))):
            out.append({"kind": "Turma", "title": r["name"], "link": "#/g/turmas"})
    return out


# ------------------------------------------------------------------ IA

@router.get("/ia/status")
def ia_status(user=Depends(current_user), conn=Depends(get_db)):
    model = ai_model(conn, user["institution_id"], user["id"])
    cfg = ai_config(conn, user["institution_id"], user["id"])
    return {**ia.status(model), "max_chars": ia.MAX_CHARS, "mode": cfg["mode"], "preferred": cfg["preferred"],
            "cloud_ready": cfg["cloud_ready"]}


class AIPrefsIn(BaseModel):
    mode: str = ""            # "" = padrão da instituição | nuvem | local
    url: str | None = None    # somente administrador geral: IA própria
    key: str | None = None
    model: str | None = None
    local_model: str | None = None


def _prefs(conn, uid: int) -> dict:
    return jload(one(conn.execute("SELECT ai_prefs FROM users WHERE id=?", (uid,)))["ai_prefs"], {}) or {}


@router.get("/me/ia")
def my_ai(user=Depends(current_user), conn=Depends(get_db)):
    """Preferência de IA do usuário (nuvem ou local). O administrador geral também vê a IA própria."""
    prefs = _prefs(conn, user["id"])
    cfg = ai_config(conn, user["institution_id"], user["id"])
    out = {"mode": prefs.get("mode") or "", "active": cfg["mode"], "cloud_ready": cfg["cloud_ready"],
           "is_superadmin": bool(user.get("is_superadmin")) and not user["impersonated_by"]}
    if out["is_superadmin"]:
        out.update(url=prefs.get("url") or "", key_masked=mask_key(prefs.get("key")), model=prefs.get("model") or "",
                   local_model=prefs.get("local_model") or "")
    return out


@router.put("/me/ia")
def set_my_ai(body: AIPrefsIn, user=Depends(current_user), conn=Depends(get_db)):
    if body.mode not in ("", "nuvem", "local"):
        raise HTTPException(400, "Modo inválido: use nuvem ou local")
    prefs = _prefs(conn, user["id"])
    prefs["mode"] = body.mode
    if user.get("is_superadmin") and not user["impersonated_by"]:
        if body.url is not None:
            url = body.url.strip()
            if url and not re.match(r"^https?://", url, re.I):
                raise HTTPException(400, "O link da API precisa começar com http:// ou https://")
            prefs["url"] = url[:500]
        if body.key == "-":               # "-" apaga a chave
            prefs.pop("key", None)
        elif body.key:                    # vazio = mantém a chave atual
            prefs["key"] = body.key.strip()[:500]
        if body.model is not None:
            prefs["model"] = body.model.strip()[:120]
        if body.local_model is not None:
            prefs["local_model"] = body.local_model.strip()[:120]
    conn.execute("UPDATE users SET ai_prefs=? WHERE id=?", (jdump(prefs), user["id"]))
    audit(conn, user, "ia.preferencia", body.mode or "padrão")
    return my_ai(user, conn)


@router.get("/config")
def public_config():
    """O que as telas públicas precisam saber (sem dados sensíveis)."""
    return {"email_configured": correio.configurado()}
