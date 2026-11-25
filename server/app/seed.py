"""Dados de teste: uma escola completa e os administradores gerais da plataforma.

Criados automaticamente na inicialização quando o banco está vazio (sem usuários).
Para zerar o banco e recriar tudo:  .venv\\Scripts\\python.exe resetar_banco.py --confirmar

Senha de todas as contas: Teste@2026

  Instituição "plataforma" (administradores gerais da plataforma):
    admin@plataforma.edu.br · admin2@plataforma.edu.br
  Instituição "escola-teste":
    gestores:    gestor@escolateste.edu.br · gestor2@escolateste.edu.br
    secretaria:  secretaria@escolateste.edu.br
    professores: professor@escolateste.edu.br (com dados) · professor2@… · professor3@… (sem dados)
    alunos:      aluno@escolateste.edu.br · aluno02@… até aluno18@escolateste.edu.br
"""
import random
import time

from . import ia
from .auth import hash_password
from .db import connect, jdump, jload, meta_get, meta_set, one
from .scoring import submit

PASSWORD = "Teste@2026"

FUNCOES = """Funções do 1º grau

Uma função do 1º grau, também chamada de função afim, é toda função da forma f(x) = ax + b, em que a e b são números reais e a é diferente de zero. O número a é o coeficiente angular e o número b é o coeficiente linear.

O coeficiente angular a indica a inclinação da reta. Quando a é positivo, a função é crescente: à medida que x aumenta, f(x) também aumenta. Quando a é negativo, a função é decrescente: à medida que x aumenta, f(x) diminui.

O coeficiente linear b indica o ponto em que a reta corta o eixo y. Isso acontece porque, quando x = 0, temos f(0) = b. Por exemplo, na função f(x) = 2x + 3, a reta corta o eixo y no ponto (0, 3).

O gráfico de uma função do 1º grau é sempre uma reta. Para desenhá-lo, basta encontrar dois pontos da função, marcá-los no plano cartesiano e traçar a reta que passa por eles.

A raiz ou zero da função é o valor de x para o qual f(x) = 0. Para encontrá-la, resolvemos a equação ax + b = 0, obtendo x = -b/a. A raiz indica o ponto em que a reta corta o eixo x. Na função f(x) = 2x - 6, a raiz é x = 3.

Quando b = 0, a função é chamada de função linear, f(x) = ax, e sua reta passa pela origem do plano cartesiano. Quando a = 0, não temos uma função do 1º grau, mas sim uma função constante.

As funções do 1º grau aparecem em muitas situações do cotidiano: o valor de uma corrida de táxi (bandeirada mais um valor por quilômetro), a conta de água com taxa fixa mais o consumo, ou o salário de um vendedor com parte fixa mais comissão. Em todos esses casos, há um valor fixo (b) e um valor que varia proporcionalmente (a)."""

CELULAS = """Células e organelas

A célula é a menor unidade estrutural e funcional dos seres vivos. Todos os organismos são formados por uma ou mais células. Existem dois tipos principais: as células procariontes, que não têm núcleo organizado, como as bactérias, e as células eucariontes, que possuem núcleo delimitado por membrana, como as de animais, plantas e fungos.

A membrana plasmática envolve a célula e controla a entrada e a saída de substâncias. Ela tem permeabilidade seletiva. O citoplasma é o espaço entre a membrana e o núcleo, preenchido por um líquido chamado citosol, onde ficam as organelas.

O núcleo guarda o material genético (DNA) e coordena as atividades da célula. As mitocôndrias realizam a respiração celular e produzem a energia (ATP) usada pela célula. Os ribossomos produzem proteínas. O retículo endoplasmático transporta substâncias e o complexo golgiense armazena e modifica proteínas.

As células vegetais possuem estruturas exclusivas: a parede celular, feita de celulose, que dá sustentação; os cloroplastos, onde ocorre a fotossíntese; e um grande vacúolo central, que armazena água e substâncias. Os lisossomos, responsáveis pela digestão intracelular, são mais comuns em células animais."""

REVOLUCAO = """Revolução Francesa

A Revolução Francesa começou em 1789 e transformou a política da França e do mundo ocidental. Antes dela, a sociedade francesa era dividida em três estados: o clero (primeiro estado), a nobreza (segundo estado) e o povo, incluindo a burguesia e os camponeses (terceiro estado). Apenas o terceiro estado pagava a maior parte dos impostos.

A crise financeira do reino, a fome provocada por más colheitas e as ideias do Iluminismo, que defendiam liberdade, igualdade e limitação do poder do rei, levaram à convocação dos Estados Gerais. O terceiro estado se declarou Assembleia Nacional e, em 14 de julho de 1789, a população tomou a Bastilha, prisão símbolo do absolutismo.

Em agosto de 1789 foi aprovada a Declaração dos Direitos do Homem e do Cidadão. Entre 1793 e 1794, durante o período do Terror, liderado pelos jacobinos e por Robespierre, milhares de opositores foram executados na guilhotina, inclusive o rei Luís XVI.

A revolução terminou em 1799 com o golpe do 18 Brumário, que levou Napoleão Bonaparte ao poder. O lema 'Liberdade, Igualdade e Fraternidade' tornou-se símbolo dos ideais republicanos."""

