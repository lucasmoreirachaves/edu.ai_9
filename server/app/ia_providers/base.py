"""Contrato que todo provedor de IA do EDU.AI precisa cumprir.

O restante da plataforma (prompts, validação das respostas, fallback local, limites de uso)
fica em `app/ia.py` e NÃO muda quando o provedor muda. Um provedor só precisa saber:

  1. `status(model)`  — dizer se está disponível e quais modelos existem;
  2. `chat(...)`      — receber uma instrução de sistema + um pedido e devolver o TEXTO da
                        resposta, que deve ser um JSON válido no formato do `schema` recebido.

Erros:
  - `ProvedorIndisponivel`: o serviço não respondeu, a chave é inválida, acabou a cota etc.
    A plataforma usa o gerador local na mesma hora (não tenta de novo).
  - Qualquer outra exceção (ou um JSON inválido) faz a plataforma tentar de novo, até 3 vezes.
"""
from abc import ABC, abstractmethod


class ProvedorIndisponivel(Exception):
    """O provedor não pode atender agora (fora do ar, sem credencial, sem cota...)."""


class ProvedorIA(ABC):
    #: identificador gravado em materials.ai_source e em ai_usage.provider (ex.: "ollama", "nuvem")
    nome: str = "base"
    #: nome amigável mostrado nas telas (ex.: "Ollama (servidor local)")
    rotulo: str = "Provedor de IA"
    #: True quando os documentos saem do servidor da escola (aparece como aviso de privacidade)
    externo: bool = False

    @abstractmethod
    def status(self, model: str) -> dict:
        """Devolve {"online": bool, "model_installed": bool, "models": [str], "url": str}."""

    @abstractmethod
    def chat(self, system: str, prompt: str, schema: dict, model: str, temperature: float,
             timeout: int) -> str:
        """Devolve o texto da resposta (um JSON que siga `schema`).

        `schema` é um JSON Schema. Se o seu provedor aceitar "structured output"/"JSON mode",
        passe o esquema para ele; se não aceitar, acrescente o esquema ao prompt (veja
        `esquema_no_prompt`). A plataforma valida e limpa a resposta depois.
        """

    def conversar(self, messages: list[dict], model: str, temperature: float, timeout: int) -> str:
        """Chat livre (aba "Chat com IA"): recebe [{"role": "system"|"user"|"assistant", "content"}]
        e devolve o texto da resposta. Provedores que não implementarem ficam sem chat."""
        raise ProvedorIndisponivel(f"O provedor {self.rotulo} não oferece chat livre")


def esquema_no_prompt(prompt: str, schema: dict) -> str:
    """Para provedores sem saída estruturada: descreve o JSON Schema no próprio pedido."""
    import json
    return f"{prompt}\n\nResponda SOMENTE com um JSON que siga este JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
