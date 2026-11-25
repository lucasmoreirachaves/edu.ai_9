"""Zera o banco de dados e recria as contas de teste.

Uso (dentro de server/, com o servidor PARADO):
    .venv\\Scripts\\python.exe resetar_banco.py --confirmar

O que faz:
  1. Copia o banco atual e a pasta uploads/ para backups/<data-hora>/ (dá para desfazer).
  2. Apaga o banco (todas as instituições, usuários e dados) e os arquivos enviados.
  3. Cria um banco novo com os administradores gerais e a escola de teste (app/seed.py).

Respeita a variável EDU_DB (ex.: o banco em %LOCALAPPDATA%\\EduAI usado pelo iniciar.bat).
"""
import shutil
import sys
import time
from pathlib import Path

from app import seed
from app.db import DB_PATH, UPLOAD_DIR, connect, init_db


def main():
    if "--confirmar" not in sys.argv:
        sys.exit(__doc__ + f"\nBanco alvo: {DB_PATH}\nNada foi alterado. Rode de novo com --confirmar.")

    extras = [Path(str(DB_PATH) + s) for s in ("-wal", "-shm")]
    existentes = [p for p in [DB_PATH, *extras] if p.exists()]
    if existentes or (UPLOAD_DIR.exists() and any(UPLOAD_DIR.iterdir())):
        destino = Path(__file__).resolve().parent / "backups" / time.strftime("%Y%m%d-%H%M%S")
        destino.mkdir(parents=True, exist_ok=True)
        for p in existentes:
            shutil.copy2(p, destino / p.name)
        if UPLOAD_DIR.exists():
            shutil.copytree(UPLOAD_DIR, destino / "uploads", dirs_exist_ok=True)
        print(f"Backup salvo em: {destino}")

    try:
        for p in existentes:
            p.unlink()
    except PermissionError:
        sys.exit("O banco está em uso. Pare o servidor (feche a janela do iniciar.bat) e tente de novo.")
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)

    init_db()
    seed.run_if_empty()

    conn = connect()
    print(f"\nBanco recriado: {DB_PATH}\nSenha de todas as contas: {seed.PASSWORD}\n")
    for r in conn.execute(
            "SELECT i.slug, u.role, u.is_superadmin, u.email, u.name FROM users u JOIN institutions i ON i.id=u.institution_id"
            " ORDER BY u.is_superadmin DESC, CASE u.role WHEN 'gestor' THEN 0 WHEN 'professor' THEN 1 ELSE 2 END, u.id"):
        perfil = "admin geral" if r["is_superadmin"] else r["role"]
        print(f"  {r['slug']:<13} {perfil:<11} {r['email']:<34} {r['name']}")
    conn.close()


if __name__ == "__main__":
    main()
