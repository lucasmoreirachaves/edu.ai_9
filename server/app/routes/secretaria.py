"""Painel da secretaria escolar: cadastro dos alunos (foto, matrícula e documentos), carteirinhas
de estudante e declarações montadas automaticamente com os dados do sistema.

Os chamados que a secretaria responde ficam em routes/atendimento.py (destino "secretaria").
O gestor da instituição também tem acesso a estas telas.
"""
import base64
import re
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import ia
from ..auth import current_user, secretaria_only
from ..db import CommitRoute, audit, get_db, jdump, notify, one, rows
from ..seguranca import client_ip, limitar
from ..util import ai_model, ai_quota_check, log_ai

router = APIRouter(prefix="/api/secretaria", route_class=CommitRoute)
docs_router = APIRouter(prefix="/api/documentos", route_class=CommitRoute)

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
FOTO_MAX = 700 * 1024
FOTO_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$")


def por_extenso(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _student(conn, user, sid: int) -> dict:
    s = one(conn.execute("SELECT * FROM users WHERE id=? AND institution_id=? AND role='aluno'", (sid, user["institution_id"])))
    if not s:
        raise HTTPException(404, "Aluno não encontrado")
    s.pop("password_hash", None)
    s.pop("totp_secret", None)
    s.pop("ai_prefs", None)
    s["classes"] = rows(conn.execute(
        """SELECT c.id, c.name, c.grade, c.year, co.name AS course FROM class_students cs JOIN classes c ON c.id=cs.class_id
           LEFT JOIN courses co ON co.id=c.course_id WHERE cs.user_id=? ORDER BY c.year DESC, c.name""", (sid,)))
    return s


def _institution(conn, iid: int) -> dict:
    inst = one(conn.execute("SELECT id, name, slug, cnpj, type, color, logo FROM institutions WHERE id=?", (iid,)))
    unit = one(conn.execute("SELECT name, city FROM units WHERE institution_id=? ORDER BY id LIMIT 1", (iid,)))
    inst["city"] = (unit or {}).get("city") or ""
    inst["unit"] = (unit or {}).get("name") or ""
    return inst


def _ensure_registration(conn, s: dict) -> str:
    """Número de matrícula: o cadastrado ou um gerado automaticamente (ano + id)."""
    if s.get("registration"):
        return s["registration"]
    reg = f"{(s.get('created_at') or str(date.today().year))[:4]}{s['id']:05d}"
    conn.execute("UPDATE users SET registration=? WHERE id=?", (reg, s["id"]))
    s["registration"] = reg
    return reg


def _code(conn) -> str:
    while True:
        c = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        if not one(conn.execute("SELECT id FROM issued_documents WHERE code=?", (c,))):
            return c


# ================================================================== painel

@router.get("/resumo")
def resumo(user=Depends(secretaria_only), conn=Depends(get_db)):
    iid = user["institution_id"]
    q = lambda sql, *p: conn.execute(sql, (iid, *p)).fetchone()[0]  # noqa: E731
    return {
        "alunos": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='aluno' AND status='ativo'"),
        "sem_foto": q("SELECT COUNT(*) FROM users WHERE institution_id=? AND role='aluno' AND status='ativo' AND (photo IS NULL OR photo='')"),
        "chamados_abertos": q("SELECT COUNT(*) FROM tickets WHERE institution_id=? AND COALESCE(target,'secretaria')='secretaria'"
                              " AND status IN ('aberto','em_andamento')"),
        "pedidos_documento": q("SELECT COUNT(*) FROM tickets WHERE institution_id=? AND COALESCE(target,'secretaria')='secretaria'"
                               " AND category='documento' AND status IN ('aberto','em_andamento')"),
        "documentos_mes": q("SELECT COUNT(*) FROM issued_documents WHERE institution_id=? AND created_at >= date('now','start of month')"),
        "ultimos": rows(conn.execute(
            """SELECT d.id, d.kind, d.title, d.code, d.created_at, u.name AS student FROM issued_documents d
               JOIN users u ON u.id=d.student_id WHERE d.institution_id=? ORDER BY d.id DESC LIMIT 8""", (iid,))),
    }


# ================================================================== alunos

@router.get("/turmas")
def turmas(user=Depends(secretaria_only), conn=Depends(get_db)):
    return rows(conn.execute(
        """SELECT c.id, c.name, c.grade, c.year, co.name AS course,
             (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS students
           FROM classes c LEFT JOIN courses co ON co.id=c.course_id WHERE c.institution_id=? ORDER BY c.name""",
        (user["institution_id"],)))


@router.get("/alunos")
def alunos(q: str = "", class_id: int | None = None, user=Depends(secretaria_only), conn=Depends(get_db)):
    sql = """SELECT u.id, u.name, u.email, u.registration, u.birth_date, u.document_id, u.status,
               CASE WHEN u.photo IS NULL OR u.photo='' THEN 0 ELSE 1 END AS has_photo,
               (SELECT GROUP_CONCAT(c.name, ', ') FROM class_students cs JOIN classes c ON c.id=cs.class_id WHERE cs.user_id=u.id) AS classes
             FROM users u WHERE u.institution_id=? AND u.role='aluno'"""
    params: list = [user["institution_id"]]
    if class_id:
        sql += " AND u.id IN (SELECT user_id FROM class_students WHERE class_id=?)"
        params.append(class_id)
    if q.strip():
        sql += " AND (u.name LIKE ? OR u.email LIKE ? OR u.registration LIKE ?)"
        params += [f"%{q.strip()}%"] * 3
    return rows(conn.execute(sql + " ORDER BY u.name LIMIT 1000", params))


@router.get("/alunos/{sid}")
def aluno(sid: int, user=Depends(secretaria_only), conn=Depends(get_db)):
    s = _student(conn, user, sid)
    s["documents"] = rows(conn.execute("SELECT id, kind, title, code, created_at FROM issued_documents WHERE student_id=?"
                                       " ORDER BY id DESC", (sid,)))
    return s


class AlunoIn(BaseModel):
    registration: str | None = None
    birth_date: str | None = None
    document_id: str | None = None


@router.put("/alunos/{sid}")
def editar_aluno(sid: int, body: AlunoIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    _student(conn, user, sid)
    if body.birth_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.birth_date):
        raise HTTPException(400, "Data de nascimento inválida")
    if body.registration and one(conn.execute("SELECT id FROM users WHERE institution_id=? AND registration=? AND id<>?",
                                              (user["institution_id"], body.registration.strip(), sid))):
        raise HTTPException(409, "Número de matrícula já usado por outro aluno")
    conn.execute("UPDATE users SET registration=COALESCE(?, registration), birth_date=COALESCE(?, birth_date),"
                 " document_id=COALESCE(?, document_id) WHERE id=?",
                 ((body.registration or "").strip()[:30] or None, body.birth_date or None,
                  (body.document_id or "").strip()[:30] or None, sid))
    audit(conn, user, "aluno.dados_cadastrais", f"aluno {sid}")
    return {"ok": True}


class FotoIn(BaseModel):
    photo: str | None = None     # data URL (PNG, JPEG ou WebP) ou null para remover


@router.put("/alunos/{sid}/foto")
def foto(sid: int, body: FotoIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    _student(conn, user, sid)
    if body.photo:
        m = FOTO_RE.match(body.photo)
        if not m:
            raise HTTPException(400, "Envie uma imagem PNG, JPEG ou WebP")
        try:
            size = len(base64.b64decode(m.group(2), validate=True))
        except ValueError:
            raise HTTPException(400, "Imagem inválida")
        if size > FOTO_MAX:
            raise HTTPException(400, "Foto maior que 700 KB")
    conn.execute("UPDATE users SET photo=? WHERE id=?", (body.photo or None, sid))
    audit(conn, user, "aluno.foto", f"aluno {sid} {'atualizada' if body.photo else 'removida'}")
    return {"ok": True}


# ================================================================== carteirinhas de estudante

class CarteirinhasIn(BaseModel):
    student_ids: list[int]
    valid_until: str = ""


@router.post("/carteirinhas")
def carteirinhas(body: CarteirinhasIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    """Monta as carteirinhas (dados puxados do cadastro) e registra a emissão de cada uma."""
    if not body.student_ids or len(body.student_ids) > 300:
        raise HTTPException(400, "Escolha de 1 a 300 alunos")
    valid = body.valid_until or f"{date.today().year}-12-31"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valid):
        raise HTTPException(400, "Validade inválida")
    inst = _institution(conn, user["institution_id"])
    cards = []
    for sid in dict.fromkeys(body.student_ids):
        s = _student(conn, user, sid)
        reg = _ensure_registration(conn, s)
        cls = s["classes"][0] if s["classes"] else {}
        code = _code(conn)
        card = {"student_id": sid, "name": s["name"], "photo": s.get("photo"), "registration": reg,
                "birth_date": s.get("birth_date"), "document_id": s.get("document_id"),
                "class_name": cls.get("name") or "", "course": cls.get("course") or cls.get("grade") or "",
                "year": cls.get("year") or date.today().year, "valid_until": valid, "code": code}
        conn.execute("INSERT INTO issued_documents (institution_id, student_id, kind, title, body, code, issued_by) VALUES (?,?,?,?,?,?,?)",
                     (user["institution_id"], sid, "carteirinha", "Carteirinha de estudante",
                      jdump({k: v for k, v in card.items() if k != "photo"}), code, user["id"]))
        cards.append(card)
    audit(conn, user, "carteirinhas.emitidas", f"{len(cards)} carteirinha(s)")
    return {"institution": inst, "cards": cards}


# ================================================================== declarações

MODELOS = {
    "matricula": ("Declaração de matrícula",
                  "Declaramos, para os devidos fins{finalidade}, que {nome}{documento}{nascimento}, matrícula nº {matricula}, "
                  "está regularmente matriculado(a) nesta instituição de ensino, {instituicao}{cnpj}, no ano letivo de {ano}, "
                  "cursando {turma}{curso}."),
    "frequencia": ("Declaração de frequência",
                   "Declaramos, para os devidos fins{finalidade}, que {nome}{documento}{nascimento}, matrícula nº {matricula}, "
                   "é aluno(a) regularmente matriculado(a) em {turma}{curso} nesta instituição, {instituicao}{cnpj}, e "
                   "frequenta regularmente as aulas no ano letivo de {ano}{extra}."),
    "conclusao": ("Atestado de conclusão",
                  "Atestamos, para os devidos fins{finalidade}, que {nome}{documento}{nascimento}, matrícula nº {matricula}, "
                  "concluiu {turma}{curso} nesta instituição de ensino, {instituicao}{cnpj}, no ano letivo de {ano}, "
                  "estando apto(a) a prosseguir os estudos{extra}."),
    "transferencia": ("Declaração de transferência",
                      "Declaramos, para os devidos fins{finalidade}, que {nome}{documento}{nascimento}, matrícula nº {matricula}, "
                      "esteve regularmente matriculado(a) nesta instituição, {instituicao}{cnpj}, em {turma}{curso}, no ano "
                      "letivo de {ano}, e solicitou transferência nesta data. A documentação escolar (histórico e "
                      "conteúdo programático) será fornecida no prazo legal{extra}."),
    "vinculo": ("Declaração de vínculo escolar (transporte / estágio)",
                "Declaramos, para os devidos fins{finalidade}, que {nome}{documento}{nascimento}, matrícula nº {matricula}, "
                "é estudante regularmente matriculado(a) em {turma}{curso} nesta instituição, {instituicao}{cnpj}, "
                "no ano letivo de {ano}{extra}."),
    "personalizada": ("Declaração", "{extra}"),
}
EXTRA_LABEL = {"frequencia": "Frequência ou observação (opcional)", "conclusao": "Observação (opcional)",
               "transferencia": "Destino ou observação (opcional)", "vinculo": "Turno/horário das aulas (opcional)",
               "matricula": "Observação (opcional)", "personalizada": "Texto da declaração"}


def _dados(conn, user, sid: int) -> dict:
    s = _student(conn, user, sid)
    inst = _institution(conn, user["institution_id"])
    cls = s["classes"][0] if s["classes"] else {}
    nasc = ""
    if s.get("birth_date"):
        y, m, d = s["birth_date"].split("-")
        nasc = f"{d}/{m}/{y}"
    return {"s": s, "inst": inst, "nome": s["name"], "documento": s.get("document_id") or "", "nascimento": nasc,
            "matricula": _ensure_registration(conn, s), "turma": cls.get("name") or "",
            "curso": cls.get("course") or "", "ano": cls.get("year") or date.today().year,
            "instituicao": inst["name"], "cnpj": inst.get("cnpj") or "", "cidade": inst["city"]}


def montar(kind: str, d: dict, finalidade: str = "", extra: str = "") -> tuple[str, str]:
    title, tpl = MODELOS[kind]
    texto = tpl.format(
        nome=d["nome"].upper(),
        documento=f", portador(a) do documento {d['documento']}" if d["documento"] else "",
        nascimento=f", nascido(a) em {d['nascimento']}" if d["nascimento"] else "",
        matricula=d["matricula"], instituicao=d["instituicao"],
        cnpj=f", inscrita no CNPJ sob o nº {d['cnpj']}" if d["cnpj"] else "",
        ano=d["ano"], turma=d["turma"] or "o curso regular", curso=f" ({d['curso']})" if d["curso"] else "",
        finalidade=f", especialmente para {finalidade.strip().rstrip('.')}" if finalidade.strip() else "",
        extra=(f". {extra.strip().rstrip('.')}" if kind != "personalizada" else extra.strip()) if extra.strip() else "",
    )
    if not texto.endswith("."):
        texto += "."
    if kind != "personalizada":
        texto += "\n\nPor ser verdade, firmamos a presente declaração."
    return title, texto


@router.get("/declaracoes/modelos")
def modelos(user=Depends(secretaria_only)):
    return [{"kind": k, "title": v[0], "extra_label": EXTRA_LABEL.get(k, "Observação")} for k, v in MODELOS.items()]


class DeclaracaoIn(BaseModel):
    student_id: int
    kind: str
    purpose: str = ""
    extra: str = ""
    body: str | None = None        # texto revisado pela secretaria (senão, o modelo)
    title: str | None = None
    ticket_id: int | None = None   # emite a partir de um pedido de documento no atendimento


def _check_kind(kind: str):
    if kind not in MODELOS:
        raise HTTPException(400, "Modelo de declaração inválido")


@router.post("/declaracoes/previa")
def previa(body: DeclaracaoIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    _check_kind(body.kind)
    d = _dados(conn, user, body.student_id)
    title, texto = montar(body.kind, d, body.purpose[:200], body.extra[:2000])
    return {"title": title, "body": texto, "student": {"id": d["s"]["id"], "name": d["nome"], "registration": d["matricula"],
                                                      "class_name": d["turma"]}}


@router.post("/declaracoes/redigir-ia")
def redigir_ia(body: DeclaracaoIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    """A IA redige (ou melhora) o texto da declaração com os dados do cadastro; a secretaria revisa antes de emitir."""
    _check_kind(body.kind)
    ai_quota_check(conn, user["institution_id"])
    d = _dados(conn, user, body.student_id)
    title, base = montar(body.kind, d, body.purpose[:200], body.extra[:2000])
    pedido = (f"Redija o texto de uma '{title}' escolar formal, em um ou dois parágrafos, usando SOMENTE estes dados "
              f"(não invente nenhum dado):\n- Aluno(a): {d['nome']}\n- Documento: {d['documento'] or 'não informado'}\n"
              f"- Nascimento: {d['nascimento'] or 'não informado'}\n- Matrícula: {d['matricula']}\n"
              f"- Turma: {d['turma'] or 'não informada'} {('(' + d['curso'] + ')') if d['curso'] else ''}\n- Ano letivo: {d['ano']}\n"
              f"- Instituição: {d['instituicao']} {('CNPJ ' + d['cnpj']) if d['cnpj'] else ''}\n"
              f"- Finalidade: {body.purpose or 'não informada'}\n- Observações/pedido: {(body.body or body.extra or '')[:1500]}\n\n"
              f"Modelo de referência:\n{base}\n\nResponda só com o texto da declaração, sem título, sem local/data e sem assinatura.")
    model = ai_model(conn, user["institution_id"], user["id"])
    texto, meta = ia.conversar("secretaria", [{"role": "user", "content": pedido}], model)
    if meta["ok"]:
        log_ai(conn, user, user["institution_id"], "declaracao", meta)
    return {"title": title, "body": texto if meta["ok"] else base, "ok": meta["ok"],
            "message": None if meta["ok"] else "IA indisponível: usamos o modelo padrão."}


@router.post("/declaracoes")
def emitir(body: DeclaracaoIn, user=Depends(secretaria_only), conn=Depends(get_db)):
    _check_kind(body.kind)
    d = _dados(conn, user, body.student_id)
    title, texto = montar(body.kind, d, body.purpose[:200], body.extra[:2000])
    if body.body and body.body.strip():
        texto = body.body.strip()[:8000]
    if body.title and body.title.strip():
        title = body.title.strip()[:120]
    if len(texto) < 20:
        raise HTTPException(400, "O texto da declaração está muito curto")
    ticket = None
    if body.ticket_id:
        ticket = one(conn.execute("SELECT * FROM tickets WHERE id=? AND institution_id=? AND COALESCE(target,'secretaria') IN ('secretaria','gestao')",
                                  (body.ticket_id, user["institution_id"])))
        if not ticket:
            raise HTTPException(404, "Chamado não encontrado")
    code = _code(conn)
    did = conn.execute("INSERT INTO issued_documents (institution_id, student_id, kind, title, body, code, ticket_id, issued_by)"
                       " VALUES (?,?,?,?,?,?,?,?)", (user["institution_id"], body.student_id, body.kind, title, texto, code,
                                                     body.ticket_id, user["id"])).lastrowid
    notify(conn, body.student_id, f"Documento emitido: {title}", "Documentos", f"#/documentos/{did}")
    if ticket:
        conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body) VALUES (?,?,?)",
                     (ticket["id"], user["id"], f"Documento emitido: {title} (código de verificação {code}). "
                                                f"Ele está disponível em “Meus documentos”, pronto para imprimir ou salvar em PDF."))
        conn.execute("UPDATE tickets SET status='resolvido', updated_at=CURRENT_TIMESTAMP, closed_at=CURRENT_TIMESTAMP,"
                     " assigned_to=COALESCE(assigned_to, ?) WHERE id=?", (user["id"], ticket["id"]))
        if ticket["user_id"] != body.student_id:
            notify(conn, ticket["user_id"], f"Chamado #{ticket['protocol']} resolvido: {title}", "Atendimento",
                   f"#/atendimento/{ticket['id']}")
    audit(conn, user, "declaracao.emitida", f"{title} · aluno {body.student_id} · {code}")
    return {"id": did, "code": code}


@router.get("/documentos")
def documentos(student_id: int | None = None, user=Depends(secretaria_only), conn=Depends(get_db)):
    sql = """SELECT d.id, d.kind, d.title, d.code, d.created_at, d.ticket_id, u.name AS student, u.registration, i.name AS issued_by
             FROM issued_documents d JOIN users u ON u.id=d.student_id LEFT JOIN users i ON i.id=d.issued_by
             WHERE d.institution_id=?"""
    params: list = [user["institution_id"]]
    if student_id:
        sql += " AND d.student_id=?"
        params.append(student_id)
    return rows(conn.execute(sql + " ORDER BY d.id DESC LIMIT 500", params))


def _documento_completo(conn, d: dict) -> dict:
    inst = _institution(conn, d["institution_id"])
    d["institution"] = inst
    d["place_date"] = f"{inst['city'] + ', ' if inst['city'] else ''}{por_extenso(date.fromisoformat(d['created_at'][:10]))}"
    signer = one(conn.execute("SELECT name, role FROM users WHERE id=?", (d["issued_by"],))) if d["issued_by"] else None
    d["signer"] = signer["name"] if signer else ""
    d["signer_role"] = "Secretaria escolar" if signer and signer["role"] == "secretaria" else "Direção / Gestão"
    st = one(conn.execute("SELECT name, registration FROM users WHERE id=?", (d["student_id"],)))
    d["student"], d["registration"] = st["name"], st["registration"]
    return d


@router.get("/documentos/{did}")
def documento(did: int, user=Depends(secretaria_only), conn=Depends(get_db)):
    d = one(conn.execute("SELECT * FROM issued_documents WHERE id=? AND institution_id=?", (did, user["institution_id"])))
    if not d:
        raise HTTPException(404, "Documento não encontrado")
    return _documento_completo(conn, d)


# ================================================================== aluno: meus documentos e verificação pública

@docs_router.get("/meus")
def meus(user=Depends(current_user), conn=Depends(get_db)):
    return rows(conn.execute("SELECT id, kind, title, code, created_at FROM issued_documents WHERE student_id=? AND kind<>'carteirinha'"
                             " ORDER BY id DESC", (user["id"],)))


@docs_router.get("/meus/{did}")
def meu(did: int, user=Depends(current_user), conn=Depends(get_db)):
    d = one(conn.execute("SELECT * FROM issued_documents WHERE id=? AND student_id=? AND kind<>'carteirinha'", (did, user["id"])))
    if not d:
        raise HTTPException(404, "Documento não encontrado")
    return _documento_completo(conn, d)


@docs_router.get("/verificar/{code}")
def verificar(code: str, request: Request, conn=Depends(get_db)):
    """Confere a autenticidade de uma declaração ou carteirinha pelo código impresso nela."""
    limitar(f"verificar:{client_ip(request)}", 30, 600)
    d = one(conn.execute(
        """SELECT d.kind, d.title, d.created_at, u.name AS student, i.name AS institution FROM issued_documents d
           JOIN users u ON u.id=d.student_id JOIN institutions i ON i.id=d.institution_id WHERE d.code=?""",
        (code.strip().upper(),)))
    if not d:
        raise HTTPException(404, "Código não encontrado")
    parts = d["student"].split()
    d["student"] = parts[0] + (" " + parts[-1][0] + "." if len(parts) > 1 else "")   # só o necessário para conferir
    return {**d, "valid": True}
