"""Calendário escolar.

A gestão define os PERÍODOS LETIVOS (início, fim e os dias da semana com aula) e os EVENTOS:
feriados, recessos e dias sem aula (tiram a aula do dia), aulas extras/reposições (criam aula),
provas, eventos e reuniões. Um evento vale para a escola inteira ou para uma turma.
Professores podem marcar provas e eventos nas próprias turmas. Alunos e professores veem o mês
com os dias de aula, os eventos e os prazos das atividades.
"""
import calendar
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import current_user
from ..db import CommitRoute, audit, get_db, jdump, jload, notify, one, rows
from ..util import student_class_ids

router = APIRouter(prefix="/api/calendario", route_class=CommitRoute)

TIPOS = {
    "feriado": "Feriado", "recesso": "Recesso / férias", "sem_aula": "Sem aula", "aula_extra": "Aula extra / reposição",
    "prova": "Prova / avaliação", "evento": "Evento", "reuniao": "Reunião de pais e mestres",
}
SEM_AULA = {"feriado", "recesso", "sem_aula"}
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(s: str | None, campo: str) -> date:
    if not s or not DATA.match(s):
        raise HTTPException(400, f"Data inválida em {campo}")
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"Data inválida em {campo}")


def _classes_of(conn, user) -> list[int] | None:
    """Turmas que a pessoa acompanha. None = todas (gestão)."""
    if user["role"] == "aluno":
        return student_class_ids(conn, user)
    if user["role"] == "professor":
        return [r[0] for r in conn.execute("SELECT DISTINCT class_id FROM subjects WHERE teacher_id=? AND active=1", (user["id"],))]
    return None


def _events(conn, iid: int, start: str, end: str, classes: list[int] | None, class_filter: int | None = None) -> list[dict]:
    sql = """SELECT e.*, c.name AS class_name, u.name AS author FROM calendar_events e
             LEFT JOIN classes c ON c.id=e.class_id LEFT JOIN users u ON u.id=e.created_by
             WHERE e.institution_id=? AND e.date<=? AND COALESCE(e.end_date, e.date)>=?"""
    params: list = [iid, end, start]
    ids = [class_filter] if class_filter else classes
    if ids is not None:
        sql += f" AND (e.class_id IS NULL OR e.class_id IN ({','.join('?' * len(ids)) or 'NULL'}))"
        params += ids
    out = rows(conn.execute(sql + " ORDER BY e.date, e.id", params))
    for e in out:
        e["kind_label"] = TIPOS.get(e["kind"], e["kind"])
    return out


def _class_days(conn, iid: int, start: date, end: date, events: list[dict]) -> dict[str, bool]:
    """Para cada dia: há aula? (dentro de um período letivo, num dia da semana letivo e sem
    feriado/recesso; aula extra cria aula mesmo fora disso)."""
    terms = rows(conn.execute("SELECT * FROM academic_terms WHERE institution_id=? AND start_date<=? AND end_date>=?",
                              (iid, end.isoformat(), start.isoformat())))
    for t in terms:
        t["wd"] = set(jload(t["weekdays"], []) or [])
    out = {}
    d = start
    while d <= end:
        iso = d.isoformat()
        aula = any(t["start_date"] <= iso <= t["end_date"] and d.weekday() in t["wd"] for t in terms)
        todos = [e for e in events if e["date"] <= iso <= (e["end_date"] or e["date"])]
        # `events` já vem filtrado para quem está vendo (escola inteira + as turmas da pessoa)
        if any(e["kind"] in SEM_AULA for e in todos):
            aula = False
        if any(e["kind"] == "aula_extra" for e in todos):
            aula = True
        out[iso] = aula
        d += timedelta(days=1)
    return out


def _activities(conn, user, start: str, end: str) -> list[dict]:
    if user["role"] == "aluno":
        ids = student_class_ids(conn, user) or [0]
        return rows(conn.execute(
            f"""SELECT a.id, a.title, a.due_date, s.name AS subject_name, s.color FROM activities a JOIN subjects s ON s.id=a.subject_id
                WHERE a.class_id IN ({','.join('?' * len(ids))}) AND a.status='publicada' AND a.due_date BETWEEN ? AND ?
                ORDER BY a.due_date""", (*ids, start, end)))
    if user["role"] == "professor":
        return rows(conn.execute(
            """SELECT a.id, a.title, a.due_date, s.name AS subject_name, s.color, c.name AS class_name FROM activities a
               JOIN subjects s ON s.id=a.subject_id JOIN classes c ON c.id=a.class_id
               WHERE s.teacher_id=? AND a.status='publicada' AND a.due_date BETWEEN ? AND ? ORDER BY a.due_date""",
            (user["id"], start, end)))
    return []


# ------------------------------------------------------------------ visão do mês (todos os perfis)