RESUMO_FUNCOES = {"sections": [
    {"title": "O que é uma função do 1º grau", "body": "É toda função da forma f(x) = ax + b, com a e b reais e a ≠ 0. O número a é o coeficiente angular e b é o coeficiente linear."},
    {"title": "Coeficiente angular (a)", "body": "Indica a inclinação da reta. Se a > 0, a função é crescente; se a < 0, é decrescente."},
    {"title": "Coeficiente linear (b)", "body": "Indica onde a reta corta o eixo y, pois f(0) = b. Em f(x) = 2x + 3, o ponto é (0, 3)."},
    {"title": "Raiz da função", "body": "É o valor de x em que f(x) = 0, ou seja, x = -b/a. Mostra onde a reta corta o eixo x. Em f(x) = 2x - 6, a raiz é 3."},
    {"title": "No cotidiano", "body": "Corrida de táxi, conta de água e salário com comissão: sempre um valor fixo (b) mais uma parte proporcional (a)."},
], "keywords": ["Função afim", "Coeficiente angular", "Coeficiente linear", "Raiz", "Reta", "Crescente"]}

MAPA_FUNCOES = {"center": "Função do 1º grau", "branches": [
    {"label": "Definição", "color": "#2563EB", "children": ["f(x) = ax + b", "a ≠ 0"]},
    {"label": "Coeficiente a", "color": "#16A34A", "children": ["Inclinação da reta", "a > 0: crescente", "a < 0: decrescente"]},
    {"label": "Coeficiente b", "color": "#DC2626", "children": ["Corta o eixo y", "f(0) = b"]},
    {"label": "Raiz", "color": "#9333EA", "children": ["f(x) = 0", "x = -b/a", "Corta o eixo x"]},
    {"label": "Gráfico", "color": "#EA580C", "children": ["Sempre uma reta", "Dois pontos bastam"]},
    {"label": "Aplicações", "color": "#0891B2", "children": ["Táxi", "Conta de água", "Salário + comissão"]},
]}

FLASH_FUNCOES = {"cards": [
    {"front": "Qual é a forma geral da função do 1º grau?", "back": "f(x) = ax + b, com a ≠ 0."},
    {"front": "O que o coeficiente a indica?", "back": "A inclinação da reta (coeficiente angular)."},
    {"front": "Quando a função é crescente?", "back": "Quando a > 0."},
    {"front": "O que o coeficiente b indica?", "back": "O ponto em que a reta corta o eixo y, pois f(0) = b."},
    {"front": "Como calcular a raiz?", "back": "Resolvendo ax + b = 0, ou seja, x = -b/a."},
    {"front": "Qual é a raiz de f(x) = 2x - 6?", "back": "x = 3."},
    {"front": "O que é uma função linear?", "back": "Uma função do 1º grau com b = 0; a reta passa pela origem."},
    {"front": "Qual é o formato do gráfico?", "back": "Sempre uma reta."},
]}

Q_FUNCOES = [
    {"kind": "objetiva", "statement": "Na função f(x) = 3x + 2, qual é o coeficiente angular?", "options": ["2", "3", "5", "-2"], "answer": 1,
     "explanation": "Na forma f(x) = ax + b, o coeficiente angular é a = 3.", "difficulty": "facil", "topic": "Coeficientes"},
    {"kind": "objetiva", "statement": "A função f(x) = -2x + 5 é:", "options": ["Crescente", "Constante", "Decrescente", "Linear"], "answer": 2,
     "explanation": "Como a = -2 < 0, a função é decrescente.", "difficulty": "facil", "topic": "Coeficientes"},
    {"kind": "objetiva", "statement": "Qual é a raiz da função f(x) = 2x - 6?", "options": ["-3", "6", "2", "3"], "answer": 3,
     "explanation": "2x - 6 = 0 ⇒ x = 3.", "difficulty": "media", "topic": "Raiz e gráfico"},
    {"kind": "objetiva", "statement": "Em que ponto a reta de f(x) = 4x + 1 corta o eixo y?", "options": ["(0, 1)", "(1, 0)", "(0, 4)", "(4, 1)"], "answer": 0,
     "explanation": "f(0) = b = 1, então o ponto é (0, 1).", "difficulty": "media", "topic": "Raiz e gráfico"},
    {"kind": "objetiva", "statement": "Um táxi cobra R$ 5 de bandeirada mais R$ 2 por km. Qual função representa o valor V de uma corrida de x km?",
     "options": ["V(x) = 5x + 2", "V(x) = 2x + 5", "V(x) = 7x", "V(x) = 2x - 5"], "answer": 1,
     "explanation": "Valor fixo b = 5 e valor por km a = 2.", "difficulty": "media", "topic": "Aplicações"},
    {"kind": "discursiva", "statement": "Explique, com suas palavras, o que acontece com o gráfico quando o coeficiente a é negativo.", "options": [], "answer": None,
     "expected": "A reta é inclinada para baixo: a função é decrescente, ou seja, quando x aumenta, f(x) diminui.",
     "explanation": "Com a < 0 a função é decrescente.", "difficulty": "media", "topic": "Coeficientes"},
]

