"""Regras de acesso e helpers compartilhados pelos routers."""
import random
import string
from datetime import date

from fastapi import HTTPException

from . import ia
from .db import jdump, jload, one, rows
from .ia_providers import usar_config


def institution_settings(conn, institution_id: int) -> dict:
    inst = one(conn.execute("SELECT settings FROM institutions WHERE id=?", (institution_id,)))
    return jload(inst["settings"] if inst else None, {}) or {}


def mask_key(key: str | None) -> str:
    """Mostra só o final da chave da API (a chave inteira nunca volta para o navegador)."""
    return f"••••••••{key[-4:]}" if key and len(key) > 8 else ("••••" if key else "")


def ai_config(conn, institution_id: int, user_id: int | None = None) -> dict:
    """Qual IA atende este pedido.

    - A instituição cadastra o link e a chave da API da IA em nuvem (vale para todos dela) e o modo
      padrão; cada usuário pode preferir nuvem ou local (Ollama) no chat ou no perfil.
    - O administrador geral usa o próprio link/chave (cadastrados em Administração → Minha IA).
    Sem link e chave, o modo nuvem cai no modo local."""
    s = institution_settings(conn, institution_id)
    cloud = s.get("ai_cloud") or {}
    local_model = s.get("ai_model") or ia.DEFAULT_MODEL
    default_mode = s.get("ai_default_mode") or ("nuvem" if cloud.get("url") and cloud.get("key") else "local")
    prefs, superadmin = {}, False
    if user_id:
        u = one(conn.execute("SELECT ai_prefs, is_superadmin FROM users WHERE id=?", (user_id,)))
        if u:
            prefs, superadmin = jload(u["ai_prefs"], {}) or {}, bool(u["is_superadmin"])
    if superadmin:
        cloud = {"url": prefs.get("url"), "key": prefs.get("key"), "model": prefs.get("model")}
        local_model = prefs.get("local_model") or local_model
        default_mode = "nuvem" if cloud["url"] and cloud["key"] else "local"
    mode = prefs.get("mode") if prefs.get("mode") in ("nuvem", "local") else default_mode
    cloud_ready = bool(cloud.get("url") and cloud.get("key"))
    if mode == "nuvem" and cloud_ready:
        return {"mode": "nuvem", "url": cloud["url"], "key": cloud["key"], "model": cloud.get("model") or "",
                "cloud_ready": True, "preferred": mode}
    return {"mode": "local", "model": local_model, "cloud_ready": cloud_ready, "preferred": mode}


def ai_model(conn, institution_id: int, user_id: int | None = None) -> str:
    """Ativa a IA certa para este pedido (instituição + preferência do usuário) e devolve o modelo."""
    cfg = ai_config(conn, institution_id, user_id)
    usar_config(cfg)
    if cfg["mode"] == "nuvem":
        return cfg["model"]        # "" = modelo padrão da nuvem; nunca o modelo do Ollama (ex.: llama3.2)
    return cfg["model"] or ia.DEFAULT_MODEL


def log_ai(conn, user: dict | None, institution_id: int, kind: str, meta: dict):
    conn.execute(
        "INSERT INTO ai_usage (institution_id, user_id, kind, provider, model, chars_in, chars_out, ms, ok)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (institution_id, user["id"] if user else None, kind, meta.get("provider"), meta.get("model"),
         meta.get("chars_in", 0), meta.get("chars_out", 0), meta.get("ms", 0), 1 if meta.get("ok") else 0),
    )


def ai_quota_check(conn, institution_id: int):
    """Limite mensal de gerações por plano (Fase 3: gestão de consumo de IA)."""
    if institution_settings(conn, institution_id).get("ai_enabled") is False:
        raise HTTPException(403, "A geração com IA está desativada pela instituição.")
    limit = PLANS.get(plan_of(conn, institution_id), PLANS["Escola Pro"])["ai_month"]
    used = conn.execute(
        "SELECT COUNT(*) FROM ai_usage WHERE institution_id=? AND created_at >= date('now','start of month')",
        (institution_id,)).fetchone()[0]
    if used >= limit:
        raise HTTPException(429, f"Limite mensal de {limit} gerações de IA do plano atingido.")


PLANS = {
    "Essencial": {"price": 490, "teachers": 10, "students": 300, "storage_mb": 2048, "ai_month": 300},
    "Escola Pro": {"price": 1290, "teachers": 60, "students": 1500, "storage_mb": 20480, "ai_month": 3000},
    "Rede": {"price": 3900, "teachers": 500, "students": 15000, "storage_mb": 204800, "ai_month": 30000},
}


def plan_of(conn, institution_id: int) -> str:
    r = one(conn.execute("SELECT plan FROM institutions WHERE id=?", (institution_id,)))
    return r["plan"] if r else "Escola Pro"


_rng = random.SystemRandom()  # códigos de turma e de jogo não podem ser previsíveis


def code(n: int = 6, digits_only: bool = True) -> str:
    alphabet = string.digits if digits_only else string.ascii_uppercase + string.digits
    return "".join(_rng.choice(alphabet) for _ in range(n))


