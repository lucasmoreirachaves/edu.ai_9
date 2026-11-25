"""Cria (ou redefine) um administrador (papel gestor) de uma instituição.

Uso:  .venv\\Scripts\\python.exe criar_admin.py <email> "<nome>" [senha] [instituicao]
Sem senha, gera uma aleatória. Instituição padrão: plataforma (use --geral para administrador geral).
"""
import secrets
import sys

from app import seed
from app.auth import hash_password
from app.db import connect, init_db


def main():
    geral = "--geral" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--geral"]
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    email, name = sys.argv[1].strip().lower(), sys.argv[2]
    password = sys.argv[3] if len(sys.argv) > 3 else "Edu-" + secrets.token_urlsafe(9)
    slug = sys.argv[4] if len(sys.argv) > 4 else "plataforma"
    init_db()
    seed.run_if_empty()
    conn = connect()
    inst = conn.execute("SELECT id, name FROM institutions WHERE slug=?", (slug,)).fetchone()
    if not inst:
        sys.exit(f"Instituição '{slug}' não encontrada")
    row = conn.execute("SELECT id FROM users WHERE institution_id=? AND email=?", (inst["id"], email)).fetchone()
    if row:
        conn.execute("UPDATE users SET name=?, password_hash=?, role='gestor', status='ativo', is_superadmin=? WHERE id=?",
                     (name, hash_password(password), int(geral), row["id"]))
        uid, acao = row["id"], "atualizado"
    else:
        uid = conn.execute(
            "INSERT INTO users (institution_id, name, email, password_hash, role, is_superadmin, consent_at) VALUES (?,?,?,?,'gestor',?,CURRENT_TIMESTAMP)",
            (inst["id"], name, email, hash_password(password), int(geral))).lastrowid
        acao = "criado"
    conn.execute("INSERT INTO audit_log (institution_id, user_id, action, detail) VALUES (?,?,?,?)",
                 (inst["id"], uid, "admin.criado_via_script", email))
    conn.commit()
    conn.close()
    print(f"Administrador{' geral' if geral else ''} {acao}.\n  Instituição: {slug} ({inst['name']})\n  E-mail:      {email}\n  Senha:       {password}")


if __name__ == "__main__":
    main()
