"""Área do professor: disciplinas, turmas, biblioteca, Estúdio de IA, materiais, questões, atividades e relatórios."""
import csv
import io
import re

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import ia, jobs, scoring
from ..auth import professor_only
from ..db import CommitRoute, audit, get_db, jdump, jload, notify, one, rows
from ..util import (activity_questions, ai_model, ai_quota_check, delete_material, institution_settings, log_ai, own_activity,
                    own_document, own_material, own_question, own_subject, save_material_version, teacher_subject_ids)

router = APIRouter(prefix="/api/prof", route_class=CommitRoute)
TEXT_PREVIEW = 300_000  # caracteres do texto extraído mostrados na tela do documento


def _ph(ids):
    ids = list(ids) or [0]
    return ",".join("?" * len(ids)), ids


def _teacher_class_ids(conn, user) -> list[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT class_id FROM subjects WHERE teacher_id=? AND institution_id=?",
                                       (user["id"], user["institution_id"]))]


def _check_topic(conn, subject_id: int, topic_id: int | None) -> int | None:
    """O assunto precisa pertencer à disciplina (senão vira 'sem assunto')."""
    if not topic_id:
        return None
    if not one(conn.execute("SELECT id FROM topics WHERE id=? AND subject_id=?", (topic_id, subject_id))):
        raise HTTPException(400, "Assunto inválido para esta disciplina")
    return topic_id


MAX_UPLOAD = 25 * 1024 * 1024


# ================================================================== visão geral

@router.get("/overview")
def overview(user=Depends(professor_only), conn=Depends(get_db)):
    ph, sids = _ph(teacher_subject_ids(conn, user))
    cph, cids = _ph(_teacher_class_ids(conn, user))
    to_grade = rows(conn.execute(
        f"""SELECT a.id, a.title, a.due_date, c.name AS class_name,
              (SELECT COUNT(*) FROM submissions s WHERE s.activity_id=a.id) AS delivered,
              (SELECT COUNT(*) FROM submissions s WHERE s.activity_id=a.id AND s.status='entregue') AS pending,
              (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=a.class_id) AS total
            FROM activities a JOIN classes c ON c.id=a.class_id
            WHERE a.subject_id IN ({ph}) AND a.status='publicada' ORDER BY a.due_date LIMIT 6""", sids))
    recent = rows(conn.execute(
        f"SELECT id, title, type, status, updated_at FROM materials WHERE subject_id IN ({ph}) AND status<>'arquivado'"
        " ORDER BY updated_at DESC LIMIT 6", sids))
    perf = rows(conn.execute(
        f"""SELECT c.id, c.name, ROUND(AVG(s.score * 10.0 / a.points), 1) AS avg
            FROM classes c LEFT JOIN activities a ON a.class_id=c.id AND a.subject_id IN ({ph})
            LEFT JOIN submissions s ON s.activity_id=a.id AND s.status='corrigida'
            WHERE c.id IN ({cph}) GROUP BY c.id ORDER BY c.name""", (*sids, *cids)))
    games = rows(conn.execute("SELECT id, title, status, code FROM games WHERE teacher_id=? AND status<>'finalizado' ORDER BY id DESC LIMIT 5", (user["id"],)))
    docs = rows(conn.execute(f"SELECT id, title, status, progress FROM documents WHERE subject_id IN ({ph}) ORDER BY id DESC LIMIT 4", sids))
    return {
        "kpis": {
            "classes": len(_teacher_class_ids(conn, user)),
            "materials": conn.execute(f"SELECT COUNT(*) FROM materials WHERE subject_id IN ({ph}) AND status<>'arquivado'", sids).fetchone()[0],
            "materials_week": conn.execute(f"SELECT COUNT(*) FROM materials WHERE subject_id IN ({ph}) AND created_at >= date('now','-7 day')", sids).fetchone()[0],
            "to_grade": conn.execute(f"SELECT COUNT(*) FROM submissions s JOIN activities a ON a.id=s.activity_id WHERE a.subject_id IN ({ph}) AND s.status='entregue'", sids).fetchone()[0],
            "due_today": conn.execute(f"SELECT COUNT(*) FROM activities WHERE subject_id IN ({ph}) AND status='publicada' AND date(due_date)=date('now')", sids).fetchone()[0],
            "games": len(games),
        },
        "activities": to_grade, "materials": recent, "performance": perf, "games": games, "documents": docs,
    }


# ================================================================== turmas e alunos

@router.get("/classes")
def classes(user=Depends(professor_only), conn=Depends(get_db)):
    ph, cids = _ph(_teacher_class_ids(conn, user))
    out = rows(conn.execute(
        f"""SELECT c.*, (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=c.id) AS students
            FROM classes c WHERE c.id IN ({ph}) ORDER BY c.name""", cids))
    for c in out:
        c["subjects"] = rows(conn.execute("SELECT id, name FROM subjects WHERE class_id=? AND teacher_id=?", (c["id"], user["id"])))
        r = one(conn.execute(
            "SELECT ROUND(AVG(s.score*10.0/a.points),1) AS avg, COUNT(s.id) AS n FROM submissions s JOIN activities a ON a.id=s.activity_id"
            " WHERE a.class_id=? AND a.created_by=? AND s.status='corrigida'", (c["id"], user["id"])))
        c["avg"] = r["avg"]
    return out


@router.get("/classes/{cid}")
def class_detail(cid: int, user=Depends(professor_only), conn=Depends(get_db)):
    if cid not in _teacher_class_ids(conn, user):
        raise HTTPException(404, "Turma não encontrada")
    c = one(conn.execute("SELECT * FROM classes WHERE id=?", (cid,)))
    total_acts = conn.execute("SELECT COUNT(*) FROM activities WHERE class_id=? AND created_by=? AND status<>'rascunho'", (cid, user["id"])).fetchone()[0]
    students = rows(conn.execute(
        """SELECT u.id, u.name, u.email, u.status,
             (SELECT COUNT(*) FROM submissions s JOIN activities a ON a.id=s.activity_id WHERE s.student_id=u.id AND a.class_id=? AND a.created_by=?) AS delivered,
             (SELECT ROUND(AVG(s.score*10.0/a.points),1) FROM submissions s JOIN activities a ON a.id=s.activity_id WHERE s.student_id=u.id AND a.class_id=? AND a.created_by=? AND s.status='corrigida') AS avg
           FROM users u JOIN class_students cs ON cs.user_id=u.id WHERE cs.class_id=? ORDER BY u.name""",
        (cid, user["id"], cid, user["id"], cid)))
    for s in students:
        s["completion"] = round(100 * s["delivered"] / total_acts) if total_acts else 0
    return {"class": c, "students": students, "activities": total_acts}


