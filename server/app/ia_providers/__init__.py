"""Provedores de IA intercambiáveis.

Quem decide o provedor de cada pedido:
  1. A configuração ativa (`usar_config`), montada a partir da instituição e do usuário:
     - a instituição cadastra o LINK e a CHAVE da API da IA em nuvem (vale para todos dela);
     - cada usuário escolhe entre IA em nuvem e IA local (Ollama) no chat ou no perfil;
     - o administrador geral da plataforma tem link/chave próprios.
  2. Sem configuração ativa: a variável de ambiente EDU_IA_PROVIDER (ollama | nuvem).

Para adicionar outro provedor: crie uma classe que herde de `ProvedorIA` (base.py),
registre-a em PROVEDORES abaixo e defina EDU_IA_PROVIDER com o nome dela.
"""
import contextvars
import os

from .base import ProvedorIA, ProvedorIndisponivel
from .nuvem import ProvedorNuvem
from .ollama import ProvedorOllama

PROVEDORES: dict[str, type[ProvedorIA]] = {
    "ollama": ProvedorOllama,
    "nuvem": ProvedorNuvem,
}

_atual: ProvedorIA | None = None
_ollama: ProvedorOllama | None = None
# {"mode": "nuvem"|"local", "url", "key", "model"} — definido por requisição/tarefa (util.ai_model)
_config: contextvars.ContextVar[dict | None] = contextvars.ContextVar("edu_ia_config", default=None)


def usar_config(cfg: dict | None):
    """Define o provedor dos próximos pedidos de IA neste contexto (requisição ou tarefa)."""
    _config.set(cfg)


def config_atual() -> dict | None:
    return _config.get()


def _padrao() -> ProvedorIA:
    global _atual
    if _atual is None:
        nome = os.environ.get("EDU_IA_PROVIDER", "ollama").strip().lower()
        if nome not in PROVEDORES:
            raise RuntimeError(f"EDU_IA_PROVIDER='{nome}' desconhecido. Opções: {', '.join(PROVEDORES)}")
        _atual = PROVEDORES[nome]()
    return _atual


def provedor() -> ProvedorIA:
    """Provedor da configuração ativa; sem configuração, o definido no ambiente."""
    global _ollama
    cfg = _config.get()
    if _atual is not None and getattr(_atual, "_fixo", False):
        return _atual                       # provedor trocado em testes
    if not cfg:
        return _padrao()
    if cfg.get("mode") == "nuvem" and cfg.get("url") and cfg.get("key"):
        return ProvedorNuvem(cfg["url"], cfg["key"], cfg.get("model") or "")
    if os.environ.get("EDU_IA_PROVIDER", "ollama").strip().lower() == "ollama" or cfg.get("mode") == "local":
        if _ollama is None:
            _ollama = ProvedorOllama()
        return _ollama
    return _padrao()


def definir_provedor(p: ProvedorIA):
    """Troca o provedor em tempo de execução (útil em testes): vale para todos os pedidos."""
    global _atual
    p._fixo = True
    _atual = p


__all__ = ["ProvedorIA", "ProvedorIndisponivel", "provedor", "definir_provedor", "usar_config", "config_atual", "PROVEDORES"]
