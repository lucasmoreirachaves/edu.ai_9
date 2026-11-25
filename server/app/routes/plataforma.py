"""Administração geral da plataforma (acima das instituições).

O administrador geral:
  - cadastra e gerencia as instituições clientes (além do cadastro público na tela de login);
  - emite e acompanha as FATURAS da mensalidade de cada instituição;
  - cadastra outros administradores gerais;
  - responde os chamados que os gestores abrem para o suporte da plataforma (routes/atendimento.py);
  - pode "acessar como" qualquer usuário para dar suporte: recebe um token desse usuário marcado
    com o próprio id, e toda entrada e saída fica registrada na auditoria da instituição acessada.
"""
import re
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import correio
from ..auth import current_user, hash_password, make_token, superadmin_only
from ..db import CommitRoute, get_db, notify, one, rows
from ..util import PLANS
from .common import _color, _public_user, _slugify

router = APIRouter(prefix="/api/plataforma", route_class=CommitRoute)

PLATAFORMA_TIPO = "Plataforma"   # instituição interna dos administradores gerais (fora das listas de clientes)


def _log(conn, institution_id: int, admin: dict, action: str, detail: str = ""):
    conn.execute("INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)",
                 (institution_id, admin["id"], action, f"[administrador geral {admin['name']}] {detail}"))


def _cliente(conn, iid: int) -> dict:
    inst = one(conn.execute("SELECT * FROM institutions WHERE id=? AND COALESCE(type,'')<>?", (iid, PLATAFORMA_TIPO)))
    if not inst:
        raise HTTPException(404, "Instituição não encontrada")
    return inst


# ================================================================== painel

@router.get("/resumo")
def resumo(admin=Depends(superadmin_only), conn=Depends(get_db)):
    insts = rows(conn.execute(
        """SELECT i.id, i.name, i.slug, i.type, i.plan, i.active, i.cnpj, i.created_at,
             (SELECT COUNT(*) FROM users u WHERE u.institution_id=i.id AND u.role='gestor') AS gestores,
             (SELECT COUNT(*) FROM users u WHERE u.institution_id=i.id AND u.role='secretaria') AS secretarias,
             (SELECT COUNT(*) FROM users u WHERE u.institution_id=i.id AND u.role='professor') AS professores,
             (SELECT COUNT(*) FROM users u WHERE u.institution_id=i.id AND u.role='aluno') AS alunos,
             (SELECT COUNT(*) FROM classes c WHERE c.institution_id=i.id) AS turmas,
             (SELECT COUNT(*) FROM ai_usage a WHERE a.institution_id=i.id AND a.created_at >= date('now','start of month')) AS ia_mes,
             (SELECT MAX(u.last_login) FROM users u WHERE u.institution_id=i.id) AS ultimo_acesso,
             (SELECT COUNT(*) FROM invoices f WHERE f.institution_id=i.id AND f.status='aberta' AND f.due_date < date('now')) AS faturas_vencidas,
             (SELECT COALESCE(SUM(f.amount),0) FROM invoices f WHERE f.institution_id=i.id AND f.status='aberta') AS em_aberto
           FROM institutions i WHERE COALESCE(i.type,'')<>? ORDER BY i.name""", (PLATAFORMA_TIPO,)))
    q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]  # noqa: E731
    mes = date.today().strftime("%Y-%m")
    return {
        "kpis": {"instituicoes": len(insts), "ativas": sum(1 for i in insts if i["active"]),
                 "usuarios": q("SELECT COUNT(*) FROM users WHERE is_superadmin=0"),
                 "alunos": q("SELECT COUNT(*) FROM users WHERE role='aluno'"),
                 "professores": q("SELECT COUNT(*) FROM users WHERE role='professor'"),
                 "materiais": q("SELECT COUNT(*) FROM materials"),
                 "ia_mes": q("SELECT COUNT(*) FROM ai_usage WHERE created_at >= date('now','start of month')"),
                 "mrr": sum(PLANS.get(i["plan"], {}).get("price", 0) for i in insts if i["active"]),
                 "recebido_mes": q("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='paga' AND substr(paid_at,1,7)=?", mes),
                 "em_aberto": q("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='aberta'"),
                 "vencidas": q("SELECT COUNT(*) FROM invoices WHERE status='aberta' AND due_date < date('now')"),
                 "valor_vencido": q("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='aberta' AND due_date < date('now')"),
                 "chamados_abertos": q("SELECT COUNT(*) FROM tickets WHERE target='plataforma' AND status IN ('aberto','em_andamento')"),
                 "pedidos_plano": q("SELECT COUNT(*) FROM plan_requests WHERE status='pendente'")},
        "instituicoes": insts, "planos": list(PLANS), "precos": {k: v["price"] for k, v in PLANS.items()},
        "receita_meses": rows(conn.execute(
            """SELECT reference AS mes, ROUND(SUM(CASE WHEN status='paga' THEN amount ELSE 0 END),2) AS pago,
                 ROUND(SUM(CASE WHEN status='aberta' THEN amount ELSE 0 END),2) AS aberto
               FROM invoices WHERE status<>'cancelada' GROUP BY reference ORDER BY reference DESC LIMIT 6""")),
    }