@router.get("/students/{uid}")
def student_profile(uid: int, user=Depends(professor_only), conn=Depends(get_db)):
    ph, cids = _ph(_teacher_class_ids(conn, user))
    st = one(conn.execute(
        f"SELECT u.id, u.name, u.email, u.grade, cs.class_id, c.name AS class_name FROM users u JOIN class_students cs ON cs.user_id=u.id"
        f" JOIN classes c ON c.id=cs.class_id WHERE u.id=? AND cs.class_id IN ({ph})", (uid, *cids)))
    if not st:
        raise HTTPException(404, "Aluno não encontrado nas suas turmas")
    sph, sids = _ph(teacher_subject_ids(conn, user))
    subs = rows(conn.execute(
        f"""SELECT a.id, a.title, a.points, s.score, s.status, s.submitted_at, sub.name AS subject
            FROM submissions s JOIN activities a ON a.id=s.activity_id JOIN subjects sub ON sub.id=a.subject_id
            WHERE s.student_id=? AND a.subject_id IN ({sph}) ORDER BY s.submitted_at""", (uid, *sids)))
    results = scoring.question_results(conn, f"s.student_id=? AND a.subject_id IN ({sph})", (uid, *sids))
    progress = rows(conn.execute(
        f"SELECT m.title, m.type, p.pct FROM material_progress p JOIN materials m ON m.id=p.material_id WHERE p.user_id=? AND m.subject_id IN ({sph}) ORDER BY p.updated_at DESC LIMIT 10",
        (uid, *sids)))
    return {"student": st, "submissions": subs, "topics": scoring.by_topic(conn, results), "progress": progress}


# ================================================================== disciplinas

class SubjectIn(BaseModel):
    """O que o professor pode ajustar. Nome, turma e professor da disciplina são definidos pela gestão."""
    description: str = ""
    color: str = "#2563EB"


@router.get("/subjects")
def subjects(user=Depends(professor_only), conn=Depends(get_db)):
    """Disciplinas vinculadas a este professor pela gestão (inclusive as desativadas, para consultar o histórico)."""
    return rows(conn.execute(
        """SELECT s.*, c.name AS class_name,
             (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=s.class_id) AS students,
             (SELECT COUNT(*) FROM materials m WHERE m.subject_id=s.id AND m.status<>'arquivado') AS materials,
             (SELECT COUNT(*) FROM materials m WHERE m.subject_id=s.id AND m.status='publicado') AS published,
             (SELECT COUNT(*) FROM activities a WHERE a.subject_id=s.id) AS activities,
             (SELECT COUNT(*) FROM topics t WHERE t.subject_id=s.id) AS topics
           FROM subjects s JOIN classes c ON c.id=s.class_id WHERE s.teacher_id=? ORDER BY s.active DESC, s.name""", (user["id"],)))


@router.post("/subjects")
def create_subject(user=Depends(professor_only)):
    raise HTTPException(403, "As disciplinas são criadas pela coordenação da escola, que vincula o professor à turma.")


@router.get("/subjects/{sid}")
def subject_detail(sid: int, user=Depends(professor_only), conn=Depends(get_db)):
    s = own_subject(conn, user, sid)
    s["class_name"] = conn.execute("SELECT name FROM classes WHERE id=?", (s["class_id"],)).fetchone()[0]
    s["students"] = conn.execute("SELECT COUNT(*) FROM class_students WHERE class_id=?", (s["class_id"],)).fetchone()[0]
    topics = rows(conn.execute("SELECT * FROM topics WHERE subject_id=? ORDER BY position, id", (sid,)))
    mats = rows(conn.execute("SELECT id, title, type, status, topic_id, document_id, updated_at FROM materials WHERE subject_id=? AND status<>'arquivado' ORDER BY updated_at DESC", (sid,)))
    docs = rows(conn.execute("SELECT id, title, status, topic_id, created_at FROM documents WHERE subject_id=? AND archived=0 ORDER BY id DESC", (sid,)))
    for t in topics:
        t["materials"] = [m for m in mats if m["topic_id"] == t["id"]]
        t["documents"] = [d for d in docs if d["topic_id"] == t["id"]]
    return {"subject": s, "topics": topics, "materials": mats, "documents": docs,
            "loose_materials": [m for m in mats if not m["topic_id"]]}


@router.put("/subjects/{sid}")
def update_subject(sid: int, body: SubjectIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_subject(conn, user, sid)
    color = body.color if re.fullmatch(r"#[0-9A-Fa-f]{6}", body.color or "") else "#2563EB"
    conn.execute("UPDATE subjects SET description=?, color=? WHERE id=?", (body.description[:500], color, sid))
    return {"ok": True}


class TopicIn(BaseModel):
    name: str


@router.post("/subjects/{sid}/topics")
def create_topic(sid: int, body: TopicIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_subject(conn, user, sid)
    pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM topics WHERE subject_id=?", (sid,)).fetchone()[0]
    return {"id": conn.execute("INSERT INTO topics (subject_id, name, position) VALUES (?,?,?)", (sid, body.name, pos)).lastrowid}


@router.put("/topics/{tid}")
def update_topic(tid: int, body: TopicIn, user=Depends(professor_only), conn=Depends(get_db)):
    t = one(conn.execute("SELECT * FROM topics WHERE id=?", (tid,)))
    if not t:
        raise HTTPException(404, "Assunto não encontrado")
    own_subject(conn, user, t["subject_id"])
    conn.execute("UPDATE topics SET name=? WHERE id=?", (body.name, tid))
    return {"ok": True}


@router.delete("/topics/{tid}")
def delete_topic(tid: int, user=Depends(professor_only), conn=Depends(get_db)):
    t = one(conn.execute("SELECT * FROM topics WHERE id=?", (tid,)))
    if not t:
        raise HTTPException(404, "Assunto não encontrado")
    own_subject(conn, user, t["subject_id"])
    for table in ("materials", "documents", "questions"):
        conn.execute(f"UPDATE {table} SET topic_id=NULL WHERE topic_id=?", (tid,))
    conn.execute("DELETE FROM topics WHERE id=?", (tid,))
    return {"ok": True}


# ================================================================== biblioteca de documentos

@router.get("/documents")
def documents(subject_id: int | None = None, archived: int = 0, user=Depends(professor_only), conn=Depends(get_db)):
    ph, sids = _ph([subject_id] if subject_id else teacher_subject_ids(conn, user))
    if subject_id:
        own_subject(conn, user, subject_id)
    return rows(conn.execute(
        f"""SELECT d.id, d.title, d.filename, d.size, d.pages, d.empty_pages, LENGTH(d.text) AS chars, d.folder, d.status, d.progress, d.error, d.archived, d.shared, d.created_at,
              d.subject_id, d.topic_id, s.name AS subject_name, t.name AS topic_name,
              (SELECT COUNT(*) FROM materials m WHERE m.document_id=d.id) AS materials
            FROM documents d JOIN subjects s ON s.id=d.subject_id LEFT JOIN topics t ON t.id=d.topic_id
            WHERE d.subject_id IN ({ph}) AND d.archived=? ORDER BY d.id DESC""", (*sids, archived)))


@router.post("/documents")
async def upload_document(bg: BackgroundTasks, subject_id: int = Form(...), title: str = Form(""),
                          topic_id: int | None = Form(None), folder: str = Form(""), text: str = Form(""),
                          shared: bool = Form(True), file: UploadFile | None = File(None),
                          user=Depends(professor_only), conn=Depends(get_db)):
    own_subject(conn, user, subject_id)
    topic_id = _check_topic(conn, subject_id, topic_id)
    data, filename = b"", None
    if file and file.filename:
        filename = file.filename
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in jobs.ALLOWED_EXT:
            raise HTTPException(400, "Formato não suportado. Envie PDF, DOCX, TXT ou MD.")
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, "Arquivo maior que 25 MB")
    elif not text.strip():
        raise HTTPException(400, "Envie um arquivo ou cole o texto do conteúdo")
    title = title.strip() or (filename.rsplit(".", 1)[0] if filename else "Texto colado")
    did = conn.execute(
        "INSERT INTO documents (institution_id, subject_id, topic_id, folder, title, filename, size, text, shared, created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user["institution_id"], subject_id, topic_id or None, folder.strip(), title, filename,
         len(data) or len(text.encode()), text if not filename else None, int(shared), user["id"])).lastrowid
    if filename:
        jobs.upload_path(did, filename).write_bytes(data)
    audit(conn, user, "documento.enviado", title)
    conn.commit()
    bg.add_task(jobs.process_document, did)
    return {"id": did}


