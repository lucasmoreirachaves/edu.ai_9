"""Jogos ao vivo: o professor conduz, os alunos entram com código.

Estados: rascunho → sala → pergunta → [discussao → pergunta (2ª votação)] → revelacao → … → finalizado.
Os clientes consultam o estado a cada ~1 s; o fim da votação acontece de forma preguiçosa em
`_tick` (tempo esgotado ou todos responderam).

Para o jogo servir à aprendizagem, e não só à velocidade:
  - pontuação "confianca" (padrão): o aluno diz o quanto tem certeza; acertar com certeza vale
    mais e errar com certeza custa pontos. "velocidade" é a pontuação clássica por rapidez;
  - discussão em duplas (Peer Instruction): quando a turma se divide (30–70% de acerto), a
    resposta não é revelada; os alunos discutem com um colega e votam de novo;
  - o professor vê quem votou em cada alternativa, a resposta certa e a explicação;
  - no fim, cada aluno recebe a lista do que errou, com a resposta certa e o porquê.
"""
import random
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import ia, jobs
from ..auth import aluno_only, professor_only
from ..db import CommitRoute, audit, get_db, jdump, jload, notify, one, rows
from ..util import (ai_model, ai_quota_check, code, log_ai, own_document, own_material, own_question, own_subject,
                    student_class_ids)

router = APIRouter(prefix="/api", route_class=CommitRoute)
TEAMS = ["Equipe Azul", "Equipe Amarela", "Equipe Verde", "Equipe Vermelha"]
PEER_RANGE = (30, 70)  # % de acerto da 1ª votação em que vale a pena discutir e votar de novo
# confiança → (pontos se acertar, pontos se errar)
CONFIDENCE_POINTS = {1: (400, 0), 2: (700, -100), 3: (1000, -300)}
CONFIDENCE_LABEL = {1: "Chute", 2: "Acho que sei", 3: "Tenho certeza"}


def _game(conn, gid: int) -> dict:
    g = one(conn.execute("SELECT * FROM games WHERE id=?", (gid,)))
    if not g:
        raise HTTPException(404, "Jogo não encontrado")
    g["questions"] = jload(g["questions"], [])
    g["rounds"] = jload(g["rounds"], {}) or {}
    return g


def _own_game(conn, user, gid: int) -> dict:
    g = _game(conn, gid)
    if g["teacher_id"] != user["id"]:
        raise HTTPException(404, "Jogo não encontrado")
    return g


def _time_left(g) -> float:
    if g["paused_left"] is not None:
        return g["paused_left"]
    return max(0.0, g["time_per_question"] - (time.time() - (g["question_started_at"] or time.time())))


def _answers(conn, gid: int, q_index: int) -> list[dict]:
    return rows(conn.execute(
        "SELECT a.*, p.name FROM game_answers a JOIN game_players p ON p.id=a.player_id"
        " WHERE a.game_id=? AND a.q_index=? ORDER BY a.ms", (gid, q_index)))


def _accuracy(answers: list[dict]) -> int | None:
    return round(100 * sum(1 for a in answers if a["correct"]) / len(answers)) if answers else None


def _end_voting(conn, g: dict, discuss: bool | None = None):
    """Fecha a votação: vai para a discussão em duplas (1ª votação dividida) ou revela a resposta.
    `discuss` força a decisão (botão do professor); None decide pela regra automática."""
    status = "revelacao"
    if g["round"] == 1:
        if discuss is None:
            ans = _answers(conn, g["id"], g["current"])
            acc = _accuracy(ans)
            discuss = bool(g["peer"]) and len(ans) >= 2 and acc is not None and PEER_RANGE[0] <= acc <= PEER_RANGE[1]
        if discuss:
            status = "discussao"
    conn.execute("UPDATE games SET status=?, paused_left=NULL WHERE id=?", (status, g["id"]))
    conn.commit()
    g["status"] = status


def _tick(conn, g: dict) -> dict:
    if g["status"] == "pergunta" and g["paused_left"] is None:
        players = conn.execute("SELECT COUNT(*) FROM game_players WHERE game_id=?", (g["id"],)).fetchone()[0]
        answered = conn.execute("SELECT COUNT(*) FROM game_answers WHERE game_id=? AND q_index=?", (g["id"], g["current"])).fetchone()[0]
        if _time_left(g) <= 0 or (players and answered >= players):
            _end_voting(conn, g)
    return g


