"""Área do aluno: estudar materiais publicados, flashcards com revisão espaçada, atividades e progresso.

Regra central: o aluno nunca recebe gabaritos antes da hora. A conferência de exercícios
de prática é feita no servidor, uma questão por vez.
"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import ia, jobs, scoring
from ..auth import aluno_only
from ..db import CommitRoute, get_db, jload, one, rows
from ..util import (activity_questions, ai_model, ai_quota_check, answers_released, log_ai, past_due, student_activity,
                    student_class_ids, student_material)

router = APIRouter(prefix="/api/aluno", route_class=CommitRoute)

INTERVALS = [0, 1, 3, 7, 14, 30]  # dias por caixa (Leitner)


def _ph(ids):
    ids = list(ids) or [0]
    return ",".join("?" * len(ids)), ids


def _published(conn, user, extra: str = "", params: tuple = ()) -> list[dict]:
    ph, cids = _ph(student_class_ids(conn, user))
    return rows(conn.execute(
        f"""SELECT DISTINCT m.id, m.title, m.type, m.variant, m.subject_id, m.topic_id, m.updated_at,
              s.name AS subject_name, s.color AS subject_color, t.name AS topic_name, COALESCE(p.pct, 0) AS pct
            FROM materials m JOIN material_classes mc ON mc.material_id=m.id JOIN subjects s ON s.id=m.subject_id
            LEFT JOIN topics t ON t.id=m.topic_id LEFT JOIN material_progress p ON p.material_id=m.id AND p.user_id=?
            WHERE mc.class_id IN ({ph}) AND m.status='publicado' {extra} ORDER BY m.updated_at DESC""",
        (user["id"], *cids, *params)))


def _documents(conn, user, extra: str = "", params: tuple = ()) -> list[dict]:
    """Arquivos da biblioteca do professor que o aluno pode ver e baixar: compartilhados, não
    arquivados e de uma matéria da turma do aluno (ou origem de um material publicado para ela)."""
    ph, cids = _ph(student_class_ids(conn, user))
    return rows(conn.execute(
        f"""SELECT d.id, d.title, d.filename, d.size, d.pages, d.subject_id, d.topic_id, d.created_at,
              s.name AS subject_name, s.color AS subject_color, t.name AS topic_name
            FROM documents d JOIN subjects s ON s.id=d.subject_id LEFT JOIN topics t ON t.id=d.topic_id
            WHERE d.shared=1 AND d.archived=0 AND s.active=1 AND d.institution_id=?
              AND (s.class_id IN ({ph}) OR d.id IN (
                   SELECT m.document_id FROM materials m JOIN material_classes mc ON mc.material_id=m.id
                   WHERE m.status='publicado' AND mc.class_id IN ({ph})))
              {extra}
            ORDER BY d.id DESC""", (user["institution_id"], *cids, *cids, *params)))


def _strip(m: dict) -> dict:
    """Remove gabaritos de listas de prática."""
    if m["type"] == "exercicios":
        m["content"] = {"questions": [{"kind": q.get("kind", "objetiva"), "statement": q["statement"], "options": q.get("options", [])}
                                      for q in m["content"].get("questions", [])]}
    m["content"].pop("_aviso", None)
    return m


def _my_activities(conn, user) -> list[dict]:
    ph, cids = _ph(student_class_ids(conn, user))
    acts = rows(conn.execute(
        f"""SELECT a.id, a.title, a.kind, a.due_date, a.points, a.max_attempts, a.status, a.accept_late, a.subject_id,
              s.name AS subject_name, s.color AS subject_color, x.status AS sub_status, x.score, x.published, x.attempts,
              x.submitted_at, x.late,
              (SELECT COUNT(*) FROM activity_questions aq WHERE aq.activity_id=a.id) AS questions
            FROM activities a JOIN subjects s ON s.id=a.subject_id
            LEFT JOIN submissions x ON x.activity_id=a.id AND x.student_id=?
            WHERE a.class_id IN ({ph}) AND a.status IN ('publicada','encerrada') ORDER BY a.due_date""", (user["id"], *cids)))
    for a in acts:
        if not a["published"]:
            a["score"] = None
        a["past_due"] = past_due(a)
        # ainda dá para entregar? (atividade aberta e dentro do prazo, ou aceitando atraso)
        a["open"] = a["status"] == "publicada" and (not a["past_due"] or bool(a["accept_late"])) \
            and (a["attempts"] or 0) < a["max_attempts"]
    return acts


# ================================================================== início

@router.get("/home")
def home(user=Depends(aluno_only), conn=Depends(get_db)):
    mats = _published(conn, user)
    acts = _my_activities(conn, user)
    pending = [a for a in acts if not a["sub_status"] and a["open"]]
    cont = next((m for m in sorted(mats, key=lambda m: -m["pct"]) if 0 < m["pct"] < 100), None) or (mats[0] if mats else None)
    ph, cids = _ph(student_class_ids(conn, user))
    live = rows(conn.execute(f"SELECT id, title, code, status FROM games WHERE class_id IN ({ph}) AND status IN ('sala','pergunta','discussao','revelacao')", cids))
    results = scoring.question_results(conn, "s.student_id=? AND s.published=1", (user["id"],))
    weak = [t for t in scoring.by_topic(conn, results) if t["pct"] < 70][:2]
    for w in weak:
        w["material"] = next((m for m in mats if m["topic_id"] == w["topic_id"] and m["type"] in ("flashcards", "resumo", "roteiro", "glossario")), None) \
            or next((m for m in mats if m["subject_id"] == w["subject_id"]), None)
    due = sum(d["due"] for d in _due_decks(conn, user))
    done = sum(1 for m in mats if m["pct"] >= 100)
    return {
        "progress": round(sum(m["pct"] for m in mats) / len(mats)) if mats else 0,
        "materials_done": done, "materials_total": len(mats),
        "continue": cont, "activities": pending[:4], "live_games": live, "recommendations": weak,
        "flashcards_due": due, "recent": mats[:4],
    }


# ================================================================== matérias e materiais

@router.get("/subjects")
def subjects(user=Depends(aluno_only), conn=Depends(get_db)):
    ph, cids = _ph(student_class_ids(conn, user))
    subs = rows(conn.execute(
        f"""SELECT s.id, s.name, s.description, s.color, u.name AS teacher, c.name AS class_name
            FROM subjects s JOIN users u ON u.id=s.teacher_id JOIN classes c ON c.id=s.class_id
            WHERE s.class_id IN ({ph}) AND s.active=1 ORDER BY s.name""", cids))
    mats = _published(conn, user)
    acts = _my_activities(conn, user)
    for s in subs:
        mine = [m for m in mats if m["subject_id"] == s["id"]]
        s["materials"] = len(mine)
        s["progress"] = round(sum(m["pct"] for m in mine) / len(mine)) if mine else 0
        s["pending"] = sum(1 for a in acts if a["subject_id"] == s["id"] and not a["sub_status"] and a["open"])
    return subs


@router.get("/subjects/{sid}")
def subject(sid: int, user=Depends(aluno_only), conn=Depends(get_db)):
    ph, cids = _ph(student_class_ids(conn, user))
    s = one(conn.execute(f"SELECT s.*, u.name AS teacher FROM subjects s JOIN users u ON u.id=s.teacher_id WHERE s.id=? AND s.class_id IN ({ph})", (sid, *cids)))
    if not s:
        raise HTTPException(404, "Matéria não encontrada")
    mats = _published(conn, user, "AND m.subject_id=?", (sid,))
    topics = rows(conn.execute("SELECT id, name FROM topics WHERE subject_id=? ORDER BY position, id", (sid,)))
    for t in topics:
        t["materials"] = [m for m in mats if m["topic_id"] == t["id"]]
    topics = [t for t in topics if t["materials"]]
    loose = [m for m in mats if not m["topic_id"] or m["topic_id"] not in {t["id"] for t in topics}]
    if loose:
        topics.append({"id": None, "name": "Outros materiais", "materials": loose})
    acts = [a for a in _my_activities(conn, user) if a["subject_id"] == s["id"]]
    return {"subject": s, "topics": topics, "activities": acts,
            "documents": _documents(conn, user, "AND d.subject_id=?", (sid,))}


# ================================================================== arquivos do professor

@router.get("/documentos")
def documentos(subject_id: int | None = None, user=Depends(aluno_only), conn=Depends(get_db)):
    if subject_id:
        return _documents(conn, user, "AND d.subject_id=?", (subject_id,))
    return _documents(conn, user)


@router.get("/documentos/{did}/arquivo")
def baixar_documento(did: int, user=Depends(aluno_only), conn=Depends(get_db)):
    """Baixa o arquivo original que o professor enviou (mesmo formato e nome)."""
    if not _documents(conn, user, "AND d.id=?", (did,)):
        raise HTTPException(404, "Arquivo não disponível")
    d = one(conn.execute("SELECT id, title, filename, text FROM documents WHERE id=?", (did,)))
    return jobs.document_file(d)


@router.get("/materials")
def materials(type: str | None = None, subject_id: int | None = None, user=Depends(aluno_only), conn=Depends(get_db)):
    extra, params = "", []
    if type:
        extra += " AND m.type=?"
        params.append(type)
    if subject_id:
        extra += " AND m.subject_id=?"
        params.append(subject_id)
    return _published(conn, user, extra, tuple(params))


@router.get("/materials/{mid}")
def material(mid: int, user=Depends(aluno_only), conn=Depends(get_db)):
    m = _strip(student_material(conn, user, mid))
    p = one(conn.execute("SELECT pct FROM material_progress WHERE user_id=? AND material_id=?", (user["id"], mid)))
    m["pct"] = p["pct"] if p else 0
    m["topic_name"] = conn.execute("SELECT name FROM topics WHERE id=?", (m["topic_id"],)).fetchone()[0] if m["topic_id"] else None
    m["siblings"] = [x for x in _published(conn, user, "AND m.subject_id=?", (m["subject_id"],)) if x["id"] != mid][:6]
    src = _documents(conn, user, "AND d.id=?", (m["document_id"],)) if m.get("document_id") else []
    m["document"] = src[0] if src else None     # arquivo original de onde o material foi gerado
    m.pop("document_id", None)
    if m["type"] == "flashcards":
        boxes = {r["card"]: r for r in rows(conn.execute("SELECT card, box, due_at FROM flashcard_reviews WHERE user_id=? AND material_id=?", (user["id"], mid)))}
        m["reviews"] = boxes
    return m


class ProgressIn(BaseModel):
    pct: int


@router.post("/materials/{mid}/progress")
def progress(mid: int, body: ProgressIn, user=Depends(aluno_only), conn=Depends(get_db)):
    student_material(conn, user, mid)
    pct = max(0, min(100, body.pct))
    conn.execute(
        "INSERT INTO material_progress (user_id, material_id, pct) VALUES (?,?,?)"
        " ON CONFLICT(user_id, material_id) DO UPDATE SET pct=MAX(pct, excluded.pct), updated_at=CURRENT_TIMESTAMP",
        (user["id"], mid, pct))
    return {"ok": True}


class CheckIn(BaseModel):
    index: int
    answer: int | str | None = None


@router.post("/materials/{mid}/check")
def check(mid: int, body: CheckIn, user=Depends(aluno_only), conn=Depends(get_db)):
    """Conferência de uma questão de prática (feedback imediato, uma por vez)."""
    m = student_material(conn, user, mid)
    qs = m["content"].get("questions", [])
    if m["type"] != "exercicios" or not 0 <= body.index < len(qs):
        raise HTTPException(400, "Questão inválida")
    q = qs[body.index]
    if _in_open_activity(conn, user, mid, q["statement"]):
        return {"correct": None, "locked": True,
                "explanation": "Esta questão faz parte de uma atividade em andamento. A conferência fica disponível depois que ela terminar."}
    if q.get("kind") == "discursiva":
        return {"correct": None, "expected": q.get("expected"), "explanation": q.get("explanation")}
    try:
        ok = int(body.answer) == int(q["answer"])
    except (TypeError, ValueError):
        ok = False
    return {"correct": ok, "answer": q["answer"], "explanation": q.get("explanation")}


def _in_open_activity(conn, user, mid: int, statement: str) -> bool:
    """A mesma questão (enviada ao banco a partir deste material) está numa atividade que o aluno ainda pode fazer?"""
    ph, cids = _ph(student_class_ids(conn, user))
    acts = rows(conn.execute(
        f"""SELECT DISTINCT a.* FROM activities a JOIN activity_questions aq ON aq.activity_id=a.id
            JOIN questions q ON q.id=aq.question_id
            WHERE a.class_id IN ({ph}) AND a.status='publicada' AND (q.material_id=? OR q.statement=?)""",
        (*cids, mid, statement)))
    for a in acts:
        sub = one(conn.execute("SELECT attempts FROM submissions WHERE activity_id=? AND student_id=?", (a["id"], user["id"])))
        if not answers_released(a, sub["attempts"] if sub else 0):
            return True
    return False


class AskIn(BaseModel):
    question: str
    history: list[dict] = []


def _material_context(conn, m: dict) -> str:
    """O que o tutor pode consultar: o conteúdo do material (sem gabaritos) e o documento de origem."""
    c = m["content"]
    if m["type"] in ("resumo", "roteiro"):
        own = "\n\n".join(f"{s.get('title', '')}\n{s.get('body', '')}" for s in c.get("sections", []))
    elif m["type"] == "mapa":
        own = c.get("center", "") + "\n" + "\n".join(f"{b['label']}: {'; '.join(b.get('children', []))}" for b in c.get("branches", []))
    elif m["type"] == "flashcards":
        own = "\n".join(f"{x['front']} — {x['back']}" for x in c.get("cards", []))
    elif m["type"] == "glossario":
        own = "\n".join(f"{t['term']}: {t['definition']} {t.get('example', '')}" for t in c.get("terms", []))
    else:
        own = "\n".join(q["statement"] for q in c.get("questions", []))
    doc = one(conn.execute("SELECT text FROM documents WHERE id=?", (m["document_id"],))) if m["document_id"] else None
    source = re.sub(r"^\[Página \d+\]$", "", doc["text"] or "", flags=re.M) if doc else ""
    return f"{own}\n\n{source}".strip()


@router.post("/materials/{mid}/ask")
def ask(mid: int, body: AskIn, user=Depends(aluno_only), conn=Depends(get_db)):
    """Tutor: o aluno tira dúvidas sobre o material; a IA responde só com base nele."""
    question = body.question.strip()[:600]
    if len(question) < 3:
        raise HTTPException(400, "Escreva sua dúvida")
    m = student_material(conn, user, mid)
    ai_quota_check(conn, user["institution_id"])
    res, meta = ia.ask(m["title"], _material_context(conn, m), question, body.history,
                       protect_answers=m["type"] == "exercicios", model=ai_model(conn, user["institution_id"], user["id"]))
    log_ai(conn, user, user["institution_id"], "tutor", meta)
    return {**res, "provider": meta["provider"]}


# ================================================================== flashcards (revisão espaçada)

@router.get("/flashcards/due")
def flashcards_due(user=Depends(aluno_only), conn=Depends(get_db)):
    return _due_decks(conn, user)


def _due_decks(conn, user) -> list[dict]:
    """Baralhos publicados com os cartões a revisar hoje (nunca vistos contam como pendentes)."""
    now = datetime.now().isoformat()
    decks = _published(conn, user, "AND m.type='flashcards'")
    out = []
    for d in decks:
        m = student_material(conn, user, d["id"])
        cards = m["content"].get("cards", [])
        revs = {r["card"]: r for r in rows(conn.execute("SELECT * FROM flashcard_reviews WHERE user_id=? AND material_id=?", (user["id"], d["id"])))}
        due = [i for i in range(len(cards)) if i not in revs or (revs[i]["due_at"] or "") <= now]
        mastered = sum(1 for i, r in revs.items() if r["box"] >= 3 and i < len(cards))
        d.update({"total": len(cards), "due": len(due), "mastered": mastered,
                  "cards": [{"index": i, **cards[i], "box": revs.get(i, {}).get("box", 0)} for i in due]})
        out.append(d)
    return out


class ReviewIn(BaseModel):
    material_id: int
    card: int
    rating: str   # errei | dificil | facil


@router.post("/flashcards/review")
def flashcards_review(body: ReviewIn, user=Depends(aluno_only), conn=Depends(get_db)):
    m = student_material(conn, user, body.material_id)
    total = len(m["content"].get("cards", []))
    if m["type"] != "flashcards" or not 0 <= body.card < total:
        raise HTTPException(400, "Cartão inválido")
    if body.rating not in ("errei", "dificil", "facil"):
        raise HTTPException(400, "Avaliação inválida")
    r = one(conn.execute("SELECT box FROM flashcard_reviews WHERE user_id=? AND material_id=? AND card=?",
                         (user["id"], body.material_id, body.card)))
    box = r["box"] if r else 0
    box = 0 if body.rating == "errei" else max(1, box) if body.rating == "dificil" else min(box + 1, len(INTERVALS) - 1)
    due = datetime.now() + (timedelta(minutes=5) if box == 0 else timedelta(days=INTERVALS[box]))
    conn.execute(
        "INSERT INTO flashcard_reviews (user_id, material_id, card, box, due_at, reviewed_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)"
        " ON CONFLICT(user_id, material_id, card) DO UPDATE SET box=excluded.box, due_at=excluded.due_at, reviewed_at=CURRENT_TIMESTAMP",
        (user["id"], body.material_id, body.card, box, due.isoformat()))
    seen = conn.execute("SELECT COUNT(*) FROM flashcard_reviews WHERE user_id=? AND material_id=? AND card<?",
                        (user["id"], body.material_id, total)).fetchone()[0]
    conn.execute(
        "INSERT INTO material_progress (user_id, material_id, pct) VALUES (?,?,?)"
        " ON CONFLICT(user_id, material_id) DO UPDATE SET pct=MAX(pct, excluded.pct), updated_at=CURRENT_TIMESTAMP",
        (user["id"], body.material_id, min(100, round(100 * seen / total))))
    return {"box": box, "due_at": due.isoformat()}


# ================================================================== atividades

@router.get("/activities")
def activities(user=Depends(aluno_only), conn=Depends(get_db)):
    return _my_activities(conn, user)


@router.get("/activities/{aid}")
def activity(aid: int, user=Depends(aluno_only), conn=Depends(get_db)):
    a = student_activity(conn, user, aid)
    qs = [{"id": q["id"], "kind": q["kind"], "statement": q["statement"], "options": q["options"]} for q in activity_questions(conn, aid)]
    sub = one(conn.execute("SELECT status, score, published, attempts, submitted_at, answers, late FROM submissions WHERE activity_id=? AND student_id=?", (aid, user["id"])))
    if sub:
        sub["answers"] = jload(sub["answers"], {})
        if not sub["published"]:
            sub["score"] = None
    a["past_due"] = past_due(a)
    return {"activity": a, "questions": qs, "submission": sub}


class SubmitIn(BaseModel):
    answers: dict


@router.post("/activities/{aid}/submit")
def submit(aid: int, body: SubmitIn, user=Depends(aluno_only), conn=Depends(get_db)):
    a = student_activity(conn, user, aid)
    if a["status"] != "publicada":
        raise HTTPException(400, "Atividade encerrada")
    late = past_due(a)
    if late and not a["accept_late"]:
        raise HTTPException(400, "O prazo desta atividade terminou. Fale com o seu professor se precisar de uma nova chance.")
    conn.execute("BEGIN IMMEDIATE")  # evita duas entregas simultâneas furando o limite de tentativas
    sub = one(conn.execute("SELECT attempts FROM submissions WHERE activity_id=? AND student_id=?", (aid, user["id"])))
    if sub and sub["attempts"] >= a["max_attempts"]:
        raise HTTPException(400, "Você já usou todas as tentativas desta atividade")
    valid = {str(q["id"]): q for q in activity_questions(conn, aid)}
    answers = {}
    for k, v in body.answers.items():
        q = valid.get(str(k))
        if not q:
            continue
        answers[str(k)] = str(v)[:5000] if q["kind"] == "discursiva" else v
    res = scoring.submit(conn, a, user["id"], answers, late)
    teacher = one(conn.execute("SELECT teacher_id FROM subjects WHERE id=?", (a["subject_id"],)))
    if res["pending_review"]:
        conn.execute("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)",
                     (teacher["teacher_id"], f"{user['name']} entregou “{a['title']}”{' com atraso' if late else ''} (correção pendente)",
                      "Atividades", f"#/p/correcao/{aid}"))
    if not res["published"]:
        res["score"] = None
    return res


@router.get("/activities/{aid}/result")
def result(aid: int, user=Depends(aluno_only), conn=Depends(get_db)):
    a = student_activity(conn, user, aid)
    sub = one(conn.execute("SELECT * FROM submissions WHERE activity_id=? AND student_id=?", (aid, user["id"])))
    if not sub:
        raise HTTPException(404, "Você ainda não entregou esta atividade")
    if not sub["published"]:
        return {"activity": a, "published": False, "status": sub["status"], "submitted_at": sub["submitted_at"]}
    answers, grading = jload(sub["answers"], {}), jload(sub["grading"], {})
    qs = activity_questions(conn, aid)
    tnames = scoring.topic_names(conn, [q["topic_id"] for q in qs])
    released = answers_released(a, sub["attempts"])
    items = []
    for q in qs:
        g = grading.get(str(q["id"])) or {}
        teacher_fb = g.get("feedback") if q["kind"] == "discursiva" else None
        items.append({"id": q["id"], "kind": q["kind"], "statement": q["statement"], "options": q["options"],
                      # sem o gabarito enquanto o aluno ainda pode tentar de novo
                      "answer": q["answer"] if released else None,
                      "expected": q["expected"] if q["kind"] == "discursiva" and released else None,
                      "given": answers.get(str(q["id"])), "score": g.get("score"),
                      "feedback": (g.get("feedback") or q["explanation"]) if released else teacher_fb,
                      "topic": tnames.get(q["topic_id"], "Geral"), "topic_id": q["topic_id"]})
    wrong_topics = {i["topic_id"] for i in items if (i["score"] or 0) < 0.5}
    recs = [m for m in _published(conn, user, "AND m.subject_id=?", (a["subject_id"],)) if m["topic_id"] in wrong_topics][:3]
    return {"activity": a, "published": True, "score": sub["score"], "feedback": sub["feedback"],
            "attempts": sub["attempts"], "items": items, "recommendations": recs, "answers_released": released,
            "late": bool(sub["late"]), "can_retry": sub["attempts"] < a["max_attempts"] and a["status"] == "publicada"
            and (not past_due(a) or bool(a["accept_late"])),
            "correct": sum(1 for i in items if (i["score"] or 0) >= 0.5)}


# ================================================================== progresso e plano de revisão

@router.get("/progress")
def my_progress(user=Depends(aluno_only), conn=Depends(get_db)):
    acts = _my_activities(conn, user)
    graded = [a for a in acts if a["score"] is not None]
    results = scoring.question_results(conn, "s.student_id=? AND s.published=1", (user["id"],))
    topics = scoring.by_topic(conn, results)
    mats = _published(conn, user)
    by_subject: dict = {}
    for a in graded:
        b = by_subject.setdefault(a["subject_name"], [])
        b.append(10 * a["score"] / a["points"])
    games = rows(conn.execute(
        "SELECT g.title, p.score, g.finished_at, (SELECT COUNT(*)+1 FROM game_players p2 WHERE p2.game_id=g.id AND p2.score>p.score) AS pos,"
        " (SELECT COUNT(*) FROM game_players p3 WHERE p3.game_id=g.id) AS players"
        " FROM game_players p JOIN games g ON g.id=p.game_id WHERE p.user_id=? AND g.status='finalizado' ORDER BY g.id DESC LIMIT 5", (user["id"],)))
    return {
        "avg": round(sum(10 * a["score"] / a["points"] for a in graded) / len(graded), 1) if graded else None,
        "delivered": sum(1 for a in acts if a["sub_status"]), "total": len(acts),
        "evolution": [{"label": a["title"], "value": round(10 * a["score"] / a["points"], 1)} for a in sorted(graded, key=lambda a: a["submitted_at"] or "")][-10:],
        "subjects": [{"name": k, "avg": round(sum(v) / len(v), 1)} for k, v in by_subject.items()],
        "topics": topics, "attention": [t for t in topics if t["pct"] < 70],
        "materials_done": [m for m in mats if m["pct"] >= 100], "materials_total": len(mats),
        "history": sorted([a for a in acts if a["sub_status"]], key=lambda a: a["submitted_at"] or "", reverse=True)[:10],
        "games": games,
    }


@router.post("/study-plan")
def study_plan(user=Depends(aluno_only), conn=Depends(get_db)):
    ai_quota_check(conn, user["institution_id"])
    results = scoring.question_results(conn, "s.student_id=? AND s.published=1", (user["id"],))
    weak = [t for t in scoring.by_topic(conn, results) if t["errors"]][:4]
    mats = _published(conn, user)
    weak_subjects = {w["subject_id"] for w in weak}
    pool = [m for m in mats if m["subject_id"] in weak_subjects] or mats
    plan, meta = ia.study_plan(user["name"], weak, [{"title": m["title"], "type": ia.TYPE_LABEL.get(m["type"], m["type"]),
                                                     "subject": m["subject_name"]} for m in pool],
                               ai_model(conn, user["institution_id"], user["id"]))
    log_ai(conn, user, user["institution_id"], "plano_estudo", meta)
    plan["materials"] = pool[:6]
    plan["provider"] = meta["provider"]
    return plan