@router.get("/documents/{did}")
def document_detail(did: int, user=Depends(professor_only), conn=Depends(get_db)):
    d = own_document(conn, user, did)
    d["topics"] = jload(d["topics"], [])
    text = d.pop("text") or ""
    d["chars"] = len(jobs.PAGE_MARK.sub("", text).strip())
    d["text_preview"] = text[:TEXT_PREVIEW]
    d["text_truncated"] = len(text) > TEXT_PREVIEW
    d["ai_chars"] = ia.MAX_CHARS
    d["subject_name"] = conn.execute("SELECT name FROM subjects WHERE id=?", (d["subject_id"],)).fetchone()[0]
    d["materials"] = rows(conn.execute("SELECT id, title, type, status, ai_source, created_at FROM materials WHERE document_id=? ORDER BY id DESC", (did,)))
    d["jobs"] = rows(conn.execute("SELECT id, kind, status, error, material_id FROM generation_jobs WHERE document_id=? ORDER BY id DESC LIMIT 10", (did,)))
    return d


@router.get("/documents/{did}/arquivo")
def download_document(did: int, user=Depends(professor_only), conn=Depends(get_db)):
    """Baixa o arquivo original (mesmo formato e nome do envio)."""
    return jobs.document_file(own_document(conn, user, did))


class DocUpdate(BaseModel):
    title: str
    folder: str = ""
    topic_id: int | None = None
    archived: bool = False
    shared: bool | None = None      # None mantém como está


@router.put("/documents/{did}")
def update_document(did: int, body: DocUpdate, user=Depends(professor_only), conn=Depends(get_db)):
    d = own_document(conn, user, did)
    topic_id = _check_topic(conn, d["subject_id"], body.topic_id)
    shared = d.get("shared", 1) if body.shared is None else int(body.shared)
    conn.execute("UPDATE documents SET title=?, folder=?, topic_id=?, archived=?, shared=? WHERE id=?",
                 (body.title, body.folder, topic_id, int(body.archived), shared, did))
    acao = ("documento.arquivado" if body.archived else
            "documento.compartilhado" if shared and not d.get("shared") else
            "documento.oculto_alunos" if not shared and d.get("shared") else "documento.editado")
    audit(conn, user, acao, body.title)
    return {"ok": True}


@router.post("/documents/{did}/replace")
async def replace_document(did: int, bg: BackgroundTasks, file: UploadFile = File(...),
                           user=Depends(professor_only), conn=Depends(get_db)):
    d = own_document(conn, user, did)
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in jobs.ALLOWED_EXT:
        raise HTTPException(400, "Formato não suportado")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "Arquivo maior que 25 MB")
    if d["filename"]:
        jobs.upload_path(did, d["filename"]).unlink(missing_ok=True)
    jobs.upload_path(did, file.filename).write_bytes(data)
    conn.execute("UPDATE documents SET filename=?, size=?, text=NULL, status='enviado', progress=0 WHERE id=?",
                 (file.filename, len(data), did))
    audit(conn, user, "documento.substituido", d["title"])
    conn.commit()
    bg.add_task(jobs.process_document, did)
    return {"ok": True}


@router.delete("/documents/{did}")
def delete_document(did: int, user=Depends(professor_only), conn=Depends(get_db)):
    """Exclui o documento e o arquivo. Os materiais já gerados continuam (sem documento de origem)."""
    d = own_document(conn, user, did)
    if d["filename"]:
        jobs.upload_path(did, d["filename"]).unlink(missing_ok=True)
    conn.execute("UPDATE materials SET document_id=NULL WHERE document_id=?", (did,))
    conn.execute("DELETE FROM generation_jobs WHERE document_id=?", (did,))
    conn.execute("DELETE FROM documents WHERE id=?", (did,))
    audit(conn, user, "documento.excluido", d["title"])
    return {"ok": True}


@router.post("/documents/{did}/reprocess")
def reprocess_document(did: int, bg: BackgroundTasks, user=Depends(professor_only), conn=Depends(get_db)):
    own_document(conn, user, did)
    conn.execute("UPDATE documents SET status='enviado', progress=0, error=NULL WHERE id=?", (did,))
    conn.commit()
    bg.add_task(jobs.process_document, did)
    return {"ok": True}


# ================================================================== Estúdio de IA

class StudioItem(BaseModel):
    kind: str
    variant: str = ""
    count: int | None = None
    open_count: int | None = None


class StudioIn(BaseModel):
    document_id: int
    items: list[StudioItem]
    level: str = "Ensino Fundamental II"
    difficulty: str = "media"
    notes: str = ""
    topic_id: int | None = None
    page_from: int | None = None
    page_to: int | None = None