@router.get("")
def mes(mes: str | None = None, turma: int | None = None, user=Depends(current_user), conn=Depends(get_db)):
    hoje = date.today()
    if mes:
        if not re.match(r"^\d{4}-\d{2}$", mes):
            raise HTTPException(400, "Mês inválido (use AAAA-MM)")
        ano, m = int(mes[:4]), int(mes[5:])
        if not 1 <= m <= 12:
            raise HTTPException(400, "Mês inválido")
    else:
        ano, m = hoje.year, hoje.month
    inicio, fim = date(ano, m, 1), date(ano, m, calendar.monthrange(ano, m)[1])
    iid = user["institution_id"]
    classes = _classes_of(conn, user)
    if turma and classes is not None and turma not in classes:
        raise HTTPException(404, "Turma não encontrada")
    if turma and classes is None and not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?", (turma, iid))):
        raise HTTPException(404, "Turma não encontrada")
    events = _events(conn, iid, inicio.isoformat(), fim.isoformat(), classes, turma)
    # a gestão sem filtro de turma vê os dias de aula da escola (só eventos gerais tiram aula)
    base = events if (turma or classes is not None) else [e for e in events if e["class_id"] is None]
    aulas = _class_days(conn, iid, inicio, fim, base)
    acts = _activities(conn, user, inicio.isoformat(), fim.isoformat())
    dias = []
    for iso, aula in aulas.items():
        dias.append({"date": iso, "class_day": aula,
                     "events": [e for e in events if e["date"] <= iso <= (e["end_date"] or e["date"])],
                     "activities": [a for a in acts if a["due_date"] == iso]})
    terms = rows(conn.execute("SELECT * FROM academic_terms WHERE institution_id=? ORDER BY start_date", (iid,)))
    for t in terms:
        t["weekdays"] = jload(t["weekdays"], [])
    turmas = rows(conn.execute(
        f"SELECT id, name FROM classes WHERE institution_id=? {'' if classes is None else 'AND id IN (' + (','.join(map(str, classes)) or '0') + ')'} ORDER BY name",
        (iid,)))
    return {"month": f"{ano:04d}-{m:02d}", "days": dias, "terms": terms, "kinds": TIPOS, "classes": turmas,
            "class_days": sum(1 for d in dias if d["class_day"]), "today": hoje.isoformat(),
            "can_edit": user["role"] in ("gestor", "professor")}


@router.get("/proximos")
def proximos(dias: int = 14, user=Depends(current_user), conn=Depends(get_db)):
    """Resumo para as telas iniciais: próximos dias de aula, eventos e prazos."""
    dias = max(1, min(dias, 60))
    inicio, fim = date.today(), date.today() + timedelta(days=dias)
    classes = _classes_of(conn, user)
    events = _events(conn, user["institution_id"], inicio.isoformat(), fim.isoformat(), classes)
    aulas = _class_days(conn, user["institution_id"], inicio, fim, events if classes is not None else
                        [e for e in events if e["class_id"] is None])
    proxima = next((d for d, a in aulas.items() if a), None)
    return {"next_class_day": proxima, "class_today": aulas.get(inicio.isoformat(), False),
            "events": events[:8], "activities": _activities(conn, user, inicio.isoformat(), fim.isoformat())[:8]}


# ------------------------------------------------------------------ períodos letivos (gestão)

class TermIn(BaseModel):
    name: str
    start_date: str
    end_date: str
    weekdays: list[int] = [0, 1, 2, 3, 4]


def _gestor(user):
    if user["role"] != "gestor":
        raise HTTPException(403, "Somente a gestão")


def _check_term(body: TermIn):
    a, b = _date(body.start_date, "início"), _date(body.end_date, "fim")
    if b < a:
        raise HTTPException(400, "O fim precisa ser depois do início")
    if (b - a).days > 400:
        raise HTTPException(400, "Um período letivo não pode passar de 400 dias")
    if not body.weekdays or any(w not in range(7) for w in body.weekdays):
        raise HTTPException(400, "Escolha os dias da semana com aula")
    if not body.name.strip():
        raise HTTPException(400, "Dê um nome ao período (ex.: 1º semestre 2026)")


@router.post("/periodos")
def criar_periodo(body: TermIn, user=Depends(current_user), conn=Depends(get_db)):
    _gestor(user)
    _check_term(body)
    tid = conn.execute("INSERT INTO academic_terms (institution_id, name, start_date, end_date, weekdays) VALUES (?,?,?,?,?)",
                       (user["institution_id"], body.name.strip(), body.start_date, body.end_date, jdump(sorted(set(body.weekdays))))).lastrowid
    audit(conn, user, "calendario.periodo", f"{body.name} ({body.start_date} a {body.end_date})")
    return {"id": tid}


@router.put("/periodos/{tid}")
def editar_periodo(tid: int, body: TermIn, user=Depends(current_user), conn=Depends(get_db)):
    _gestor(user)
    _check_term(body)
    n = conn.execute("UPDATE academic_terms SET name=?, start_date=?, end_date=?, weekdays=? WHERE id=? AND institution_id=?",
                     (body.name.strip(), body.start_date, body.end_date, jdump(sorted(set(body.weekdays))), tid, user["institution_id"])).rowcount
    if not n:
        raise HTTPException(404, "Período não encontrado")
    return {"ok": True}