# ================================================================== instituições

class NovaInstituicao(BaseModel):
    name: str
    type: str = "Escola"
    plan: str = "Escola Pro"
    cnpj: str = ""
    color: str = "#172033"
    units: list[str] = []
    courses: list[str] = []
    admin_name: str
    admin_email: str
    admin_password: str = ""
    first_invoice: bool = False      # já emite a fatura do mês atual
    due_day: int = 10


@router.post("/instituicoes")
def criar_instituicao(body: NovaInstituicao, admin=Depends(superadmin_only), conn=Depends(get_db)):
    if body.plan not in PLANS:
        raise HTTPException(400, "Plano inválido")
    if not body.name.strip() or "@" not in body.admin_email or not body.admin_name.strip():
        raise HTTPException(400, "Informe o nome da instituição e o nome e e-mail do gestor")
    password = body.admin_password or "Edu-" + secrets.token_urlsafe(9)
    if len(password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    slug, base, n = _slugify(body.name), _slugify(body.name), 1
    while one(conn.execute("SELECT id FROM institutions WHERE slug=?", (slug,))):
        n += 1
        slug = f"{base}-{n}"
    iid = conn.execute("INSERT INTO institutions (name, slug, cnpj, type, color, plan) VALUES (?,?,?,?,?,?)",
                       (body.name.strip(), slug, body.cnpj.strip(), body.type, _color(body.color), body.plan)).lastrowid
    for u in [x.strip() for x in body.units if x.strip()] or ["Unidade principal"]:
        conn.execute("INSERT INTO units (institution_id, name) VALUES (?,?)", (iid, u[:120]))
    for c in [x.strip() for x in body.courses if x.strip()]:
        conn.execute("INSERT INTO courses (institution_id, name) VALUES (?,?)", (iid, c[:120]))
    email = body.admin_email.strip().lower()
    conn.execute(
        "INSERT INTO users (institution_id, name, email, password_hash, role, consent_at) VALUES (?,?,?,?,'gestor',CURRENT_TIMESTAMP)",
        (iid, body.admin_name.strip(), email, hash_password(password)))
    _log(conn, iid, admin, "instituicao.criada", body.name)
    if body.first_invoice:
        _emitir(conn, admin, iid, date.today().strftime("%Y-%m"), PLANS[body.plan]["price"],
                _vencimento(date.today().strftime("%Y-%m"), body.due_day), f"Mensalidade plano {body.plan}")
    return {"id": iid, "slug": slug, "admin_email": email, "admin_password": password}


class EdicaoInstituicao(BaseModel):
    name: str
    plan: str
    active: bool
    cnpj: str | None = None


@router.put("/instituicoes/{iid}")
def editar_instituicao(iid: int, body: EdicaoInstituicao, admin=Depends(superadmin_only), conn=Depends(get_db)):
    inst = _cliente(conn, iid)
    if body.plan not in PLANS:
        raise HTTPException(400, "Plano inválido")
    conn.execute("UPDATE institutions SET name=?, plan=?, active=?, cnpj=COALESCE(?, cnpj) WHERE id=?",
                 (body.name, body.plan, int(body.active), body.cnpj, iid))
    if inst["plan"] != body.plan:
        conn.execute("UPDATE plan_requests SET status=CASE WHEN plan=? THEN 'aprovado' ELSE 'recusado' END, resolved_at=CURRENT_TIMESTAMP"
                     " WHERE institution_id=? AND status='pendente'", (body.plan, iid))
    if bool(inst["active"]) != body.active:
        _log(conn, iid, admin, "instituicao.reativada" if body.active else "instituicao.suspensa", body.name)
    if inst["plan"] != body.plan:
        _log(conn, iid, admin, "plano.alterado", body.plan)
    return {"ok": True}


@router.get("/pedidos-plano")
def pedidos_plano(admin=Depends(superadmin_only), conn=Depends(get_db)):
    return rows(conn.execute(
        """SELECT r.id, r.plan, r.created_at, i.id AS institution_id, i.name AS institution, i.plan AS current_plan, u.name AS requester
           FROM plan_requests r JOIN institutions i ON i.id=r.institution_id JOIN users u ON u.id=r.user_id
           WHERE r.status='pendente' ORDER BY r.id"""))


class DecisaoPlano(BaseModel):
    approve: bool


@router.post("/pedidos-plano/{rid}")
def decidir_plano(rid: int, body: DecisaoPlano, admin=Depends(superadmin_only), conn=Depends(get_db)):
    r = one(conn.execute("SELECT * FROM plan_requests WHERE id=? AND status='pendente'", (rid,)))
    if not r:
        raise HTTPException(404, "Pedido não encontrado")
    conn.execute("UPDATE plan_requests SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE id=?",
                 ("aprovado" if body.approve else "recusado", rid))
    if body.approve:
        conn.execute("UPDATE institutions SET plan=? WHERE id=?", (r["plan"], r["institution_id"]))
        _log(conn, r["institution_id"], admin, "plano.alterado", r["plan"])
    notify(conn, r["user_id"], f"Pedido do plano {r['plan']} {'aprovado' if body.approve else 'recusado'}", "Planos", "#/g/planos")
    return {"ok": True}


# ================================================================== faturas (mensalidade das instituições)

def _vencimento(reference: str, due_day: int) -> str:
    y, m = (int(x) for x in reference.split("-"))
    return date(y, m, max(1, min(28, int(due_day or 10)))).isoformat()


def _check_ref(reference: str):
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", reference or ""):
        raise HTTPException(400, "Referência inválida: use AAAA-MM")


def _emitir(conn, admin, iid: int, reference: str, amount: float, due_date: str, description: str) -> int:
    fid = conn.execute("INSERT INTO invoices (institution_id, reference, description, amount, due_date, created_by) VALUES (?,?,?,?,?,?)",
                       (iid, reference, description, round(float(amount), 2), due_date, admin["id"])).lastrowid
    _log(conn, iid, admin, "fatura.emitida", f"{reference} · R$ {amount:.2f} · vence {due_date}")
    gestores = rows(conn.execute("SELECT id, email FROM users WHERE institution_id=? AND role='gestor' AND status='ativo' AND is_superadmin=0", (iid,)))
    for g in gestores:
        notify(conn, g["id"], f"Nova fatura da plataforma ({reference}): R$ {amount:.2f}, vence em {due_date[8:10]}/{due_date[5:7]}",
               "Faturas", "#/g/planos?aba=faturas")
        correio.enviar(conn, g["email"], f"Fatura EDU.AI {reference}",
                       f"Uma nova fatura da plataforma EDU.AI foi emitida.\n\n{description}\nValor: R$ {amount:.2f}\n"
                       f"Vencimento: {due_date}\n\nVeja em {correio.link('#/g/planos?aba=faturas')}", iid)
    return fid


def _fatura_view(f: dict) -> dict:
    f["overdue"] = f["status"] == "aberta" and f["due_date"] < date.today().isoformat()
    f["situacao"] = "vencida" if f["overdue"] else f["status"]
    return f


@router.get("/faturas")
def faturas(status: str = "", institution_id: int | None = None, reference: str = "",
            admin=Depends(superadmin_only), conn=Depends(get_db)):
    sql = """SELECT f.*, i.name AS institution, i.slug, i.plan FROM invoices f JOIN institutions i ON i.id=f.institution_id WHERE 1=1"""
    params: list = []
    if institution_id:
        sql += " AND f.institution_id=?"
        params.append(institution_id)
    if reference:
        sql += " AND f.reference=?"
        params.append(reference)
    if status == "vencida":
        sql += " AND f.status='aberta' AND f.due_date < date('now')"
    elif status:
        sql += " AND f.status=?"
        params.append(status)
    return [_fatura_view(f) for f in rows(conn.execute(sql + " ORDER BY f.due_date DESC, i.name LIMIT 1000", params))]


class FaturaIn(BaseModel):
    institution_id: int
    reference: str
    amount: float | None = None      # vazio = preço do plano atual
    due_date: str = ""
    description: str = ""


@router.post("/faturas")
def criar_fatura(body: FaturaIn, admin=Depends(superadmin_only), conn=Depends(get_db)):
    inst = _cliente(conn, body.institution_id)
    _check_ref(body.reference)
    amount = body.amount if body.amount is not None else PLANS.get(inst["plan"], {}).get("price", 0)
    if amount < 0 or amount > 10_000_000:
        raise HTTPException(400, "Valor inválido")
    due = body.due_date or _vencimento(body.reference, 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        raise HTTPException(400, "Vencimento inválido")
    fid = _emitir(conn, admin, inst["id"], body.reference, amount, due,
                  body.description.strip()[:300] or f"Mensalidade plano {inst['plan']} — {body.reference}")
    return {"id": fid}


class GerarMesIn(BaseModel):
    reference: str
    due_day: int = 10


@router.post("/faturas/gerar-mes")
def gerar_mes(body: GerarMesIn, admin=Depends(superadmin_only), conn=Depends(get_db)):
    """Emite a mensalidade do mês para todas as instituições ativas que ainda não têm fatura nessa referência."""
    _check_ref(body.reference)
    due = _vencimento(body.reference, body.due_day)
    criadas, puladas = 0, 0
    for inst in rows(conn.execute("SELECT id, plan FROM institutions WHERE active=1 AND COALESCE(type,'')<>?", (PLATAFORMA_TIPO,))):
        if one(conn.execute("SELECT id FROM invoices WHERE institution_id=? AND reference=? AND status<>'cancelada'",
                            (inst["id"], body.reference))):
            puladas += 1
            continue
        _emitir(conn, admin, inst["id"], body.reference, PLANS.get(inst["plan"], {}).get("price", 0), due,
                f"Mensalidade plano {inst['plan']} — {body.reference}")
        criadas += 1
    return {"criadas": criadas, "ja_existiam": puladas}


class AtualizaFatura(BaseModel):
    status: str | None = None        # aberta | paga | cancelada
    paid_at: str | None = None
    payment_method: str | None = None
    notes: str | None = None
    amount: float | None = None
    due_date: str | None = None


@router.put("/faturas/{fid}")
def atualizar_fatura(fid: int, body: AtualizaFatura, admin=Depends(superadmin_only), conn=Depends(get_db)):
    f = one(conn.execute("SELECT * FROM invoices WHERE id=?", (fid,)))
    if not f:
        raise HTTPException(404, "Fatura não encontrada")
    if body.status and body.status not in ("aberta", "paga", "cancelada"):
        raise HTTPException(400, "Situação inválida")
    if body.due_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.due_date):
        raise HTTPException(400, "Vencimento inválido")
    if body.amount is not None and not 0 <= body.amount <= 10_000_000:
        raise HTTPException(400, "Valor inválido")
    status = body.status or f["status"]
    paid_at = (body.paid_at or f["paid_at"] or date.today().isoformat()) if status == "paga" else None
    conn.execute("""UPDATE invoices SET status=?, paid_at=?, payment_method=COALESCE(?, payment_method), notes=COALESCE(?, notes),
                      amount=COALESCE(?, amount), due_date=COALESCE(?, due_date) WHERE id=?""",
                 (status, paid_at, body.payment_method, body.notes, body.amount, body.due_date, fid))
    if status != f["status"]:
        _log(conn, f["institution_id"], admin, f"fatura.{status}", f"{f['reference']} · R$ {f['amount']:.2f}")
        if status == "paga":
            for g in rows(conn.execute("SELECT id FROM users WHERE institution_id=? AND role='gestor' AND is_superadmin=0 AND status='ativo'",
                                       (f["institution_id"],))):
                notify(conn, g["id"], f"Pagamento da fatura {f['reference']} confirmado", "Faturas", "#/g/planos?aba=faturas")
    return {"ok": True}


# ================================================================== administradores gerais

@router.get("/administradores")
def administradores(admin=Depends(superadmin_only), conn=Depends(get_db)):
    return rows(conn.execute("SELECT id, name, email, status, last_login, created_at, two_factor FROM users"
                             " WHERE is_superadmin=1 ORDER BY name"))


class NovoAdmin(BaseModel):
    name: str
    email: str
    password: str = ""


@router.post("/administradores")
def criar_admin(body: NovoAdmin, admin=Depends(superadmin_only), conn=Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or not body.name.strip():
        raise HTTPException(400, "Informe nome e e-mail válidos")
    if one(conn.execute("SELECT id FROM users WHERE lower(email)=? AND is_superadmin=1", (email,))):
        raise HTTPException(409, "Já existe um administrador geral com este e-mail")
    if one(conn.execute("SELECT id FROM users WHERE institution_id=? AND lower(email)=?", (admin["institution_id"], email))):
        raise HTTPException(409, "E-mail já usado na instituição da plataforma")
    password = body.password or "Adm-" + secrets.token_urlsafe(10)
    if len(password) < 10:
        raise HTTPException(400, "A senha de administrador precisa ter pelo menos 10 caracteres")
    uid = conn.execute("INSERT INTO users (institution_id, name, email, password_hash, role, is_superadmin, consent_at)"
                       " VALUES (?,?,?,?,'gestor',1,CURRENT_TIMESTAMP)",
                       (admin["institution_id"], body.name.strip(), email, hash_password(password))).lastrowid
    _log(conn, admin["institution_id"], admin, "admin.criado", email)
    correio.enviar(conn, email, "Acesso de administrador — EDU.AI",
                   f"Olá, {body.name.strip()}.\n\nVocê recebeu acesso de administrador geral da plataforma EDU.AI.\n"
                   f"Entre em {correio.link('#/admin/login')} com o seu e-mail. A senha inicial será informada por "
                   f"{admin['name']}; troque-a no primeiro acesso.", admin["institution_id"])
    return {"id": uid, "email": email, "password": password}


class StatusAdmin(BaseModel):
    status: str


@router.put("/administradores/{uid}")
def status_admin(uid: int, body: StatusAdmin, admin=Depends(superadmin_only), conn=Depends(get_db)):
    alvo = one(conn.execute("SELECT * FROM users WHERE id=? AND is_superadmin=1", (uid,)))
    if not alvo:
        raise HTTPException(404, "Administrador não encontrado")
    if body.status not in ("ativo", "inativo"):
        raise HTTPException(400, "Situação inválida")
    if uid == admin["id"] and body.status != "ativo":
        raise HTTPException(400, "Você não pode desativar a sua própria conta")
    if body.status == "inativo" and conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_superadmin=1 AND status='ativo' AND id<>?", (uid,)).fetchone()[0] == 0:
        raise HTTPException(400, "A plataforma precisa de pelo menos um administrador ativo")
    conn.execute("UPDATE users SET status=?, token_version=token_version+1 WHERE id=?", (body.status, uid))
    _log(conn, alvo["institution_id"], admin, "admin.desativado" if body.status == "inativo" else "admin.reativado", alvo["email"])
    return {"ok": True}


# ================================================================== usuários de todas as instituições

@router.get("/usuarios")
def usuarios(q: str = "", institution_id: int | None = None, admin=Depends(superadmin_only), conn=Depends(get_db)):
    sql = """SELECT u.id, u.name, u.email, u.role, u.status, u.is_superadmin, u.last_login, i.id AS institution_id,
               i.name AS institution, i.slug FROM users u JOIN institutions i ON i.id=u.institution_id WHERE u.is_superadmin=0"""
    params: list = []
    if institution_id:
        sql += " AND u.institution_id=?"
        params.append(institution_id)
    if q.strip():
        sql += " AND (u.name LIKE ? OR u.email LIKE ?)"
        params += [f"%{q.strip()}%"] * 2
    return rows(conn.execute(sql + " ORDER BY i.name, u.role, u.name LIMIT 300", params))


@router.post("/acessar/{uid}")
def acessar_como(uid: int, admin=Depends(superadmin_only), conn=Depends(get_db)):
    alvo = one(conn.execute("SELECT * FROM users WHERE id=?", (uid,)))
    if not alvo:
        raise HTTPException(404, "Usuário não encontrado")
    if alvo["id"] == admin["id"] or alvo["is_superadmin"]:
        raise HTTPException(400, "Não é possível acessar a conta de um administrador geral")
    if alvo["status"] != "ativo":
        raise HTTPException(400, "Usuário desativado")
    _log(conn, alvo["institution_id"], admin, "suporte.acesso_iniciado", f"acessou como {alvo['email']}")
    alvo["impersonated_by"] = {"id": admin["id"], "name": admin["name"]}
    return {"token": make_token(alvo, impersonated_by=admin["id"]), "user": _public_user(conn, alvo)}


@router.post("/voltar")
def voltar(user=Depends(current_user), conn=Depends(get_db)):
    """Encerra o 'acessar como' e devolve a sessão do administrador geral."""
    if not user["impersonated_by"]:
        raise HTTPException(400, "Você não está acessando como outro usuário")
    admin = one(conn.execute("SELECT * FROM users WHERE id=?", (user["impersonated_by"]["id"],)))
    _log(conn, user["institution_id"], admin, "suporte.acesso_encerrado", f"saiu da conta de {user['email']}")
    return {"token": make_token(admin), "user": _public_user(conn, admin)}
