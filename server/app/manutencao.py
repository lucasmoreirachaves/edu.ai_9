"""Rotinas em segundo plano do servidor.

- Na inicialização: retoma documentos e gerações de IA interrompidos (ex.: o servidor foi
  reiniciado no meio de um processamento) e reenvia e-mails pendentes.
- A cada hora: aplica a política de retenção de dados de cada instituição (1x por dia) e,
  às segundas-feiras, envia os resumos semanais por e-mail.
"""
import threading
import time
from datetime import date

from . import correio, jobs
from .db import connect, jload, meta_get, meta_set, rows


def retomar_processamentos():
    conn = connect()
    try:
        docs = [r[0] for r in conn.execute("SELECT id FROM documents WHERE status IN ('enviado','processando')")]
        conn.execute("UPDATE generation_jobs SET status='pendente' WHERE status='processando'")
        pend = [r[0] for r in conn.execute("SELECT id FROM generation_jobs WHERE status='pendente' ORDER BY id")]
        conn.commit()
    finally:
        conn.close()
    for d in docs:
        jobs.process_document(d)
    jobs.run_jobs(pend)
    if docs or pend:
        print(f"[manutenção] retomados {len(docs)} documento(s) e {len(pend)} geração(ões) interrompidos")


def aplicar_retencao(conn):
    hoje = date.today().isoformat()
    if meta_get(conn, "retencao") == hoje:
        return
    for inst in rows(conn.execute("SELECT id, settings FROM institutions")):
        days = (jload(inst["settings"], {}) or {}).get("retention_days") or 365
        if not isinstance(days, int) or days < 30:
            continue
        conn.execute("DELETE FROM audit_log WHERE institution_id=? AND created_at < date('now', ?)", (inst["id"], f"-{days} day"))
        conn.execute("DELETE FROM notifications WHERE read=1 AND created_at < date('now', ?) AND user_id IN "
                     "(SELECT id FROM users WHERE institution_id=?)", (f"-{days} day", inst["id"]))
    conn.execute("DELETE FROM password_resets WHERE expires_at < ?", (time.time() - 86400,))
    conn.execute("DELETE FROM outbox WHERE created_at < date('now', '-180 day')")
    meta_set(conn, "retencao", hoje)
    conn.commit()


RESUMO_GESTOR = [
    ("Pessoas que acessaram", "SELECT COUNT(DISTINCT user_id) FROM audit_log WHERE institution_id=? AND action='login'"
                              " AND created_at >= date('now','-7 day')"),
    ("Entregas de atividades", "SELECT COUNT(*) FROM submissions s JOIN activities a ON a.id=s.activity_id JOIN subjects x"
                               " ON x.id=a.subject_id WHERE x.institution_id=? AND s.submitted_at >= date('now','-7 day')"),
    ("Materiais publicados", "SELECT COUNT(*) FROM materials m JOIN subjects x ON x.id=m.subject_id WHERE x.institution_id=?"
                             " AND m.status='publicado' AND m.updated_at >= date('now','-7 day')"),
    ("Chamados abertos no atendimento", "SELECT COUNT(*) FROM tickets WHERE institution_id=? AND status IN ('aberto','em_andamento')"),
]


def resumos_semanais(conn):
    hoje = date.today()
    semana = f"{hoje.isocalendar()[0]}-{hoje.isocalendar()[1]}"
    if hoje.weekday() != 0 or meta_get(conn, "resumo_semanal") == semana:
        return
    meta_set(conn, "resumo_semanal", semana)  # marca antes: nunca manda duas vezes na mesma semana
    conn.commit()
    for inst in rows(conn.execute("SELECT id, name, settings FROM institutions WHERE active=1")):
        iid, s = inst["id"], jload(inst["settings"], {}) or {}
        if s.get("notify_weekly_report", True):
            linhas = [f"{rotulo}: {conn.execute(sql, (iid,)).fetchone()[0]}" for rotulo, sql in RESUMO_GESTOR]
            txt = (f"Resumo da semana — {inst['name']}\n\n" + "\n".join(linhas)
                   + f"\n\nPainel completo: {correio.link('#/g/dashboard')}")
            for g in rows(conn.execute("SELECT email FROM users WHERE institution_id=? AND role='gestor' AND status='ativo'", (iid,))):
                correio.enviar(conn, g["email"], f"Resumo semanal — {inst['name']}", txt, iid)
        for u in rows(conn.execute("SELECT id, name, email, role FROM users WHERE institution_id=? AND status='ativo' AND weekly_email=1"
                                   " AND role IN ('aluno','professor')", (iid,))):
            if u["role"] == "aluno":
                n = conn.execute(
                    """SELECT COUNT(*) FROM activities a JOIN class_students cs ON cs.class_id=a.class_id AND cs.user_id=?
                       LEFT JOIN submissions x ON x.activity_id=a.id AND x.student_id=?
                       WHERE a.status='publicada' AND x.id IS NULL AND (a.due_date IS NULL OR a.due_date >= date('now'))""",
                    (u["id"], u["id"])).fetchone()[0]
                if not n:
                    continue
                corpo = f"Olá, {u['name'].split()[0]}!\n\nVocê tem {n} atividade(s) pendente(s) nesta semana.\n{correio.link('#/a/atividades')}"
            else:
                n = conn.execute("SELECT COUNT(*) FROM submissions s JOIN activities a ON a.id=s.activity_id JOIN subjects x ON x.id=a.subject_id"
                                 " WHERE x.teacher_id=? AND s.status='entregue'", (u["id"],)).fetchone()[0]
                if not n:
                    continue
                corpo = f"Olá, {u['name'].split()[0]}!\n\nHá {n} entrega(s) aguardando a sua correção.\n{correio.link('#/p/atividades')}"
            correio.enviar(conn, u["email"], "Sua semana na plataforma", corpo + "\n\n(Desative este resumo em Perfil.)", iid)
    conn.commit()


def _loop():
    time.sleep(5)
    try:
        retomar_processamentos()
        correio.reenviar_pendentes()
    except Exception as e:  # noqa: BLE001
        print(f"[manutenção] falha ao retomar tarefas: {e}")
    while True:
        conn = connect()
        try:
            aplicar_retencao(conn)
            resumos_semanais(conn)
        except Exception as e:  # noqa: BLE001 — a rotina nunca derruba o servidor
            print(f"[manutenção] {e}")
        finally:
            conn.close()
        time.sleep(3600)


def iniciar():
    threading.Thread(target=_loop, name="edu-manutencao", daemon=True).start()
