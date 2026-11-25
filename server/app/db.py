"""Banco SQLite do EDU.AI: conexão, esquema e utilitários.

Multi-instituição: toda consulta parte do `institution_id` do usuário logado.
"""
import json
import os
import sqlite3

from fastapi import Request
from fastapi.routing import APIRoute
from pathlib import Path

DB_PATH = Path(os.environ.get("EDU_DB", Path(__file__).resolve().parent.parent / "edu.db"))
UPLOAD_DIR = DB_PATH.parent / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS institutions (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, cnpj TEXT,
  type TEXT DEFAULT 'Escola', color TEXT DEFAULT '#172033', logo TEXT,
  plan TEXT DEFAULT 'Escola Pro', settings TEXT DEFAULT '{}',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS units (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, name TEXT NOT NULL, city TEXT
);
CREATE TABLE IF NOT EXISTS courses (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, name TEXT NOT NULL, level TEXT
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, unit_id INTEGER,
  name TEXT NOT NULL, email TEXT NOT NULL, password_hash TEXT,
  role TEXT NOT NULL CHECK (role IN ('gestor','professor','aluno','secretaria')),
  status TEXT DEFAULT 'ativo',        -- ativo | inativo | convidado
  grade TEXT, two_factor INTEGER DEFAULT 0, weekly_email INTEGER DEFAULT 1,
  consent_at TEXT, last_login TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE (institution_id, email)
);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, email TEXT NOT NULL,
  name TEXT, role TEXT NOT NULL, class_id INTEGER, token TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'pendente', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS classes (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, unit_id INTEGER, course_id INTEGER,
  name TEXT NOT NULL, grade TEXT, year INTEGER DEFAULT 2026, code TEXT
);
CREATE TABLE IF NOT EXISTS class_students (
  class_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (class_id, user_id)
);
CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, teacher_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT,
  color TEXT DEFAULT '#2563EB', active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, name TEXT NOT NULL, position INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, subject_id INTEGER NOT NULL, topic_id INTEGER,
  folder TEXT DEFAULT '', title TEXT NOT NULL, filename TEXT, size INTEGER DEFAULT 0,
  text TEXT, topics TEXT DEFAULT '[]',
  status TEXT DEFAULT 'enviado',      -- enviado | processando | concluido | erro
  progress INTEGER DEFAULT 0, error TEXT, archived INTEGER DEFAULT 0,
  created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS materials (
  id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, topic_id INTEGER, document_id INTEGER,
  type TEXT NOT NULL,                 -- ver ia.TYPES
  title TEXT NOT NULL, variant TEXT, content TEXT NOT NULL DEFAULT '{}',
  status TEXT DEFAULT 'rascunho',     -- rascunho | revisao | publicado | arquivado
  ai_source TEXT, created_by INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS material_versions (
  id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL, title TEXT, content TEXT NOT NULL,
  note TEXT, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS material_classes (
  material_id INTEGER NOT NULL, class_id INTEGER NOT NULL, published_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (material_id, class_id)
);
CREATE TABLE IF NOT EXISTS material_progress (
  user_id INTEGER NOT NULL, material_id INTEGER NOT NULL, pct INTEGER DEFAULT 0,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, material_id)
);
CREATE TABLE IF NOT EXISTS flashcard_reviews (
  user_id INTEGER NOT NULL, material_id INTEGER NOT NULL, card INTEGER NOT NULL,
  box INTEGER DEFAULT 0, due_at TEXT, reviewed_at TEXT,
  PRIMARY KEY (user_id, material_id, card)
);
CREATE TABLE IF NOT EXISTS generation_jobs (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, document_id INTEGER NOT NULL,
  material_id INTEGER, kind TEXT NOT NULL, options TEXT DEFAULT '{}',
  status TEXT DEFAULT 'pendente',     -- pendente | processando | concluido | erro
  error TEXT, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, topic_id INTEGER, material_id INTEGER,
  kind TEXT DEFAULT 'objetiva',       -- objetiva | discursiva
  statement TEXT NOT NULL, options TEXT DEFAULT '[]', answer INTEGER, expected TEXT,
  explanation TEXT, difficulty TEXT DEFAULT 'media', reviewed INTEGER DEFAULT 0,
  created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activities (
  id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, class_id INTEGER NOT NULL,
  title TEXT NOT NULL, kind TEXT DEFAULT 'atividade',   -- atividade | simulado | prova
  instructions TEXT, due_date TEXT, points REAL DEFAULT 10, max_attempts INTEGER DEFAULT 1,
  auto_publish INTEGER DEFAULT 1,
  status TEXT DEFAULT 'rascunho',     -- rascunho | publicada | encerrada
  created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activity_questions (
  activity_id INTEGER NOT NULL, question_id INTEGER NOT NULL, position INTEGER DEFAULT 0,
  PRIMARY KEY (activity_id, question_id)
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  answers TEXT DEFAULT '{}',          -- {question_id: índice da opção | texto}
  grading TEXT DEFAULT '{}',          -- {question_id: {score 0..1, feedback, ai_score, ai_feedback}}
  score REAL, attempts INTEGER DEFAULT 0,
  status TEXT DEFAULT 'entregue',     -- entregue | corrigida
  published INTEGER DEFAULT 0, feedback TEXT,
  submitted_at TEXT, UNIQUE (activity_id, student_id)
);
CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, subject_id INTEGER NOT NULL,
  class_id INTEGER, teacher_id INTEGER NOT NULL, title TEXT NOT NULL, code TEXT,
  mode TEXT DEFAULT 'individual',     -- individual | equipes
  time_per_question INTEGER DEFAULT 20, show_ranking INTEGER DEFAULT 1,
  questions TEXT DEFAULT '[]',        -- cópia das questões no momento da criação
  status TEXT DEFAULT 'rascunho',     -- rascunho | sala | pergunta | discussao | revelacao | finalizado
  current INTEGER DEFAULT -1, question_started_at REAL, paused_left REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS game_players (
  id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL,
  team INTEGER DEFAULT 0, score INTEGER DEFAULT 0, streak INTEGER DEFAULT 0,
  UNIQUE (game_id, user_id)
);
CREATE TABLE IF NOT EXISTS game_answers (
  game_id INTEGER NOT NULL, player_id INTEGER NOT NULL, q_index INTEGER NOT NULL,
  choice INTEGER, correct INTEGER, points INTEGER, ms INTEGER,
  PRIMARY KEY (game_id, player_id, q_index)
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, text TEXT NOT NULL, kind TEXT, link TEXT,
  read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, institution_id INTEGER, user_id INTEGER, action TEXT NOT NULL,
  detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ai_usage (
  id INTEGER PRIMARY KEY, institution_id INTEGER, user_id INTEGER, kind TEXT, provider TEXT,
  model TEXT, chars_in INTEGER, chars_out INTEGER, ms INTEGER, ok INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS data_requests (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,                 -- exportacao | correcao | exclusao
  detail TEXT, status TEXT DEFAULT 'aberta',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS password_resets (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token_hash TEXT UNIQUE NOT NULL,
  expires_at REAL NOT NULL, used INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS outbox (                -- e-mails enviados (ou só registrados, sem SMTP)
  id INTEGER PRIMARY KEY, institution_id INTEGER, to_email TEXT NOT NULL, subject TEXT NOT NULL,
  body TEXT NOT NULL, status TEXT DEFAULT 'pendente',   -- pendente | enviado | registrado | erro
  error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS plan_requests (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, user_id INTEGER NOT NULL, plan TEXT NOT NULL,
  status TEXT DEFAULT 'pendente',     -- pendente | aprovado | recusado
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS tickets (                -- ouvidoria / secretaria: chamados de alunos e professores
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  protocol TEXT NOT NULL, category TEXT NOT NULL, subject TEXT NOT NULL,
  status TEXT DEFAULT 'aberto',       -- aberto | em_andamento | aguardando | resolvido | fechado
  anonymous INTEGER DEFAULT 0, assigned_to INTEGER, rating INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS ticket_messages (
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, user_id INTEGER NOT NULL, body TEXT NOT NULL,
  attachment TEXT, attachment_size INTEGER, internal INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS academic_terms (          -- períodos letivos: datas e dias da semana com aula
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, name TEXT NOT NULL,
  start_date TEXT NOT NULL, end_date TEXT NOT NULL, weekdays TEXT DEFAULT '[0,1,2,3,4]'  -- 0 = segunda
);
CREATE TABLE IF NOT EXISTS calendar_events (
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, class_id INTEGER,  -- NULL = toda a escola
  kind TEXT NOT NULL,                 -- feriado | recesso | sem_aula | aula_extra | prova | evento | reuniao
  title TEXT NOT NULL, description TEXT, date TEXT NOT NULL, end_date TEXT,
  created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS invoices (              -- faturas da mensalidade da plataforma (por instituição)
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, reference TEXT NOT NULL,   -- AAAA-MM
  description TEXT, amount REAL NOT NULL DEFAULT 0, due_date TEXT NOT NULL,
  status TEXT DEFAULT 'aberta',       -- aberta | paga | cancelada  (vencida = aberta com prazo passado)
  paid_at TEXT, payment_method TEXT, notes TEXT,
  created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chat_conversations (    -- chat com IA (cada usuário vê só as próprias)
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, institution_id INTEGER NOT NULL, title TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role TEXT NOT NULL,   -- user | assistant
  content TEXT NOT NULL, provider TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_games (        -- estúdio de aprendizado gamificado
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  class_id INTEGER,                   -- jogo do professor publicado para uma turma (NULL = pessoal)
  material_id INTEGER, title TEXT NOT NULL, topic TEXT, kind TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '{}', ai_source TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_game_plays (
  id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  score INTEGER DEFAULT 0, max_score INTEGER DEFAULT 0, correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
  duration_ms INTEGER DEFAULT 0, details TEXT DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS issued_documents (      -- declarações e carteirinhas emitidas pela secretaria
  id INTEGER PRIMARY KEY, institution_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
  ticket_id INTEGER, issued_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS ix_invoices_inst ON invoices(institution_id, status);
CREATE INDEX IF NOT EXISTS ix_chat_conv_user ON chat_conversations(user_id);
CREATE INDEX IF NOT EXISTS ix_chat_msgs ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_lgames_user ON learning_games(user_id);
CREATE INDEX IF NOT EXISTS ix_lplays_game ON learning_game_plays(game_id);
CREATE INDEX IF NOT EXISTS ix_lplays_user ON learning_game_plays(user_id);
CREATE INDEX IF NOT EXISTS ix_issued_docs ON issued_documents(institution_id, student_id);
CREATE INDEX IF NOT EXISTS ix_tickets_inst ON tickets(institution_id, status);
CREATE INDEX IF NOT EXISTS ix_ticket_messages ON ticket_messages(ticket_id);
CREATE INDEX IF NOT EXISTS ix_calendar_inst ON calendar_events(institution_id, date);
CREATE INDEX IF NOT EXISTS ix_materials_subject ON materials(subject_id);
CREATE INDEX IF NOT EXISTS ix_documents_subject ON documents(subject_id);
CREATE INDEX IF NOT EXISTS ix_submissions_activity ON submissions(activity_id);
CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications(user_id, read);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """Colunas adicionadas depois da primeira versão (bancos existentes)."""
    for table, col, ddl in (
        ("users", "is_superadmin", "INTEGER DEFAULT 0"),   # administrador geral da plataforma
        ("institutions", "active", "INTEGER DEFAULT 1"),   # instituição suspensa não faz login
        ("documents", "pages", "INTEGER DEFAULT 0"),       # páginas do PDF (0 = sem paginação)
        ("documents", "empty_pages", "INTEGER DEFAULT 0"), # páginas sem texto extraível (escaneadas)
        ("documents", "digests", "TEXT DEFAULT '{}'"),     # notas condensadas por intervalo de páginas (documentos longos)
        ("documents", "shared", "INTEGER DEFAULT 1"),      # 1 = alunos da turma podem ver e baixar o arquivo original
        ("games", "scoring", "TEXT DEFAULT 'confianca'"),  # confianca | velocidade
        ("games", "peer", "INTEGER DEFAULT 1"),            # pausa para discussão em duplas quando a turma se divide
        ("games", "round", "INTEGER DEFAULT 1"),           # 1ª ou 2ª votação da pergunta atual
        ("games", "rounds", "TEXT DEFAULT '{}'"),          # {q_index: {"counts": [...], "accuracy": n}} da 1ª votação
        ("game_answers", "confidence", "INTEGER DEFAULT 2"),  # 1 chute · 2 acho que sei · 3 tenho certeza
        ("game_answers", "prev_streak", "INTEGER DEFAULT 0"), # sequência antes da resposta (para desfazer na 2ª votação)
        ("users", "token_version", "INTEGER DEFAULT 0"),   # incrementa ao trocar senha: derruba sessões antigas
        ("users", "totp_secret", "TEXT"),                  # verificação em duas etapas (app autenticador)
        ("activities", "accept_late", "INTEGER DEFAULT 0"), # aceita entrega após o prazo (marcada como atrasada)
        ("submissions", "late", "INTEGER DEFAULT 0"),
        ("users", "ai_prefs", "TEXT DEFAULT '{}'"),        # {"mode": ""|"nuvem"|"local"} (+ url/key/model do admin geral)
        ("users", "photo", "TEXT"),                        # foto do aluno (data URL) para a carteirinha
        ("users", "registration", "TEXT"),                 # número de matrícula
        ("users", "birth_date", "TEXT"),
        ("users", "document_id", "TEXT"),                  # RG ou CPF
        ("tickets", "target", "TEXT DEFAULT 'secretaria'"),  # secretaria | gestao | plataforma
    ):
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    _allow_secretaria(conn)


def _allow_secretaria(conn):
    """Bancos antigos: o CHECK do papel não aceitava 'secretaria'. O SQLite não altera CHECK,
    então a tabela de usuários é recriada com o mesmo conteúdo."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    old = "CHECK (role IN ('gestor','professor','aluno'))"
    if not row or old not in row[0]:
        return
    cols = ", ".join(r[1] for r in conn.execute("PRAGMA table_info(users)"))
    new_sql = row[0].replace(old, "CHECK (role IN ('gestor','professor','aluno','secretaria'))")
    new_sql = new_sql.replace("CREATE TABLE users", "CREATE TABLE users__novo", 1)
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(new_sql)
    conn.execute(f"INSERT INTO users__novo ({cols}) SELECT {cols} FROM users")
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users__novo RENAME TO users")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def get_db(request: Request):
    """Dependência FastAPI: uma conexão por requisição.

    O commit acontece em `CommitRoute`, ANTES de a resposta ser enviada. (O código depois do
    `yield` só roda depois do envio: sem isso, o navegador podia receber "publicado" e, na
    requisição seguinte, ainda ler o dado antigo.) Se a rota levantar erro, nada é gravado."""
    conn = connect()
    request.state.db = conn
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class CommitRoute(APIRoute):
    """Rota que confirma a transação da requisição assim que a função da rota termina com sucesso."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            response = await original(request)
            conn = getattr(request.state, "db", None)
            if conn is not None:
                conn.commit()
            return response

        return handler


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def one(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def jload(value, default=None):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def jdump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def audit(conn, user, action: str, detail: str = ""):
    conn.execute(
        "INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)",
        (user["institution_id"], user["id"], action, detail),
    )


def meta_get(conn, key: str, default=None):
    r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def meta_set(conn, key: str, value: str):
    conn.execute("INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def notify(conn, user_id: int, text: str, kind: str = "", link: str = ""):
    conn.execute("INSERT INTO notifications (user_id, text, kind, link) VALUES (?,?,?,?)",
                 (user_id, text, kind, link))