@router.post("/studio/generate")
def studio_generate(body: StudioIn, bg: BackgroundTasks, user=Depends(professor_only), conn=Depends(get_db)):
    d = own_document(conn, user, body.document_id)
    if d["status"] != "concluido":
        raise HTTPException(400, "O documento ainda não terminou de ser processado")
    if not body.items:
        raise HTTPException(400, "Escolha pelo menos um formato")
    if len(body.items) > 8:
        raise HTTPException(400, "Escolha no máximo 8 formatos por vez")
    _check_topic(conn, d["subject_id"], body.topic_id)
    ai_quota_check(conn, user["institution_id"])
    ids = []
    for it in body.items:
        if it.kind not in ia.TYPES:
            raise HTTPException(400, f"Formato inválido: {it.kind}")
        count = max(1, min(it.count, 30)) if it.count else None
        open_count = max(0, min(it.open_count or 0, count or 10)) if it.open_count is not None else None
        opts = {"variant": it.variant, "count": count, "open_count": open_count, "level": body.level,
                "difficulty": body.difficulty, "notes": body.notes, "topic_id": body.topic_id,
                "page_from": body.page_from, "page_to": body.page_to}
        ids.append(conn.execute("INSERT INTO generation_jobs (institution_id, document_id, kind, options, created_by) VALUES (?,?,?,?,?)",
                                (user["institution_id"], d["id"], it.kind, jdump(opts), user["id"])).lastrowid)
    audit(conn, user, "ia.geracao", f"{d['title']}: {', '.join(i.kind for i in body.items)}")
    conn.commit()
    bg.add_task(jobs.run_jobs, ids)
    return {"jobs": ids}


@router.get("/studio/jobs")
def studio_jobs(ids: str = "", user=Depends(professor_only), conn=Depends(get_db)):
    if ids:
        ph, idl = _ph(int(i) for i in ids.split(",") if i.strip().isdigit())
        where, params = f"j.id IN ({ph})", idl
    else:
        where, params = "j.created_by=?", [user["id"]]
    return rows(conn.execute(
        f"""SELECT j.id, j.kind, j.status, j.error, j.material_id, j.options, j.created_at, d.title AS document_title,
              m.title AS material_title, m.ai_source
            FROM generation_jobs j JOIN documents d ON d.id=j.document_id LEFT JOIN materials m ON m.id=j.material_id
            WHERE {where} AND j.created_by=? ORDER BY j.id DESC LIMIT 20""", (*params, user["id"])))


# ================================================================== materiais

@router.get("/materials")
def materials(subject_id: int | None = None, type: str | None = None, status: str | None = None,
              user=Depends(professor_only), conn=Depends(get_db)):
    ph, sids = _ph([subject_id] if subject_id else teacher_subject_ids(conn, user))
    sql = (f"""SELECT m.id, m.title, m.type, m.variant, m.status, m.ai_source, m.updated_at, m.subject_id, m.topic_id,
                 s.name AS subject_name, d.title AS document_title, t.name AS topic_name,
                 (SELECT GROUP_CONCAT(c.name, ', ') FROM material_classes mc JOIN classes c ON c.id=mc.class_id WHERE mc.material_id=m.id) AS classes
               FROM materials m JOIN subjects s ON s.id=m.subject_id LEFT JOIN documents d ON d.id=m.document_id
               LEFT JOIN topics t ON t.id=m.topic_id WHERE m.subject_id IN ({ph})""")
    params = list(sids)
    if type:
        sql += " AND m.type=?"
        params.append(type)
    if status:
        sql += " AND m.status=?"
        params.append(status)
    else:
        sql += " AND m.status<>'arquivado'"
    return rows(conn.execute(sql + " ORDER BY m.updated_at DESC", params))