# ------------------------------------------------------------------ acesso do professor

def own_subject(conn, user: dict, subject_id: int) -> dict:
    s = one(conn.execute("SELECT * FROM subjects WHERE id=? AND institution_id=?", (subject_id, user["institution_id"])))
    if not s or (user["role"] == "professor" and s["teacher_id"] != user["id"]):
        raise HTTPException(404, "Disciplina não encontrada")
    return s


def teacher_subject_ids(conn, user: dict) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM subjects WHERE teacher_id=?", (user["id"],))]


def own_document(conn, user: dict, doc_id: int) -> dict:
    d = one(conn.execute("SELECT * FROM documents WHERE id=? AND institution_id=?", (doc_id, user["institution_id"])))
    if not d:
        raise HTTPException(404, "Documento não encontrado")
    own_subject(conn, user, d["subject_id"])
    return d


def own_material(conn, user: dict, mid: int) -> dict:
    m = one(conn.execute("SELECT m.* FROM materials m JOIN subjects s ON s.id=m.subject_id WHERE m.id=? AND s.institution_id=?",
                         (mid, user["institution_id"])))
    if not m:
        raise HTTPException(404, "Material não encontrado")
    own_subject(conn, user, m["subject_id"])
    m["content"] = jload(m["content"], {})
    return m


def own_activity(conn, user: dict, aid: int) -> dict:
    a = one(conn.execute("SELECT * FROM activities WHERE id=?", (aid,)))
    if not a:
        raise HTTPException(404, "Atividade não encontrada")
    own_subject(conn, user, a["subject_id"])
    return a


def own_question(conn, user: dict, qid: int) -> dict:
    q = one(conn.execute("SELECT * FROM questions WHERE id=?", (qid,)))
    if not q:
        raise HTTPException(404, "Questão não encontrada")
    own_subject(conn, user, q["subject_id"])
    return q


# ------------------------------------------------------------------ acesso do aluno

def student_class_ids(conn, user: dict) -> list[int]:
    return [r[0] for r in conn.execute("SELECT class_id FROM class_students WHERE user_id=?", (user["id"],))]


def student_material(conn, user: dict, mid: int) -> dict:
    """Aluno só vê material publicado para uma das suas turmas."""
    m = one(conn.execute(
        "SELECT m.*, s.name AS subject_name, s.color AS subject_color FROM materials m"
        " JOIN subjects s ON s.id=m.subject_id"
        " JOIN material_classes mc ON mc.material_id=m.id"
        " JOIN class_students cs ON cs.class_id=mc.class_id AND cs.user_id=?"
        " WHERE m.id=? AND m.status='publicado'", (user["id"], mid)))
    if not m:
        raise HTTPException(404, "Material não disponível")
    m["content"] = jload(m["content"], {})
    return m


def student_activity(conn, user: dict, aid: int) -> dict:
    a = one(conn.execute(
        "SELECT a.*, s.name AS subject_name FROM activities a JOIN subjects s ON s.id=a.subject_id"
        " JOIN class_students cs ON cs.class_id=a.class_id AND cs.user_id=?"
        " WHERE a.id=? AND a.status IN ('publicada','encerrada')", (user["id"], aid)))
    if not a:
        raise HTTPException(404, "Atividade não disponível")
    return a


def past_due(activity: dict) -> bool:
    """O prazo vale até o fim do dia informado (horário do servidor)."""
    return bool(activity.get("due_date")) and date.today().isoformat() > activity["due_date"][:10]


def answers_released(activity: dict, attempts_used: int) -> bool:
    """Gabarito só aparece quando o aluno não pode mais entregar: usou todas as tentativas,
    a atividade foi encerrada ou o prazo passou (sem aceitar atraso)."""
    return (attempts_used >= activity["max_attempts"] or activity["status"] == "encerrada"
            or (past_due(activity) and not activity.get("accept_late")))


def activity_questions(conn, aid: int) -> list[dict]:
    qs = rows(conn.execute(
        "SELECT q.* FROM questions q JOIN activity_questions aq ON aq.question_id=q.id"
        " WHERE aq.activity_id=? ORDER BY aq.position, q.id", (aid,)))
    for q in qs:
        q["options"] = jload(q["options"], [])
    return qs


def save_material_version(conn, user: dict, m: dict, note: str):
    conn.execute("INSERT INTO material_versions (material_id, title, content, note, created_by) VALUES (?,?,?,?,?)",
                 (m["id"], m["title"], m["content"] if isinstance(m["content"], str) else jdump(m["content"]),
                  note, user["id"] if user else None))


def delete_material(conn, mid: int):
    """Exclui o material e tudo o que depende dele. Questões enviadas ao banco continuam no banco."""
    for table in ("material_versions", "material_classes", "material_progress", "flashcard_reviews"):
        conn.execute(f"DELETE FROM {table} WHERE material_id=?", (mid,))
    conn.execute("UPDATE generation_jobs SET material_id=NULL WHERE material_id=?", (mid,))
    conn.execute("UPDATE questions SET material_id=NULL WHERE material_id=?", (mid,))
    conn.execute("DELETE FROM materials WHERE id=?", (mid,))