def _ranking(conn, gid: int) -> list[dict]:
    return rows(conn.execute("SELECT id, user_id, name, team, score, streak FROM game_players WHERE game_id=? ORDER BY score DESC, name", (gid,)))


def _teams(players: list[dict]) -> list[dict]:
    out = {}
    for p in players:
        t = out.setdefault(p["team"], {"team": p["team"], "name": TEAMS[p["team"] % 4], "score": 0, "members": 0})
        t["score"] += p["score"]
        t["members"] += 1
    return sorted(out.values(), key=lambda t: -t["score"])


def _counts(q: dict, answers: list[dict]) -> list[int]:
    counts = [0] * len(q["options"])
    for a in answers:
        if a["choice"] is not None and 0 <= a["choice"] < len(counts):
            counts[a["choice"]] += 1
    return counts


# ================================================================== professor

class GameIn(BaseModel):
    subject_id: int
    class_id: int | None = None
    title: str
    mode: str = "individual"
    scoring: str = "confianca"
    peer: bool = True
    time_per_question: int = 20
    show_ranking: bool = True
    question_ids: list[int] = []
    material_id: int | None = None
    document_id: int | None = None
    ai_count: int = 8


def _cards_to_questions(pairs: list[tuple[str, str]], topic_id) -> list[dict]:
    """Pares (pergunta, resposta) viram questões com distratores sorteados entre as outras respostas.
    A posição da correta também é sorteada (antes seguia A, B, C, D… e os alunos percebiam o padrão)."""
    qs = []
    rng = random.SystemRandom()
    for i, (front, back) in enumerate(pairs):
        others = list({b for j, (_, b) in enumerate(pairs) if j != i and b != back})
        if len(others) < 3:
            continue
        opts = rng.sample(others, 3) + [back]
        rng.shuffle(opts)
        qs.append({"statement": front, "options": opts, "answer": opts.index(back), "explanation": back, "topic_id": topic_id})
    return qs


def _clean_questions(raw: list) -> list[dict]:
    """Valida perguntas editadas à mão: enunciado, 2 a 6 alternativas e gabarito dentro delas."""
    out = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        statement = str(q.get("statement") or "").strip()
        options = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        try:
            answer = int(q.get("answer"))
        except (TypeError, ValueError):
            answer = -1
        if not statement or not 2 <= len(options) <= 6 or not 0 <= answer < len(options):
            raise HTTPException(400, f"Pergunta {len(out) + 1} incompleta: precisa de enunciado, 2 a 6 alternativas e a resposta certa")
        out.append({"statement": statement[:500], "options": [o[:200] for o in options], "answer": answer,
                    "explanation": str(q.get("explanation") or "")[:1000], "topic_id": q.get("topic_id")})
    if not out:
        raise HTTPException(400, "O jogo precisa de pelo menos uma pergunta")
    return out[:50]


def _snapshot(conn, user, body: GameIn) -> list[dict]:
    qs = []
    for qid in body.question_ids:
        q = own_question(conn, user, qid)
        if q["kind"] == "objetiva":
            qs.append({"statement": q["statement"], "options": jload(q["options"], []), "answer": q["answer"],
                       "explanation": q["explanation"] or "", "topic_id": q["topic_id"]})
    if body.material_id:
        m = own_material(conn, user, body.material_id)
        if m["type"] == "exercicios":
            qs += [{"statement": q["statement"], "options": q["options"], "answer": q["answer"],
                    "explanation": q.get("explanation", ""), "topic_id": m["topic_id"]}
                   for q in m["content"].get("questions", []) if q.get("kind") != "discursiva"]
        elif m["type"] == "flashcards":
            qs += _cards_to_questions([(c["front"], c["back"]) for c in m["content"].get("cards", [])], m["topic_id"])
        elif m["type"] == "glossario":
            qs += _cards_to_questions([(f"O que significa “{t['term']}”?", t["definition"])
                                       for t in m["content"].get("terms", [])], m["topic_id"])
    if body.document_id:
        d = own_document(conn, user, body.document_id)
        ai_quota_check(conn, user["institution_id"])
        content, meta = ia.generate("exercicios", d["title"], jobs.source_text(conn, d, user_id=user["id"]),
                                    {"count": max(3, min(body.ai_count, 15)),
                                     "notes": "Perguntas curtas, adequadas para um quiz ao vivo com tempo limitado. "
                                              "Prefira perguntas que testem entendimento, não decoreba."},
                                    ai_model(conn, user["institution_id"], user["id"]))
        log_ai(conn, user, user["institution_id"], "jogo", meta)
        qs += [{"statement": q["statement"], "options": q["options"], "answer": q["answer"], "explanation": q["explanation"],
                "topic_id": d["topic_id"]} for q in content["questions"] if q["kind"] == "objetiva"]
    return [q for q in qs if len(q["options"]) >= 2][:30]


