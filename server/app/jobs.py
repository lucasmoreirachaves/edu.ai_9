"""Tarefas em segundo plano: processamento de documentos e geração de materiais.

Rodam fora da requisição (BackgroundTasks), cada uma com a sua própria conexão.
"""
import re
import zipfile
from pathlib import Path

from . import ia
from .db import UPLOAD_DIR, connect, jdump, jload, notify, one
from .util import ai_model, log_ai, save_material_version

TEXT_EXT = {".txt", ".md", ".csv", ".html", ".htm"}
ALLOWED_EXT = {".pdf", ".docx"} | TEXT_EXT


PAGE_MARK = re.compile(r"^\[Página (\d+)\]$", re.M)


def extract_text(path: Path) -> tuple[str, int, int]:
    """Extrai o texto inteiro do arquivo. Devolve (texto, páginas, páginas sem texto).

    Em PDFs cada página começa com a marca "[Página N]", usada para gerar materiais
    a partir de um intervalo de páginas.
    """
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts, empty = [], 0
        for i, page in enumerate(reader.pages, 1):
            t = (page.extract_text() or "").strip()
            if len(t) < 20:
                empty += 1
            parts.append(f"[Página {i}]\n{t}")
        return "\n\n".join(parts), len(reader.pages), empty
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml), 0, 0
    raw = path.read_bytes()
    for enc in ("utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if ext in (".html", ".htm"):
        text = re.sub(r"<[^>]+>", " ", text)
    return text, 0, 0


def page_range(text: str, start: int | None, end: int | None) -> str:
    """Recorta o texto entre as marcas de página (inclusive). Sem marcas, devolve tudo."""
    if not start and not end:
        return text
    marks = list(PAGE_MARK.finditer(text))
    if not marks:
        return text
    start, end = start or 1, end or len(marks)
    chosen = [text[m.start():(marks[i + 1].start() if i + 1 < len(marks) else len(text))]
              for i, m in enumerate(marks) if start <= int(m.group(1)) <= end]
    return "".join(chosen).strip() or text


def source_text(conn, d: dict, page_from: int | None = None, page_to: int | None = None, user_id: int | None = None) -> str:
    """Texto que a IA recebe para gerar a partir do documento `d` (no intervalo de páginas pedido).

    Se não couber num prompt, a IA lê em partes e o resultado (notas condensadas) fica guardado
    em documents.digests para as próximas gerações do mesmo trecho. Notas feitas pelo modo
    local não são guardadas, para que a IA de verdade as refaça quando estiver disponível.
    """
    text = page_range(d["text"] or "", page_from, page_to)
    if not ia.needs_digest(text):
        return text
    key = f"{page_from or ''}-{page_to or ''}"
    row = one(conn.execute("SELECT digests FROM documents WHERE id=?", (d["id"],)))
    cache = jload(row["digests"] if row else None, {}) or {}
    if key in cache:
        return cache[key]
    notes, meta = ia.digest(d["title"], text, ai_model(conn, d["institution_id"], user_id or d["created_by"]))
    log_ai(conn, {"id": user_id}, d["institution_id"], "leitura", meta)
    if meta["ok"]:
        cache[key] = notes
        conn.execute("UPDATE documents SET digests=? WHERE id=?", (jdump(cache), d["id"]))
    conn.commit()
    return notes


def upload_path(doc_id: int, filename: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[-80:]
    return UPLOAD_DIR / f"{doc_id}_{safe}"


def document_file(d: dict):
    """Resposta HTTP com o arquivo original do documento, no formato e com o nome em que foi enviado.
    Conteúdo colado como texto (sem arquivo) sai como .txt."""
    from urllib.parse import quote

    from fastapi import HTTPException
    from fastapi.responses import FileResponse, Response

    if d.get("filename"):
        p = upload_path(d["id"], d["filename"])
        if not p.exists():
            raise HTTPException(404, "O arquivo original não está mais no servidor. Peça ao professor para reenviá-lo.")
        return FileResponse(p, filename=d["filename"])   # tipo (PDF, DOCX…) deduzido da extensão; baixa como anexo
    text = d.get("text") or ""
    if not text.strip():
        raise HTTPException(404, "Este conteúdo não tem arquivo para baixar")
    nome = re.sub(r'[\\/:*?"<>|]+', "_", d.get("title") or "conteudo").strip()[:80] + ".txt"
    return Response(PAGE_MARK.sub("", text).strip() + "\n", media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"})


def process_document(doc_id: int):
    conn = connect()
    try:
        d = one(conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)))
        if not d:
            return
        conn.execute("UPDATE documents SET status='processando', progress=15, error=NULL WHERE id=?", (doc_id,))
        conn.commit()
        text, pages, empty = d["text"] or "", 0, 0
        if d["filename"]:
            p = upload_path(doc_id, d["filename"])
            if p.exists():
                text, pages, empty = extract_text(p)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(PAGE_MARK.sub("", text).strip()) < 40:
            raise ValueError("Não foi possível extrair texto do arquivo: ele parece ser uma imagem escaneada. "
                             "Envie a versão digital do PDF, um DOCX ou cole o texto.")
        conn.execute("UPDATE documents SET text=?, pages=?, empty_pages=?, digests='{}', progress=55 WHERE id=?",
                     (text, pages, empty, doc_id))
        conn.commit()
        topics, meta = ia.extract_topics(d["title"], text, ai_model(conn, d["institution_id"], d["created_by"]))
        log_ai(conn, {"id": d["created_by"]}, d["institution_id"], "topicos", meta)
        conn.execute("UPDATE documents SET topics=?, status='concluido', progress=100 WHERE id=?",
                     (jdump(topics), doc_id))
        notify(conn, d["created_by"], f"A IA terminou de processar “{d['title']}”", "Biblioteca",
               f"#/p/documento/{doc_id}")
        conn.commit()
    except Exception as e:  # noqa: BLE001 — qualquer falha vira estado de erro visível ao professor
        conn.rollback()
        conn.execute("UPDATE documents SET status='erro', error=? WHERE id=?", (str(e)[:300], doc_id))
        d = one(conn.execute("SELECT created_by, title FROM documents WHERE id=?", (doc_id,)))
        if d:
            notify(conn, d["created_by"], f"Falha ao processar “{d['title']}”", "Biblioteca", f"#/p/documento/{doc_id}")
        conn.commit()
    finally:
        conn.close()


def run_jobs(job_ids: list[int]):
    for jid in job_ids:
        run_job(jid)


def run_job(job_id: int):
    conn = connect()
    try:
        j = one(conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)))
        if not j or j["status"] != "pendente":
            return
        conn.execute("UPDATE generation_jobs SET status='processando' WHERE id=?", (job_id,))
        conn.commit()
        d = one(conn.execute("SELECT * FROM documents WHERE id=?", (j["document_id"],)))
        opts = jload(j["options"], {})
        kind = j["kind"]
        text = source_text(conn, d, opts.get("page_from"), opts.get("page_to"), j["created_by"])
        content, meta = ia.generate(kind, d["title"], text, opts, ai_model(conn, j["institution_id"], j["created_by"]))
        log_ai(conn, {"id": j["created_by"]}, j["institution_id"], kind, meta)
        variant = opts.get("variant") or ""
        label = ia.VARIANT_LABEL.get(variant) or ia.TYPE_LABEL[kind]
        title = opts.get("title") or f"{label} · {d['title']}"
        if opts.get("page_from") or opts.get("page_to"):
            title += f" (p. {opts.get('page_from') or 1}–{opts.get('page_to') or d['pages']})"
        source = f"{meta['provider']}:{meta['model']}"
        if meta.get("error"):
            content["_aviso"] = "Gerado pelo modo local (Ollama indisponível): revise com atenção."
        cur = conn.execute(
            "INSERT INTO materials (subject_id, topic_id, document_id, type, title, variant, content, status, ai_source, created_by)"
            " VALUES (?,?,?,?,?,?,?, 'rascunho', ?, ?)",
            (d["subject_id"], opts.get("topic_id") or d["topic_id"], d["id"], kind, title, variant,
             jdump(content), source, j["created_by"]))
        mid = cur.lastrowid
        save_material_version(conn, {"id": j["created_by"]}, {"id": mid, "title": title, "content": content},
                              f"Gerado pela IA ({source})")
        conn.execute("UPDATE generation_jobs SET status='concluido', material_id=? WHERE id=?", (mid, job_id))
        notify(conn, j["created_by"], f"{label} de “{d['title']}” pronto para revisão", "Estúdio de IA",
               f"#/p/material/{mid}")
        conn.commit()
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        conn.execute("UPDATE generation_jobs SET status='erro', error=? WHERE id=?", (str(e)[:300], job_id))
        conn.commit()
    finally:
        conn.close()
