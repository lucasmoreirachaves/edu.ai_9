"""Atendimento e ouvidoria: chamados com conversa, anexos, prazo e avaliação.

Cada chamado tem um DESTINO, que define quem responde:
  secretaria  alunos e professores → secretaria escolar (o gestor também vê e pode responder)
  gestao      alunos, professores e secretaria → gestor(es) da instituição
  plataforma  gestor da instituição → administradores gerais da plataforma

Exemplos: pedir declaração de matrícula ou histórico, revisão de nota, questões financeiras,
reclamações, sugestões e denúncias (estas podem ser anônimas). Todos podem anexar arquivos.

Status: aberto → em_andamento → aguardando (esperando o solicitante) → resolvido → fechado.
"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import correio
from ..auth import current_user
from ..db import CommitRoute, UPLOAD_DIR, audit, get_db, notify, one, rows
from ..seguranca import limitar
from ..util import institution_settings

router = APIRouter(prefix="/api/chamados", route_class=CommitRoute)

DESTINOS = {
    "secretaria": "Secretaria escolar",
    "gestao": "Gestão da instituição",
    "plataforma": "Suporte da plataforma EDU.AI",
}
CATEGORIAS = {
    "documento": "Solicitação de documento",
    "secretaria": "Secretaria (matrícula, cadastro, transferência)",
    "pedagogico": "Coordenação pedagógica (notas, frequência, revisão de prova)",
    "financeiro": "Financeiro",
    "suporte": "Problema na plataforma",
    "reclamacao": "Reclamação",
    "sugestao": "Sugestão ou elogio",
    "denuncia": "Denúncia (ouvidoria)",
    "outro": "Outro assunto",
}
CATEGORIAS_GESTAO = {
    "administrativo": "Assunto administrativo",
    "pedagogico": "Coordenação pedagógica",
    "recursos": "Recursos, materiais e infraestrutura",
    "suporte": "Problema na plataforma",
    "reclamacao": "Reclamação",
    "sugestao": "Sugestão ou elogio",
    "denuncia": "Denúncia (ouvidoria)",
    "outro": "Outro assunto",
}
CATEGORIAS_PLATAFORMA = {
    "financeiro": "Faturas e pagamentos",
    "suporte": "Problema técnico na plataforma",
    "ia": "Inteligência artificial (configuração e uso)",
    "plano": "Plano, limites e contratação",
    "sugestao": "Sugestão de melhoria",
    "outro": "Outro assunto",
}
CATEGORIAS_POR_DESTINO = {"secretaria": CATEGORIAS, "gestao": CATEGORIAS_GESTAO, "plataforma": CATEGORIAS_PLATAFORMA}
TODAS_CATEGORIAS = {**CATEGORIAS_PLATAFORMA, **CATEGORIAS_GESTAO, **CATEGORIAS}
DOCUMENTOS = ["Declaração de matrícula", "Declaração de frequência", "Histórico escolar", "Boletim",
              "Atestado de conclusão", "Declaração de transferência", "Carteirinha de estudante",
              "Conteúdo programático", "Outro documento"]
ANONIMO_PERMITIDO = {"denuncia", "reclamacao", "sugestao"}
STATUS = ("aberto", "em_andamento", "aguardando", "resolvido", "fechado")
ANEXO_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".doc", ".odt", ".xlsx", ".xls", ".ods", ".csv", ".txt", ".zip"}
ANEXO_MAX = 10 * 1024 * 1024
ANEXO_DIR = UPLOAD_DIR / "chamados"
SLA_PLATAFORMA = 2  # dias úteis de resposta do suporte da plataforma


def _superadmin(user) -> bool:
    return bool(user.get("is_superadmin")) and not user.get("impersonated_by")


def destinos_de(user) -> list[str]:
    """Para quem este usuário pode abrir chamados."""
    if _superadmin(user):
        return []
    return {"aluno": ["secretaria", "gestao"], "professor": ["secretaria", "gestao"],
            "secretaria": ["gestao"], "gestor": ["plataforma"]}.get(user["role"], [])


def _handles(user, t: dict) -> bool:
    """O usuário responde por este chamado (faz parte da equipe do destino)?"""
    target = t.get("target") or "secretaria"
    if target == "plataforma":
        return _superadmin(user)
    if t["institution_id"] != user["institution_id"]:
        return False
    if target == "gestao":
        return user["role"] == "gestor"
    return user["role"] in ("secretaria", "gestor")


def _is_queue_staff(user) -> bool:
    return _superadmin(user) or user["role"] in ("secretaria", "gestor")


def _staff_link(user_row: dict, tid: int) -> str:
    if user_row.get("is_superadmin"):
        return f"#/admin/chamado/{tid}"
    return f"#/g/chamado/{tid}" if user_row["role"] == "gestor" else f"#/s/chamado/{tid}"


def _sla_days(conn, t: dict) -> int:
    if (t.get("target") or "secretaria") == "plataforma":
        return SLA_PLATAFORMA
    v = institution_settings(conn, t["institution_id"]).get("ticket_sla_days", 5)
    return v if isinstance(v, int) and v > 0 else 5


def _decorate(conn, t: dict, viewer: dict) -> dict:
    """Esconde a identidade em chamados anônimos (para a equipe) e calcula o prazo."""
    staff = _handles(viewer, t)
    t["target"] = t.get("target") or "secretaria"
    t["target_label"] = DESTINOS.get(t["target"], t["target"])
    t["category_label"] = TODAS_CATEGORIAS.get(t["category"], t["category"])
    if t["anonymous"] and staff:
        t["requester"], t["requester_role"], t["requester_email"], t["requester_classes"] = "Anônimo", None, None, None
        t.pop("user_id", None)
    created = datetime.fromisoformat(t["created_at"].replace(" ", "T"))
    due = created + timedelta(days=_sla_days(conn, t))
    t["due_at"] = due.isoformat(sep=" ", timespec="seconds")
    t["overdue"] = t["status"] in ("aberto", "em_andamento") and datetime.utcnow() > due
    return t


def _ticket(conn, user, tid: int) -> dict:
    t = one(conn.execute(
        """SELECT t.*, u.name AS requester, u.role AS requester_role, u.email AS requester_email, a.name AS assignee,
             i.name AS institution_name,
             (SELECT GROUP_CONCAT(c.name, ', ') FROM class_students cs JOIN classes c ON c.id=cs.class_id WHERE cs.user_id=t.user_id) AS requester_classes
           FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users a ON a.id=t.assigned_to
           JOIN institutions i ON i.id=t.institution_id WHERE t.id=?""", (tid,)))
    if not t or (t["user_id"] != user["id"] and not _handles(user, t)):
        raise HTTPException(404, "Chamado não encontrado")
    return t


def _save_attachment(file: UploadFile | None, data: bytes, prefix: str) -> tuple[str | None, int]:
    if not file or not file.filename:
        return None, 0
    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    if ext not in ANEXO_EXT:
        raise HTTPException(400, "Anexo não permitido. Envie PDF, imagem, documento (DOCX/ODT), planilha, TXT ou ZIP.")
    if len(data) > ANEXO_MAX:
        raise HTTPException(400, "Anexo maior que 10 MB")
    ANEXO_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename)[-80:]
    name = f"{prefix}_{safe}"
    (ANEXO_DIR / name).write_bytes(data)
    return name, len(data)


def _staff_ids(conn, iid: int, target: str) -> list[dict]:
    if target == "plataforma":
        return rows(conn.execute("SELECT id, role, is_superadmin FROM users WHERE is_superadmin=1 AND status='ativo'"))
    if target == "gestao":
        return rows(conn.execute("SELECT id, role, is_superadmin FROM users WHERE institution_id=? AND role='gestor'"
                                 " AND is_superadmin=0 AND status='ativo'", (iid,)))
    sec = rows(conn.execute("SELECT id, role, is_superadmin FROM users WHERE institution_id=? AND role='secretaria' AND status='ativo'", (iid,)))
    # sem secretaria cadastrada, os gestores recebem os chamados
    return sec or _staff_ids(conn, iid, "gestao")


def _notify_staff(conn, t: dict, text: str, only: int | None = None):
    staff = _staff_ids(conn, t["institution_id"], t.get("target") or "secretaria")
    if only:
        staff = [s for s in staff if s["id"] == only] or rows(conn.execute(
            "SELECT id, role, is_superadmin FROM users WHERE id=?", (only,)))
    for s in staff:
        notify(conn, s["id"], text, "Atendimento", _staff_link(s, t["id"]))


# ------------------------------------------------------------------ catálogo

@router.get("/opcoes")
def opcoes(target: str = "", user=Depends(current_user), conn=Depends(get_db)):
    alvos = destinos_de(user)
    target = target if target in alvos else (alvos[0] if alvos else "secretaria")
    sla = SLA_PLATAFORMA if target == "plataforma" else _sla_days(conn, {"institution_id": user["institution_id"]})
    return {"targets": {k: DESTINOS[k] for k in alvos}, "target": target,
            "categories": CATEGORIAS_POR_DESTINO[target], "categories_by_target": {k: CATEGORIAS_POR_DESTINO[k] for k in alvos},
            "all_categories": TODAS_CATEGORIAS, "documents": DOCUMENTOS, "anonymous_allowed": sorted(ANONIMO_PERMITIDO),
            "sla_days": sla, "status": STATUS}


# ------------------------------------------------------------------ listar e abrir

@router.get("")
def listar(status: str | None = None, category: str | None = None, mine: int = 0, target: str | None = None,
           user=Depends(current_user), conn=Depends(get_db)):
    """Sem `mine`: a equipe vê a sua fila (secretaria, gestão ou plataforma); os demais, os próprios chamados."""
    sql = """SELECT t.*, u.name AS requester, u.role AS requester_role, NULL AS requester_email, NULL AS requester_classes,
               a.name AS assignee, i.name AS institution_name,
               (SELECT COUNT(*) FROM ticket_messages m WHERE m.ticket_id=t.id AND m.internal=0) AS messages,
               (SELECT m.user_id FROM ticket_messages m WHERE m.ticket_id=t.id AND m.internal=0 ORDER BY m.id DESC LIMIT 1) AS last_author
             FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users a ON a.id=t.assigned_to
             JOIN institutions i ON i.id=t.institution_id WHERE 1=1"""
    params: list = []
    queue = _is_queue_staff(user) and not mine
    if not queue:
        sql += " AND t.user_id=?"
        params.append(user["id"])
    elif _superadmin(user):
        sql += " AND t.target='plataforma'"
    elif user["role"] == "gestor":
        sql += " AND t.institution_id=? AND COALESCE(t.target,'secretaria') IN ('secretaria','gestao')"
        params.append(user["institution_id"])
    else:
        sql += " AND t.institution_id=? AND COALESCE(t.target,'secretaria')='secretaria'"
        params.append(user["institution_id"])
    if target:
        sql += " AND COALESCE(t.target,'secretaria')=?"
        params.append(target)
    if status:
        sql += " AND t.status=?"
        params.append(status)
    if category:
        sql += " AND t.category=?"
        params.append(category)
    out = [_decorate(conn, t, user) for t in rows(conn.execute(sql + " ORDER BY t.updated_at DESC LIMIT 500", params))]
    for t in out:
        t.pop("user_id", None)
        t["waiting_me"] = ((t["last_author"] != user["id"]) and t["status"] not in ("resolvido", "fechado")) \
            if queue else (t["status"] == "aguardando")
        t.pop("last_author", None)
    return out


@router.post("")
async def abrir(category: str = Form(...), subject: str = Form(...), body: str = Form(...), anonymous: bool = Form(False),
                document_type: str = Form(""), target: str = Form(""), file: UploadFile | None = File(None),
                user=Depends(current_user), conn=Depends(get_db)):
    alvos = destinos_de(user)
    if not alvos:
        raise HTTPException(400, "O administrador geral responde chamados; não abre.")
    if user["impersonated_by"]:
        raise HTTPException(403, "Não é possível abrir chamados ao acessar como outro usuário")
    target = target or alvos[0]
    if target not in alvos:
        raise HTTPException(400, "Destino inválido para o seu perfil")
    limitar(f"chamado:{user['id']}", 10, 3600, "Você abriu muitos chamados na última hora. Aguarde um pouco.")
    if category not in CATEGORIAS_POR_DESTINO[target]:
        raise HTTPException(400, "Categoria inválida")
    subject, body = subject.strip()[:150], body.strip()[:5000]
    if category == "documento" and document_type:
        if document_type not in DOCUMENTOS:
            raise HTTPException(400, "Documento inválido")
        subject = subject or document_type
        if not subject.startswith(document_type):
            subject = f"{document_type} — {subject}"[:150]
    if len(subject) < 3 or len(body) < 5:
        raise HTTPException(400, "Descreva o assunto e o pedido")
    anonymous = bool(anonymous) and category in ANONIMO_PERMITIDO and target != "plataforma"
    data = await file.read(ANEXO_MAX + 1) if file and file.filename else b""
    tid = conn.execute("INSERT INTO tickets (institution_id, user_id, protocol, category, subject, anonymous, target) VALUES (?,?,?,?,?,?,?)",
                       (user["institution_id"], user["id"], "", category, subject, int(anonymous), target)).lastrowid
    protocol = f"{datetime.now().year}{tid:06d}"
    conn.execute("UPDATE tickets SET protocol=? WHERE id=?", (protocol, tid))
    name, size = _save_attachment(file, data, f"t{tid}")
    conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body, attachment, attachment_size) VALUES (?,?,?,?,?)",
                 (tid, user["id"], body, name, size))
    quem = "Anônimo" if anonymous else user["name"]
    t = {"id": tid, "institution_id": user["institution_id"], "target": target}
    if target == "plataforma":
        inst = one(conn.execute("SELECT name FROM institutions WHERE id=?", (user["institution_id"],)))
        quem = f"{user['name']} · {inst['name']}"
    _notify_staff(conn, t, f"Novo chamado #{protocol}: {subject} ({quem})")
    if not anonymous:
        audit(conn, user, "chamado.aberto", f"#{protocol} {DESTINOS[target]} · {TODAS_CATEGORIAS[category]}")
    sla = SLA_PLATAFORMA if target == "plataforma" else _sla_days(conn, t)
    correio.enviar(conn, user["email"], f"Chamado #{protocol} recebido",
                   f"Recebemos o seu chamado “{subject}” ({DESTINOS[target]}).\nProtocolo: {protocol}\n"
                   f"Prazo de resposta: até {sla} dia(s).\n"
                   f"Acompanhe em {correio.link('#/atendimento/' + str(tid))}", user["institution_id"])
    return {"id": tid, "protocol": protocol}


@router.get("/{tid}")
def detalhe(tid: int, user=Depends(current_user), conn=Depends(get_db)):
    raw = _ticket(conn, user, tid)
    requester_id, anonymous = raw["user_id"], bool(raw["anonymous"])
    staff = _handles(user, raw)
    t = _decorate(conn, raw, user)
    msgs = rows(conn.execute(
        """SELECT m.id, m.user_id, m.body, m.attachment, m.attachment_size, m.internal, m.created_at, u.name, u.role,
             u.is_superadmin FROM ticket_messages m JOIN users u ON u.id=m.user_id WHERE m.ticket_id=? ORDER BY m.id""", (tid,)))
    out = []
    for m in msgs:
        if m["internal"] and not staff:
            continue  # notas internas da equipe não aparecem para o solicitante
        m["mine"] = m["user_id"] == user["id"]
        if m["user_id"] == requester_id and anonymous and staff:
            m["name"], m["role"] = "Anônimo", None
        if m.pop("is_superadmin"):
            m["role"] = "admin"
        m.pop("user_id")
        m["attachment_name"] = m["attachment"].split("_", 1)[1] if m["attachment"] else None
        m.pop("attachment", None)
        out.append(m)
    t["messages"] = out
    t["can_reply"] = t["status"] != "fechado"
    t["is_staff"] = staff
    t["is_requester"] = requester_id == user["id"]
    return t


# ------------------------------------------------------------------ conversa

@router.post("/{tid}/mensagens")
async def responder(tid: int, body: str = Form(""), internal: bool = Form(False), status: str = Form(""),
                    file: UploadFile | None = File(None), user=Depends(current_user), conn=Depends(get_db)):
    t = _ticket(conn, user, tid)
    if t["status"] == "fechado":
        raise HTTPException(400, "Chamado fechado. Abra um novo chamado se precisar.")
    limitar(f"chamado-msg:{user['id']}", 60, 3600)
    body = body.strip()[:5000]
    data = await file.read(ANEXO_MAX + 1) if file and file.filename else b""
    if not body and not data:
        raise HTTPException(400, "Escreva uma mensagem ou anexe um arquivo")
    staff = _handles(user, t)
    internal = bool(internal) and staff
    mid = conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body, internal) VALUES (?,?,?,?)",
                       (tid, user["id"], body or "(anexo)", int(internal))).lastrowid
    name, size = _save_attachment(file, data, f"t{tid}m{mid}")
    if name:
        conn.execute("UPDATE ticket_messages SET attachment=?, attachment_size=? WHERE id=?", (name, size, mid))
    new_status = t["status"]
    if staff:
        if status in STATUS:
            new_status = status
        elif not internal and t["status"] == "aberto":
            new_status = "em_andamento"
        if not t["assigned_to"]:
            conn.execute("UPDATE tickets SET assigned_to=? WHERE id=?", (user["id"], tid))
    elif t["status"] in ("aguardando", "resolvido"):
        new_status = "em_andamento"  # o solicitante respondeu: volta para a fila
    conn.execute("UPDATE tickets SET status=?, updated_at=CURRENT_TIMESTAMP, closed_at=CASE WHEN ? IN ('resolvido','fechado') THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",
                 (new_status, new_status, tid))
    if internal:
        return {"ok": True, "status": new_status}
    if staff:
        quem = "O suporte da plataforma" if t["target"] == "plataforma" else "A escola"
        notify(conn, t["user_id"], f"Resposta no chamado #{t['protocol']}: {t['subject']}", "Atendimento", f"#/atendimento/{tid}")
        requester = one(conn.execute("SELECT email FROM users WHERE id=?", (t["user_id"],)))
        correio.enviar(conn, requester["email"], f"Resposta ao chamado #{t['protocol']}",
                       f"{quem} respondeu ao seu chamado “{t['subject']}”.\n\n{body}\n\n"
                       f"Veja a conversa{' e o anexo' if name else ''} em {correio.link('#/atendimento/' + str(tid))}",
                       t["institution_id"])
    else:
        _notify_staff(conn, t, f"Nova mensagem no chamado #{t['protocol']}", only=t["assigned_to"])
    return {"ok": True, "status": new_status}


@router.post("/{tid}/status")
def mudar_status(tid: int, payload: dict, user=Depends(current_user), conn=Depends(get_db)):
    t = _ticket(conn, user, tid)
    status = payload.get("status")
    if status not in STATUS:
        raise HTTPException(400, "Status inválido")
    staff = _handles(user, t)
    if not staff:
        # o solicitante pode encerrar (resolvido/fechado) ou reabrir um chamado resolvido
        if status not in ("fechado", "resolvido") and not (status == "aberto" and t["status"] == "resolvido"):
            raise HTTPException(403, "Você pode encerrar ou reabrir o seu chamado")
    conn.execute("UPDATE tickets SET status=?, updated_at=CURRENT_TIMESTAMP, closed_at=CASE WHEN ? IN ('resolvido','fechado') THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",
                 (status, status, tid))
    if staff:
        conn.execute("INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)",
                     (t["institution_id"], user["id"], "chamado.status", f"#{t['protocol']}: {t['status']} → {status}"))
        if status in ("resolvido", "aguardando"):
            notify(conn, t["user_id"], f"Chamado #{t['protocol']} {'resolvido' if status == 'resolvido' else 'aguarda a sua resposta'}",
                   "Atendimento", f"#/atendimento/{tid}")
    return {"ok": True}


@router.post("/{tid}/assumir")
def assumir(tid: int, user=Depends(current_user), conn=Depends(get_db)):
    t = _ticket(conn, user, tid)
    if not _handles(user, t):
        raise HTTPException(403, "Somente a equipe de atendimento")
    conn.execute("UPDATE tickets SET assigned_to=?, status=CASE WHEN status='aberto' THEN 'em_andamento' ELSE status END,"
                 " updated_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"], tid))
    return {"ok": True}


@router.post("/{tid}/encaminhar")
def encaminhar(tid: int, payload: dict, user=Depends(current_user), conn=Depends(get_db)):
    """A secretaria encaminha um chamado para a gestão (ou a gestão devolve para a secretaria)."""
    t = _ticket(conn, user, tid)
    alvo = payload.get("target")
    if not _handles(user, t) or t["target"] == "plataforma" or alvo not in ("secretaria", "gestao") or alvo == t["target"]:
        raise HTTPException(400, "Encaminhamento inválido")
    conn.execute("UPDATE tickets SET target=?, assigned_to=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (alvo, tid))
    conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body, internal) VALUES (?,?,?,1)",
                 (tid, user["id"], f"Chamado encaminhado para: {DESTINOS[alvo]}"))
    t["target"] = alvo
    _notify_staff(conn, t, f"Chamado #{t['protocol']} encaminhado para {DESTINOS[alvo].lower()}")
    audit(conn, user, "chamado.encaminhado", f"#{t['protocol']} → {alvo}")
    return {"ok": True}


@router.post("/{tid}/avaliar")
def avaliar(tid: int, payload: dict, user=Depends(current_user), conn=Depends(get_db)):
    t = _ticket(conn, user, tid)
    if t["user_id"] != user["id"] or t["status"] not in ("resolvido", "fechado"):
        raise HTTPException(400, "Avalie depois que o chamado for resolvido")
    rating = payload.get("rating")
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise HTTPException(400, "Nota de 1 a 5")
    conn.execute("UPDATE tickets SET rating=?, status='fechado', closed_at=COALESCE(closed_at, CURRENT_TIMESTAMP) WHERE id=?", (rating, tid))
    return {"ok": True}


@router.get("/{tid}/anexo/{mid}")
def anexo(tid: int, mid: int, user=Depends(current_user), conn=Depends(get_db)):
    t = _ticket(conn, user, tid)
    m = one(conn.execute("SELECT attachment, internal FROM ticket_messages WHERE id=? AND ticket_id=?", (mid, tid)))
    if not m or not m["attachment"] or (m["internal"] and not _handles(user, t)):
        raise HTTPException(404, "Anexo não encontrado")
    path = ANEXO_DIR / m["attachment"]
    if not path.exists():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(path, filename=m["attachment"].split("_", 1)[1])


# ------------------------------------------------------------------ painel da equipe

@router.get("/resumo/gestao")
def resumo(user=Depends(current_user), conn=Depends(get_db)):
    if not _is_queue_staff(user):
        raise HTTPException(403, "Somente a equipe de atendimento")
    if _superadmin(user):
        where, params = "target='plataforma'", []
    elif user["role"] == "gestor":
        where, params = "institution_id=? AND COALESCE(target,'secretaria') IN ('secretaria','gestao')", [user["institution_id"]]
    else:
        where, params = "institution_id=? AND COALESCE(target,'secretaria')='secretaria'", [user["institution_id"]]
    by_status = {r["status"]: r["n"] for r in rows(conn.execute(
        f"SELECT status, COUNT(*) AS n FROM tickets WHERE {where} GROUP BY status", params))}
    by_cat = rows(conn.execute(
        f"SELECT category, COUNT(*) AS n FROM tickets WHERE {where} AND created_at >= date('now','-90 day') GROUP BY category ORDER BY n DESC", params))
    avg = one(conn.execute(
        f"""SELECT ROUND(AVG((julianday(closed_at) - julianday(created_at)) * 24), 1) AS hours, ROUND(AVG(rating), 1) AS rating
           FROM tickets WHERE {where} AND closed_at IS NOT NULL AND created_at >= date('now','-90 day')""", params))
    open_t = [_decorate(conn, t, user) for t in rows(conn.execute(
        f"SELECT * FROM tickets WHERE {where} AND status IN ('aberto','em_andamento')", params))]
    return {"by_status": by_status, "by_category": [{**c, "label": TODAS_CATEGORIAS.get(c["category"], c["category"])} for c in by_cat],
            "avg_hours": avg["hours"], "avg_rating": avg["rating"], "overdue": sum(1 for t in open_t if t["overdue"])}
