"""IA EM NUVEM — qualquer API no formato "chat completions".

Quem configura
--------------
- O GESTOR DA INSTITUIÇÃO cadastra, no painel (Configurações → IA em nuvem), o LINK da API e a
  CHAVE da API. A configuração vale para todos da instituição (professores, alunos, secretaria
  e gestores), e cada um pode alternar entre a IA em nuvem e a IA local (Ollama) no chat ou nas
  configurações do perfil.
- O ADMINISTRADOR GERAL da plataforma cadastra link e chave próprios (Administração → Minha IA).
- Sem nada cadastrado no painel, ainda vale a configuração por variáveis de ambiente:
     EDU_IA_PROVIDER=nuvem
     EDU_NUVEM_URL=https://sua-ia.exemplo.com/v1/chat/completions
     EDU_NUVEM_API_KEY=chave-secreta              (nunca grave a chave no código)
     EDU_NUVEM_MODELO=nome-do-modelo-padrao
     EDU_NUVEM_MODELOS=modelo-a,modelo-b          (opcional: lista mostrada ao gestor)

Formato
-------
Funciona com APIs compatíveis com "chat completions" (OpenAI, OpenRouter, Groq, DeepSeek,
Mistral, Together, Google Gemini pelo endpoint compatível, Azure OpenAI etc.). O link pode ser
o endereço completo (…/v1/chat/completions) ou só a base (…/v1): o final é completado aqui.
Se a sua IA usar outro formato, troque apenas `_montar_pedido` e `_ler_resposta`.

LGPD
----
Com um provedor externo, o texto dos documentos dos professores e as dúvidas dos alunos (que
podem ser menores de idade) saem do servidor da escola. Garanta contrato de tratamento de dados
com o provedor e que ele não use os dados para treinar modelos. As telas avisam quando a IA é externa.
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

from .base import ProvedorIA, ProvedorIndisponivel, esquema_no_prompt

NUVEM_URL = os.environ.get("EDU_NUVEM_URL", "")
NUVEM_API_KEY = os.environ.get("EDU_NUVEM_API_KEY", "")
NUVEM_MODELO = os.environ.get("EDU_NUVEM_MODELO", "")
NUVEM_MODELOS = [m.strip() for m in os.environ.get("EDU_NUVEM_MODELOS", "").split(",") if m.strip()]
NUVEM_MAX_TOKENS = int(os.environ.get("EDU_NUVEM_MAX_TOKENS") or 0) or None   # opcional: teto de tokens de saída

log = logging.getLogger("edu.ia.nuvem")
# max_tokens descoberto por (link, modelo) quando a API recusa o pedido por limite de tokens de saída
_MAX_TOKENS: dict[tuple[str, str], int] = {}


ESPERA_MAX = float(os.environ.get("EDU_NUVEM_ESPERA_MAX") or 60)   # segundos, somando as esperas de um pedido


def _espera_pedida(e, detail: str) -> float | None:
    """Em HTTP 429 por limite de uso, quantos segundos a API pediu para aguardar."""
    if e.code != 429:
        return None
    try:
        retry_after = float(e.headers.get("retry-after") or "")
    except (TypeError, ValueError):
        retry_after = None
    m = re.search(r"try again in\s+(?:(\d+)m)?([\d.]+)s", detail)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return retry_after


def _limite_de_tokens(code: int, detail: str) -> int | None:
    """Se o erro diz que o pedido excede o limite de tokens de saída, devolve esse limite."""
    if code not in (400, 413, 429) or "max_tokens" not in detail:
        return None
    m = re.search(r"Limit\s+(\d+)", detail)
    return max(64, int(m.group(1)) - 16) if m else None


def endpoint(url: str) -> str:
    """Aceita a base da API (…/v1) ou o endereço completo (…/chat/completions)."""
    url = (url or "").strip().rstrip("/")
    if url and not url.endswith("/chat/completions") and not url.endswith("/completions"):
        url += "/chat/completions"
    return url


class ProvedorNuvem(ProvedorIA):
    nome = "nuvem"
    rotulo = "IA em nuvem"
    externo = True

    def __init__(self, url: str = NUVEM_URL, api_key: str = NUVEM_API_KEY, modelo: str = NUVEM_MODELO):
        self.url = endpoint(url)
        self.api_key = api_key
        self.modelo = modelo
        self._json_simples = False  # API sem "json_schema": usa "json_object" + esquema no pedido

    # ------------------------------------------------------------------ disponibilidade
    def status(self, model: str) -> dict:
        configurado = bool(self.url and self.api_key)
        modelos = NUVEM_MODELOS or ([self.modelo] if self.modelo else [])
        return {"online": configurado, "model_installed": configurado, "models": modelos,
                "url": self.url or "(link da API não cadastrado)"}

    # ------------------------------------------------------------------ chamada HTTP
    def _post(self, body: dict, timeout: int, _espera: float = 0) -> dict:
        if not (self.url and self.api_key):
            raise ProvedorIndisponivel("IA em nuvem não configurada (cadastre o link e a chave da API)")
        body = self._com_limite(body)
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Authorization": f"Bearer {self.api_key}",
                     "api-key": self.api_key,     # "api-key": formato do Azure OpenAI
                     # Sem User-Agent próprio, o urllib manda "Python-urllib/3.x", que o Cloudflare
                     # (na frente da Groq e de outras APIs) bloqueia com "HTTP 403: error code: 1010".
                     "User-Agent": "EduAI/1.0 (+https://edu.ai)"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:600]
            limite = _limite_de_tokens(e.code, detail)
            if limite and body.get("max_tokens") != limite:
                # ex.: Groq gratuito: "Request too large ... (OTPM): Limit 1000, Requested 1435 ...
                # reduce max_tokens". Guarda o limite e repete o pedido dentro dele.
                _MAX_TOKENS[(self.url, body.get("model"))] = limite
                return self._post({**body, "max_tokens": limite}, timeout, _espera)
            espera = _espera_pedida(e, detail)
            if espera is not None and espera + _espera <= ESPERA_MAX:
                # limite por minuto (ex.: Groq gratuito, "Please try again in 38.8s"): espera e repete
                log.info("IA em nuvem pediu para aguardar %.1fs (limite de uso); tentando de novo", espera)
                time.sleep(espera + 0.5)
                return self._post(body, timeout, _espera + espera)
            log.warning("IA em nuvem respondeu HTTP %s (%s, modelo %s): %s", e.code, self.url, body.get("model"), detail)
            if e.code in (401, 403, 429) or e.code >= 500:
                # credencial inválida, cota esgotada ou serviço fora do ar: usa o modo local
                raise ProvedorIndisponivel(f"IA em nuvem HTTP {e.code}: {detail}")
            raise RuntimeError(f"IA em nuvem HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            log.warning("IA em nuvem indisponível (%s): %s", self.url, e)
            raise ProvedorIndisponivel(f"IA em nuvem indisponível ({e})")

    def _com_limite(self, body: dict) -> dict:
        """Aplica o max_tokens já descoberto para este link/modelo (ou o de EDU_NUVEM_MAX_TOKENS)."""
        limite = _MAX_TOKENS.get((self.url, body.get("model"))) or NUVEM_MAX_TOKENS
        return {**body, "max_tokens": limite} if limite else body

    # ------------------------------------------------------------------ geração estruturada
    def chat(self, system, prompt, schema, model, temperature, timeout):
        body = self._montar_pedido(system, prompt, schema, model or self.modelo, temperature)
        try:
            data = self._post(body, timeout)
        except RuntimeError as e:
            if self._json_simples or "400" not in str(e):
                raise
            self._json_simples = True       # a API não aceita json_schema: tenta o modo JSON simples
            data = self._post(self._montar_pedido(system, prompt, schema, model or self.modelo, temperature), timeout)
        return self._ler_resposta(data)

    def conversar(self, messages, model, temperature, timeout):
        data = self._post({"model": model or self.modelo, "temperature": temperature, "messages": messages}, timeout)
        return self._ler_resposta(data)

    # ------------------------------------------------------------------ formato da API
    def _montar_pedido(self, system: str, prompt: str, schema: dict, model: str, temperature: float) -> dict:
        if self._json_simples:
            return {"model": model, "temperature": temperature,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": esquema_no_prompt(prompt, schema)}],
                    "response_format": {"type": "json_object"}}
        return {
            "model": model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "resposta", "schema": schema}},
        }

    def _ler_resposta(self, data: dict) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"Resposta inesperada da IA em nuvem: {str(data)[:200]}")
        if isinstance(content, list):   # alguns provedores devolvem partes [{type, text}]
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return content or ""
