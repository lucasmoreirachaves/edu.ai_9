"""Provedor padrão: Ollama (modelos rodando no próprio servidor da escola).

Variáveis de ambiente: OLLAMA_URL (padrão http://127.0.0.1:11434) e OLLAMA_NUM_CTX (padrão 16384).
"""
import json
import os
import urllib.error
import urllib.request

from .base import ProvedorIA, ProvedorIndisponivel, esquema_no_prompt

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))


class ProvedorOllama(ProvedorIA):
    nome = "ollama"
    rotulo = "Ollama (servidor local)"
    externo = False

    def __init__(self, url: str = OLLAMA_URL):
        self.url = url
        self._sem_schema = False  # Ollama < 0.5 não aceita JSON Schema em "format"

    def status(self, model: str) -> dict:
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=3) as r:
                data = json.loads(r.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            has = any(m == model or m.split(":")[0] == model for m in models)
            return {"online": True, "model_installed": has, "models": models, "url": self.url}
        except (urllib.error.URLError, OSError, ValueError):
            return {"online": False, "model_installed": False, "models": [], "url": self.url}

    def chat(self, system, prompt, schema, model, temperature, timeout):
        fmt, text = ("json", esquema_no_prompt(prompt, schema)) if self._sem_schema else (schema, prompt)
        payload = {
            "model": model, "stream": False, "format": fmt,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
            "options": {"temperature": temperature, "num_ctx": NUM_CTX},
        }
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:200]
            if e.code == 400 and not self._sem_schema:
                self._sem_schema = True       # versão antiga: repete com format="json"
                return self.chat(system, prompt, schema, model, temperature, timeout)
            if e.code == 404:
                raise ProvedorIndisponivel(f"Modelo '{model}' não instalado no Ollama (rode: ollama pull {model})")
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError) as e:
            raise ProvedorIndisponivel(f"Ollama indisponível em {self.url} ({e})")
        return data.get("message", {}).get("content", "")

    def conversar(self, messages, model, temperature, timeout):
        payload = {"model": model, "stream": False, "messages": messages,
                   "options": {"temperature": temperature, "num_ctx": NUM_CTX}}
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ProvedorIndisponivel(f"Modelo '{model}' não instalado no Ollama (rode: ollama pull {model})")
            raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}")
        except (urllib.error.URLError, OSError) as e:
            raise ProvedorIndisponivel(f"Ollama indisponível em {self.url} ({e})")
        return data.get("message", {}).get("content", "")