@router.delete("/periodos/{tid}")
def excluir_periodo(tid: int, user=Depends(current_user), conn=Depends(get_db)):
    _gestor(user)
    conn.execute("DELETE FROM academic_terms WHERE id=? AND institution_id=?", (tid, user["institution_id"]))
    return {"ok": True}


# ------------------------------------------------------------------ eventos (gestão; professor nas próprias turmas)

class EventIn(BaseModel):
    kind: str
    title: str
    date: str
    end_date: str | None = None
    class_id: int | None = None
    description: str = ""
    notify: bool = True


def _check_event(conn, user, body: EventIn):
    if body.kind not in TIPOS:
        raise HTTPException(400, "Tipo de evento inválido")
    if not body.title.strip():
        raise HTTPException(400, "Dê um título ao evento")
    a = _date(body.date, "data")
    if body.end_date:
        b = _date(body.end_date, "data final")
        if b < a or (b - a).days > 120:
            raise HTTPException(400, "Data final inválida (até 120 dias depois do início)")
    if user["role"] == "professor":
        if body.kind not in ("prova", "evento", "aula_extra"):
            raise HTTPException(403, "Professores podem marcar provas, eventos e aulas extras; feriados e recessos são da gestão")
        if not body.class_id or body.class_id not in (_classes_of(conn, user) or []):
            raise HTTPException(400, "Escolha uma das suas turmas")
    elif user["role"] == "gestor":
        if body.class_id and not one(conn.execute("SELECT id FROM classes WHERE id=? AND institution_id=?",
                                                  (body.class_id, user["institution_id"]))):
            raise HTTPException(400, "Turma inválida")
    else:
        raise HTTPException(403, "Sem permissão para editar o calendário")


def _avisar(conn, user, body: EventIn, eid: int):
    if not body.notify:
        return
    if body.class_id:
        alvo = [r[0] for r in conn.execute("SELECT user_id FROM class_students WHERE class_id=?", (body.class_id,))]
        alvo += [r[0] for r in conn.execute("SELECT DISTINCT teacher_id FROM subjects WHERE class_id=? AND active=1", (body.class_id,))]
    else:
        alvo = [r[0] for r in conn.execute("SELECT id FROM users WHERE institution_id=? AND status='ativo' AND role IN ('aluno','professor')",
                                           (user["institution_id"],))]
    quando = date.fromisoformat(body.date).strftime("%d/%m")
    for uid in set(alvo):
        if uid != user["id"]:
            notify(conn, uid, f"Calendário: {TIPOS[body.kind]} — {body.title.strip()} ({quando})", "Calendário",
                   f"#/calendario?mes={body.date[:7]}")


@router.post("/eventos")
def criar_evento(body: EventIn, user=Depends(current_user), conn=Depends(get_db)):
    _check_event(conn, user, body)
    eid = conn.execute(
        "INSERT INTO calendar_events (institution_id, class_id, kind, title, description, date, end_date, created_by) VALUES (?,?,?,?,?,?,?,?)",
        (user["institution_id"], body.class_id, body.kind, body.title.strip()[:150], body.description[:1000], body.date,
         body.end_date if body.end_date and body.end_date != body.date else None, user["id"])).lastrowid
    _avisar(conn, user, body, eid)
    audit(conn, user, "calendario.evento", f"{TIPOS[body.kind]}: {body.title.strip()} ({body.date})")
    return {"id": eid}


def _own_event(conn, user, eid: int) -> dict:
    e = one(conn.execute("SELECT * FROM calendar_events WHERE id=? AND institution_id=?", (eid, user["institution_id"])))
    if not e:
        raise HTTPException(404, "Evento não encontrado")
    if user["role"] == "professor" and e["created_by"] != user["id"]:
        raise HTTPException(403, "Você só pode alterar eventos que criou")
    if user["role"] == "aluno":
        raise HTTPException(403, "Sem permissão")
    return e


@router.put("/eventos/{eid}")
def editar_evento(eid: int, body: EventIn, user=Depends(current_user), conn=Depends(get_db)):
    _own_event(conn, user, eid)
    _check_event(conn, user, body)
    conn.execute("UPDATE calendar_events SET class_id=?, kind=?, title=?, description=?, date=?, end_date=? WHERE id=?",
                 (body.class_id, body.kind, body.title.strip()[:150], body.description[:1000], body.date,
                  body.end_date if body.end_date and body.end_date != body.date else None, eid))
    return {"ok": True}


@router.delete("/eventos/{eid}")
def excluir_evento(eid: int, user=Depends(current_user), conn=Depends(get_db)):
    e = _own_event(conn, user, eid)
    conn.execute("DELETE FROM calendar_events WHERE id=?", (eid,))
    audit(conn, user, "calendario.evento_excluido", f"{e['title']} ({e['date']})")
    return {"ok": True}


@router.get("/dias-semana")
def dias_semana():
    return DIAS
