"""Chat com IA para todos os perfis (aluno, professor, secretaria, gestor e administrador geral).

Cada pessoa vê só as próprias conversas. A IA usada segue a configuração da instituição (link e
chave da API da IA em nuvem) e a preferência do usuário (nuvem ou local/Ollama), que pode ser
trocada no próprio chat ou no perfil. O administrador geral usa a própria chave.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import ia
from ..auth import current_user
from ..db import CommitRoute, get_db, jdump, jload, one, rows
from ..seguranca import limitar
from ..util import ai_config, ai_model, ai_quota_check, log_ai

router = APIRouter(prefix="/api/chat", route_class=CommitRoute)


def _papel(user) -> str:
    return "admin" if user.get("is_superadmin") and not user["impersonated_by"] else user["role"]


def _conversa(conn, user, cid: int) -> dict:
    c = one(conn.execute("SELECT * FROM chat_conversations WHERE id=? AND user_id=?", (cid, user["id"])))
    if not c:
        raise HTTPException(404, "Conversa não encontrada")
    return c


@router.get("/conversas")
def conversas(user=Depends(current_user), conn=Depends(get_db)):
    return rows(conn.execute(
        """SELECT c.id, c.title, c.updated_at, (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id=c.id) AS messages
           FROM chat_conversations c WHERE c.user_id=? ORDER BY c.updated_at DESC LIMIT 100""", (user["id"],)))


class NovaConversa(BaseModel):
    title: str = ""


@router.post("/conversas")
def nova(body: NovaConversa, user=Depends(current_user), conn=Depends(get_db)):
    if user["impersonated_by"]:
        raise HTTPException(403, "O chat não fica disponível ao acessar como outro usuário")
    cid = conn.execute("INSERT INTO chat_conversations (user_id, institution_id, title) VALUES (?,?,?)",
                       (user["id"], user["institution_id"], body.title.strip()[:80] or "Nova conversa")).lastrowid
    return {"id": cid}


@router.get("/conversas/{cid}")
def abrir(cid: int, user=Depends(current_user), conn=Depends(get_db)):
    c = _conversa(conn, user, cid)
    c["messages"] = rows(conn.execute("SELECT id, role, content, provider, created_at FROM chat_messages"
                                      " WHERE conversation_id=? ORDER BY id", (cid,)))
    return c


@router.delete("/conversas/{cid}")
def apagar(cid: int, user=Depends(current_user), conn=Depends(get_db)):
    _conversa(conn, user, cid)
    conn.execute("DELETE FROM chat_messages WHERE conversation_id=?", (cid,))
    conn.execute("DELETE FROM chat_conversations WHERE id=?", (cid,))
    return {"ok": True}


class Mensagem(BaseModel):
    text: str
    mode: str = ""      # "" mantém a preferência | nuvem | local (troca a preferência do usuário)


@router.post("/conversas/{cid}/mensagens")
def enviar(cid: int, body: Mensagem, user=Depends(current_user), conn=Depends(get_db)):
    c = _conversa(conn, user, cid)
    text = body.text.strip()[:6000]
    if len(text) < 1:
        raise HTTPException(400, "Escreva uma mensagem")
    limitar(f"chat:{user['id']}", 60, 3600, "Muitas mensagens na última hora. Aguarde um pouco.")
    superadmin = user.get("is_superadmin") and not user["impersonated_by"]
    if not superadmin:
        ai_quota_check(conn, user["institution_id"])
    if body.mode in ("nuvem", "local"):
        prefs = jload(one(conn.execute("SELECT ai_prefs FROM users WHERE id=?", (user["id"],)))["ai_prefs"], {}) or {}
        if prefs.get("mode") != body.mode:
            prefs["mode"] = body.mode
            conn.execute("UPDATE users SET ai_prefs=? WHERE id=?", (jdump(prefs), user["id"]))
            conn.commit()
    historico = rows(conn.execute("SELECT role, content FROM chat_messages WHERE conversation_id=? ORDER BY id DESC LIMIT 12", (cid,)))[::-1]
    historico.append({"role": "user", "content": text})
    model = ai_model(conn, user["institution_id"], user["id"])
    resposta, meta = ia.conversar(_papel(user), historico, model)   # nada é gravado durante a espera pela IA
    source = f"{meta['provider']}:{meta['model']}"
    conn.execute("INSERT INTO chat_messages (conversation_id, role, content) VALUES (?,?,?)", (cid, "user", text))
    mid = conn.execute("INSERT INTO chat_messages (conversation_id, role, content, provider) VALUES (?,?,?,?)",
                       (cid, "assistant", resposta, source)).lastrowid
    title = c["title"]
    if title == "Nova conversa":
        title = (text[:60] + ("…" if len(text) > 60 else "")).replace("\n", " ")
    conn.execute("UPDATE chat_conversations SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (title, cid))
    if meta["ok"]:
        log_ai(conn, user, user["institution_id"], "chat", meta)
    cfg = ai_config(conn, user["institution_id"], user["id"])
    return {"id": mid, "role": "assistant", "content": resposta, "provider": source, "ok": meta["ok"],
            "error": meta["error"], "title": title, "mode": cfg["mode"], "cloud_ready": cfg["cloud_ready"]}