@router.get("/materials/{mid}")
def material_detail(mid: int, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    m["subject"] = one(conn.execute("SELECT id, name, class_id FROM subjects WHERE id=?", (m["subject_id"],)))
    m["document"] = one(conn.execute("SELECT id, title FROM documents WHERE id=?", (m["document_id"],))) if m["document_id"] else None
    m["classes"] = rows(conn.execute("SELECT c.id, c.name, mc.published_at FROM material_classes mc JOIN classes c ON c.id=mc.class_id WHERE mc.material_id=?", (mid,)))
    m["versions"] = rows(conn.execute("SELECT id, title, note, created_at FROM material_versions WHERE material_id=? ORDER BY id DESC LIMIT 30", (mid,)))
    m["topics"] = rows(conn.execute("SELECT id, name FROM topics WHERE subject_id=? ORDER BY position", (m["subject_id"],)))
    m["in_bank"] = conn.execute("SELECT COUNT(*) FROM questions WHERE material_id=?", (mid,)).fetchone()[0]
    return m


class MaterialIn(BaseModel):
    title: str
    content: dict
    topic_id: int | None = None
    note: str = "Edição manual"


@router.put("/materials/{mid}")
def update_material(mid: int, body: MaterialIn, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    content = ia.normalize(m["type"], body.content) or body.content
    topic_id = _check_topic(conn, m["subject_id"], body.topic_id)
    if m["type"] == "mapa":  # mantém cores escolhidas no editor
        for b, src in zip(content.get("branches", []), body.content.get("branches", [])):
            b["color"] = src.get("color") or b.get("color")
    conn.execute("UPDATE materials SET title=?, content=?, topic_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (body.title, jdump(content), topic_id, mid))
    save_material_version(conn, user, {"id": mid, "title": body.title, "content": content}, body.note)
    return {"ok": True, "content": content}


class StatusIn(BaseModel):
    status: str


@router.post("/materials/{mid}/status")
def material_status(mid: int, body: StatusIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_material(conn, user, mid)
    if body.status not in ("rascunho", "revisao", "arquivado"):
        raise HTTPException(400, "Status inválido (para publicar use /publish)")
    conn.execute("UPDATE materials SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (body.status, mid))
    if body.status == "arquivado":
        conn.execute("DELETE FROM material_classes WHERE material_id=?", (mid,))
    return {"ok": True}


class PublishIn(BaseModel):
    class_ids: list[int]


@router.post("/materials/{mid}/publish")
def publish_material(mid: int, body: PublishIn, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    if institution_settings(conn, user["institution_id"]).get("publish_requires_review") and m["status"] == "rascunho":
        raise HTTPException(400, "A política da instituição exige marcar o material como revisado antes de publicar")
    allowed = set(_teacher_class_ids(conn, user))
    cids = [c for c in body.class_ids if c in allowed]
    if not cids:
        raise HTTPException(400, "Selecione ao menos uma das suas turmas")
    conn.execute("DELETE FROM material_classes WHERE material_id=?", (mid,))
    for c in cids:
        conn.execute("INSERT INTO material_classes (material_id, class_id) VALUES (?,?)", (mid, c))
    conn.execute("UPDATE materials SET status='publicado', updated_at=CURRENT_TIMESTAMP WHERE id=?", (mid,))
    save_material_version(conn, user, m, "Publicado")
    ph, cl = _ph(cids)
    for s in rows(conn.execute(f"SELECT DISTINCT user_id FROM class_students WHERE class_id IN ({ph})", cl)):
        notify(conn, s["user_id"], f"Novo material: {m['title']}", "Materiais", f"#/a/estudar/{mid}")
    audit(conn, user, "material.publicado", m["title"])
    return {"ok": True}


@router.post("/materials/{mid}/unpublish")
def unpublish_material(mid: int, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    conn.execute("DELETE FROM material_classes WHERE material_id=?", (mid,))
    conn.execute("UPDATE materials SET status='rascunho', updated_at=CURRENT_TIMESTAMP WHERE id=?", (mid,))
    audit(conn, user, "material.despublicado", m["title"])
    return {"ok": True}


class RegenIn(BaseModel):
    instructions: str = ""
    index: int | None = None      # None = material inteiro
    detail: str = ""              # basico | medio | detalhado (mapa)


def _doc_text(conn, m) -> tuple[str, str]:
    """Texto de origem do material, no mesmo intervalo de páginas usado na geração original."""
    d = one(conn.execute("SELECT * FROM documents WHERE id=?", (m["document_id"],))) if m["document_id"] else None
    if not d:
        return m["title"], ""
    job = one(conn.execute("SELECT options FROM generation_jobs WHERE material_id=? ORDER BY id LIMIT 1", (m["id"],)))
    opts = jload(job["options"], {}) if job else {}
    return d["title"], jobs.source_text(conn, d, opts.get("page_from"), opts.get("page_to"), m["created_by"])


@router.post("/materials/{mid}/regenerate")
def regenerate(mid: int, body: RegenIn, user=Depends(professor_only), conn=Depends(get_db)):
    """Inteiro: grava nova versão. Parte (index): devolve só o item sugerido; o editor decide se aplica."""
    m = own_material(conn, user, mid)
    ai_quota_check(conn, user["institution_id"])
    title, text = _doc_text(conn, m)
    if not text:
        raise HTTPException(400, "Material sem documento de origem para regenerar")
    model = ai_model(conn, user["institution_id"], user["id"])
    if body.index is not None:
        items = m["content"].get(ia.ITEMS_KEY[m["type"]], [])
        if not 0 <= body.index < len(items):
            raise HTTPException(400, "Item inexistente")
        part, meta = ia.regenerate_part(m["type"], title, text, items[body.index], body.instructions, model)
        log_ai(conn, user, user["institution_id"], f"{m['type']}.parte", meta)
        return {"part": part, "provider": meta["provider"], "error": meta.get("error")}
    opts = {"variant": m["variant"], "notes": body.instructions}
    if m["type"] in ("flashcards", "glossario"):
        opts["count"] = len(m["content"].get(ia.ITEMS_KEY[m["type"]], [])) or None
    if m["type"] == "exercicios":
        qs = m["content"].get("questions", [])
        opts["count"] = len(qs) or 5
        opts["open_count"] = sum(1 for q in qs if q.get("kind") == "discursiva")
    if body.detail:
        opts["notes"] = f"Nível de detalhe: {body.detail}. {body.instructions}"
    content, meta = ia.generate(m["type"], title, text, opts, model)
    log_ai(conn, user, user["institution_id"], m["type"], meta)
    source = f"{meta['provider']}:{meta['model']}"
    conn.execute("UPDATE materials SET content=?, ai_source=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (jdump(content), source, mid))
    save_material_version(conn, user, {"id": mid, "title": m["title"], "content": content}, f"Regenerado pela IA ({source})")
    return {"content": content, "provider": meta["provider"], "error": meta.get("error")}


@router.get("/materials/{mid}/versions/{vid}")
def material_version(mid: int, vid: int, user=Depends(professor_only), conn=Depends(get_db)):
    own_material(conn, user, mid)
    v = one(conn.execute("SELECT * FROM material_versions WHERE id=? AND material_id=?", (vid, mid)))
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    v["content"] = jload(v["content"], {})
    return v


@router.post("/materials/{mid}/versions/{vid}/restore")
def restore_version(mid: int, vid: int, user=Depends(professor_only), conn=Depends(get_db)):
    own_material(conn, user, mid)
    v = one(conn.execute("SELECT * FROM material_versions WHERE id=? AND material_id=?", (vid, mid)))
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    conn.execute("UPDATE materials SET content=?, title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (v["content"], v["title"], mid))
    save_material_version(conn, user, {"id": mid, "title": v["title"], "content": v["content"]}, f"Restaurada a versão de {v['created_at']}")
    return {"ok": True}


@router.delete("/materials/{mid}")
def delete_material_route(mid: int, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    delete_material(conn, mid)
    audit(conn, user, "material.excluido", m["title"])
    return {"ok": True}


@router.post("/materials/{mid}/duplicate")
def duplicate_material(mid: int, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    nid = conn.execute(
        "INSERT INTO materials (subject_id, topic_id, document_id, type, title, variant, content, status, ai_source, created_by)"
        " VALUES (?,?,?,?,?,?,?,'rascunho',?,?)",
        (m["subject_id"], m["topic_id"], m["document_id"], m["type"], m["title"] + " (cópia)", m["variant"],
         jdump(m["content"]), m["ai_source"], user["id"])).lastrowid
    save_material_version(conn, user, {"id": nid, "title": m["title"] + " (cópia)", "content": m["content"]}, f"Cópia do material #{mid}")
    return {"id": nid}


@router.post("/materials/{mid}/to-bank")
def material_to_bank(mid: int, user=Depends(professor_only), conn=Depends(get_db)):
    m = own_material(conn, user, mid)
    if m["type"] != "exercicios":
        raise HTTPException(400, "Só listas de exercícios podem ir para o banco")
    existing = {r[0] for r in conn.execute("SELECT statement FROM questions WHERE material_id=?", (mid,))}
    n = 0
    for q in m["content"].get("questions", []):
        if q["statement"] in existing:
            continue
        conn.execute(
            "INSERT INTO questions (subject_id, topic_id, material_id, kind, statement, options, answer, expected, explanation, difficulty, reviewed, created_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,1,?)",
            (m["subject_id"], m["topic_id"], mid, q.get("kind", "objetiva"), q["statement"], jdump(q.get("options", [])),
             q.get("answer"), q.get("expected", ""), q.get("explanation", ""), q.get("difficulty", "media"), user["id"]))
        n += 1
    return {"added": n}


# ================================================================== banco de questões

class QuestionIn(BaseModel):
    subject_id: int
    topic_id: int | None = None
    kind: str = "objetiva"
    statement: str
    options: list[str] = []
    answer: int | None = None
    expected: str = ""
    explanation: str = ""
    difficulty: str = "media"
    reviewed: bool = True


def _check_question(body: QuestionIn):
    if body.kind == "objetiva":
        opts = [o for o in body.options if o.strip()]
        if len(opts) < 2 or body.answer is None or not 0 <= body.answer < len(opts):
            raise HTTPException(400, "Questão objetiva precisa de ao menos 2 alternativas e do gabarito")
        body.options = opts
    else:
        body.options, body.answer = [], None


@router.get("/questions")
def questions(subject_id: int | None = None, topic_id: int | None = None, difficulty: str | None = None,
              kind: str | None = None, q: str | None = None, user=Depends(professor_only), conn=Depends(get_db)):
    ph, sids = _ph([subject_id] if subject_id else teacher_subject_ids(conn, user))
    sql = (f"""SELECT q.*, s.name AS subject_name, t.name AS topic_name,
                 (SELECT COUNT(*) FROM activity_questions aq WHERE aq.question_id=q.id) AS uses
               FROM questions q JOIN subjects s ON s.id=q.subject_id LEFT JOIN topics t ON t.id=q.topic_id
               WHERE q.subject_id IN ({ph})""")
    params = list(sids)
    for col, val in (("q.topic_id", topic_id), ("q.difficulty", difficulty), ("q.kind", kind)):
        if val:
            sql += f" AND {col}=?"
            params.append(val)
    if q:
        sql += " AND q.statement LIKE ?"
        params.append(f"%{q}%")
    out = rows(conn.execute(sql + " ORDER BY q.id DESC", params))
    for r in out:
        r["options"] = jload(r["options"], [])
    return out


@router.post("/questions")
def create_question(body: QuestionIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_subject(conn, user, body.subject_id)
    body.topic_id = _check_topic(conn, body.subject_id, body.topic_id)
    _check_question(body)
    qid = conn.execute(
        "INSERT INTO questions (subject_id, topic_id, kind, statement, options, answer, expected, explanation, difficulty, reviewed, created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (body.subject_id, body.topic_id, body.kind, body.statement, jdump(body.options), body.answer, body.expected,
         body.explanation, body.difficulty, int(body.reviewed), user["id"])).lastrowid
    return {"id": qid}


@router.put("/questions/{qid}")
def update_question(qid: int, body: QuestionIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_question(conn, user, qid)
    own_subject(conn, user, body.subject_id)
    body.topic_id = _check_topic(conn, body.subject_id, body.topic_id)
    _check_question(body)
    conn.execute(
        "UPDATE questions SET subject_id=?, topic_id=?, kind=?, statement=?, options=?, answer=?, expected=?, explanation=?, difficulty=?, reviewed=? WHERE id=?",
        (body.subject_id, body.topic_id, body.kind, body.statement, jdump(body.options), body.answer, body.expected,
         body.explanation, body.difficulty, int(body.reviewed), qid))
    return {"ok": True}


@router.delete("/questions/{qid}")
def delete_question(qid: int, user=Depends(professor_only), conn=Depends(get_db)):
    own_question(conn, user, qid)
    if conn.execute("SELECT COUNT(*) FROM activity_questions WHERE question_id=?", (qid,)).fetchone()[0]:
        raise HTTPException(409, "Questão usada em atividade; remova-a da atividade antes")
    conn.execute("DELETE FROM questions WHERE id=?", (qid,))
    return {"ok": True}


class QGenIn(BaseModel):
    document_id: int
    count: int = 5
    open_count: int = 0
    difficulty: str = "media"
    topic_id: int | None = None
    notes: str = ""


@router.post("/questions/generate")
def generate_questions(body: QGenIn, user=Depends(professor_only), conn=Depends(get_db)):
    d = own_document(conn, user, body.document_id)
    if d["status"] != "concluido":
        raise HTTPException(400, "Documento ainda em processamento")
    ai_quota_check(conn, user["institution_id"])
    topic_id = _check_topic(conn, d["subject_id"], body.topic_id)
    count = max(1, min(body.count, 20))
    content, meta = ia.generate("exercicios", d["title"], jobs.source_text(conn, d, user_id=user["id"]),
                                {"count": count, "open_count": max(0, min(body.open_count, count)),
                                 "difficulty": body.difficulty, "notes": body.notes}, ai_model(conn, user["institution_id"], user["id"]))
    log_ai(conn, user, user["institution_id"], "questoes", meta)
    ids = []
    for q in content["questions"]:
        ids.append(conn.execute(
            "INSERT INTO questions (subject_id, topic_id, kind, statement, options, answer, expected, explanation, difficulty, reviewed, created_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,?)",
            (d["subject_id"], topic_id or d["topic_id"], q["kind"], q["statement"], jdump(q["options"]), q["answer"],
             q["expected"], q["explanation"], body.difficulty, user["id"])).lastrowid)
    return {"ids": ids, "provider": meta["provider"], "error": meta.get("error")}


# ================================================================== atividades e avaliações

class ActivityIn(BaseModel):
    subject_id: int
    class_id: int | None = None
    title: str
    kind: str = "atividade"
    instructions: str = ""
    due_date: str | None = None
    points: float = 10
    max_attempts: int = 1
    auto_publish: bool = True
    accept_late: bool = False      # aceita entrega depois do prazo (fica marcada como atrasada)
    question_ids: list[int] = []


def _check_activity(conn, user, body: ActivityIn, subject: dict) -> int:
    """Valida a atividade e devolve a turma. A turma precisa ser a da disciplina."""
    if body.kind not in ("atividade", "simulado", "prova"):
        raise HTTPException(400, "Tipo inválido")
    if not body.title.strip():
        raise HTTPException(400, "Dê um título à atividade")
    if body.points <= 0:
        raise HTTPException(400, "A pontuação precisa ser maior que zero")
    if body.due_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.due_date):
        raise HTTPException(400, "Data de entrega inválida")
    cid = body.class_id or subject["class_id"]
    if cid != subject["class_id"]:
        raise HTTPException(400, "A atividade precisa ser da turma da disciplina")
    return cid


def _set_questions(conn, user, aid: int, qids: list[int]):
    conn.execute("DELETE FROM activity_questions WHERE activity_id=?", (aid,))
    for pos, qid in enumerate(qids):
        own_question(conn, user, qid)
        conn.execute("INSERT OR IGNORE INTO activity_questions (activity_id, question_id, position) VALUES (?,?,?)", (aid, qid, pos))


@router.get("/activities")
def activities(subject_id: int | None = None, user=Depends(professor_only), conn=Depends(get_db)):
    ph, sids = _ph([subject_id] if subject_id else teacher_subject_ids(conn, user))
    return rows(conn.execute(
        f"""SELECT a.*, s.name AS subject_name, c.name AS class_name,
              (SELECT COUNT(*) FROM activity_questions aq WHERE aq.activity_id=a.id) AS questions,
              (SELECT COUNT(*) FROM submissions x WHERE x.activity_id=a.id) AS delivered,
              (SELECT COUNT(*) FROM submissions x WHERE x.activity_id=a.id AND x.status='entregue') AS to_grade,
              (SELECT COUNT(*) FROM submissions x WHERE x.activity_id=a.id AND x.status='corrigida' AND x.published=0) AS unpublished,
              (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=a.class_id) AS students,
              (SELECT ROUND(AVG(x.score*10.0/a.points),1) FROM submissions x WHERE x.activity_id=a.id AND x.status='corrigida') AS avg
            FROM activities a JOIN subjects s ON s.id=a.subject_id JOIN classes c ON c.id=a.class_id
            WHERE a.subject_id IN ({ph}) ORDER BY a.id DESC""", sids))


@router.post("/activities")
def create_activity(body: ActivityIn, user=Depends(professor_only), conn=Depends(get_db)):
    s = own_subject(conn, user, body.subject_id)
    cid = _check_activity(conn, user, body, s)
    aid = conn.execute(
        "INSERT INTO activities (subject_id, class_id, title, kind, instructions, due_date, points, max_attempts, auto_publish, accept_late, created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (body.subject_id, cid, body.title.strip(), body.kind, body.instructions, body.due_date or None, body.points,
         max(1, min(body.max_attempts, 10)), int(body.auto_publish), int(body.accept_late), user["id"])).lastrowid
    _set_questions(conn, user, aid, body.question_ids)
    return {"id": aid}


@router.get("/activities/{aid}")
def activity_detail(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    a = own_activity(conn, user, aid)
    a["questions"] = activity_questions(conn, aid)
    a["class_name"] = conn.execute("SELECT name FROM classes WHERE id=?", (a["class_id"],)).fetchone()[0]
    a["subject_name"] = conn.execute("SELECT name FROM subjects WHERE id=?", (a["subject_id"],)).fetchone()[0]
    return a


@router.put("/activities/{aid}")
def update_activity(aid: int, body: ActivityIn, user=Depends(professor_only), conn=Depends(get_db)):
    own_activity(conn, user, aid)
    s = own_subject(conn, user, body.subject_id)
    cid = _check_activity(conn, user, body, s)
    has_subs = conn.execute("SELECT COUNT(*) FROM submissions WHERE activity_id=?", (aid,)).fetchone()[0]
    conn.execute(
        "UPDATE activities SET subject_id=?, class_id=?, title=?, kind=?, instructions=?, due_date=?, points=?, max_attempts=?,"
        " auto_publish=?, accept_late=? WHERE id=?",
        (body.subject_id, cid, body.title.strip(), body.kind, body.instructions, body.due_date or None,
         body.points, max(1, min(body.max_attempts, 10)), int(body.auto_publish), int(body.accept_late), aid))
    if not has_subs:
        _set_questions(conn, user, aid, body.question_ids)
    return {"ok": True, "questions_locked": bool(has_subs)}


@router.post("/activities/{aid}/publish")
def publish_activity(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    a = own_activity(conn, user, aid)
    if not conn.execute("SELECT COUNT(*) FROM activity_questions WHERE activity_id=?", (aid,)).fetchone()[0]:
        raise HTTPException(400, "Adicione questões antes de publicar")
    conn.execute("UPDATE activities SET status='publicada' WHERE id=?", (aid,))
    if institution_settings(conn, user["institution_id"]).get("notify_new_activity", True):
        for s in rows(conn.execute("SELECT user_id FROM class_students WHERE class_id=?", (a["class_id"],))):
            notify(conn, s["user_id"], f"Nova atividade: {a['title']}", "Atividades", f"#/a/atividade/{aid}")
    audit(conn, user, "atividade.publicada", a["title"])
    return {"ok": True}


@router.delete("/activities/{aid}")
def delete_activity(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    """Exclui a atividade com as entregas e notas. As questões continuam no banco."""
    a = own_activity(conn, user, aid)
    n = conn.execute("SELECT COUNT(*) FROM submissions WHERE activity_id=?", (aid,)).fetchone()[0]
    conn.execute("DELETE FROM submissions WHERE activity_id=?", (aid,))
    conn.execute("DELETE FROM activity_questions WHERE activity_id=?", (aid,))
    conn.execute("DELETE FROM activities WHERE id=?", (aid,))
    audit(conn, user, "atividade.excluida", f"{a['title']} ({n} entrega(s))")
    return {"ok": True}


@router.post("/activities/{aid}/close")
def close_activity(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    own_activity(conn, user, aid)
    conn.execute("UPDATE activities SET status='encerrada' WHERE id=?", (aid,))
    return {"ok": True}


class DuplicateIn(BaseModel):
    class_id: int


@router.post("/activities/{aid}/duplicate")
def duplicate_activity(aid: int, body: DuplicateIn, user=Depends(professor_only), conn=Depends(get_db)):
    a = own_activity(conn, user, aid)
    if body.class_id not in _teacher_class_ids(conn, user):
        raise HTTPException(400, "Turma inválida")
    subj = one(conn.execute("SELECT id FROM subjects WHERE class_id=? AND teacher_id=? ORDER BY (name = (SELECT name FROM subjects WHERE id=?)) DESC LIMIT 1",
                            (body.class_id, user["id"], a["subject_id"])))
    nid = conn.execute(
        "INSERT INTO activities (subject_id, class_id, title, kind, instructions, due_date, points, max_attempts, auto_publish, created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (subj["id"] if subj else a["subject_id"], body.class_id, a["title"], a["kind"], a["instructions"], a["due_date"],
         a["points"], a["max_attempts"], a["auto_publish"], user["id"])).lastrowid
    conn.execute("INSERT INTO activity_questions (activity_id, question_id, position) SELECT ?, question_id, position FROM activity_questions WHERE activity_id=?", (nid, aid))
    return {"id": nid}


@router.get("/activities/{aid}/submissions")
def activity_submissions(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    a = own_activity(conn, user, aid)
    students = rows(conn.execute(
        """SELECT u.id AS student_id, u.name, s.id, s.score, s.status, s.published, s.attempts, s.submitted_at, s.late
           FROM class_students cs JOIN users u ON u.id=cs.user_id
           LEFT JOIN submissions s ON s.activity_id=? AND s.student_id=u.id
           WHERE cs.class_id=? ORDER BY u.name""", (aid, a["class_id"])))
    results = scoring.question_results(conn, "a.id=?", (aid,))
    return {"activity": a, "students": students, "questions": scoring.by_question(results)}


@router.get("/submissions/{sub_id}")
def submission_detail(sub_id: int, user=Depends(professor_only), conn=Depends(get_db)):
    s = one(conn.execute("SELECT s.*, u.name AS student_name FROM submissions s JOIN users u ON u.id=s.student_id WHERE s.id=?", (sub_id,)))
    if not s:
        raise HTTPException(404, "Entrega não encontrada")
    a = own_activity(conn, user, s["activity_id"])
    s["answers"], s["grading"] = jload(s["answers"], {}), jload(s["grading"], {})
    return {"submission": s, "activity": a, "questions": activity_questions(conn, a["id"])}


@router.post("/submissions/{sub_id}/ai-grade")
def submission_ai_grade(sub_id: int, user=Depends(professor_only), conn=Depends(get_db)):
    """Sugestões da IA para as discursivas. Não publica nada: o professor valida."""
    s = one(conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)))
    if not s:
        raise HTTPException(404, "Entrega não encontrada")
    a = own_activity(conn, user, s["activity_id"])
    answers, grading = jload(s["answers"], {}), jload(s["grading"], {})
    model = ai_model(conn, user["institution_id"], user["id"])
    for q in activity_questions(conn, a["id"]):
        if q["kind"] != "discursiva":
            continue
        res, meta = ia.grade_open(q["statement"], q["expected"] or "", str(answers.get(str(q["id"])) or ""), model)
        log_ai(conn, user, user["institution_id"], "correcao", meta)
        g = grading.setdefault(str(q["id"]), {"score": None, "feedback": ""})
        g["ai_score"], g["ai_feedback"] = res["score"], res["feedback"]
    conn.execute("UPDATE submissions SET grading=? WHERE id=?", (jdump(grading), sub_id))
    return {"grading": grading}


class GradeIn(BaseModel):
    grading: dict
    feedback: str = ""
    publish: bool = True


@router.put("/submissions/{sub_id}/grade")
def grade_submission(sub_id: int, body: GradeIn, user=Depends(professor_only), conn=Depends(get_db)):
    s = one(conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)))
    if not s:
        raise HTTPException(404, "Entrega não encontrada")
    a = own_activity(conn, user, s["activity_id"])
    qs = activity_questions(conn, a["id"])
    grading = jload(s["grading"], {})
    for q in qs:
        k = str(q["id"])
        g = body.grading.get(k)
        if g is None:
            continue
        cur = grading.setdefault(k, {})
        if not isinstance(g, dict):
            raise HTTPException(400, "Correção em formato inválido")
        if g.get("score") is not None:
            try:
                cur["score"] = max(0.0, min(1.0, float(g["score"])))
            except (TypeError, ValueError):
                raise HTTPException(400, "Nota inválida")
        cur["feedback"] = str(g.get("feedback", cur.get("feedback", "")))[:2000]
    score = scoring.final_score(grading, a["points"], len(qs))
    if score is None:
        raise HTTPException(400, "Atribua nota a todas as questões discursivas")
    conn.execute("UPDATE submissions SET grading=?, score=?, status='corrigida', feedback=?, published=? WHERE id=?",
                 (jdump(grading), score, body.feedback, int(body.publish), sub_id))
    if body.publish and institution_settings(conn, user["institution_id"]).get("notify_grades", True):
        notify(conn, s["student_id"], f"Nota publicada: {a['title']}", "Atividades", f"#/a/resultado/{a['id']}")
    audit(conn, user, "correcao.salva", f"{a['title']} · entrega {sub_id}")
    return {"score": score}


@router.post("/activities/{aid}/publish-grades")
def publish_grades(aid: int, user=Depends(professor_only), conn=Depends(get_db)):
    a = own_activity(conn, user, aid)
    subs = rows(conn.execute("SELECT id, student_id FROM submissions WHERE activity_id=? AND status='corrigida' AND published=0", (aid,)))
    avisar = institution_settings(conn, user["institution_id"]).get("notify_grades", True)
    for s in subs:
        conn.execute("UPDATE submissions SET published=1 WHERE id=?", (s["id"],))
        if avisar:
            notify(conn, s["student_id"], f"Nota publicada: {a['title']}", "Atividades", f"#/a/resultado/{aid}")
    return {"published": len(subs)}


# ================================================================== desempenho

def _performance(conn, user, subject_id, class_id):
    sids = [subject_id] if subject_id else teacher_subject_ids(conn, user)
    if subject_id:
        own_subject(conn, user, subject_id)
    ph, sids = _ph(sids)
    where, params = f"a.subject_id IN ({ph})", list(sids)
    if class_id:
        where += " AND a.class_id=?"
        params.append(class_id)
    results = scoring.question_results(conn, where, tuple(params))
    acts = rows(conn.execute(
        f"""SELECT a.id, a.title, a.due_date, a.points, c.name AS class_name,
              (SELECT COUNT(*) FROM submissions s WHERE s.activity_id=a.id) AS delivered,
              (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id=a.class_id) AS students,
              (SELECT ROUND(AVG(s.score*10.0/a.points),1) FROM submissions s WHERE s.activity_id=a.id AND s.status='corrigida') AS avg
            FROM activities a JOIN classes c ON c.id=a.class_id WHERE {where} AND a.status<>'rascunho' ORDER BY a.created_at""", params))
    by_class = rows(conn.execute(
        f"""SELECT c.name, ROUND(AVG(s.score*10.0/a.points),1) AS avg, COUNT(s.id) AS n
            FROM activities a JOIN classes c ON c.id=a.class_id JOIN submissions s ON s.activity_id=a.id AND s.status='corrigida'
            WHERE {where} GROUP BY c.id ORDER BY c.name""", params))
    delivered = sum(x["delivered"] for x in acts)
    expected = sum(x["students"] for x in acts)
    avgs = [x["avg"] for x in acts if x["avg"] is not None]
    students = rows(conn.execute(
        f"""SELECT u.id, u.name, c.name AS class_name, ROUND(AVG(s.score*10.0/a.points),1) AS avg, COUNT(s.id) AS n
            FROM submissions s JOIN activities a ON a.id=s.activity_id JOIN users u ON u.id=s.student_id JOIN classes c ON c.id=a.class_id
            WHERE {where} AND s.status='corrigida' GROUP BY u.id ORDER BY avg""", params))
    topics = scoring.by_topic(conn, results)
    return {
        "kpis": {"avg": round(sum(avgs) / len(avgs), 1) if avgs else None,
                 "completion": round(100 * delivered / expected) if expected else None,
                 "activities": len(acts), "answers": len(results),
                 "at_risk": sum(1 for s in students if s["avg"] is not None and s["avg"] < 6)},
        "evolution": [{"label": x["title"], "avg": x["avg"]} for x in acts if x["avg"] is not None][-10:],
        "activities": acts, "by_class": by_class, "topics": topics,
        "questions": scoring.by_question(results)[:8], "students": students,
        "review": [t for t in topics if t["pct"] < 60],
    }


@router.get("/performance")
def performance(subject_id: int | None = None, class_id: int | None = None, user=Depends(professor_only), conn=Depends(get_db)):
    return _performance(conn, user, subject_id, class_id)


@router.get("/performance/export.csv")
def performance_csv(subject_id: int | None = None, class_id: int | None = None, user=Depends(professor_only), conn=Depends(get_db)):
    p = _performance(conn, user, subject_id, class_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Aluno", "Turma", "Média (0-10)", "Atividades corrigidas"])
    for s in p["students"]:
        w.writerow([s["name"], s["class_name"], s["avg"], s["n"]])
    w.writerow([])
    w.writerow(["Assunto", "Disciplina", "Acerto (%)", "Respostas"])
    for t in p["topics"]:
        w.writerow([t["topic"], t["subject"], t["pct"], t["total"]])
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=desempenho.csv"})
