"""Estúdio de aprendizado gamificado (aluno e professor).

- O ALUNO escolhe o que quer aprender (um material publicado, um texto colado ou só um tema) e a IA
  monta jogos com esse conteúdo: memória, quiz estilo Kahoot, verdadeiro ou falso, completar frases,
  adivinhar o conceito e desafios de programação. Cada partida fica registrada.
- O PROFESSOR cria jogos para as suas turmas (a partir dos seus documentos e materiais) e acompanha
  o aprendizado dos alunos: jogos criados, partidas, acertos e onde erraram.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import ia, jobs
from ..auth import current_user
from ..db import CommitRoute, get_db, jdump, jload, one, rows
from ..seguranca import limitar
from ..util import ai_model, ai_quota_check, log_ai, own_document, own_material, student_class_ids, student_material
from .aluno import _material_context

router = APIRouter(prefix="/api/aprendizado", route_class=CommitRoute)


def _who(user):
    if user["role"] not in ("aluno", "professor"):
        raise HTTPException(403, "O estúdio de aprendizado é de alunos e professores")
    return user


def _teacher_class_ids(conn, user) -> list[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT class_id FROM subjects WHERE teacher_id=? AND active=1", (user["id"],))]


def _teacher_student_ids(conn, user) -> set[int]:
    cids = _teacher_class_ids(conn, user) or [0]
    ph = ",".join("?" * len(cids))
    return {r[0] for r in conn.execute(f"SELECT user_id FROM class_students WHERE class_id IN ({ph})", cids)}


def _game(conn, user, gid: int, play: bool = False) -> dict:
    """Quem acessa: o dono; alunos da turma para a qual o jogo foi publicado; o professor de um
    aluno (para ver o que ele estudou — só leitura)."""
    g = one(conn.execute("SELECT * FROM learning_games WHERE id=? AND institution_id=?", (gid, user["institution_id"])))
    if not g:
        raise HTTPException(404, "Jogo não encontrado")
    ok = g["user_id"] == user["id"]
    if not ok and user["role"] == "aluno" and g["class_id"]:
        ok = g["class_id"] in student_class_ids(conn, user)
    if not ok and user["role"] == "professor" and not play:
        ok = g["user_id"] in _teacher_student_ids(conn, user)
    if not ok:
        raise HTTPException(404, "Jogo não encontrado")
    g["content"] = jload(g["content"], {})
    g["kind_label"] = ia.GAME_LABEL.get(g["kind"], g["kind"])
    return g


# ================================================================== fontes de conteúdo

@router.get("/opcoes")
def opcoes(user=Depends(current_user), conn=Depends(get_db)):
    _who(user)
    out = {"kinds": [{"kind": k, "label": ia.GAME_LABEL[k]} for k in ia.GAME_KINDS], "materials": [], "documents": [], "classes": []}
    if user["role"] == "aluno":
        cids = student_class_ids(conn, user) or [0]
        ph = ",".join("?" * len(cids))
        out["materials"] = rows(conn.execute(
            f"""SELECT DISTINCT m.id, m.title, m.type, s.name AS subject FROM materials m JOIN material_classes mc ON mc.material_id=m.id
                JOIN subjects s ON s.id=m.subject_id WHERE mc.class_id IN ({ph}) AND m.status='publicado' ORDER BY s.name, m.title""", cids))
    else:
        out["materials"] = rows(conn.execute(
            """SELECT m.id, m.title, m.type, s.name AS subject FROM materials m JOIN subjects s ON s.id=m.subject_id
               WHERE s.teacher_id=? AND m.status<>'arquivado' ORDER BY s.name, m.title""", (user["id"],)))
        out["documents"] = rows(conn.execute(
            """SELECT d.id, d.title, s.name AS subject FROM documents d JOIN subjects s ON s.id=d.subject_id
               WHERE s.teacher_id=? AND d.status='concluido' AND d.archived=0 ORDER BY s.name, d.title""", (user["id"],)))
        cids = _teacher_class_ids(conn, user) or [0]
        ph = ",".join("?" * len(cids))
        out["classes"] = rows(conn.execute(f"SELECT id, name FROM classes WHERE id IN ({ph}) ORDER BY name", cids))
    return out


class GerarIn(BaseModel):
    kind: str
    title: str = ""
    topic: str = ""
    text: str = ""
    material_id: int | None = None
    document_id: int | None = None
    level: str = ""
    class_id: int | None = None      # professor: já publica para a turma


@router.post("/gerar")
def gerar(body: GerarIn, user=Depends(current_user), conn=Depends(get_db)):
    _who(user)
    if body.kind not in ia.GAME_KINDS:
        raise HTTPException(400, "Tipo de jogo inválido")
    limitar(f"aprendizado:{user['id']}", 40, 3600, "Muitos jogos gerados na última hora. Aguarde um pouco.")
    ai_quota_check(conn, user["institution_id"])
    material_id, title = None, body.title.strip()[:120]
    if body.material_id:
        m = student_material(conn, user, body.material_id) if user["role"] == "aluno" else own_material(conn, user, body.material_id)
        text, title, material_id = _material_context(conn, m), title or m["title"], m["id"]
    elif body.document_id:
        if user["role"] != "professor":
            raise HTTPException(403, "Somente professores usam documentos da biblioteca")
        d = own_document(conn, user, body.document_id)
        text, title = jobs.source_text(conn, d, user_id=user["id"]), title or d["title"]
    else:
        text = (body.text.strip() or body.topic.strip())[:40000]
        title = title or body.topic.strip()[:120] or (text[:60] + "…" if len(text) > 60 else text)
        if len(text) < 3:
            raise HTTPException(400, "Escolha um material, cole um texto ou escreva o tema que deseja aprender")
    class_id = None
    if body.class_id and user["role"] == "professor":
        if body.class_id not in _teacher_class_ids(conn, user):
            raise HTTPException(400, "Turma inválida")
        class_id = body.class_id
    level = body.level.strip()[:80] or (user.get("grade") or "")
    model = ai_model(conn, user["institution_id"], user["id"])
    content, meta = ia.learning_game(body.kind, title, text, level, model)
    log_ai(conn, user, user["institution_id"], "jogo_aprendizado", meta)
    source = f"{meta['provider']}:{meta['model']}"
    if not meta["ok"]:
        content["_aviso"] = "Jogo montado pelo modo local (IA indisponível): pode ficar mais simples."
    gid = conn.execute("INSERT INTO learning_games (institution_id, user_id, class_id, material_id, title, topic, kind, content, ai_source)"
                       " VALUES (?,?,?,?,?,?,?,?,?)",
                       (user["institution_id"], user["id"], class_id, material_id, title or "Jogo", body.topic.strip()[:200],
                        body.kind, jdump(content), source)).lastrowid
    return _game(conn, user, gid)


# ================================================================== jogos e partidas

def _stats_sql(alias: str = "g") -> str:
    return (f"(SELECT COUNT(*) FROM learning_game_plays p WHERE p.game_id={alias}.id AND p.user_id=?) AS plays,"
            f" (SELECT MAX(CASE WHEN p.max_score>0 THEN 100*p.score/p.max_score END) FROM learning_game_plays p"
            f"  WHERE p.game_id={alias}.id AND p.user_id=?) AS best_pct")


@router.get("/jogos")
def jogos(user=Depends(current_user), conn=Depends(get_db)):
    _who(user)
    meus = rows(conn.execute(
        f"""SELECT g.id, g.title, g.kind, g.class_id, g.created_at, g.ai_source, c.name AS class_name, {_stats_sql()},
              (SELECT COUNT(*) FROM learning_game_plays p WHERE p.game_id=g.id) AS total_plays
            FROM learning_games g LEFT JOIN classes c ON c.id=g.class_id WHERE g.user_id=? ORDER BY g.id DESC""",
        (user["id"], user["id"], user["id"])))
    turma = []
    if user["role"] == "aluno":
        cids = student_class_ids(conn, user) or [0]
        ph = ",".join("?" * len(cids))
        turma = rows(conn.execute(
            f"""SELECT g.id, g.title, g.kind, g.created_at, c.name AS class_name, u.name AS author, {_stats_sql()}
                FROM learning_games g JOIN classes c ON c.id=g.class_id JOIN users u ON u.id=g.user_id
                WHERE g.class_id IN ({ph}) AND g.user_id<>? ORDER BY g.id DESC""", (user["id"], user["id"], *cids, user["id"])))
    for g in meus + turma:
        g["kind_label"] = ia.GAME_LABEL.get(g["kind"], g["kind"])
    pts = one(conn.execute("SELECT COALESCE(SUM(score),0) AS pontos, COUNT(*) AS partidas FROM learning_game_plays WHERE user_id=?",
                           (user["id"],)))
    return {"meus": meus, "turma": turma, "pontos": pts["pontos"], "partidas": pts["partidas"]}


@router.get("/jogos/{gid}")
def jogo(gid: int, user=Depends(current_user), conn=Depends(get_db)):
    _who(user)
    g = _game(conn, user, gid)
    g["can_play"] = g["user_id"] == user["id"] or user["role"] == "aluno"
    g["ranking"] = rows(conn.execute(
        """SELECT u.name, MAX(p.score) AS score FROM learning_game_plays p JOIN users u ON u.id=p.user_id
           WHERE p.game_id=? GROUP BY p.user_id ORDER BY score DESC LIMIT 10""", (gid,))) if g["class_id"] else []
    return g


@router.delete("/jogos/{gid}")
def apagar(gid: int, user=Depends(current_user), conn=Depends(get_db)):
    g = _game(conn, user, gid)
    if g["user_id"] != user["id"]:
        raise HTTPException(403, "Só quem criou o jogo pode excluí-lo")
    conn.execute("DELETE FROM learning_game_plays WHERE game_id=?", (gid,))
    conn.execute("DELETE FROM learning_games WHERE id=?", (gid,))
    return {"ok": True}


class PublicarIn(BaseModel):
    class_id: int | None = None


@router.put("/jogos/{gid}/publicar")
def publicar(gid: int, body: PublicarIn, user=Depends(current_user), conn=Depends(get_db)):
    g = _game(conn, user, gid)
    if user["role"] != "professor" or g["user_id"] != user["id"]:
        raise HTTPException(403, "Só o professor que criou o jogo pode publicá-lo")
    if body.class_id and body.class_id not in _teacher_class_ids(conn, user):
        raise HTTPException(400, "Turma inválida")
    conn.execute("UPDATE learning_games SET class_id=? WHERE id=?", (body.class_id, gid))
    if body.class_id:
        for r in conn.execute("SELECT user_id FROM class_students WHERE class_id=?", (body.class_id,)).fetchall():
            conn.execute("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)",
                         (r[0], f"Novo jogo de aprendizado: {g['title']}", "Aprendizado gamificado", f"#/aprender/jogo/{gid}"))
    return {"ok": True}


class PartidaIn(BaseModel):
    score: int
    max_score: int
    correct: int
    total: int
    duration_ms: int = 0
    details: list = []     # [{"q": texto, "ok": bool, "answer": ..., "right": ...}]


@router.post("/jogos/{gid}/partidas")
def partida(gid: int, body: PartidaIn, user=Depends(current_user), conn=Depends(get_db)):
    _who(user)
    _game(conn, user, gid, play=True)
    limitar(f"partida:{user['id']}", 200, 3600)
    if not (0 <= body.total <= 100 and 0 <= body.correct <= body.total and 0 <= body.max_score <= 100000
            and 0 <= body.score <= body.max_score):
        raise HTTPException(400, "Resultado inválido")
    details = [{"q": str(d.get("q", ""))[:300], "ok": bool(d.get("ok")), "answer": str(d.get("answer", ""))[:200],
                "right": str(d.get("right", ""))[:200]} for d in body.details[:100] if isinstance(d, dict)]
    pid = conn.execute("INSERT INTO learning_game_plays (game_id, user_id, score, max_score, correct, total, duration_ms, details)"
                       " VALUES (?,?,?,?,?,?,?,?)", (gid, user["id"], body.score, body.max_score, body.correct, body.total,
                                                     max(0, min(body.duration_ms, 86_400_000)), jdump(details))).lastrowid
    best = one(conn.execute("SELECT MAX(score) AS s FROM learning_game_plays WHERE game_id=? AND user_id=?", (gid, user["id"])))
    return {"id": pid, "best": best["s"], "record": best["s"] == body.score}


# ================================================================== professor: aprendizado dos alunos

def _prof(user):
    if user["role"] != "professor":
        raise HTTPException(403, "Somente professores")
    return user


@router.get("/professor/alunos")
def alunos(class_id: int | None = None, user=Depends(current_user), conn=Depends(get_db)):
    _prof(user)
    cids = _teacher_class_ids(conn, user)
    if class_id:
        if class_id not in cids:
            raise HTTPException(404, "Turma não encontrada")
        cids = [class_id]
    cids = cids or [0]
    ph = ",".join("?" * len(cids))
    out = rows(conn.execute(
        f"""SELECT u.id, u.name, (SELECT GROUP_CONCAT(c.name, ', ') FROM class_students cs2 JOIN classes c ON c.id=cs2.class_id
                                  WHERE cs2.user_id=u.id AND cs2.class_id IN ({ph})) AS classes,
              (SELECT COUNT(*) FROM learning_games g WHERE g.user_id=u.id) AS games_created,
              (SELECT COUNT(*) FROM learning_game_plays p WHERE p.user_id=u.id) AS plays,
              (SELECT ROUND(AVG(100.0*p.correct/p.total)) FROM learning_game_plays p WHERE p.user_id=u.id AND p.total>0) AS avg_pct,
              (SELECT MAX(p.created_at) FROM learning_game_plays p WHERE p.user_id=u.id) AS last_play
            FROM users u WHERE u.role='aluno' AND u.id IN (SELECT user_id FROM class_students WHERE class_id IN ({ph}))
            ORDER BY u.name""", (*cids, *cids)))
    classes = rows(conn.execute(f"SELECT id, name FROM classes WHERE id IN ({ph}) ORDER BY name", cids))
    turma_jogos = rows(conn.execute(
        f"""SELECT g.id, g.title, g.kind, c.name AS class_name, g.created_at,
              (SELECT COUNT(DISTINCT p.user_id) FROM learning_game_plays p WHERE p.game_id=g.id) AS players,
              (SELECT ROUND(AVG(100.0*p.correct/p.total)) FROM learning_game_plays p WHERE p.game_id=g.id AND p.total>0) AS avg_pct
            FROM learning_games g JOIN classes c ON c.id=g.class_id WHERE g.user_id=? ORDER BY g.id DESC""", (user["id"],)))
    for g in turma_jogos:
        g["kind_label"] = ia.GAME_LABEL.get(g["kind"], g["kind"])
    return {"students": out, "classes": classes, "class_games": turma_jogos}


@router.get("/professor/alunos/{sid}")
def aluno(sid: int, user=Depends(current_user), conn=Depends(get_db)):
    _prof(user)
    if sid not in _teacher_student_ids(conn, user):
        raise HTTPException(404, "Aluno não encontrado nas suas turmas")
    st = one(conn.execute("SELECT id, name, grade FROM users WHERE id=?", (sid,)))
    plays = rows(conn.execute(
        """SELECT p.id, p.score, p.max_score, p.correct, p.total, p.duration_ms, p.details, p.created_at,
             g.id AS game_id, g.title, g.kind, g.topic, CASE WHEN g.user_id=? THEN 'aluno' ELSE 'professor' END AS origin
           FROM learning_game_plays p JOIN learning_games g ON g.id=p.game_id WHERE p.user_id=? ORDER BY p.id DESC LIMIT 200""",
        (sid, sid)))
    erros: dict[str, int] = {}
    for p in plays:
        p["kind_label"] = ia.GAME_LABEL.get(p["kind"], p["kind"])
        p["details"] = jload(p["details"], [])
        p["pct"] = round(100 * p["correct"] / p["total"]) if p["total"] else None
        for d in p["details"]:
            if not d.get("ok") and d.get("q"):
                erros[d["q"]] = erros.get(d["q"], 0) + 1
    games = rows(conn.execute("SELECT id, title, kind, topic, created_at FROM learning_games WHERE user_id=? ORDER BY id DESC", (sid,)))
    for g in games:
        g["kind_label"] = ia.GAME_LABEL.get(g["kind"], g["kind"])
    by_kind = {}
    for p in plays:
        k = by_kind.setdefault(p["kind_label"], {"plays": 0, "pct_sum": 0, "n": 0})
        k["plays"] += 1
        if p["pct"] is not None:
            k["pct_sum"] += p["pct"]
            k["n"] += 1
    return {"student": st, "plays": plays, "games": games,
            "by_kind": [{"kind": k, "plays": v["plays"], "avg_pct": round(v["pct_sum"] / v["n"]) if v["n"] else None}
                        for k, v in by_kind.items()],
            "top_errors": [{"q": re.sub(r"\s+", " ", q), "n": n} for q, n in sorted(erros.items(), key=lambda x: -x[1])[:10]]}
