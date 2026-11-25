"""Envio de e-mails (convites, recuperação de senha, ouvidoria, resumos semanais).

Configuração por variáveis de ambiente:
  EDU_SMTP_HOST      servidor SMTP (sem ele, os e-mails só ficam registrados na tabela `outbox`
                     e aparecem no console do servidor — útil em testes)
  EDU_SMTP_PORT      padrão 587
  EDU_SMTP_USER      usuário SMTP
  EDU_SMTP_PASSWORD  senha SMTP
  EDU_SMTP_FROM      remetente (padrão: EDU.AI <nao-responda@eduai.local>)
  EDU_SMTP_SSL       "1" para SMTPS na porta 465 (padrão: STARTTLS)
  EDU_BASE_URL       endereço público da plataforma, usado nos links (padrão http://localhost:8000)

O envio acontece numa thread separada: a tela nunca espera o servidor de e-mail.
"""
import os
import smtplib
import threading
from email.message import EmailMessage

from .db import connect

SMTP_HOST = os.environ.get("EDU_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("EDU_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("EDU_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("EDU_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("EDU_SMTP_FROM", "EDU.AI <nao-responda@eduai.local>")
SMTP_SSL = os.environ.get("EDU_SMTP_SSL", "") == "1"
BASE_URL = os.environ.get("EDU_BASE_URL", "http://localhost:8000").rstrip("/")


def configurado() -> bool:
    return bool(SMTP_HOST)


def link(hash_route: str) -> str:
    """Link absoluto para uma rota da plataforma, ex.: link('#/convite/abc')."""
    return f"{BASE_URL}/app/{hash_route}"


def enviar(conn, to: str, subject: str, body: str, institution_id: int | None = None):
    """Registra o e-mail na `outbox` (mesma transação de quem chamou) e agenda o envio."""
    if not to or "@" not in to or to.endswith("@anonimo.local"):
        return
    cur = conn.execute("INSERT INTO outbox (institution_id, to_email, subject, body, status) VALUES (?,?,?,?,?)",
                       (institution_id, to, subject, body, "pendente" if configurado() else "registrado"))
    if not configurado():
        msg = f"[e-mail] (SMTP não configurado) para {to}: {subject}\n{body}\n"
        try:
            print(msg)
        except UnicodeEncodeError:   # console do Windows (cp1252) sem suporte a "→", emojis etc.
            print(msg.encode("ascii", "replace").decode())
        return
    oid = cur.lastrowid
    # envia depois do commit de quem chamou (a thread relê a linha)
    threading.Timer(1.0, _enviar_agora, args=(oid,)).start()


def _enviar_agora(oid: int):
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM outbox WHERE id=? AND status='pendente'", (oid,)).fetchone()
        if not r:
            return
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = SMTP_FROM, r["to_email"], r["subject"]
        msg.set_content(r["body"])
        try:
            if SMTP_SSL:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                    if SMTP_USER:
                        s.login(SMTP_USER, SMTP_PASSWORD)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                    s.starttls()
                    if SMTP_USER:
                        s.login(SMTP_USER, SMTP_PASSWORD)
                    s.send_message(msg)
            conn.execute("UPDATE outbox SET status='enviado' WHERE id=?", (oid,))
        except (smtplib.SMTPException, OSError) as e:
            conn.execute("UPDATE outbox SET status='erro', error=? WHERE id=?", (str(e)[:300], oid))
        conn.commit()
    finally:
        conn.close()


def reenviar_pendentes():
    """Na inicialização: tenta de novo os e-mails que ficaram pendentes ou com erro."""
    if not configurado():
        return
    conn = connect()
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM outbox WHERE status IN ('pendente','erro') AND created_at >= datetime('now','-2 day')")]
        for oid in ids:
            conn.execute("UPDATE outbox SET status='pendente' WHERE id=?", (oid,))
        conn.commit()
    finally:
        conn.close()
    for oid in ids:
        _enviar_agora(oid)