Q_CELULAS = [
    {"kind": "objetiva", "statement": "Qual organela é responsável pela respiração celular?", "options": ["Ribossomo", "Mitocôndria", "Lisossomo", "Cloroplasto"], "answer": 1,
     "explanation": "As mitocôndrias produzem ATP pela respiração celular.", "difficulty": "facil", "topic": "Organelas"},
    {"kind": "objetiva", "statement": "Qual estrutura é exclusiva das células vegetais?", "options": ["Núcleo", "Membrana plasmática", "Parede celular", "Ribossomo"], "answer": 2,
     "explanation": "A parede celular de celulose existe nas células vegetais.", "difficulty": "facil", "topic": "Célula vegetal"},
    {"kind": "objetiva", "statement": "As bactérias são exemplos de células:", "options": ["Eucariontes", "Procariontes", "Vegetais", "Animais"], "answer": 1,
     "explanation": "Bactérias não têm núcleo organizado: são procariontes.", "difficulty": "media", "topic": "Tipos de célula"},
    {"kind": "objetiva", "statement": "Onde ocorre a fotossíntese?", "options": ["Cloroplastos", "Mitocôndrias", "Vacúolo", "Complexo golgiense"], "answer": 0,
     "explanation": "A fotossíntese ocorre nos cloroplastos.", "difficulty": "facil", "topic": "Célula vegetal"},
]

Q_REVOLUCAO = [
    {"kind": "objetiva", "statement": "Em que ano começou a Revolução Francesa?", "options": ["1776", "1789", "1799", "1815"], "answer": 1,
     "explanation": "A revolução começou em 1789.", "difficulty": "facil", "topic": "Antecedentes"},
    {"kind": "objetiva", "statement": "Qual grupo pagava a maior parte dos impostos?", "options": ["Clero", "Nobreza", "Terceiro estado", "Rei"], "answer": 2,
     "explanation": "O terceiro estado sustentava a carga tributária.", "difficulty": "facil", "topic": "Antecedentes"},
    {"kind": "objetiva", "statement": "Qual evento marcou o fim da Revolução Francesa?", "options": ["Tomada da Bastilha", "Golpe do 18 Brumário", "Período do Terror", "Estados Gerais"], "answer": 1,
     "explanation": "O golpe do 18 Brumário (1799) levou Napoleão ao poder.", "difficulty": "media", "topic": "Fases"},
    {"kind": "objetiva", "statement": "Quem liderou o período do Terror?", "options": ["Napoleão", "Luís XVI", "Robespierre", "Voltaire"], "answer": 2,
     "explanation": "Robespierre e os jacobinos lideraram o Terror.", "difficulty": "media", "topic": "Fases"},
]


DEMO_SLUG = "escola-teste"
DEMO_NAME = "Escola Teste"
DOMAIN = "escolateste.edu.br"
PLATFORM_SLUG = "plataforma"
PLATFORM_NAME = "EDU.AI · Administração"
PLATFORM_ADMINS = [("Administrador Geral", "admin@plataforma.edu.br"),
                   ("Administradora Geral 2", "admin2@plataforma.edu.br")]


def run_if_empty():
    """Semeia os dados de teste só quando o banco não tem nenhum usuário."""
    conn = connect()
    empty = not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    conn.close()
    if empty:
        create_platform_admins()
        create_demo()
    complement_demo()
    complement_v2()