def _scoring(v: str) -> str:
    return v if v in ("confianca", "velocidade") else "confianca"


@router.get("/jogos")
def list_games(user=Depends(professor_only), conn=Depends(get_db)):
    gs = rows(conn.execute(
        """SELECT g.id, g.title, g.code, g.mode, g.scoring, g.status, g.time_per_question, g.created_at, g.finished_at, g.questions,
             s.name AS subject_name, c.name AS class_name,
             (SELECT COUNT(*) FROM game_players p WHERE p.game_id=g.id) AS players
           FROM games g JOIN subjects s ON s.id=g.subject_id LEFT JOIN classes c ON c.id=g.class_id
           WHERE g.teacher_id=? ORDER BY g.id DESC""", (user["id"],)))
    for g in gs:
        g["questions"] = len(jload(g["questions"], []))
    return gs


@router.post("/jogos")
def create_game(body: GameIn, user=Depends(professor_only), conn=Depends(get_db)):
    s = own_subject(conn, user, body.subject_id)
    if body.class_id and body.class_id != s["class_id"]:
        raise HTTPException(400, "O jogo precisa ser da turma da disciplina")
    if body.mode not in ("individual", "equipes"):
        raise HTTPException(400, "Modo inválido")
    qs = _snapshot(conn, user, body)
    if not qs:
        raise HTTPException(400, "Escolha questões objetivas, um material de exercícios/flashcards/glossário ou um documento")
    gid = conn.execute(
        "INSERT INTO games (institution_id, subject_id, class_id, teacher_id, title, mode, scoring, peer, time_per_question, show_ranking, questions)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user["institution_id"], body.subject_id, body.class_id or s["class_id"], user["id"], body.title,
         body.mode, _scoring(body.scoring), int(body.peer), max(5, min(body.time_per_question, 120)),
         int(body.show_ranking), jdump(qs))).lastrowid
    return {"id": gid, "questions": len(qs)}


