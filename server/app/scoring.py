"""Correção automática e estatísticas de desempenho."""
from .db import jdump, jload, rows
from .util import activity_questions


def auto_grade(questions: list[dict], answers: dict, previous: dict | None = None) -> tuple[dict, bool]:
    """Corrige as objetivas; discursivas ficam pendentes (score None) até o professor validar.

    Devolve (grading, precisa_de_revisao).
    """
    grading = {}
    pending = False
    prev = previous or {}
    for q in questions:
        key = str(q["id"])
        given = answers.get(key)
        if q["kind"] == "discursiva":
            old = prev.get(key) or {}
            grading[key] = {"score": None, "feedback": "", "ai_score": old.get("ai_score"), "ai_feedback": old.get("ai_feedback")}
            pending = True
        else:
            try:
                ok = given is not None and int(given) == int(q["answer"])
            except (TypeError, ValueError):
                ok = False
            grading[key] = {"score": 1.0 if ok else 0.0, "feedback": q.get("explanation") or ""}
    return grading, pending


def final_score(grading: dict, points: float, n_questions: int) -> float | None:
    if not n_questions:
        return 0.0
    scores = [g.get("score") for g in grading.values()]
    if any(s is None for s in scores):
        return None
    return round(points * sum(scores) / n_questions, 2)


def submit(conn, activity: dict, student_id: int, answers: dict, late: bool = False) -> dict:
    qs = activity_questions(conn, activity["id"])
    grading, pending = auto_grade(qs, answers)
    score = None if pending else final_score(grading, activity["points"], len(qs))
    status = "entregue" if pending else "corrigida"
    published = 1 if (not pending and activity["auto_publish"]) else 0
    conn.execute(
        "INSERT INTO submissions (activity_id, student_id, answers, grading, score, attempts, status, published, late, submitted_at)"
        " VALUES (?,?,?,?,?,1,?,?,?,CURRENT_TIMESTAMP)"
        " ON CONFLICT(activity_id, student_id) DO UPDATE SET answers=excluded.answers, grading=excluded.grading,"
        " score=excluded.score, attempts=submissions.attempts+1, status=excluded.status, published=excluded.published,"
        " late=excluded.late, submitted_at=CURRENT_TIMESTAMP",
        (activity["id"], student_id, jdump(answers), jdump(grading), score, status, published, int(late)))
    return {"status": status, "score": score, "published": published, "pending_review": pending, "late": bool(late)}


def question_results(conn, where: str, params: tuple) -> list[dict]:
    """Uma linha por (aluno, questão) respondida em submissões corrigidas. `where` filtra activities a / submissions s."""
    subs = rows(conn.execute(
        "SELECT s.student_id, s.answers, s.grading, s.activity_id, a.subject_id, a.class_id, s.submitted_at"
        " FROM submissions s JOIN activities a ON a.id=s.activity_id"
        f" WHERE s.status='corrigida' AND {where}", params))
    if not subs:
        return []
    cache: dict[int, list[dict]] = {}
    out = []
    for s in subs:
        if s["activity_id"] not in cache:
            cache[s["activity_id"]] = activity_questions(conn, s["activity_id"])
        grading = jload(s["grading"], {})
        for q in cache[s["activity_id"]]:
            g = grading.get(str(q["id"])) or {}
            sc = g.get("score")
            if sc is None:
                continue
            out.append({"student_id": s["student_id"], "question_id": q["id"], "statement": q["statement"],
                        "topic_id": q["topic_id"], "subject_id": s["subject_id"], "class_id": s["class_id"],
                        "score": float(sc), "submitted_at": s["submitted_at"]})
    return out


def topic_names(conn, ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    return {r["id"]: r["name"] for r in rows(conn.execute(f"SELECT id, name FROM topics WHERE id IN ({ph})", ids))}


def by_topic(conn, results: list[dict]) -> list[dict]:
    names = topic_names(conn, [r["topic_id"] for r in results])
    subj = {r["id"]: r["name"] for r in rows(conn.execute("SELECT id, name FROM subjects"))}
    agg: dict = {}
    for r in results:
        k = (r["subject_id"], r["topic_id"])
        a = agg.setdefault(k, {"subject": subj.get(r["subject_id"], ""), "topic": names.get(r["topic_id"], "Geral"),
                               "topic_id": r["topic_id"], "subject_id": r["subject_id"], "total": 0, "sum": 0.0, "errors": 0})
        a["total"] += 1
        a["sum"] += r["score"]
        a["errors"] += 1 if r["score"] < 0.5 else 0
    out = []
    for a in agg.values():
        a["pct"] = round(100 * a.pop("sum") / a["total"])
        out.append(a)
    return sorted(out, key=lambda x: x["pct"])


def by_question(results: list[dict]) -> list[dict]:
    agg: dict = {}
    for r in results:
        a = agg.setdefault(r["question_id"], {"question_id": r["question_id"], "statement": r["statement"], "total": 0, "errors": 0})
        a["total"] += 1
        a["errors"] += 1 if r["score"] < 0.5 else 0
    out = list(agg.values())
    for a in out:
        a["error_rate"] = round(100 * a["errors"] / a["total"])
    return sorted(out, key=lambda x: -x["error_rate"])
