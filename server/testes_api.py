"""Testes automáticos da API do EDU.AI.

Sobe um servidor próprio (porta 8799) com um banco TEMPORÁRIO — o banco real não é tocado —
e confere as regras de segurança, de notas e os recursos de atendimento e calendário.
Também sobe uma "IA em nuvem" falsa (porta 8798) para conferir o link e a chave da API da instituição.

Uso (dentro de server/):   .venv\\Scripts\\python.exe testes_api.py
Sai com código 0 se tudo passar.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PORTA = 8799
BASE = f"http://127.0.0.1:{PORTA}"
SENHA = "Teste@2026"
falhas: list[str] = []
PORTA_IA = 8798
pedidos_ia: list[dict] = []


class IAFalsa(BaseHTTPRequestHandler):
    """Imita uma API "chat completions": guarda o pedido e responde texto ou um quiz em JSON."""

    def do_POST(self):  # noqa: N802
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        pedidos_ia.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": corpo})
        if "response_format" in corpo:
            texto = json.dumps({"questions": [{"question": f"Pergunta {i} da nuvem?", "options": ["A", "B", "C", "D"],
                                               "answer": 1, "explanation": "Porque sim."} for i in range(5)]})
        else:
            texto = "Resposta da IA em nuvem"
        out = json.dumps({"choices": [{"message": {"content": texto}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_):
        pass


def req(metodo, caminho, corpo=None, token=None, form=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        limite = "----edu-teste"
        partes = []
        for k, v in form.items():
            if isinstance(v, tuple):  # (nome_arquivo, bytes)
                partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"; filename="{v[0]}"\r\n'
                              f"Content-Type: application/octet-stream\r\n\r\n".encode() + v[1] + b"\r\n")
            else:
                partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        data = b"".join(partes) + f"--{limite}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={limite}"
    elif corpo is not None:
        data = json.dumps(corpo).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + "/api" + caminho, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(r, timeout=60) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if x.headers.get("content-type", "").startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def ok(cond, nome, extra=""):
    print(("  ok   " if cond else "  FALHOU ") + nome + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        falhas.append(nome)


def login(email, inst="escola-teste", senha=SENHA):
    st, r = req("POST", "/auth/login", {"institution": inst, "email": email, "password": senha})
    assert st == 200, (email, st, r)
    return r["token"]


def login_admin(email="admin@plataforma.edu.br", senha=SENHA):
    st, r = req("POST", "/auth/admin-login", {"email": email, "password": senha})
    assert st == 200, (email, st, r)
    return r["token"]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="edu-teste-"))
    env = {**os.environ, "EDU_DB": str(tmp / "edu.db"), "OLLAMA_URL": "http://127.0.0.1:9",  # sem IA: modo local
           "EDU_IA_PROVIDER": "ollama", "EDU_SMTP_HOST": ""}
    ia_falsa = HTTPServer(("127.0.0.1", PORTA_IA), IAFalsa)
    threading.Thread(target=ia_falsa.serve_forever, daemon=True).start()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORTA)],
                           cwd=Path(__file__).parent, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE + "/api/config", timeout=1)
                break
            except OSError:
                time.sleep(0.25)
        else:
            sys.exit("servidor de teste não subiu")
        executar()
    finally:
        srv.terminate()
        srv.wait(10)
    print(f"\n{'TUDO CERTO' if not falhas else f'{len(falhas)} FALHA(S)'}")
    sys.exit(1 if falhas else 0)


def executar():
    prof, aluno, gestor = login("professor@escolateste.edu.br"), login("aluno@escolateste.edu.br"), login("gestor@escolateste.edu.br")

    print("\nIsolamento entre escolas")
    st, nova = req("POST", "/onboarding", {"name": "Escola Isolada", "admin_name": "G", "admin_email": "g@isolada.br",
                                           "admin_password": "12345678", "plan": "Rede"})
    gb = nova["token"]
    ok(req("GET", "/gestor/plan", token=gb)[1]["plan"] == "Essencial", "cadastro público começa no plano Essencial")
    st, r = req("PUT", "/gestor/plan", {"plan": "Rede"}, gb)
    ok(st == 200 and r.get("requested") and req("GET", "/gestor/plan", token=gb)[1]["plan"] == "Essencial",
       "gestor só PEDE a troca de plano")
    cb = req("POST", "/gestor/classes", {"name": "Turma B"}, gb)[1]["id"]
    s = req("GET", "/prof/subjects", token=prof)[1][0]
    st, _ = req("PUT", f"/prof/subjects/{s['id']}", {"description": "x", "color": "#123456", "class_id": cb}, prof)
    ok(req("GET", f"/prof/classes/{cb}", token=prof)[0] == 404, "professor não alcança turma de outra escola")
    ok(req("DELETE", f"/gestor/classes/{cb}", token=gestor)[0] == 404, "gestor não exclui turma de outra escola")
    ok(req("POST", "/prof/subjects", {"name": "X"}, prof)[0] == 403, "professor não cria disciplina")
    st, _ = req("PUT", f"/gestor/subjects/{s['id']}", {"class_id": cb, "teacher_id": 1, "name": "X"}, gestor)
    ok(st == 400, "gestor não vincula disciplina a turma de outra escola", st)
    ok(req("POST", "/gestor/invites", {"emails": ["a@b.br"], "role": "aluno", "class_id": cb}, gestor)[0] == 400,
       "convite não aponta para turma de outra escola")

    print("\nDisciplinas pela gestão")
    turmas = req("GET", "/gestor/classes", token=gestor)[1]
    profs = req("GET", "/gestor/users?role=professor", token=gestor)[1]
    p2 = next(p for p in profs if p["email"].startswith("professor2"))
    st, r = req("POST", "/gestor/subjects", {"class_id": turmas[0]["id"], "teacher_id": p2["id"], "name": "Filosofia"}, gestor)
    ok(st == 200, "gestor cria disciplina e escolhe o professor")
    nova_sid = r["id"]
    t2 = login("professor2@escolateste.edu.br")
    ok(any(x["id"] == nova_sid for x in req("GET", "/prof/subjects", token=t2)[1]), "professor vê a disciplina vinculada")
    ok(req("DELETE", f"/gestor/subjects/{nova_sid}", token=gestor)[0] == 200, "disciplina sem conteúdo pode ser excluída")

    print("\nAtividades, prazo e gabarito")
    meus = {x["id"] for x in req("GET", "/aluno/subjects", token=aluno)[1]}
    sub = next(x for x in req("GET", "/prof/subjects", token=prof)[1] if x["id"] in meus)
    qids = []
    for i in range(3):
        qids.append(req("POST", "/prof/questions", {"subject_id": sub["id"], "statement": f"Pergunta teste {i}",
                                                    "options": ["a", "b", "c", "d"], "answer": (i + 1) % 4}, prof)[1]["id"])
    ontem = (date.today() - timedelta(days=1)).isoformat()
    amanha = (date.today() + timedelta(days=1)).isoformat()
    aid = req("POST", "/prof/activities", {"subject_id": sub["id"], "title": "Vencida", "due_date": ontem, "question_ids": qids}, prof)[1]["id"]
    req("POST", f"/prof/activities/{aid}/publish", {}, prof)
    st, r = req("POST", f"/aluno/activities/{aid}/submit", {"answers": {}}, aluno)
    ok(st == 400, "prazo vencido recusa a entrega", (st, r))
    aid2 = req("POST", "/prof/activities", {"subject_id": sub["id"], "title": "Atrasada aceita", "due_date": ontem,
                                            "accept_late": True, "question_ids": qids}, prof)[1]["id"]
    req("POST", f"/prof/activities/{aid2}/publish", {}, prof)
    st, r = req("POST", f"/aluno/activities/{aid2}/submit", {"answers": {}}, aluno)
    ok(st == 200 and r.get("late"), "com 'aceitar atraso' a entrega entra marcada como atrasada", (st, r))
    aid3 = req("POST", "/prof/activities", {"subject_id": sub["id"], "title": "Duas tentativas", "due_date": amanha,
                                            "max_attempts": 2, "question_ids": qids}, prof)[1]["id"]
    req("POST", f"/prof/activities/{aid3}/publish", {}, prof)
    req("POST", f"/aluno/activities/{aid3}/submit", {"answers": {}}, aluno)
    r = req("GET", f"/aluno/activities/{aid3}/result", token=aluno)[1]
    ok(all(i["answer"] is None for i in r["items"]) and not r["answers_released"], "gabarito escondido enquanto há tentativa")
    req("POST", f"/aluno/activities/{aid3}/submit", {"answers": {}}, aluno)
    r = req("GET", f"/aluno/activities/{aid3}/result", token=aluno)[1]
    ok(all(i["answer"] is not None for i in r["items"]), "gabarito liberado depois da última tentativa")
    ok(req("POST", f"/aluno/activities/{aid3}/submit", {"answers": {}}, aluno)[0] == 400, "terceira tentativa recusada")

    print("\nFlashcards")
    decks = req("GET", "/aluno/materials?type=flashcards", token=aluno)[1]
    if decks:
        ok(req("POST", "/aluno/flashcards/review", {"material_id": decks[0]["id"], "card": 999, "rating": "facil"}, aluno)[0] == 400,
           "cartão inexistente é recusado")

    print("\nSessão e senha")
    t_antigo = login("aluno02@escolateste.edu.br")
    st, r = req("POST", "/me/password", {"current": SENHA, "new": "NovaSenha@1"}, t_antigo)
    ok(st == 200 and r.get("token"), "troca de senha devolve sessão nova")
    ok(req("GET", "/me", token=t_antigo)[0] == 401, "sessão antiga é encerrada após trocar a senha")
    ok(req("GET", "/me", token=r["token"])[0] == 200, "sessão nova funciona")
    st, r = req("POST", "/auth/forgot", {"institution": "escola-teste", "email": "aluno03@escolateste.edu.br"})
    ok(st == 200, "esqueci minha senha responde")
    for _ in range(8):
        req("POST", "/auth/login", {"institution": "escola-teste", "email": "aluno04@escolateste.edu.br", "password": "errada"})
    ok(req("POST", "/auth/login", {"institution": "escola-teste", "email": "aluno04@escolateste.edu.br", "password": SENHA})[0] == 429,
       "força bruta bloqueada após 8 tentativas")

    print("\nVerificação em duas etapas")
    sys.path.insert(0, str(Path(__file__).parent))
    from app.seguranca import _codigo  # noqa: PLC0415
    t5 = login("aluno05@escolateste.edu.br")
    seg = req("POST", "/me/2fa/setup", {}, t5)[1]["secret"]
    codigo = _codigo(seg, int(time.time() // 30))
    ok(req("POST", "/me/2fa/enable", {"code": codigo}, t5)[0] == 200, "ativa a verificação em duas etapas")
    st, r = req("POST", "/auth/login", {"institution": "escola-teste", "email": "aluno05@escolateste.edu.br", "password": SENHA})
    ok(st == 200 and r.get("needs_2fa") and "token" not in r, "login pede o código do autenticador")
    ok(req("GET", "/me", token=r["ticket"])[0] == 401, "comprovante do 1º passo não vale como sessão")
    ok(req("POST", "/auth/2fa", {"ticket": r["ticket"], "code": _codigo(seg, int(time.time() // 30))})[0] == 200, "código certo entra")

    print("\nAtendimento / ouvidoria")
    st, r = req("POST", "/chamados", form={"category": "documento", "document_type": "Declaração de matrícula",
                                           "subject": "Para o estágio", "body": "Preciso da declaração, por favor."}, token=aluno)
    ok(st == 200 and r["protocol"], "aluno abre chamado pedindo documento")
    tid = r["id"]
    st, _ = req("POST", f"/chamados/{tid}/mensagens", form={"body": "Segue a declaração.", "status": "resolvido",
                                                           "file": ("declaracao.pdf", b"%PDF-1.4 teste")}, token=gestor)
    ok(st == 200, "gestão responde com o documento anexado")
    d = req("GET", f"/chamados/{tid}", token=aluno)[1]
    ok(d["status"] == "resolvido" and d["messages"][-1]["attachment_name"] == "declaracao.pdf", "aluno vê resposta e anexo")
    mid = d["messages"][-1]["id"]
    ok(req("GET", f"/chamados/{tid}/anexo/{mid}", token=aluno)[0] == 200, "aluno baixa o anexo")
    outro = login("aluno06@escolateste.edu.br")
    ok(req("GET", f"/chamados/{tid}", token=outro)[0] == 404, "outro aluno não vê o chamado")
    st, r = req("POST", "/chamados", form={"category": "denuncia", "subject": "Bullying no intervalo",
                                           "body": "Relato anônimo.", "anonymous": "true"}, token=outro)
    lista = req("GET", "/chamados", token=gestor)[1]
    den = next((t for t in lista if t["id"] == r.get("id")), {"requester": None, "debug": r})
    ok(den["requester"] == "Anônimo" and "user_id" not in den, "denúncia anônima esconde a identidade da gestão", den.get("debug"))
    ok(req("POST", "/chamados", form={"category": "x", "subject": "abc", "body": "abcdef"}, token=aluno)[0] == 400, "categoria inválida recusada")

    print("\nCalendário escolar")
    ano = date.today().year
    st, _ = req("POST", "/calendario/periodos", {"name": f"Ano letivo {ano}", "start_date": f"{ano}-01-01",
                                                 "end_date": f"{ano}-12-31", "weekdays": [0, 1, 2, 3, 4]}, gestor)
    ok(st == 200, "gestão define o período letivo e os dias de aula")
    seg_feira = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    if seg_feira.year == ano:
        req("POST", "/calendario/eventos", {"kind": "feriado", "title": "Feriado teste", "date": seg_feira.isoformat()}, gestor)
        cal = req("GET", f"/calendario?mes={seg_feira.isoformat()[:7]}", token=aluno)[1]
        dia = next(d for d in cal["days"] if d["date"] == seg_feira.isoformat())
        ok(not dia["class_day"] and dia["events"], "aluno vê o feriado e o dia sem aula")
        terca = (seg_feira + timedelta(days=1)).isoformat()
        dia2 = next((d for d in cal["days"] if d["date"] == terca), None)
        ok(dia2 is None or dia2["class_day"], "dia letivo normal aparece com aula")
    ok(req("POST", "/calendario/eventos", {"kind": "feriado", "title": "x", "date": f"{ano}-05-05"}, prof)[0] == 403,
       "professor não cria feriado")
    ok(req("POST", "/calendario/eventos", {"kind": "feriado", "title": "x", "date": f"{ano}-05-05"}, aluno)[0] == 403,
       "aluno não edita o calendário")

    print("\nPrática não entrega gabarito de atividade em andamento")
    mats = req("GET", "/aluno/materials?type=exercicios", token=aluno)[1]
    if mats:
        m = req("GET", f"/aluno/materials/{mats[0]['id']}", token=aluno)[1]
        alvo = next((x for x in req("GET", "/prof/materials?type=exercicios", token=prof)[1] if x["id"] == m["id"]), None)
        if alvo:
            req("POST", f"/prof/materials/{m['id']}/to-bank", {}, prof)
            banco = [q for q in req("GET", f"/prof/questions?subject_id={m['subject_id']}", token=prof)[1] if q["material_id"] == m["id"]]
            aidp = req("POST", "/prof/activities", {"subject_id": m["subject_id"], "title": "Prova com questões da prática",
                                                    "due_date": amanha, "question_ids": [banco[0]["id"]]}, prof)[1]["id"]
            req("POST", f"/prof/activities/{aidp}/publish", {}, prof)
            idx = next(i for i, q in enumerate(m["content"]["questions"]) if q["statement"] == banco[0]["statement"])
            r = req("POST", f"/aluno/materials/{m['id']}/check", {"index": idx, "answer": 0}, aluno)[1]
            ok(r.get("locked") and "answer" not in r, "conferência bloqueada enquanto a prova está aberta")

    print("\nTodas as telas respondem")
    telas = {
        prof: ["/me", "/prof/overview", "/prof/subjects", "/prof/classes", "/prof/documents", "/prof/materials", "/prof/questions",
               "/prof/activities", "/prof/performance", "/jogos", "/notifications", "/calendario", "/calendario/proximos",
               "/chamados", "/chamados/opcoes", "/ia/status", "/prof/studio/jobs"],
        aluno: ["/aluno/home", "/aluno/subjects", "/aluno/materials", "/aluno/activities", "/aluno/flashcards/due", "/aluno/progress",
                "/calendario", "/calendario/proximos", "/chamados"],
        gestor: ["/gestor/dashboard", "/gestor/institution", "/gestor/users", "/gestor/invites", "/gestor/classes", "/gestor/subjects",
                 "/gestor/contents", "/gestor/reports", "/gestor/plan", "/gestor/settings", "/gestor/audit", "/gestor/data-requests",
                 "/calendario", "/chamados", "/chamados/resumo/gestao"],
    }
    for tok, caminhos in telas.items():
        for c in caminhos:
            st, _ = req("GET", c, token=tok)
            ok(st == 200, f"GET {c}", st)
    admin = login_admin()
    for c in ("/plataforma/resumo", "/plataforma/usuarios", "/plataforma/pedidos-plano", "/plataforma/faturas",
              "/plataforma/administradores", "/chamados", "/chamados/resumo/gestao", "/chat/conversas", "/me/ia"):
        ok(req("GET", c, token=admin)[0] == 200, f"GET {c} (admin geral)")
    secretaria = login("secretaria@escolateste.edu.br")
    for c in ("/secretaria/resumo", "/secretaria/alunos", "/secretaria/turmas", "/secretaria/declaracoes/modelos",
              "/secretaria/documentos", "/chamados", "/chamados/resumo/gestao", "/calendario", "/chat/conversas", "/me/ia"):
        ok(req("GET", c, token=secretaria)[0] == 200, f"GET {c} (secretaria)")
    for c in ("/aprendizado/opcoes", "/aprendizado/jogos", "/aprendizado/professor/alunos", "/gestor/ia-nuvem"):
        tok = gestor if c.startswith("/gestor") else prof
        ok(req("GET", c, token=tok)[0] == 200, f"GET {c}")
    ok(req("GET", "/aprendizado/jogos", token=aluno)[0] == 200 and req("GET", "/documentos/meus", token=aluno)[0] == 200,
       "GET telas novas do aluno")

    print("\nLogin do administrador geral")
    st, _ = req("POST", "/auth/login", {"institution": "plataforma", "email": "admin@plataforma.edu.br", "password": SENHA})
    ok(st == 403, "admin geral não entra pelo login das instituições", st)
    ok(req("POST", "/auth/admin-login", {"email": "gestor@escolateste.edu.br", "password": SENHA})[0] == 401,
       "gestor de escola não entra pelo login administrativo")
    ok(req("GET", "/plataforma/resumo", token=gestor)[0] == 403, "gestor não acessa a administração geral")
    ok(req("GET", "/secretaria/alunos", token=prof)[0] == 403, "professor não acessa a secretaria")

    print("\nAdministradores gerais")
    st, novo = req("POST", "/plataforma/administradores", {"name": "Terceira Admin", "email": "admin3@plataforma.edu.br",
                                                           "password": "SenhaForte@123"}, admin)
    ok(st == 200, "admin geral cadastra outro administrador", st)
    a3 = login_admin("admin3@plataforma.edu.br", "SenhaForte@123")
    ok(req("GET", "/plataforma/resumo", token=a3)[0] == 200, "novo administrador acessa o painel")
    me = req("GET", "/me", token=admin)[1]
    ok(req("PUT", f"/plataforma/administradores/{me['id']}", {"status": "inativo"}, admin)[0] == 400,
       "admin não desativa a própria conta")
    ok(req("PUT", f"/plataforma/administradores/{novo['id']}", {"status": "inativo"}, admin)[0] == 200
       and req("GET", "/plataforma/resumo", token=a3)[0] == 401, "admin desativado perde o acesso")

    print("\nInstituições e faturas")
    st, inst = req("POST", "/plataforma/instituicoes", {"name": "Colégio Fatura", "plan": "Essencial", "cnpj": "11.111.111/0001-11",
                                                        "admin_name": "Gestora F", "admin_email": "g@fatura.br",
                                                        "admin_password": "12345678", "first_invoice": True}, admin)
    ok(st == 200, "admin geral cadastra instituição", st)
    fats = req("GET", f"/plataforma/faturas?institution_id={inst['id']}", token=admin)[1]
    ok(len(fats) == 1 and fats[0]["amount"] == 490, "primeira fatura emitida com o preço do plano", fats)
    gf = login("g@fatura.br", inst["slug"], "12345678")
    ok(len(req("GET", "/gestor/faturas", token=gf)[1]) == 1, "gestor vê as faturas da própria instituição")
    ok(req("PUT", f"/plataforma/faturas/{fats[0]['id']}", {"status": "paga", "payment_method": "PIX"}, admin)[0] == 200
       and req("GET", "/gestor/faturas", token=gf)[1][0]["status"] == "paga", "admin geral dá baixa na fatura")
    ref = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    r1 = req("POST", "/plataforma/faturas/gerar-mes", {"reference": ref, "due_day": 5}, admin)[1]
    r2 = req("POST", "/plataforma/faturas/gerar-mes", {"reference": ref, "due_day": 5}, admin)[1]
    ok(r1["criadas"] >= 2 and r2["criadas"] == 0, "mensalidade do mês gerada sem duplicar", (r1, r2))
    ok(all(f["institution"] != "EDU.AI · Administração" for f in req("GET", "/plataforma/faturas", token=admin)[1]),
       "a instituição interna da plataforma não recebe fatura")
    ok(req("GET", "/gestor/faturas", token=gestor)[0] == 200 and
       all(f["status"] != "cancelada" for f in req("GET", "/gestor/faturas", token=gestor)[1]), "gestor da escola vê as faturas")

    print("\nChamados: secretaria, gestão e plataforma")
    st, t1 = req("POST", "/chamados", token=aluno, form={"category": "documento", "subject": "Para o estágio", "body": "Preciso da declaração",
                                                         "document_type": "Declaração de matrícula", "target": "secretaria",
                                                         "file": ("rg.pdf", b"%PDF-1.4 teste")})
    ok(st == 200, "aluno abre chamado para a secretaria com anexo", st)
    ok(any(t["id"] == t1["id"] for t in req("GET", "/chamados", token=secretaria)[1]), "secretaria vê o chamado na fila")
    st, tk2 = req("POST", "/chamados", token=secretaria, form={"category": "recursos", "subject": "Impressora", "body": "Sem toner na secretaria",
                                                              "target": "gestao", "file": ("foto.png", b"\x89PNG teste")})
    ok(st == 200, "secretaria abre chamado para a gestão com anexo", st)
    ok(not any(t["id"] == tk2["id"] for t in req("GET", "/chamados", token=secretaria)[1]), "chamado da secretaria não cai na própria fila")
    ok(any(t["id"] == tk2["id"] for t in req("GET", "/chamados", token=gestor)[1]), "gestor recebe o chamado da secretaria")
    ok(req("POST", "/chamados", token=secretaria, form={"category": "suporte", "subject": "xxx", "body": "yyyyyy", "target": "plataforma"})[0] == 400,
       "secretaria não abre chamado direto para a plataforma")
    st, t3 = req("POST", "/chamados", token=gestor, form={"category": "ia", "subject": "Chave da IA", "body": "Como cadastro a chave?",
                                                          "target": "plataforma", "file": ("print.png", b"\x89PNG")})
    ok(st == 200, "gestor abre chamado para o suporte da plataforma", st)
    ok(any(t["id"] == t3["id"] for t in req("GET", "/chamados", token=admin)[1]), "admin geral vê o chamado do gestor")
    ok(not any(t["id"] == t3["id"] for t in req("GET", "/chamados", token=gestor)[1]), "o chamado do gestor não aparece na fila da escola")
    ok(any(t["id"] == t3["id"] for t in req("GET", "/chamados?mine=1", token=gestor)[1]), "gestor acompanha em “meus chamados”")
    st, _ = req("POST", f"/chamados/{t3['id']}/mensagens", token=admin, form={"body": "Em Configurações → IA em nuvem.",
                                                                              "file": ("guia.pdf", b"%PDF guia")})
    _m = req("GET", f"/chamados/{t3['id']}", token=gestor)[1]["messages"]
    ok(st == 200 and _m[-1]["attachment_name"] == "guia.pdf", "admin geral responde com anexo", (st, _m[-1]))
    ok(req("GET", f"/chamados/{t3['id']}", token=secretaria)[0] == 404, "secretaria não lê chamados da plataforma")
    ok(req("GET", f"/chamados/{tk2['id']}", token=prof)[0] == 404, "professor não lê chamados de outros")

    print("\nSecretaria: foto, carteirinha e declaração")
    al = next(a for a in req("GET", "/secretaria/alunos", token=secretaria)[1] if a["email"] == "aluno@escolateste.edu.br")
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    ok(req("PUT", f"/secretaria/alunos/{al['id']}/foto", {"photo": png}, secretaria)[0] == 200, "secretaria envia a foto do aluno")
    ok(req("PUT", f"/secretaria/alunos/{al['id']}/foto", {"photo": "data:text/html;base64,PGI+"}, secretaria)[0] == 400,
       "foto que não é imagem é recusada")
    st, cart = req("POST", "/secretaria/carteirinhas", {"student_ids": [al["id"]]}, secretaria)
    ok(st == 200 and cart["cards"][0]["photo"] == png and cart["cards"][0]["registration"] and cart["cards"][0]["class_name"],
       "carteirinha puxa foto, matrícula e turma do sistema")
    st, prev = req("POST", "/secretaria/declaracoes/previa", {"student_id": al["id"], "kind": "matricula", "purpose": "estágio"}, secretaria)
    ok(st == 200 and al["name"].upper() in prev["body"] and "Escola Teste" in prev["body"], "declaração montada com os dados do aluno")
    st, dec = req("POST", "/secretaria/declaracoes", {"student_id": al["id"], "kind": "matricula", "purpose": "estágio",
                                                      "ticket_id": t1["id"]}, secretaria)
    ok(st == 200, "secretaria emite a declaração a partir do chamado", st)
    ok(req("GET", f"/chamados/{t1['id']}", token=aluno)[1]["status"] == "resolvido", "o chamado do pedido fica resolvido")
    meus = req("GET", "/documentos/meus", token=aluno)[1]
    ok(any(d["id"] == dec["id"] for d in meus) and req("GET", f"/documentos/meus/{dec['id']}", token=aluno)[0] == 200,
       "aluno vê a declaração em Meus documentos")
    ok(req("GET", f"/documentos/verificar/{dec['code']}")[1].get("valid"), "código de verificação público confere")
    ok(req("GET", f"/secretaria/alunos/{al['id']}", token=gb)[0] in (403, 404), "gestor de outra escola não vê o aluno")

    print("\nIA em nuvem da instituição (link e chave da API)")
    url_ia = f"http://127.0.0.1:{PORTA_IA}/v1"
    st, cfg = req("PUT", "/gestor/ia-nuvem", {"url": url_ia, "key": "sk-chave-secreta-da-escola", "model": "modelo-x",
                                              "default_mode": "nuvem"}, gestor)
    ok(st == 200 and cfg["ready"] and "sk-chave" not in json.dumps(cfg), "gestor cadastra link e chave (a chave não volta)")
    ok("sk-chave" not in json.dumps(req("GET", "/gestor/settings", token=gestor)[1]), "configurações não expõem a chave")
    ok(req("POST", "/gestor/ia-nuvem/testar", {}, gestor)[1].get("ok"), "teste de conexão com a IA em nuvem")
    ok(req("PUT", "/gestor/ia-nuvem", {"url": "ftp://x"}, gestor)[0] == 400, "link da API inválido é recusado")
    ok(req("PUT", "/gestor/ia-nuvem", {"key": "x"}, prof)[0] == 403, "professor não altera a chave da instituição")
    cid = req("POST", "/chat/conversas", {}, aluno)[1]["id"]
    pedidos_ia.clear()
    st, resp = req("POST", f"/chat/conversas/{cid}/mensagens", {"text": "Me explique frações"}, aluno)
    ok(st == 200 and resp["content"] == "Resposta da IA em nuvem" and resp["mode"] == "nuvem",
       "aluno usa a IA em nuvem da instituição no chat", resp)
    ok(pedidos_ia and pedidos_ia[-1]["auth"] == "Bearer sk-chave-secreta-da-escola"
       and pedidos_ia[-1]["path"] == "/v1/chat/completions" and pedidos_ia[-1]["body"]["model"] == "modelo-x",
       "a chave e o link da instituição são usados no pedido")
    st, resp = req("POST", f"/chat/conversas/{cid}/mensagens", {"text": "E decimais?", "mode": "local"}, aluno)
    ok(st == 200 and resp["mode"] == "local" and not resp["ok"], "aluno alterna para a IA local no chat (sem Ollama: avisa)")
    ok(req("GET", "/me/ia", token=aluno)[1]["mode"] == "local", "preferência fica salva no perfil")
    ok(req("PUT", "/me/ia", {"mode": "nuvem"}, aluno)[0] == 200 and req("GET", "/ia/status", token=aluno)[1]["mode"] == "nuvem",
       "aluno volta para a nuvem nas configurações")
    sec_status = req("GET", "/ia/status", token=secretaria)[1]
    ok(sec_status["mode"] == "nuvem" and sec_status["provider"] == "nuvem", "a configuração vale para a secretaria")
    ok(len(req("GET", f"/chat/conversas/{cid}", token=aluno)[1]["messages"]) == 4, "conversa guardada")
    ok(req("GET", f"/chat/conversas/{cid}", token=prof)[0] == 404, "ninguém lê a conversa de outra pessoa")
    req("PUT", "/me/ia", {"mode": "nuvem", "url": "", "key": "-"}, admin)
    ok(req("GET", "/ia/status", token=admin)[1]["mode"] == "local", "admin geral sem chave própria usa a IA local")
    req("PUT", "/me/ia", {"mode": "nuvem", "url": url_ia, "key": "sk-chave-do-admin"}, admin)
    cadm = req("POST", "/chat/conversas", {}, admin)[1]["id"]
    pedidos_ia.clear()
    resp = req("POST", f"/chat/conversas/{cadm}/mensagens", {"text": "Resumo das faturas"}, admin)[1]
    ok(resp["content"] == "Resposta da IA em nuvem" and pedidos_ia[-1]["auth"] == "Bearer sk-chave-do-admin",
       "admin geral usa a própria chave da API")
    ok("sk-chave" not in json.dumps(req("GET", "/me/ia", token=admin)[1]), "a chave do admin não volta para a tela")

    print("\nAprendizado gamificado")
    mats = req("GET", "/aprendizado/opcoes", token=aluno)[1]["materials"]
    st, jogo = req("POST", "/aprendizado/gerar", {"kind": "quiz", "material_id": mats[0]["id"]}, aluno)
    ok(st == 200 and len(jogo["content"]["questions"]) == 5 and jogo["ai_source"].startswith("nuvem"),
       "aluno gera quiz com a IA em nuvem a partir de um material", st)
    req("PUT", "/me/ia", {"mode": "local"}, aluno)
    for k in ("memoria", "verdadeiro_falso", "completar", "adivinhacao", "programacao"):
        st, g = req("POST", "/aprendizado/gerar", {"kind": k, "topic": "Funções do 1º grau",
                                                   "text": "A função afim f(x) = ax + b tem coeficiente angular a e coeficiente linear b. "
                                                           "Quando a é positivo a função é crescente. A raiz é x = -b/a."}, aluno)
        ok(st == 200 and g["content"], f"jogo “{k}” gerado (modo local)", st)
    st, p = req("POST", f"/aprendizado/jogos/{jogo['id']}/partidas", {"score": 300, "max_score": 500, "correct": 3, "total": 5,
                                                                      "details": [{"q": "Pergunta 0", "ok": False, "answer": "A", "right": "B"}]}, aluno)
    ok(st == 200 and p["best"] == 300, "partida registrada")
    ok(req("POST", f"/aprendizado/jogos/{jogo['id']}/partidas", {"score": 900, "max_score": 500, "correct": 3, "total": 5}, aluno)[0] == 400,
       "pontuação impossível é recusada")
    alunos_prof = req("GET", "/aprendizado/professor/alunos", token=prof)[1]["students"]
    eu = next((a for a in alunos_prof if a["name"] == al["name"]), None)
    ok(eu and eu["plays"] >= 1, "professor vê o aprendizado do aluno")
    det = req("GET", f"/aprendizado/professor/alunos/{al['id']}", token=prof)[1]
    ok(det["top_errors"] and det["top_errors"][0]["q"] == "Pergunta 0", "professor vê onde o aluno errou")
    ok(req("GET", f"/aprendizado/jogos/{jogo['id']}", token=prof)[0] == 200, "professor abre o jogo do aluno")
    ok(req("GET", f"/aprendizado/professor/alunos/{al['id']}", token=t2)[0] == 404, "professor de fora não vê o aluno")
    op = req("GET", "/aprendizado/opcoes", token=prof)[1]
    st, gp = req("POST", "/aprendizado/gerar", {"kind": "memoria", "document_id": op["documents"][0]["id"],
                                                "class_id": op["classes"][0]["id"]}, prof)
    ok(st == 200 and gp["class_id"], "professor cria jogo para a turma", st)
    turma_aluno = req("GET", "/aprendizado/jogos", token=aluno)[1]["turma"]
    ok(isinstance(turma_aluno, list), "aluno lista os jogos da turma")
    ok(req("DELETE", f"/aprendizado/jogos/{jogo['id']}", token=prof)[0] == 403, "professor não apaga o jogo do aluno")

    print("\nIA (modo local, sem Ollama)")
    st, s_ia = req("GET", "/ia/status", token=gb)   # escola sem IA em nuvem cadastrada
    ok(st == 200 and s_ia["provider"] == "simulada" and s_ia["provider_name"] == "ollama", "status do provedor de IA")


if __name__ == "__main__":
    main()