@router.get("/jogos/{gid}")
def game_detail(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    return _own_game(conn, user, gid)


class GameQuestionsIn(BaseModel):
    questions: list[dict]
    title: str
    time_per_question: int = 20
    mode: str = "individual"
    scoring: str = "confianca"
    peer: bool = True
    show_ranking: bool = True


@router.put("/jogos/{gid}")
def update_game(gid: int, body: GameQuestionsIn, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    if g["status"] not in ("rascunho", "finalizado"):
        raise HTTPException(400, "Só é possível editar jogos que não estão em andamento")
    if body.mode not in ("individual", "equipes"):
        raise HTTPException(400, "Modo inválido")
    conn.execute("UPDATE games SET questions=?, title=?, time_per_question=?, mode=?, scoring=?, peer=?, show_ranking=? WHERE id=?",
                 (jdump(_clean_questions(body.questions)), body.title, max(5, min(body.time_per_question, 120)), body.mode,
                  _scoring(body.scoring), int(body.peer), int(body.show_ranking), gid))
    return {"ok": True}


@router.delete("/jogos/{gid}")
def delete_game(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    _own_game(conn, user, gid)
    for t in ("game_answers", "game_players"):
        conn.execute(f"DELETE FROM {t} WHERE game_id=?", (gid,))
    conn.execute("DELETE FROM games WHERE id=?", (gid,))
    return {"ok": True}


@router.post("/jogos/{gid}/abrir")
def open_room(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    if g["status"] not in ("rascunho", "finalizado"):
        return {"code": g["code"]}
    new = code(6)
    while one(conn.execute("SELECT id FROM games WHERE code=? AND status NOT IN ('rascunho','finalizado')", (new,))):
        new = code(6)
    for t in ("game_answers", "game_players"):
        conn.execute(f"DELETE FROM {t} WHERE game_id=?", (gid,))
    conn.execute("UPDATE games SET status='sala', code=?, current=-1, round=1, rounds='{}', paused_left=NULL, finished_at=NULL WHERE id=?",
                 (new, gid))
    if g["class_id"]:
        for s in rows(conn.execute("SELECT user_id FROM class_students WHERE class_id=?", (g["class_id"],))):
            notify(conn, s["user_id"], f"Jogo ao vivo “{g['title']}” aberto! Código {new}", "Jogos", f"#/a/jogar/{new}")
    audit(conn, user, "jogo.aberto", g["title"])
    return {"code": new}


@router.post("/jogos/{gid}/proxima")
def next_question(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    if g["status"] not in ("sala", "revelacao", "pergunta", "discussao"):
        raise HTTPException(400, "Jogo não está em andamento")
    nxt = g["current"] + 1
    if nxt >= len(g["questions"]):
        conn.execute("UPDATE games SET status='finalizado', finished_at=CURRENT_TIMESTAMP WHERE id=?", (gid,))
    else:
        conn.execute("UPDATE games SET status='pergunta', current=?, round=1, question_started_at=?, paused_left=NULL WHERE id=?",
                     (nxt, time.time(), gid))
    return {"ok": True}


@router.post("/jogos/{gid}/revelar")
def reveal(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    _own_game(conn, user, gid)
    conn.execute("UPDATE games SET status='revelacao', paused_left=NULL WHERE id=? AND status IN ('pergunta','discussao')", (gid,))
    return {"ok": True}


@router.post("/jogos/{gid}/discutir")
def discuss(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    """Encerra a 1ª votação sem revelar a resposta e pede discussão em duplas."""
    g = _own_game(conn, user, gid)
    if g["status"] != "pergunta" or g["round"] != 1:
        raise HTTPException(400, "A discussão só pode ser pedida durante a 1ª votação")
    _end_voting(conn, g, discuss=True)
    return {"ok": True}


@router.post("/jogos/{gid}/revotar")
def revote(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    """2ª votação depois da discussão: guarda o resultado da 1ª e desfaz os pontos dela."""
    g = _own_game(conn, user, gid)
    if g["status"] != "discussao":
        raise HTTPException(400, "A turma não está em discussão")
    q = g["questions"][g["current"]]
    ans = _answers(conn, gid, g["current"])
    g["rounds"][str(g["current"])] = {"counts": _counts(q, ans), "accuracy": _accuracy(ans), "answered": len(ans)}
    for a in ans:
        conn.execute("UPDATE game_players SET score=score-?, streak=? WHERE id=?", (a["points"] or 0, a["prev_streak"] or 0, a["player_id"]))
    conn.execute("DELETE FROM game_answers WHERE game_id=? AND q_index=?", (gid, g["current"]))
    conn.execute("UPDATE games SET status='pergunta', round=2, rounds=?, question_started_at=?, paused_left=NULL WHERE id=?",
                 (jdump(g["rounds"]), time.time(), gid))
    return {"ok": True}


@router.post("/jogos/{gid}/pausar")
def pause(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    if g["status"] != "pergunta":
        return {"ok": False}
    if g["paused_left"] is None:
        conn.execute("UPDATE games SET paused_left=? WHERE id=?", (_time_left(g), gid))
    else:
        conn.execute("UPDATE games SET question_started_at=?, paused_left=NULL WHERE id=?",
                     (time.time() - (g["time_per_question"] - g["paused_left"]), gid))
    return {"ok": True}


@router.post("/jogos/{gid}/encerrar")
def finish(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    conn.execute("UPDATE games SET status='finalizado', finished_at=CURRENT_TIMESTAMP WHERE id=?", (gid,))
    audit(conn, user, "jogo.encerrado", g["title"])
    return {"ok": True}


@router.get("/jogos/{gid}/estado")
def host_state(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _tick(conn, _own_game(conn, user, gid))
    players = _ranking(conn, gid)
    out = {"id": gid, "title": g["title"], "code": g["code"], "status": g["status"], "mode": g["mode"],
           "scoring": g["scoring"], "peer": bool(g["peer"]), "round": g["round"],
           "current": g["current"], "total": len(g["questions"]), "time_per_question": g["time_per_question"],
           "time_left": round(_time_left(g), 1), "paused": g["paused_left"] is not None,
           "players": players, "teams": _teams(players) if g["mode"] == "equipes" else []}
    if 0 <= g["current"] < len(g["questions"]):
        q = g["questions"][g["current"]]
        ans = _answers(conn, gid, g["current"])
        counts = _counts(q, ans)
        answered_ids = {a["player_id"] for a in ans}
        out.update({
            "question": q, "counts": counts, "answered": len(ans), "accuracy": _accuracy(ans),
            # painel do professor: quem votou em quê e quem ainda não respondeu
            "voters": [{"name": a["name"], "choice": a["choice"], "correct": bool(a["correct"]),
                        "confidence": a["confidence"]} for a in ans],
            "waiting": [p["name"] for p in players if p["id"] not in answered_ids],
            "first_round": g["rounds"].get(str(g["current"])),
        })
    return out


@router.get("/jogos/{gid}/relatorio")
def report(gid: int, user=Depends(professor_only), conn=Depends(get_db)):
    g = _own_game(conn, user, gid)
    players = _ranking(conn, gid)
    answers = rows(conn.execute("SELECT * FROM game_answers WHERE game_id=?", (gid,)))
    qstats = []
    for i, q in enumerate(g["questions"]):
        ans = [a for a in answers if a["q_index"] == i]
        counts = _counts(q, ans)
        wrong = [(c, j) for j, c in enumerate(counts) if j != q["answer"] and c]
        top = max(wrong) if wrong else None
        first = g["rounds"].get(str(i))
        qstats.append({
            "index": i, "statement": q["statement"], "options": q["options"], "answer": q["answer"],
            "explanation": q.get("explanation", ""), "counts": counts, "answered": len(ans),
            "accuracy": _accuracy(ans),
            "avg_ms": round(sum(a["ms"] or 0 for a in ans) / len(ans)) if ans else None,
            # alternativa errada mais escolhida: pista de uma confusão comum da turma
            "top_wrong": {"option": q["options"][top[1]], "letter": "ABCDE"[top[1]], "pct": round(100 * top[0] / len(ans))} if top else None,
            "before": first["accuracy"] if first else None,
            # erraram tendo certeza: concepções erradas firmes, que merecem atenção em aula
            "overconfident": sum(1 for a in ans if not a["correct"] and a["confidence"] == 3) if g["scoring"] == "confianca" else 0,
        })
    for p in players:
        mine = [a for a in answers if a["player_id"] == p["id"]]
        p["correct"] = sum(1 for a in mine if a["correct"])
    total_ans = len(answers)
    discussed = [q for q in qstats if q["before"] is not None and q["accuracy"] is not None]
    return {"game": {k: g[k] for k in ("id", "title", "status", "mode", "scoring", "peer", "finished_at", "created_at")},
            "total": len(g["questions"]), "players": players, "teams": _teams(players) if g["mode"] == "equipes" else [],
            "questions": qstats,
            "accuracy": round(100 * sum(1 for a in answers if a["correct"]) / total_ans) if total_ans else None,
            "review": [q for q in qstats if q["accuracy"] is not None and q["accuracy"] < 60],
            "discussion_gain": round(sum(q["accuracy"] - q["before"] for q in discussed) / len(discussed)) if discussed else None}


# ================================================================== aluno

class JoinIn(BaseModel):
    code: str


@router.post("/jogar/entrar")
def join(body: JoinIn, user=Depends(aluno_only), conn=Depends(get_db)):
    g = one(conn.execute("SELECT * FROM games WHERE code=? AND institution_id=? AND status NOT IN ('rascunho','finalizado')",
                         (body.code.strip(), user["institution_id"])))
    if not g:
        raise HTTPException(404, "Nenhum jogo ativo com este código")
    if g["class_id"] and g["class_id"] not in student_class_ids(conn, user):
        raise HTTPException(403, "Este jogo é de outra turma")
    if not one(conn.execute("SELECT id FROM game_players WHERE game_id=? AND user_id=?", (g["id"], user["id"]))):
        n = conn.execute("SELECT COUNT(*) FROM game_players WHERE game_id=?", (g["id"],)).fetchone()[0]
        conn.execute("INSERT INTO game_players (game_id, user_id, name, team) VALUES (?,?,?,?)",
                     (g["id"], user["id"], user["name"], n % 4 if g["mode"] == "equipes" else 0))
    return {"game_id": g["id"]}


def _player(conn, user, gid):
    p = one(conn.execute("SELECT * FROM game_players WHERE game_id=? AND user_id=?", (gid, user["id"])))
    if not p:
        raise HTTPException(403, "Entre no jogo com o código primeiro")
    return p


@router.get("/jogar/{gid}/estado")
def player_state(gid: int, user=Depends(aluno_only), conn=Depends(get_db)):
    g = _tick(conn, _game(conn, gid))
    p = _player(conn, user, gid)
    ranking = _ranking(conn, gid)
    pos = next((i + 1 for i, r in enumerate(ranking) if r["user_id"] == user["id"]), None)
    out = {"title": g["title"], "status": g["status"], "mode": g["mode"], "scoring": g["scoring"], "round": g["round"],
           "current": g["current"], "total": len(g["questions"]), "time_left": round(_time_left(g), 1),
           "paused": g["paused_left"] is not None,
           "me": {"name": p["name"], "score": p["score"], "streak": p["streak"], "position": pos,
                  "team": TEAMS[p["team"] % 4] if g["mode"] == "equipes" else None},
           "players": len(ranking)}
    if g["show_ranking"] or g["status"] == "finalizado":
        out["ranking"] = [{"name": r["name"], "score": r["score"], "me": r["user_id"] == user["id"]} for r in ranking[:10]]
    if g["mode"] == "equipes":
        out["teams"] = _teams(ranking)
    if 0 <= g["current"] < len(g["questions"]) and g["status"] in ("pergunta", "discussao", "revelacao"):
        q = g["questions"][g["current"]]
        mine = one(conn.execute("SELECT choice, correct, points, confidence FROM game_answers WHERE game_id=? AND player_id=? AND q_index=?",
                                (gid, p["id"], g["current"])))
        out["question"] = {"statement": q["statement"], "options": q["options"]}
        if g["status"] == "revelacao":
            out["question"]["answer"] = q["answer"]
            out["question"]["explanation"] = q.get("explanation", "")
        elif mine:  # antes da revelação o aluno só vê a própria escolha, nunca se acertou
            mine = {"choice": mine["choice"], "confidence": mine["confidence"]}
        out["my_answer"] = mine
    if g["status"] == "finalizado":
        mine = {a["q_index"]: a for a in rows(conn.execute(
            "SELECT q_index, choice, correct FROM game_answers WHERE game_id=? AND player_id=?", (gid, p["id"])))}
        out["correct"] = sum(1 for a in mine.values() if a["correct"])
        # revisão pessoal: o que errou ou deixou passar, com a resposta certa e a explicação
        out["review"] = [{"statement": q["statement"], "right": q["options"][q["answer"]],
                          "given": q["options"][mine[i]["choice"]] if i in mine and mine[i]["choice"] is not None
                          and 0 <= mine[i]["choice"] < len(q["options"]) else None,
                          "explanation": q.get("explanation", "")}
                         for i, q in enumerate(g["questions"]) if not (i in mine and mine[i]["correct"])]
    return out


class AnswerIn(BaseModel):
    choice: int
    q_index: int
    confidence: int = 2


@router.post("/jogar/{gid}/responder")
def answer(gid: int, body: AnswerIn, user=Depends(aluno_only), conn=Depends(get_db)):
    g = _tick(conn, _game(conn, gid))
    p = _player(conn, user, gid)
    if g["status"] != "pergunta" or body.q_index != g["current"] or g["paused_left"] is not None:
        raise HTTPException(400, "Tempo esgotado para esta pergunta")
    if one(conn.execute("SELECT 1 FROM game_answers WHERE game_id=? AND player_id=? AND q_index=?", (gid, p["id"], g["current"]))):
        raise HTTPException(400, "Você já respondeu")
    q = g["questions"][g["current"]]
    elapsed = time.time() - g["question_started_at"]
    correct = body.choice == q["answer"]
    conf = body.confidence if body.confidence in CONFIDENCE_POINTS else 2
    streak = p["streak"] + 1 if correct else 0
    bonus = 100 * min(streak - 1, 3) if correct else 0  # sequência de acertos
    if g["scoring"] == "velocidade":  # 500–1000 pela rapidez
        points = round(1000 * (1 - min(elapsed, g["time_per_question"]) / (2 * g["time_per_question"]))) + bonus if correct else 0
    else:  # confiança: premia saber que sabe; errar com certeza custa pontos
        right, wrong = CONFIDENCE_POINTS[conf]
        points = right + bonus if correct else wrong
    cur = conn.execute(
        "INSERT OR IGNORE INTO game_answers (game_id, player_id, q_index, choice, correct, points, ms, confidence, prev_streak)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (gid, p["id"], g["current"], body.choice, int(correct), points, int(elapsed * 1000), conf, p["streak"]))
    if not cur.rowcount:
        raise HTTPException(400, "Você já respondeu")
    conn.execute("UPDATE game_players SET score=score+?, streak=? WHERE id=?", (points, streak, p["id"]))
    return {"ok": True}
