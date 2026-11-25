"""Proteções de acesso: limite de tentativas (força bruta) e verificação em duas etapas (TOTP)."""
import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# ------------------------------------------------------------------ limite de tentativas

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request | None) -> str:
    if request is None:
        return "-"
    fwd = request.headers.get("x-forwarded-for")  # atrás de proxy reverso (nginx, Caddy…)
    return (fwd.split(",")[0].strip() if fwd else None) or (request.client.host if request.client else "-")


def limitar(chave: str, maximo: int, janela_s: int, msg: str = "Muitas tentativas. Aguarde alguns minutos e tente de novo."):
    """Conta uma tentativa para `chave`; acima de `maximo` na janela, recusa com HTTP 429."""
    agora = time.time()
    with _lock:
        q = _hits[chave]
        while q and q[0] < agora - janela_s:
            q.popleft()
        if len(q) >= maximo:
            raise HTTPException(429, msg)
        q.append(agora)
        if len(_hits) > 50_000:  # evita crescer sem limite
            for k in [k for k, v in _hits.items() if not v or v[-1] < agora - 3600]:
                del _hits[k]


def limpar(chave: str):
    with _lock:
        _hits.pop(chave, None)


# ------------------------------------------------------------------ TOTP (RFC 6238)
# Compatível com Google Authenticator, Microsoft Authenticator, Authy etc.

def novo_segredo() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo(segredo: str, contador: int) -> str:
    key = base64.b32decode(segredo + "=" * (-len(segredo) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", contador), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def verificar_totp(segredo: str | None, codigo: str) -> bool:
    """Aceita o código atual e o vizinho (±30 s) para tolerar relógios fora de sincronia."""
    codigo = (codigo or "").replace(" ", "")
    if not segredo or len(codigo) != 6 or not codigo.isdigit():
        return False
    t = int(time.time() // 30)
    return any(hmac.compare_digest(_codigo(segredo, t + d), codigo) for d in (-1, 0, 1))


def otpauth_uri(segredo: str, conta: str, emissor: str = "EDU.AI") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(emissor)}:{quote(conta)}?secret={segredo}&issuer={quote(emissor)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