def complement_v2(slug: str = DEMO_SLUG):
    """Recursos da versão 2 na escola de teste (também em bancos antigos): conta da secretaria,
    dados cadastrais dos alunos para carteirinhas/declarações e faturas de exemplo da plataforma."""
    from datetime import date
    conn = connect()
    try:
        if meta_get(conn, "seed_v2"):
            return
        inst = one(conn.execute("SELECT id, plan FROM institutions WHERE slug=?", (slug,)))
        if inst:
            iid = inst["id"]
            if not conn.execute("SELECT 1 FROM users WHERE institution_id=? AND role='secretaria'", (iid,)).fetchone():
                unit = conn.execute("SELECT id FROM units WHERE institution_id=? ORDER BY id LIMIT 1", (iid,)).fetchone()
                conn.execute("INSERT INTO users (institution_id, unit_id, name, email, password_hash, role, consent_at, last_login)"
                             " VALUES (?,?,?,?,?,'secretaria',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                             (iid, unit[0] if unit else None, "Marta Siqueira", f"secretaria@{DOMAIN}", hash_password(PASSWORD)))
            rng = random.Random(11)
            alunos = conn.execute("SELECT id, created_at FROM users WHERE institution_id=? AND role='aluno' AND registration IS NULL",
                                  (iid,)).fetchall()
            for uid, created in alunos:
                ano = date.today().year - rng.randint(13, 16)
                conn.execute("UPDATE users SET registration=?, birth_date=?, document_id=? WHERE id=?",
                             (f"{(created or str(date.today().year))[:4]}{uid:05d}", f"{ano}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                              f"{rng.randint(10, 59)}.{rng.randint(100, 999)}.{rng.randint(100, 999)}-{rng.randint(0, 9)}", uid))
            conn.execute("UPDATE units SET city=COALESCE(city, 'São Paulo') WHERE institution_id=?", (iid,))
            admin = conn.execute("SELECT id FROM users WHERE is_superadmin=1 ORDER BY id LIMIT 1").fetchone()
            if admin and not conn.execute("SELECT 1 FROM invoices WHERE institution_id=?", (iid,)).fetchone():
                hoje = date.today()
                preco = {"Essencial": 490, "Escola Pro": 1290, "Rede": 3900}.get(inst["plan"], 1290)
                for back in (2, 1, 0):
                    y, m = hoje.year, hoje.month - back
                    while m < 1:
                        y, m = y - 1, m + 12
                    ref = f"{y}-{m:02d}"
                    paga = back > 0
                    conn.execute("INSERT INTO invoices (institution_id, reference, description, amount, due_date, status, paid_at,"
                                 " payment_method, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (iid, ref, f"Mensalidade plano {inst['plan']} — {ref}", preco, f"{ref}-10",
                                  "paga" if paga else "aberta", f"{ref}-08" if paga else None, "Boleto" if paga else None, admin[0]))
        meta_set(conn, "seed_v2", "1")
        conn.commit()
        print("[seed] secretaria, dados cadastrais e faturas de exemplo adicionados")
    finally:
        conn.close()


def complement_demo(slug: str = DEMO_SLUG):
    """Exemplos de calendário e atendimento na escola de teste (também em bancos criados antes
    desses recursos). Só age se a escola de teste existir e ainda não tiver calendário."""
    from datetime import date, timedelta
    conn = connect()
    try:
        inst = one(conn.execute("SELECT id FROM institutions WHERE slug=?", (slug,)))
        if not inst or conn.execute("SELECT 1 FROM academic_terms WHERE institution_id=?", (inst["id"],)).fetchone():
            return
        iid = inst["id"]
        ano = date.today().year
        conn.execute("INSERT INTO academic_terms (institution_id, name, start_date, end_date, weekdays) VALUES (?,?,?,?,?)",
                     (iid, f"Ano letivo {ano}", f"{ano}-02-02", f"{ano}-12-18", "[0,1,2,3,4]"))
        gestor = one(conn.execute("SELECT id FROM users WHERE institution_id=? AND role='gestor' ORDER BY id LIMIT 1", (iid,)))
        prof = one(conn.execute("SELECT id FROM users WHERE email=?", (f"professor@{DOMAIN}",)))
        turma = one(conn.execute("SELECT s.class_id FROM subjects s WHERE s.teacher_id=? ORDER BY s.id LIMIT 1", (prof["id"],))) if prof else None
        gid = gestor["id"] if gestor else None
        eventos = [
            (None, "recesso", "Férias de julho", f"{ano}-07-13", f"{ano}-07-24", gid),
            (None, "feriado", "Tiradentes", f"{ano}-04-21", None, gid),
            (None, "feriado", "Dia do Trabalho", f"{ano}-05-01", None, gid),
            (None, "feriado", "Independência do Brasil", f"{ano}-09-07", None, gid),
            (None, "feriado", "Nossa Senhora Aparecida", f"{ano}-10-12", None, gid),
            (None, "feriado", "Finados", f"{ano}-11-02", None, gid),
            (None, "feriado", "Proclamação da República", f"{ano}-11-15", None, gid),
            (None, "feriado", "Dia da Consciência Negra", f"{ano}-11-20", None, gid),
            (None, "reuniao", "Reunião de pais e mestres", (date.today() + timedelta(days=10)).isoformat(), None, gid),
        ]
        if turma and prof:
            eventos.append((turma["class_id"], "prova", "Prova de Matemática", (date.today() + timedelta(days=6)).isoformat(), None, prof["id"]))
        for cid, kind, title, d, end, by in eventos:
            conn.execute("INSERT INTO calendar_events (institution_id, class_id, kind, title, date, end_date, created_by) VALUES (?,?,?,?,?,?,?)",
                         (iid, cid, kind, title, d, end, by))
        aluno = one(conn.execute("SELECT id FROM users WHERE email=?", (f"aluno@{DOMAIN}",)))
        if aluno and not conn.execute("SELECT 1 FROM tickets WHERE institution_id=?", (iid,)).fetchone():
            for cat, subj, body, status in (
                ("documento", "Declaração de matrícula — para o transporte escolar",
                 "Preciso da declaração de matrícula para renovar o passe do ônibus.", "aberto"),
                ("pedagogico", "Revisão da nota de Ciências", "Acho que a questão 3 da revisão foi corrigida errada. Podem conferir?", "em_andamento"),
            ):
                tid = conn.execute("INSERT INTO tickets (institution_id, user_id, protocol, category, subject, status) VALUES (?,?,?,?,?,?)",
                                   (iid, aluno["id"], "", cat, subj, status)).lastrowid
                conn.execute("UPDATE tickets SET protocol=? WHERE id=?", (f"{ano}{tid:06d}", tid))
                conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body) VALUES (?,?,?)", (tid, aluno["id"], body))
                if status == "em_andamento" and gid:
                    conn.execute("UPDATE tickets SET assigned_to=? WHERE id=?", (gid, tid))
                    conn.execute("INSERT INTO ticket_messages (ticket_id, user_id, body) VALUES (?,?,?)",
                                 (tid, gid, "Recebemos o pedido e encaminhamos ao professor. Retornamos em breve."))
        conn.commit()
        print("[seed] calendário e chamados de exemplo adicionados à escola de teste")
    finally:
        conn.close()


def create_platform_admins(slug: str = PLATFORM_SLUG, name: str = PLATFORM_NAME) -> bool:
    """Instituição interna com os administradores gerais (papel gestor + is_superadmin)."""
    conn = connect()
    if conn.execute("SELECT 1 FROM institutions WHERE slug=?", (slug,)).fetchone():
        conn.close()
        return False
    pw = hash_password(PASSWORD)
    iid = conn.execute("INSERT INTO institutions (name, slug, type, plan, settings) VALUES (?,?,?,?,?)",
                       (name, slug, "Plataforma", "Escola Pro", jdump({"ai_model": ia.DEFAULT_MODEL}))).lastrowid
    for n, email in PLATFORM_ADMINS:
        uid = conn.execute("INSERT INTO users (institution_id, name, email, password_hash, role, is_superadmin, consent_at)"
                           " VALUES (?,?,?,?,'gestor',1,CURRENT_TIMESTAMP)", (iid, n, email, pw)).lastrowid
        conn.execute("INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)",
                     (iid, uid, "admin.criado_via_seed", email))
    conn.commit()
    conn.close()
    print(f"[seed] administradores gerais criados na instituição '{slug}'")
    return True


def create_demo(slug: str = DEMO_SLUG, name: str = DEMO_NAME) -> bool:
    """Cria a escola de teste com gestores, professores, alunos e dados. Não faz nada se já existir."""
    conn = connect()
    if conn.execute("SELECT 1 FROM institutions WHERE slug=?", (slug,)).fetchone():
        conn.close()
        return False
    random.seed(7)
    pw = hash_password(PASSWORD)
    x = conn.execute

    iid = x("INSERT INTO institutions (name, slug, cnpj, type, color, plan, settings) VALUES (?,?,?,?,?,?,?)",
            (name, slug, "12.345.678/0001-90", "Escola", "#172033", "Escola Pro",
             jdump({"ai_model": ia.DEFAULT_MODEL, "allow_class_code": True}))).lastrowid
    unit = x("INSERT INTO units (institution_id, name, city) VALUES (?,?,?)", (iid, "Unidade Centro", "São Paulo")).lastrowid
    x("INSERT INTO units (institution_id, name, city) VALUES (?,?,?)", (iid, "Unidade Norte", "São Paulo"))
    fund = x("INSERT INTO courses (institution_id, name, level) VALUES (?,?,?)", (iid, "Ensino Fundamental II", "Fundamental")).lastrowid
    medio = x("INSERT INTO courses (institution_id, name, level) VALUES (?,?,?)", (iid, "Ensino Médio", "Médio")).lastrowid

    def user(name, email, role, grade=None):
        return x("INSERT INTO users (institution_id, unit_id, name, email, password_hash, role, grade, consent_at, last_login)"
                 " VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", (iid, unit, name, email, pw, role, grade)).lastrowid

    admin = user("Fernanda Rocha", f"gestor@{DOMAIN}", "gestor")
    user("Paulo Andrade", f"gestor2@{DOMAIN}", "gestor")
    ana = user("Juliana Prado", f"professor@{DOMAIN}", "professor")
    user("Ricardo Nogueira", f"professor2@{DOMAIN}", "professor")
    user("Camila Torres", f"professor3@{DOMAIN}", "professor")

    def klass(name, grade, course, code):
        return x("INSERT INTO classes (institution_id, unit_id, course_id, name, grade, code) VALUES (?,?,?,?,?,?)",
                 (iid, unit, course, name, grade, code)).lastrowid

    c9b, c8a, c1em = klass("9º B", "9º ano", fund, "MAT9B1"), klass("8º A", "8º ano", fund, "CIE8A2"), klass("1º EM", "1ª série", medio, "HIS1M3")
    names = {
        c9b: ["Bruna Azevedo", "Caio Mendonça", "Larissa Freitas", "Diego Vasconcelos", "Natália Campos", "Otávio Brandão", "Yasmin Correia", "Rodrigo Siqueira"],
        c8a: ["Lívia Pacheco", "Thiago Moura", "Clara Bittencourt", "Vinícius Duarte", "Melissa Rezende"],
        c1em: ["Bernardo Fontes", "Giovana Lacerda", "Samuel Quintela", "Rebeca Amaral", "Fábio Guimarães"],
    }
    students = {}
    seq = 0
    for cid, lst in names.items():
        grade = {c9b: "9º ano", c8a: "8º ano", c1em: "1ª série"}[cid]
        students[cid] = []
        for n in lst:
            seq += 1
            email = f"aluno@{DOMAIN}" if seq == 1 else f"aluno{seq:02d}@{DOMAIN}"
            uid = user(n, email, "aluno", grade)
            x("INSERT INTO class_students (class_id, user_id) VALUES (?,?)", (cid, uid))
            students[cid].append(uid)

    def subject(cid, name, desc, color):
        return x("INSERT INTO subjects (institution_id, teacher_id, class_id, name, description, color) VALUES (?,?,?,?,?,?)",
                 (iid, ana, cid, name, desc, color)).lastrowid

    s_mat = subject(c9b, "Matemática", "Funções, equações e geometria do 9º ano.", "#2563EB")
    s_cie = subject(c8a, "Ciências", "Biologia celular e corpo humano.", "#16A34A")
    s_his = subject(c1em, "História", "Idade Moderna e Contemporânea.", "#DC2626")

    def topics(sid, lst):
        return {n: x("INSERT INTO topics (subject_id, name, position) VALUES (?,?,?)", (sid, n, i)).lastrowid for i, n in enumerate(lst)}

    t_mat = topics(s_mat, ["Coeficientes", "Raiz e gráfico", "Aplicações"])
    t_cie = topics(s_cie, ["Tipos de célula", "Organelas", "Célula vegetal"])
    t_his = topics(s_his, ["Antecedentes", "Fases"])

    def doc(sid, title, text, topic, folder):
        return x("INSERT INTO documents (institution_id, subject_id, topic_id, folder, title, filename, size, text, topics, status, progress, created_by)"
                 " VALUES (?,?,?,?,?,NULL,?,?,?, 'concluido', 100, ?)",
                 (iid, sid, topic, folder, title, len(text.encode()), text, jdump(ia.fallback("resumo", title, text)["keywords"][:6]), ana)).lastrowid

    d_fun = doc(s_mat, "Funções do 1º grau", FUNCOES, None, "Matemática / Álgebra")
    d_cel = doc(s_cie, "Células e organelas", CELULAS, None, "Ciências / Biologia")
    d_rev = doc(s_his, "Revolução Francesa", REVOLUCAO, None, "História / Idade Contemporânea")

    def material(sid, did, kind, title, content, status, classes=(), topic=None, variant=""):
        mid = x("INSERT INTO materials (subject_id, topic_id, document_id, type, title, variant, content, status, ai_source, created_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)", (sid, topic, did, kind, title, variant, jdump(content), status, "demonstracao", ana)).lastrowid
        x("INSERT INTO material_versions (material_id, title, content, note, created_by) VALUES (?,?,?,?,?)",
          (mid, title, jdump(content), "Gerado pela IA", ana))
        for c in classes:
            x("INSERT INTO material_classes (material_id, class_id) VALUES (?,?)", (mid, c))
        return mid

    material(s_mat, d_fun, "resumo", "Resumo · Funções do 1º grau", RESUMO_FUNCOES, "publicado", [c9b], t_mat["Coeficientes"], "simplificado")
    material(s_mat, d_fun, "mapa", "Mapa mental · Funções do 1º grau", MAPA_FUNCOES, "publicado", [c9b], t_mat["Raiz e gráfico"])
    material(s_mat, d_fun, "flashcards", "Flashcards · Funções do 1º grau", FLASH_FUNCOES, "publicado", [c9b], t_mat["Coeficientes"])
    material(s_mat, d_fun, "exercicios", "Exercícios · Funções do 1º grau",
             {"questions": [{k: v for k, v in q.items() if k != "topic"} for q in Q_FUNCOES[:5]]}, "publicado", [c9b], t_mat["Raiz e gráfico"])
    material(s_mat, d_fun, "roteiro", "Roteiro de revisão · Funções", ia.fallback("roteiro", "Funções do 1º grau", FUNCOES), "rascunho", topic=t_mat["Aplicações"])
    material(s_cie, d_cel, "resumo", "Resumo · Células e organelas", ia.fallback("resumo", "Células e organelas", CELULAS), "revisao", topic=t_cie["Organelas"])
    material(s_cie, d_cel, "flashcards", "Flashcards · Células", ia.fallback("flashcards", "Células", CELULAS), "publicado", [c8a], t_cie["Organelas"])
    material(s_his, d_rev, "mapa", "Mapa mental · Revolução Francesa", ia.fallback("mapa", "Revolução Francesa", REVOLUCAO), "rascunho", topic=t_his["Fases"])

    def bank(sid, tmap, qs):
        ids = []
        for q in qs:
            ids.append(x("INSERT INTO questions (subject_id, topic_id, kind, statement, options, answer, expected, explanation, difficulty, reviewed, created_by)"
                         " VALUES (?,?,?,?,?,?,?,?,?,1,?)",
                         (sid, tmap.get(q["topic"]), q["kind"], q["statement"], jdump(q["options"]), q["answer"], q.get("expected", ""),
                          q["explanation"], q["difficulty"], ana)).lastrowid)
        return ids

    qf, qc, qr = bank(s_mat, t_mat, Q_FUNCOES), bank(s_cie, t_cie, Q_CELULAS), bank(s_his, t_his, Q_REVOLUCAO)

    def activity(sid, cid, title, qids, due, kind="atividade", status="publicada"):
        aid = x("INSERT INTO activities (subject_id, class_id, title, kind, instructions, due_date, points, max_attempts, status, created_by, created_at)"
                " VALUES (?,?,?,?,?,date('now', ?),10,?,?,?, datetime('now', ?))",
                (sid, cid, title, kind, "Leia com atenção e responda todas as questões.", due, 2 if kind == "atividade" else 1, status, ana,
                 f"{int(due.split()[0]) - 10} day")).lastrowid
        for i, q in enumerate(qids):
            x("INSERT INTO activity_questions (activity_id, question_id, position) VALUES (?,?,?)", (aid, q, i))
        return aid

    a1 = activity(s_mat, c9b, "Lista – Coeficientes", qf[:2] + [qf[4]], "-12 day")
    a2 = activity(s_mat, c9b, "Lista – Funções do 1º grau", qf[:6], "-3 day")
    activity(s_mat, c9b, "Simulado de Matemática", qf[:5], "+5 day", "simulado")
    a4 = activity(s_cie, c8a, "Revisão de ciências", qc, "-1 day")
    activity(s_his, c1em, "Simulado de História", qr, "+2 day", "simulado")
    activity(s_mat, c9b, "Desafio extra (rascunho)", qf[2:4], "+10 day", status="rascunho")

    def answer_sheet(qids, skill):
        out = {}
        for qid in qids:
            q = one(conn.execute("SELECT * FROM questions WHERE id=?", (qid,)))
            if q["kind"] == "discursiva":
                out[str(qid)] = "Quando a é negativo a reta desce, a função é decrescente." if random.random() < skill else "A reta fica reta."
            else:
                n = len(jload(q["options"], [])) or 4
                out[str(qid)] = q["answer"] if random.random() < skill else (q["answer"] + 1) % n
        return out

    for aid, cid, qids in ((a1, c9b, qf[:2] + [qf[4]]), (a2, c9b, qf[:6]), (a4, c8a, qc)):
        act = one(conn.execute("SELECT * FROM activities WHERE id=?", (aid,)))
        for i, sid_ in enumerate(students[cid]):
            if aid == a2 and i >= 6:
                continue  # dois alunos ainda não entregaram
            skill = 0.45 + 0.07 * ((i * 3) % 8)
            submit(conn, act, sid_, answer_sheet(qids, skill))
        x("UPDATE submissions SET submitted_at=datetime(?, '-' || (id % 3) || ' day') WHERE activity_id=?",
          (act["due_date"], aid))

    # jogo já finalizado com placar
    gq = [{"statement": q["statement"], "options": q["options"], "answer": q["answer"], "explanation": q["explanation"], "topic_id": t_mat.get(q["topic"])}
          for q in Q_FUNCOES if q["kind"] == "objetiva"]
    gid = x("INSERT INTO games (institution_id, subject_id, class_id, teacher_id, title, code, status, current, questions, time_per_question, finished_at)"
            " VALUES (?,?,?,?,?,?, 'finalizado', ?, ?, 20, datetime('now','-2 day'))",
            (iid, s_mat, c9b, ana, "Desafio de funções", "482915", len(gq) - 1, jdump(gq))).lastrowid
    for i, uid in enumerate(students[c9b][:6]):
        name = one(conn.execute("SELECT name FROM users WHERE id=?", (uid,)))["name"]
        pid = x("INSERT INTO game_players (game_id, user_id, name) VALUES (?,?,?)", (gid, uid, name)).lastrowid
        total = 0
        for qi, q in enumerate(gq):
            ok = random.random() < 0.5 + 0.08 * (i % 5)
            pts = random.randint(600, 980) if ok else 0
            total += pts
            x("INSERT INTO game_answers (game_id, player_id, q_index, choice, correct, points, ms) VALUES (?,?,?,?,?,?,?)",
              (gid, pid, qi, q["answer"] if ok else (q["answer"] + 1) % 4, int(ok), pts, random.randint(2000, 15000)))
        x("UPDATE game_players SET score=? WHERE id=?", (total, pid))
    x("INSERT INTO games (institution_id, subject_id, class_id, teacher_id, title, questions, time_per_question) VALUES (?,?,?,?,?,?,20)",
      (iid, s_his, c1em, ana, "Quiz da Revolução Francesa",
       jdump([{"statement": q["statement"], "options": q["options"], "answer": q["answer"], "explanation": q["explanation"], "topic_id": None} for q in Q_REVOLUCAO])))

    for uid, text, kind, link in (
        (ana, "18 alunos entregaram “Revisão de ciências”", "Atividades", "#/p/atividades"),
        (ana, "A IA terminou de processar “Funções do 1º grau”", "Biblioteca", f"#/p/documento/{d_fun}"),
        (ana, "Lívia Pacheco aceitou o convite", "Turmas", "#/p/turmas"),
    ):
        x("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)", (uid, text, kind, link))
    for uid in students[c9b]:
        x("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)", (uid, "Novo material: Mapa mental · Funções do 1º grau", "Materiais", "#/a/materias"))
    for day in range(20):
        for _ in range(random.randint(1, 4)):
            x("INSERT INTO ai_usage (institution_id, user_id, kind, provider, model, chars_in, chars_out, ms, ok, created_at)"
              " VALUES (?,?,?,?,?,?,?,?,1, datetime('now', ?))",
              (iid, ana, random.choice(ia.TYPES), "ollama", ia.DEFAULT_MODEL, random.randint(3000, 12000), random.randint(800, 3000),
               random.randint(4000, 30000), f"-{day} day"))
    for d in range(30):
        for uid in random.sample(students[c9b] + students[c8a] + [ana, admin], 6):
            x("INSERT INTO audit_log (institution_id, user_id, action, detail, created_at) VALUES (?,?,?,?, datetime('now', ?))",
              (iid, uid, "login", "", f"-{d} day"))
    x("INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)", (iid, admin, "instituicao.criada", name))
    x("INSERT INTO invites (institution_id, email, role, token, class_id) VALUES (?,?,?,?,?)",
      (iid, f"novo.professor@{DOMAIN}", "professor", "convite-teste-professor", None))
    conn.commit()
    conn.close()
    print(f"[seed] instituição de teste '{slug}' criada ({time.strftime('%H:%M:%S')}) — senha: {PASSWORD}")
    return True
