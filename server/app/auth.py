"""Autenticação: senha (bcrypt), JWT e dependências de papel."""
import os
import time

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException

from .db import get_db, one

SECRET = os.environ.get("EDU_SECRET", "edu-ai-dev-secret-troque-em-producao-0123456789")
ALGO = "HS256"
TTL = 60 * 60 * 12


def make_2fa_ticket(user: dict) -> str:
    """Comprovante curto (5 min) de que a senha conferiu; falta o código do autenticador."""
    return jwt.encode({"sub": str(user["id"]), "exp": int(time.time()) + 300, "2fa": 1}, SECRET, algorithm=ALGO)


def read_2fa_ticket(ticket: str) -> int:
    try:
        data = jwt.decode(ticket, SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "O tempo para digitar o código acabou. Entre novamente.")
    if not data.get("2fa"):
        raise HTTPException(401, "Comprovante inválido")
    return int(data["sub"])


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str | None) -> bool:
    try:
        return bool(hashed) and bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: dict, impersonated_by: int | None = None) -> str:
    """`impersonated_by`: id do administrador geral que está acessando como este usuário."""
    payload = {"sub": str(user["id"]), "exp": int(time.time()) + TTL, "v": user.get("token_version") or 0}
    if impersonated_by:
        payload["imp"] = impersonated_by
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def current_user(authorization: str | None = Header(default=None), conn=Depends(get_db)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Não autenticado")
    try:
        data = jwt.decode(authorization[7:], SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sessão expirada")
    if data.get("2fa"):
        raise HTTPException(401, "Sessão inválida")
    user = one(conn.execute("SELECT * FROM users WHERE id=?", (int(data["sub"]),)))
    if not user or user["status"] != "ativo":
        raise HTTPException(401, "Usuário inativo")
    if not data.get("imp") and int(data.get("v", 0)) != (user.get("token_version") or 0):
        raise HTTPException(401, "Sessão encerrada (a senha foi alterada). Entre novamente.")
    user.pop("password_hash", None)
    user.pop("totp_secret", None)
    user["impersonated_by"] = None
    if data.get("imp"):
        admin = one(conn.execute("SELECT id, name, status, is_superadmin FROM users WHERE id=?", (int(data["imp"]),)))
        if not admin or not admin["is_superadmin"] or admin["status"] != "ativo":
            raise HTTPException(401, "Sessão de acesso administrativo inválida")
        user["impersonated_by"] = {"id": admin["id"], "name": admin["name"]}
    elif not user.get("is_superadmin"):
        inst = one(conn.execute("SELECT active FROM institutions WHERE id=?", (user["institution_id"],)))
        if inst and not inst["active"]:
            raise HTTPException(403, "Instituição suspensa. Fale com o suporte da plataforma.")
    return user


def require_role(*roles: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Sem permissão para este recurso")
        return user

    return dep


professor_only = require_role("professor")
aluno_only = require_role("aluno")
gestor_only = require_role("gestor")
secretaria_only = require_role("secretaria", "gestor")   # secretaria escolar (o gestor também acessa)


def superadmin_only(user: dict = Depends(current_user)) -> dict:
    """Administrador geral, na própria sessão (não enquanto acessa como outro usuário)."""
    if not user.get("is_superadmin") or user["impersonated_by"]:
        raise HTTPException(403, "Restrito ao administrador geral da plataforma")
    return user
