"""Camada de IA do EDU.AI.

O modelo de IA em si fica em `app/ia_providers/` (Ollama por padrão; há um modelo pronto para
uma IA em nuvem). Este módulo cuida dos prompts, da validação das respostas e do fallback local.
Configuração por variáveis de ambiente:
  EDU_IA_PROVIDER   ollama (padrão) | nuvem
  EDU_IA_MODEL      modelo padrão (OLLAMA_MODEL também é aceito; padrão llama3.2 — o gestor pode trocar)
  EDU_IA_MAX_CHARS  quanto texto cabe num prompt (padrão 20000, ~6 a 8 páginas)
  EDU_IA_MAX_CHUNKS em quantas partes, no máximo, um documento longo é lido (padrão 12)
  OLLAMA_NUM_CTX    janela de contexto do modelo em tokens (padrão 16384)

Documentos maiores que EDU_IA_MAX_CHARS passam antes por `digest`: a IA lê o texto em
partes e escreve notas de estudo condensadas, e a geração trabalha sobre essas notas.

Se o provedor não responder, cada função cai num gerador local simples ("simulada"),
para a plataforma continuar utilizável. Toda função pública devolve (dados, meta),
onde meta = {provider, model, ms, chars_in, chars_out, ok, error}.

Formatos de `content` (JSON) por tipo de material:
  resumo / roteiro  {"sections":[{"title","body"}], "keywords":[str]}
  mapa        {"center":str, "branches":[{"label":str, "color":str, "children":[str]}]}
  flashcards  {"cards":[{"front","back"}]}
  exercicios  {"questions":[{"kind","statement","options":[str],"answer":int,"expected","explanation","difficulty"}]}
  glossario   {"terms":[{"term","definition","example"}]}
"""
import json
import logging
import os
import random
import re
import time

from .ia_providers import ProvedorIndisponivel, provedor
from .ia_providers.ollama import NUM_CTX, OLLAMA_URL  # noqa: F401  (OLLAMA_URL mantido por compatibilidade)

DEFAULT_MODEL = os.environ.get("EDU_IA_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.2")
MAX_CHARS = int(os.environ.get("EDU_IA_MAX_CHARS", "20000"))
MAX_CHUNKS = int(os.environ.get("EDU_IA_MAX_CHUNKS", "12"))
TIMEOUT = int(os.environ.get("EDU_IA_TIMEOUT") or os.environ.get("OLLAMA_TIMEOUT", "300"))

TYPES = ("resumo", "mapa", "flashcards", "exercicios", "roteiro", "glossario")
TYPE_LABEL = {"resumo": "Resumo", "mapa": "Mapa mental", "flashcards": "Flashcards",
              "exercicios": "Exercícios", "roteiro": "Roteiro de revisão", "glossario": "Glossário"}
# chave da lista de itens dentro de `content`, por tipo
ITEMS_KEY = {"resumo": "sections", "roteiro": "sections", "flashcards": "cards", "exercicios": "questions",
             "mapa": "branches", "glossario": "terms"}
VARIANT_LABEL = {"simplificado": "Resumo simplificado", "aprofundado": "Resumo aprofundado", "lista": "Lista de exercícios",
                 "simulado": "Simulado", "jogo": "Questionário para jogo"}
COLORS = ["#2563EB", "#16A34A", "#DC2626", "#9333EA", "#EA580C", "#0891B2", "#CA8A04"]

SYSTEM = (
    "Você é um especialista em design instrucional e professor experiente de uma plataforma educacional "
    "brasileira. Antes de escrever, você entende o material: identifica do que ele trata, qual é a ideia "
    "central, quais conceitos são essenciais e quais são detalhes secundários, e o que o estudante precisa "
    "ser capaz de explicar ou fazer depois de estudá-lo. O material que você produz prioriza o que é "
    "importante para aprender o conteúdo, não trechos aleatórios. "
    "Responda sempre em português do Brasil, com linguagem clara e adequada ao nível de ensino indicado. "
    "Use apenas informações presentes no material fornecido (ou na análise feita a partir dele); não invente "
    "fatos, números, datas ou nomes. "
    "Responda exclusivamente com JSON válido no formato pedido."
)


# ---------------------------------------------------------------- provedor (Ollama, nuvem…)

_status_cache: dict = {}
log = logging.getLogger("edu.ia")


def _modelo(p, model: str | None) -> str:
    """Modelo do pedido. Na nuvem, sem modelo informado, usa o cadastrado no provedor —
    o padrão do Ollama (ex.: llama3.2) não existe nas APIs em nuvem."""
    if model:
        return model
    if p.nome == "nuvem":
        return getattr(p, "modelo", "") or ""
    return DEFAULT_MODEL


def explicar_erro(erro: str) -> str:
    """Traduz o erro técnico do provedor numa dica curta para quem usa o chat."""
    e = erro or ""
    if "1010" in e or ("403" in e and "cloudflare" in e.lower()):
        return "A API bloqueou a requisição do servidor (HTTP 403 / Cloudflare 1010)."
    if "401" in e or "invalid_api_key" in e or "Invalid API Key" in e:
        return "A chave da API foi recusada (HTTP 401). Confira a chave cadastrada."
    if "model_not_found" in e or ("404" in e and "model" in e.lower()):
        return "O modelo cadastrado não existe nessa API (HTTP 404). Confira o nome do modelo."
    if "404" in e:
        return "O link da API não foi encontrado (HTTP 404). Confira o link cadastrado."
    if "429" in e:
        return "Limite de uso da API atingido (HTTP 429). Aguarde um pouco ou revise o plano/modelo."
    if "timed out" in e or "Timeout" in e:
        return "A API demorou demais para responder (tempo esgotado)."
    if "não configurada" in e:
        return "Link ou chave da API não cadastrados."
    return e[:200]


def status(model: str | None = None) -> dict:
    """Situação do provedor de IA ativo (cache de 10 s por provedor/endereço/modelo).

    `provider` é o nome do provedor quando ele está pronto para gerar, ou "simulada" quando a
    plataforma vai usar o gerador local."""
    model = model or DEFAULT_MODEL
    p = provedor()
    key = (p.nome, getattr(p, "url", ""), model)
    hit = _status_cache.get(key)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    st = p.status(model)
    result = {"provider": p.nome if st["online"] and st["model_installed"] else "simulada",
              "provider_name": p.nome, "provider_label": p.rotulo, "external": p.externo,
              "url": st.get("url", ""), "online": st["online"], "model": model,
              "model_installed": st["model_installed"], "models": st.get("models", [])}
    _status_cache[key] = (time.time(), result)
    return result


def _json(out: str):
    """Lê o JSON da resposta (alguns provedores cercam o JSON com ```json … ```)."""
    out = (out or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", out)
    return json.loads(out)


def _run(prompt: str, schema: dict, model: str | None, normalize, fallback, temperature=0.3):
    """Pede ao provedor (até 3 tentativas); se ele estiver indisponível, usa o gerador local."""
    p = provedor()
    model = _modelo(p, model)
    error = None
    for _ in range(3):
        t0 = time.time()
        try:
            out = p.chat(SYSTEM, prompt, schema, model, temperature, TIMEOUT)
            meta = {"provider": p.nome, "model": model, "ms": int((time.time() - t0) * 1000),
                    "chars_in": len(prompt), "chars_out": len(out or ""), "ok": True, "error": None}
            data = normalize(_json(out))
            if data:
                return data, meta
            error = "Resposta do modelo fora do formato esperado"
        except ProvedorIndisponivel as e:
            error = str(e)
            break
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            error = f"JSON inválido do modelo: {e}"
        except Exception as e:  # noqa: BLE001 — erro do provedor: tenta de novo
            error = str(e)[:300]
    log.warning("IA (%s, modelo %s) falhou; usando o gerador local: %s", p.nome, model or "(padrão)", error)
    data = fallback()
    return data, {"provider": "simulada", "model": "local", "ms": 0, "chars_in": len(prompt),
                  "chars_out": len(json.dumps(data, ensure_ascii=False)), "ok": False, "error": error}


# ---------------------------------------------------------------- Esquemas JSON

def _arr(items, mn=1):
    return {"type": "array", "items": items, "minItems": mn}


S_STR = {"type": "string"}
SCHEMAS = {
    "resumo": {"type": "object", "required": ["sections", "keywords"], "properties": {
        "sections": _arr({"type": "object", "required": ["title", "body"],
                          "properties": {"title": S_STR, "body": S_STR}}),
        "keywords": _arr(S_STR)}},
    "mapa": {"type": "object", "required": ["center", "branches"], "properties": {
        "center": S_STR,
        "branches": _arr({"type": "object", "required": ["label", "children"],
                          "properties": {"label": S_STR, "children": _arr(S_STR)}})}},
    "flashcards": {"type": "object", "required": ["cards"], "properties": {
        "cards": _arr({"type": "object", "required": ["front", "back"],
                       "properties": {"front": S_STR, "back": S_STR}})}},
    "exercicios": {"type": "object", "required": ["questions"], "properties": {
        "questions": _arr({"type": "object",
                           "required": ["kind", "statement", "options", "answer", "expected", "explanation"],
                           "properties": {"kind": {"type": "string", "enum": ["objetiva", "discursiva"]},
                                          "statement": S_STR, "options": {"type": "array", "items": S_STR},
                                          "answer": {"type": "integer"}, "expected": S_STR,
                                          "explanation": S_STR,
                                          "difficulty": {"type": "string", "enum": ["facil", "media", "dificil"]}}})}},
    "glossario": {"type": "object", "required": ["terms"], "properties": {
        "terms": _arr({"type": "object", "required": ["term", "definition", "example"],
                       "properties": {"term": S_STR, "definition": S_STR, "example": S_STR}})}},
}
SCHEMAS["roteiro"] = SCHEMAS["resumo"]
S_NOTES = {"type": "object", "required": ["notes"], "properties": {"notes": _arr(S_STR)}}
S_ANSWER = {"type": "object", "required": ["answer", "found"],
            "properties": {"answer": S_STR, "found": {"type": "boolean"}}}
S_TOPICS = {"type": "object", "required": ["topics"], "properties": {"topics": _arr(S_STR)}}
S_GRADE = {"type": "object", "required": ["score", "feedback"],
           "properties": {"score": {"type": "number"}, "feedback": S_STR}}
S_ANALYSIS = {"type": "object",
              "required": ["tema", "area", "objetivos", "conceitos", "ideias_chave", "exemplos", "erros_comuns"],
              "properties": {
                  "tema": S_STR, "area": S_STR,
                  "objetivos": _arr(S_STR),
                  "conceitos": _arr({"type": "object", "required": ["termo", "explicacao"],
                                     "properties": {"termo": S_STR, "explicacao": S_STR}}),
                  "ideias_chave": _arr(S_STR),
                  "exemplos": _arr(S_STR, 0),
                  "erros_comuns": _arr(S_STR, 0)}}
S_PLAN = {"type": "object", "required": ["intro", "steps"], "properties": {
    "intro": S_STR, "steps": _arr({"type": "object", "required": ["title", "detail"],
                                   "properties": {"title": S_STR, "detail": S_STR}})}}


# ---------------------------------------------------------------- Normalização

def _s(v) -> str:
    return str(v or "").strip()


def _unique(items, key=lambda x: x):
    """Remove repetidos (ignorando maiúsculas, espaços e pontuação final), mantendo a ordem."""
    seen, out = set(), []
    for it in items:
        k = re.sub(r"[\s.;:!]+$", "", re.sub(r"\s+", " ", key(it).lower()))
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


# "Todas as anteriores", "Nenhuma das alternativas"… dependem da ordem e ficam por último
PINNED_OPTION = re.compile(r"^(todas|nenhuma)\s+(as|das)\s+(anteriores|alternativas|acima)", re.I)


def _shuffle_options(statement: str, opts: list[str], answer: int) -> tuple[list[str], int]:
    """Modelos pequenos tendem a pôr a correta sempre na mesma letra. Embaralha de forma
    estável (mesma questão → mesma ordem), mantendo alternativas do tipo "todas as anteriores" no fim."""
    if not 0 <= answer < len(opts):
        return opts, answer
    free = [i for i, o in enumerate(opts) if not PINNED_OPTION.match(o)]
    if answer not in free:
        return opts, answer
    order = free[:]
    random.Random(statement).shuffle(order)
    order += [i for i in range(len(opts)) if i not in free]
    return [opts[i] for i in order], order.index(answer)


def normalize(kind: str, raw, from_ai: bool = False) -> dict | None:
    """Valida e limpa o conteúdo. `from_ai` embaralha as alternativas (só para o que a IA gerou;
    a ordem escolhida pelo professor numa edição manual é preservada)."""
    if not isinstance(raw, dict):
        return None
    if kind in ("resumo", "roteiro"):
        secs = [{"title": _s(s.get("title")), "body": _s(s.get("body"))}
                for s in raw.get("sections", []) if isinstance(s, dict) and _s(s.get("body"))]
        kws = _unique([_s(k) for k in raw.get("keywords", []) if _s(k)])[:10]
        return {"sections": secs, "keywords": kws} if secs else None
    if kind == "mapa":
        brs = []
        for b in _unique([b for b in raw.get("branches", []) if isinstance(b, dict) and _s(b.get("label"))],
                         key=lambda b: _s(b["label"]))[:8]:
            kids = [_s(c.get("label") if isinstance(c, dict) else c) for c in b.get("children", [])]
            color = _s(b.get("color"))
            brs.append({"label": _s(b["label"]),
                        "color": color if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else COLORS[len(brs) % len(COLORS)],
                        "children": _unique([k for k in kids if k])[:5]})
        return {"center": _s(raw.get("center")) or "Tema", "branches": brs} if brs else None
    if kind == "flashcards":
        cards = [{"front": _s(c.get("front")), "back": _s(c.get("back"))}
                 for c in raw.get("cards", []) if isinstance(c, dict) and _s(c.get("front")) and _s(c.get("back"))]
        cards = _unique(cards, key=lambda c: c["front"])
        return {"cards": cards} if cards else None
    if kind == "glossario":
        terms = [{"term": _s(t.get("term")), "definition": _s(t.get("definition")), "example": _s(t.get("example"))}
                 for t in raw.get("terms", []) if isinstance(t, dict) and _s(t.get("term")) and _s(t.get("definition"))]
        terms = _unique(terms, key=lambda t: t["term"])[:40]
        return {"terms": terms} if terms else None
    if kind == "exercicios":
        qs = []
        for q in raw.get("questions", []):
            if not isinstance(q, dict) or not _s(q.get("statement")):
                continue
            raw_opts = [_s(o) for o in q.get("options") or []]
            try:
                ans = int(q.get("answer", 0))
            except (TypeError, ValueError):
                ans = 0
            right = raw_opts[ans] if 0 <= ans < len(raw_opts) else ""
            opts = _unique([o for o in raw_opts if o])[:5]
            is_open = q.get("kind") == "discursiva" or len(opts) < 2
            if not is_open:
                # gabarito inválido (índice fora das alternativas): descarta a questão em vez de
                # assumir a alternativa A em silêncio
                if not right or right not in opts:
                    continue
                ans = opts.index(right)
                if from_ai:
                    opts, ans = _shuffle_options(_s(q["statement"]), opts, ans)
            qs.append({
                "kind": "discursiva" if is_open else "objetiva",
                "statement": _s(q["statement"]),
                "options": [] if is_open else opts,
                "answer": None if is_open else ans,
                "expected": _s(q.get("expected")),
                "explanation": _s(q.get("explanation")),
                "difficulty": _s(q.get("difficulty")) or "media",
            })
        qs = _unique(qs, key=lambda q: q["statement"])
        return {"questions": qs} if qs else None
    return None


# ---------------------------------------------------------------- Prompts

LEVELS = {"facil": "fácil", "media": "média", "dificil": "difícil"}


def _squash(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text or "").strip()


def _clip(text: str) -> str:
    return _squash(text)[:MAX_CHARS]


# ---------------------------------------------------------------- Etapa 1: análise do conteúdo
#
# Antes de gerar qualquer material, a IA lê o conteúdo e escreve uma análise estruturada (tema,
# objetivos, conceitos-chave, ideias centrais, exemplos e confusões comuns). A geração recebe essa
# análise como guia: assim o resumo cobre o que importa, os flashcards cobrem os conceitos certos e
# as questões testam os objetivos de aprendizagem, com distratores baseados em erros reais.

_ANALYSIS_CACHE: dict[str, dict] = {}   # hash(modelo + texto) -> análise (evita reanalisar o mesmo conteúdo)
_ANALYSIS_CACHE_MAX = 64


def _analysis_key(title: str, text: str, model: str | None) -> str:
    import hashlib
    return hashlib.sha1(f"{model}\0{title}\0{_clip(text)}".encode("utf-8", "ignore")).hexdigest()


def _norm_analysis(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    conceitos = [{"termo": _s(c.get("termo")), "explicacao": _s(c.get("explicacao"))}
                 for c in raw.get("conceitos", []) if isinstance(c, dict) and _s(c.get("termo"))]
    conceitos = _unique(conceitos, key=lambda c: c["termo"])[:15]
    lista = lambda k, n: _unique([_s(x) for x in raw.get(k, []) if _s(x)])[:n]  # noqa: E731
    out = {"tema": _s(raw.get("tema")), "area": _s(raw.get("area")), "objetivos": lista("objetivos", 6),
           "conceitos": conceitos, "ideias_chave": lista("ideias_chave", 15), "exemplos": lista("exemplos", 8),
           "erros_comuns": lista("erros_comuns", 8)}
    return out if out["tema"] and conceitos else None


def analyze(title: str, text: str, model: str | None = None, level: str = "") -> tuple[dict | None, dict]:
    """Etapa 1: entende o conteúdo antes de gerar. Devolve (análise ou None, meta)."""
    key = _analysis_key(title, text, model)
    if key in _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE[key], {"provider": "cache", "model": model or "-", "ms": 0, "chars_in": 0,
                                      "chars_out": 0, "ok": True, "error": None}
    prompt = (
        f"Material: \"{title}\"\n"
        + (f"Nível de ensino: {level}\n" if level else "")
        + "Tarefa: ANALISE este material como um professor faria ao planejar uma aula sobre ele. "
        "Ainda não crie exercícios; apenas entenda o conteúdo e registre:\n"
        "- 'tema': em 1 ou 2 frases, do que exatamente o material trata e qual é a ideia central;\n"
        "- 'area': disciplina e assunto (ex.: 'Biologia — fisiologia vegetal');\n"
        "- 'objetivos': 3 a 6 objetivos de aprendizagem, começando com verbo (ex.: 'Explicar…', "
        "'Diferenciar…', 'Calcular…', 'Relacionar…'), do que o estudante deve ser capaz de fazer depois de estudar;\n"
        "- 'conceitos': 5 a 15 conceitos-chave EM ORDEM DE IMPORTÂNCIA (o mais central primeiro), cada um com "
        "'termo' e 'explicacao' fiel ao material em 1 ou 2 frases. Ignore detalhes irrelevantes, cabeçalhos, "
        "nomes de autores e exemplos de rodapé;\n"
        "- 'ideias_chave': 5 a 15 afirmações completas com o que é essencial saber: definições, fatos, "
        "fórmulas, datas, etapas de processos, relações de causa e efeito e comparações;\n"
        "- 'exemplos': exemplos e aplicações que aparecem no material (lista vazia se não houver);\n"
        "- 'erros_comuns': 2 a 6 confusões ou interpretações erradas que estudantes costumam ter sobre "
        "este assunto (serão usadas para criar alternativas incorretas plausíveis).\n"
        f"\nConteúdo do material:\n\"\"\"\n{_clip(text)}\n\"\"\"")
    data, meta = _run(prompt, S_ANALYSIS, model, _norm_analysis, lambda: None, temperature=0.2)
    if data and meta["ok"]:
        if len(_ANALYSIS_CACHE) >= _ANALYSIS_CACHE_MAX:
            _ANALYSIS_CACHE.pop(next(iter(_ANALYSIS_CACHE)))
        _ANALYSIS_CACHE[key] = data
    return (data if meta["ok"] else None), meta


def _analysis_block(a: dict | None) -> str:
    """Análise em texto para entrar no prompt de geração."""
    if not a:
        return ""
    lin = [f"Tema: {a['tema']}"]
    if a.get("area"):
        lin.append(f"Área: {a['area']}")
    sec = lambda titulo, itens: [f"{titulo}:"] + [f"- {i}" for i in itens] if itens else []  # noqa: E731
    lin += sec("Objetivos de aprendizagem", a.get("objetivos"))
    lin += sec("Conceitos-chave (do mais para o menos importante)",
               [f"{c['termo']}: {c['explicacao']}" if c["explicacao"] else c["termo"] for c in a.get("conceitos", [])])
    lin += sec("Ideias e fatos essenciais", a.get("ideias_chave"))
    lin += sec("Exemplos do material", a.get("exemplos"))
    lin += sec("Confusões comuns dos estudantes", a.get("erros_comuns"))
    return ("ANÁLISE DO CONTEÚDO (feita antes por você; use-a como guia do que é importante. "
            "Se algo da análise contradisser o material, vale o material):\n" + "\n".join(lin) + "\n")


# ---------------------------------------------------------------- Etapa 2: geração

# nível de Bloom pedido em cada dificuldade
BLOOM = {"facil": "lembrar e compreender (reconhecer definições, identificar exemplos, explicar com outras palavras)",
         "media": "compreender e aplicar (interpretar situações, relacionar conceitos, usar o conceito num caso novo)",
         "dificil": "aplicar, analisar e avaliar (comparar, inferir causas e consequências, resolver problemas, "
                    "julgar afirmações)"}


def _prompt(kind: str, title: str, text: str, o: dict, analysis: dict | None = None) -> str:
    nivel = o.get("level") or "Ensino Fundamental II"
    dif_key = o.get("difficulty", "media") if o.get("difficulty") in LEVELS else "media"
    dif = LEVELS[dif_key]
    extra = f"\nInstruções do professor (siga com prioridade): {o['notes']}" if o.get("notes") else ""
    head = f"Material: \"{title}\"\nNível de ensino: {nivel}\nDificuldade: {dif}{extra}\n"
    guia = ("Use a análise acima: " if analysis else
            "Antes de escrever, identifique mentalmente o tema central, os conceitos-chave e o que o aluno precisa "
            "aprender; depois: ")
    if kind == "resumo":
        if o.get("variant") == "aprofundado":
            task = ("Escreva um RESUMO APROFUNDADO em 4 a 6 seções que sigam a lógica do conteúdo (do geral para o "
                    "específico, ou na ordem do processo/acontecimentos). Cada seção tem um título informativo "
                    "(que diga o assunto, não 'Introdução' ou 'Parte 1') e um corpo de 2 a 4 parágrafos que explique "
                    "o conceito, como ele se relaciona com os outros e traga exemplos do material. ")
        else:
            task = ("Escreva um RESUMO SIMPLIFICADO em 3 a 4 seções curtas (título informativo e 2 a 4 frases cada), "
                    "para estudo rápido: só o essencial, sem detalhes secundários. ")
        task += ("Todos os conceitos-chave principais precisam aparecer, cada um definido na primeira vez em que é "
                 "citado. Explique o porquê e as relações de causa e efeito, não apenas liste fatos. Não escreva "
                 "frases vazias como 'Este texto fala sobre…' ou 'É muito importante estudar…'. "
                 "Em 'keywords' liste de 4 a 8 conceitos-chave (termos do material, não frases).")
    elif kind == "roteiro":
        task = ("Crie um ROTEIRO DE REVISÃO para a véspera da prova, em 4 a 6 etapas ordenadas do conceito base para "
                "os mais complexos. Cada etapa é uma seção com título (ex.: 'Etapa 1 — Conceitos básicos') e um corpo "
                "dizendo exatamente o que revisar (cite os conceitos e ideias essenciais), como praticar (ex.: explicar "
                "em voz alta, fazer um esquema, resolver um exercício) e quanto tempo dedicar. Inclua um alerta sobre "
                "as confusões mais comuns. Liste os conceitos-chave em keywords.")
    elif kind == "mapa":
        task = ("Crie um MAPA MENTAL que mostre a estrutura do conteúdo: 'center' é o tema central (até 5 palavras); "
                "'branches' tem de 4 a 6 ramos com as grandes ideias (não detalhes), cada um com 'label' curto (até 4 "
                "palavras) e 2 a 4 'children' curtos (até 8 palavras) com conceitos, exemplos ou relações daquele ramo.")
    elif kind == "flashcards":
        n = int(o.get("count") or 8)
        task = (f"Crie {n} FLASHCARDS para memorização ativa. Distribua os cartões pelos conceitos-chave, começando "
                "pelos mais importantes; cada cartão testa UMA ideia e não pode repetir a de outro cartão. Varie os "
                "tipos: definição ('O que é…?'), função/finalidade ('Para que serve…?'), causa e efeito ('Por que…?' / "
                "'O que acontece quando…?'), comparação ('Qual a diferença entre… e…?') e aplicação/exemplo. "
                "'front' é uma pergunta direta e autossuficiente (entendível sem o texto; nunca 'segundo o texto'); "
                "'back' é a resposta correta, objetiva, em até 2 frases. Evite perguntas de sim/não e respostas que "
                "apenas repitam a pergunta.")
    elif kind == "glossario":
        n = int(o.get("count") or 10)
        task = (f"Crie um GLOSSÁRIO com os {n} termos mais importantes para entender o material (comece pelos "
                "conceitos-chave), sem repetir. 'term' é a palavra ou expressão; 'definition' explica o termo em 1 ou 2 "
                "frases, na linguagem do nível de ensino indicado, sem usar o próprio termo para defini-lo; 'example' "
                "traz um exemplo ou aplicação curta tirada do material (ou \"\" se não houver).")
    else:
        n = int(o.get("count") or 5)
        n_open = int(o.get("open_count") or 0)
        task = (f"Crie {n} QUESTÕES para um banco de questões. Cada questão avalia um objetivo de aprendizagem ou um "
                "conceito-chave diferente; cubra os mais importantes primeiro e não faça duas questões sobre o mesmo "
                f"ponto. Nível cognitivo pedido para a dificuldade {dif}: {BLOOM[dif_key]}. Prefira questões que exijam "
                "entender o conceito (situações, exemplos novos, causa e efeito, comparação) em vez de copiar uma frase "
                "do texto. O enunciado é claro, completo e autossuficiente (não use 'segundo o texto' a menos que "
                "a questão seja de interpretação); evite enunciados negativos ('NÃO é…'). "
                f"{n - n_open} objetivas (kind 'objetiva') com exatamente 4 alternativas em 'options' e 'answer' com o "
                "índice (0 a 3) da correta; nelas 'expected' fica \"\". Só uma alternativa pode estar correta, sem "
                "ambiguidade. Todas as alternativas respondem diretamente à pergunta do enunciado e no mesmo formato "
                "(se a pergunta é 'Qual movimento…?', as 4 alternativas são nomes de movimentos; se é 'Por que…?', "
                "as 4 são explicações). As incorretas (distratores) devem ser plausíveis, do mesmo assunto, com tamanho "
                "e estilo parecidos com a correta, e representar as confusões comuns dos estudantes; nada absurdo ou "
                "obviamente errado. Evite 'todas as anteriores' e 'nenhuma das anteriores'. ")
        if n_open:
            task += (f"{n_open} discursivas (kind 'discursiva', options vazio, answer 0) que peçam para explicar, "
                     "justificar ou relacionar conceitos, com 'expected' contendo a resposta esperada completa (os "
                     "pontos que uma resposta correta precisa ter). ")
        task += ("Em 'explanation' (até 3 frases) explique por que a resposta está correta com base no material e, "
                 "nas objetivas, por que a alternativa incorreta mais tentadora está errada. As alternativas serão "
                 "embaralhadas depois: NUNCA se refira a elas por letra, número ou posição ('alternativa B', "
                 "'a opção 2'); cite o conteúdo delas (ex.: 'quebrar máquinas era o ludismo, não o cartismo'). "
                 f"Em 'difficulty' indique a dificuldade real de cada questão (facil, media ou dificil), "
                 f"mantendo a maioria em '{dif_key}'.")
    return (f"{head}\n{_analysis_block(analysis)}\nTarefa: {guia}{task}\n\n"
            f"Conteúdo do material:\n\"\"\"\n{_clip(text)}\n\"\"\"")


# ---------------------------------------------------------------- API pública

def generate(kind: str, title: str, text: str, options: dict | None = None, model: str | None = None):
    if kind not in TYPES:
        raise ValueError(f"tipo desconhecido: {kind}")
    o = options or {}
    # Etapa 1: entender o conteúdo (fica em cache; se falhar, a geração segue sem a análise)
    analysis, ameta = analyze(title, text, model, o.get("level") or "")
    # Etapa 2: gerar o material guiado pela análise
    data, meta = _run(_prompt(kind, title, text, o, analysis), SCHEMAS[kind], model,
                      lambda raw: normalize(kind, raw, from_ai=True), lambda: fallback(kind, title, text, o))
    for k in ("ms", "chars_in", "chars_out"):
        meta[k] = (meta.get(k) or 0) + (ameta.get(k) or 0)
    meta["analysis"] = analysis
    return data, meta


def regenerate_part(kind: str, title: str, text: str, current, instructions: str, model: str | None = None):
    """Reescreve uma parte (seção, cartão, questão ou ramo) mantendo o formato."""
    wrap = ITEMS_KEY[kind]
    part_schema = SCHEMAS[kind]["properties"][wrap]["items"]
    analysis = _ANALYSIS_CACHE.get(_analysis_key(title, text, model))   # reaproveita a análise, se já existir
    prompt = (f"Material: \"{title}\"\n{_analysis_block(analysis)}\nReescreva o item abaixo de um "
              f"{TYPE_LABEL[kind].lower()}, mantendo exatamente o mesmo formato JSON e o foco no que é importante "
              f"aprender do material.\nPedido do professor: {instructions or 'melhore a clareza e a precisão'}\n"
              f"Item atual:\n{json.dumps(current, ensure_ascii=False)}\n\nConteúdo do material:\n\"\"\"\n{_clip(text)[:6000]}\n\"\"\"")

    def norm(raw):
        n = normalize(kind, {wrap: [raw], "center": "x", "keywords": []}, from_ai=True)
        return n[wrap][0] if n else None

    return _run(prompt, part_schema, model, norm, lambda: current, temperature=0.6)


def extract_topics(title: str, text: str, model: str | None = None):
    """Etapa 'IA interpreta o conteúdo': tópicos e conceitos principais.

    Usa a análise completa do conteúdo (que fica em cache e é reaproveitada na geração dos materiais)."""
    analysis, meta = analyze(title, text, model)
    if analysis:
        return [c["termo"][:60] for c in analysis["conceitos"][:8]], meta
    prompt = (f"Material: \"{title}\"\nListe de 4 a 8 tópicos/conceitos principais abordados (cada um com "
              f"até 5 palavras).\n\nConteúdo:\n\"\"\"\n{_clip(text)}\n\"\"\"")

    def norm(raw):
        t = [_s(x) for x in raw.get("topics", []) if _s(x)][:8] if isinstance(raw, dict) else []
        return t or None

    return _run(prompt, S_TOPICS, model, norm, lambda: _keywords(text, 6) or [title])


def grade_open(statement: str, expected: str, answer: str, model: str | None = None):
    """Sugestão de correção de questão discursiva. O professor valida antes de publicar."""
    if not _s(answer):
        return {"score": 0.0, "feedback": "Questão sem resposta."}, {"provider": "regra", "model": "-", "ms": 0,
                                                                      "chars_in": 0, "chars_out": 0, "ok": True, "error": None}
    prompt = (f"Corrija a resposta de um aluno.\nPergunta: {statement}\nResposta esperada: {expected}\n"
              f"Resposta do aluno: {answer}\n\nDê 'score' de 0 a 1 (aceite respostas corretas com outras palavras; "
              f"dê crédito parcial) e um 'feedback' curto, respeitoso e construtivo, dirigido ao aluno.")

    def norm(raw):
        try:
            return {"score": max(0.0, min(1.0, float(raw["score"]))), "feedback": _s(raw["feedback"])}
        except (KeyError, TypeError, ValueError):
            return None

    return _run(prompt, S_GRADE, model, norm, lambda: _grade_overlap(expected, answer), temperature=0.1)


def study_plan(student: str, weak: list[dict], materials: list[dict], model: str | None = None):
    """Plano de revisão sugerido. É recomendação de estudo, nunca avaliação da capacidade do aluno."""
    weak_txt = "\n".join(f"- {w['topic']} ({w['subject']}): {w['errors']} erro(s) em {w['total']} questão(ões)"
                         for w in weak) or "- nenhum erro registrado"
    mat_txt = "\n".join(f"- {m['title']} ({m['type']}, {m['subject']})" for m in materials[:12]) or "- nenhum"
    prompt = (f"Monte um plano de revisão curto (3 a 5 passos) para o(a) estudante {student.split()[0]}.\n"
              f"Assuntos com mais erros recentes:\n{weak_txt}\nMateriais liberados pelo professor:\n{mat_txt}\n\n"
              "Sugira somente materiais da lista. Tom encorajador; trate como recomendação de estudo, "
              "nunca como avaliação da capacidade do aluno. 'intro' com 1 ou 2 frases.")

    def norm(raw):
        try:
            steps = [{"title": _s(s["title"]), "detail": _s(s["detail"])} for s in raw["steps"] if _s(s.get("title"))]
            return {"intro": _s(raw["intro"]), "steps": steps[:6]} if steps else None
        except (KeyError, TypeError):
            return None

    return _run(prompt, S_PLAN, model, norm, lambda: _plan_fallback(weak, materials), temperature=0.5)


def needs_digest(text: str) -> bool:
    return len(_squash(text)) > MAX_CHARS


def _chunks(text: str, size: int) -> list[str]:
    """Corta em blocos de até `size` caracteres, preferindo quebrar entre parágrafos/páginas."""
    out, cur = [], ""
    for para in re.split(r"\n{2,}", text):
        while len(para) > size:  # parágrafo gigante (PDF sem quebras): corta num espaço
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if cur.strip():
                out.append(cur.strip())
                cur = ""
            out.append(para[:cut].strip())
            para = para[cut:].strip()
        if cur and len(cur) + len(para) + 2 > size:
            out.append(cur.strip())
            cur = ""
        cur += "\n\n" + para
    if cur.strip():
        out.append(cur.strip())
    return out


def digest(title: str, text: str, model: str | None = None) -> tuple[str, dict]:
    """Lê um documento longo em partes e devolve notas de estudo que cabem num prompt.

    Cada parte vira uma lista de notas (conceitos, definições, datas, fórmulas, exemplos);
    as notas de todas as partes, em ordem, substituem o texto original na geração.
    """
    size = max(MAX_CHARS, len(text) // MAX_CHUNKS + 1)
    size = min(size, int(NUM_CTX * 2.5))          # ~2,5 caracteres por token, com folga para a resposta
    parts = _chunks(_squash(text), size)
    skipped = max(0, len(parts) - MAX_CHUNKS)
    parts = parts[:MAX_CHUNKS]
    budget = max(800, MAX_CHARS // max(1, len(parts)) - 40)
    notes, total = [], {"provider": "ollama", "model": model or DEFAULT_MODEL, "ms": 0, "chars_in": 0,
                        "chars_out": 0, "ok": True, "error": None}
    for i, part in enumerate(parts, 1):
        prompt = (f"Material: \"{title}\" — parte {i} de {len(parts)}.\nLeia o trecho e escreva NOTAS DE ESTUDO com "
                  f"tudo o que é importante para aprender o conteúdo: conceitos, definições, fatos, datas, fórmulas, "
                  f"exemplos e relações de causa e efeito. Cada nota é uma frase completa e autoexplicativa. "
                  f"Use no máximo {budget // 6} palavras no total e não invente nada.\n\nTrecho:\n\"\"\"\n{part}\n\"\"\"")

        def norm(raw):
            n = [_s(x) for x in raw.get("notes", []) if _s(x)] if isinstance(raw, dict) else []
            return n or None

        got, meta = _run(prompt, S_NOTES, model, norm, lambda p=part: _extract(p, budget), temperature=0.2)
        for k in ("ms", "chars_in", "chars_out"):
            total[k] += meta.get(k) or 0
        if not meta["ok"]:
            total.update(provider=meta["provider"], model=meta["model"], ok=False, error=meta["error"])
        notes.append(f"[Parte {i}]\n" + "\n".join(f"- {n}" for n in got)[:budget])
    if skipped:
        notes.append(f"[{skipped} parte(s) final(is) do documento não foram lidas: escolha um intervalo de páginas.]")
    return "\n\n".join(notes), total


def _relevant(context: str, question: str) -> str:
    """Se o conteúdo não cabe no prompt, fica com os trechos que mais compartilham palavras com a
    pergunta (na ordem original). O início do conteúdo — o próprio material — sempre entra."""
    if not needs_digest(context):
        return _squash(context)
    blocks = _chunks(_squash(context), 1500)
    q = _words(question)
    ranked = sorted(range(1, len(blocks)), key=lambda i: -len(_words(blocks[i]) & q))
    chosen, size = {0}, len(blocks[0])
    for i in ranked:
        if size + len(blocks[i]) > MAX_CHARS:
            break
        chosen.add(i)
        size += len(blocks[i])
    return "\n\n[…]\n\n".join(blocks[i] for i in sorted(chosen))[:MAX_CHARS]


def ask(title: str, context: str, question: str, history: list[dict] | None = None,
        protect_answers: bool = False, model: str | None = None):
    """Tutor do aluno: responde dúvidas usando só o material. Devolve {"answer", "found"}."""
    hist = "\n".join(f"{'Aluno' if h.get('role') == 'aluno' else 'Tutor'}: {_s(h.get('text'))[:500]}"
                     for h in (history or [])[-6:] if _s(h.get("text")))
    rule = ("Este material tem exercícios: NÃO entregue a resposta de nenhuma questão; ajude com dicas, "
            "perguntas-guia e explicação do conceito. " if protect_answers else "")
    prompt = (f"Você é um tutor paciente que ajuda um estudante a entender o material \"{title}\".\n"
              f"Responda à pergunta usando SOMENTE o conteúdo abaixo. Explique com linguagem simples, passo a passo "
              f"quando ajudar, em no máximo 2 parágrafos curtos, e termine com uma pergunta curta que faça o aluno "
              f"pensar. {rule}Se a resposta não estiver no conteúdo, diga isso com gentileza, sugira perguntar ao "
              f"professor e marque 'found' como false.\n"
              + (f"\nConversa até agora:\n{hist}\n" if hist else "")
              + f"\nPergunta do aluno: {question}\n\nConteúdo:\n\"\"\"\n{_relevant(context, question)}\n\"\"\"")

    def norm(raw):
        if not isinstance(raw, dict) or not _s(raw.get("answer")):
            return None
        return {"answer": _s(raw["answer"]), "found": bool(raw.get("found", True))}

    return _run(prompt, S_ANSWER, model, norm, lambda: _ask_fallback(context, question), temperature=0.4)


# ---------------------------------------------------------------- Gerador local (fallback)

STOP = set("""para como mais pelo pela pelos pelas entre sobre quando onde que uma uns umas dos das com sem por
não são foi ser tem têm este esta isso essa esse estes essas esses aquele aquela também muito muitos
muita outras outros outra outro qual quais cada todo toda todos todas seus suas sua seu pode podem
deve devem assim ainda mesmo mesma depois antes durante sendo forma partir através""".split())


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    parts = [re.sub(r"^[-•*]\s+", "", p.strip()) for p in parts]  # marcadores de lista (ex.: notas condensadas)
    return [p for p in parts if len(p) > 25]


def _keywords(text: str, n: int = 6) -> list[str]:
    freq: dict[str, int] = {}
    for w in re.findall(r"[A-Za-zÀ-ÿ]{5,}", (text or "").lower()):
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    return [w.capitalize() for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:n]]


def _sentence_with(sents: list[str], word: str, default: str) -> str:
    w = word.lower()
    return next((s for s in sents if w in s.lower()), default)


def fallback(kind: str, title: str, text: str, o: dict | None = None) -> dict:
    o = o or {}
    sents = _sentences(text) or [f"{title} é o tema deste material.", "Revise os conceitos principais antes de praticar."]
    kws = _keywords(text, 8) or [title]
    if kind in ("resumo", "roteiro"):
        if kind == "roteiro":
            secs = [{"title": f"Etapa {i + 1} — {k}",
                     "body": f"Releia o trecho sobre {k.lower()}: {_sentence_with(sents, k, sents[i % len(sents)])} "
                             f"Depois, explique o conceito com suas palavras e resolva um exercício. (15 min)"}
                    for i, k in enumerate(kws[:5])]
            return {"sections": secs, "keywords": kws}
        size = 2 if o.get("variant") != "aprofundado" else 4
        chunks = [sents[i:i + size] for i in range(0, len(sents), size)][: (3 if size == 2 else 6)]
        return {"sections": [{"title": f"{kws[i % len(kws)]}", "body": " ".join(c)} for i, c in enumerate(chunks)],
                "keywords": kws[:6]}
    if kind == "mapa":
        branches = []
        for i, k in enumerate(kws[:5]):
            related = [s for s in sents if k.lower() in s.lower()][:3] or sents[i:i + 2]
            branches.append({"label": k, "color": COLORS[i % len(COLORS)],
                             "children": [s[:60].rstrip(" ,;") for s in related]})
        return {"center": title, "branches": branches}
    if kind == "flashcards":
        n = int(o.get("count") or 8)
        return {"cards": [{"front": f"O que o material diz sobre “{k}”?",
                           "back": _sentence_with(sents, k, sents[i % len(sents)])} for i, k in enumerate(kws[:n])]}
    if kind == "glossario":
        n = int(o.get("count") or 10)
        return {"terms": [{"term": k, "definition": _sentence_with(sents, k, sents[i % len(sents)]), "example": ""}
                          for i, k in enumerate(_keywords(text, n) or [title])]}
    if kind == "exercicios":
        # Sem IA: questões de "complete a frase". Uma frase do material com uma palavra-chave
        # ocultada; as alternativas são palavras-chave do próprio material (só uma completa a frase).
        n = int(o.get("count") or 5)
        n_open = int(o.get("open_count") or 0)
        pool = _keywords(text, 16) or kws
        qs, used = [], set()
        for i in range(n):
            k = kws[i % len(kws)]
            right = _sentence_with(sents, k, sents[i % len(sents)])
            if i >= n - n_open:
                qs.append({"kind": "discursiva", "statement": f"Explique, com suas palavras, o conceito de “{k}”.",
                           "options": [], "answer": None, "expected": right,
                           "explanation": f"O material afirma: {right}", "difficulty": o.get("difficulty", "media")})
                continue
            frase = next((s for s in sents if k.lower() in s.lower() and s not in used), None)
            distratores = [w for w in pool if w.lower() != k.lower() and (not frase or w.lower() not in frase.lower())]
            if not frase or len(distratores) < 3:
                continue
            used.add(frase)
            lacuna = re.sub(re.escape(k), "_____", frase, count=1, flags=re.I)
            rng = random.Random(frase)
            opts = rng.sample(distratores, 3) + [k]
            rng.shuffle(opts)
            qs.append({"kind": "objetiva", "statement": f"Complete a frase do material: “{lacuna[:220]}”",
                       "options": opts, "answer": opts.index(k), "expected": "",
                       "explanation": f"O material afirma: {frase}", "difficulty": o.get("difficulty", "media")})
        if not qs:
            qs.append({"kind": "discursiva", "statement": f"Explique, com suas palavras, o tema “{title}”.",
                       "options": [], "answer": None, "expected": sents[0],
                       "explanation": f"O material afirma: {sents[0]}", "difficulty": o.get("difficulty", "media")})
        return {"questions": qs}
    raise ValueError(kind)


def _grade_overlap(expected: str, answer: str) -> dict:
    exp = {w for w in re.findall(r"[a-zà-ÿ]{4,}", (expected or "").lower()) if w not in STOP}
    ans = {w for w in re.findall(r"[a-zà-ÿ]{4,}", (answer or "").lower()) if w not in STOP}
    score = round(len(exp & ans) / len(exp), 2) if exp else 0.5
    score = min(1.0, score * 1.4)
    fb = ("Boa resposta, cobre os pontos principais." if score >= 0.7 else
          "Resposta parcial: revise os conceitos centrais do material." if score >= 0.3 else
          "A resposta não aborda os pontos esperados. Revise o material e tente explicar com suas palavras.")
    return {"score": round(score, 2), "feedback": fb}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ]{4,}", (text or "").lower()) if w not in STOP}


def _extract(text: str, budget: int) -> list[str]:
    """Notas extrativas (sem IA): as frases que mais repetem as palavras-chave do trecho, em ordem."""
    sents = _sentences(PAGE_MARK_RE.sub("", text))
    kws = {k.lower() for k in _keywords(text, 12)}
    ranked = sorted(range(len(sents)), key=lambda i: -len(_words(sents[i]) & kws))
    chosen, size = set(), 0
    for i in ranked:
        if size + len(sents[i]) > budget:
            continue
        chosen.add(i)
        size += len(sents[i]) + 3
    return [sents[i] for i in sorted(chosen)] or [text[:budget]]


PAGE_MARK_RE = re.compile(r"^\[Página \d+\]$", re.M)


def _ask_fallback(context: str, question: str) -> dict:
    """Sem IA: devolve os trechos do material mais parecidos com a pergunta."""
    q = _words(question)
    sents = _sentences(PAGE_MARK_RE.sub("", context))
    best = [s for s in _unique(sorted(sents, key=lambda s: -len(_words(s) & q))) if _words(s) & q][:3]
    if not best:
        return {"answer": "Não encontrei isso no material. Tente usar outras palavras ou pergunte ao seu professor.",
                "found": False}
    return {"answer": "Encontrei estes trechos no material que podem ajudar:\n\n" + "\n\n".join(f"“{s}”" for s in best),
            "found": True}


def _plan_fallback(weak: list[dict], materials: list[dict]) -> dict:
    steps = []
    for w in weak[:3]:
        mats = [m for m in materials if m.get("subject") == w["subject"]][:2]
        tip = " e ".join(f"“{m['title']}” ({m['type']})" for m in mats) or "os materiais da disciplina"
        steps.append({"title": f"Revisar {w['topic']}",
                      "detail": f"Releia {tip}. Depois, refaça as questões que você errou ({w['errors']})."})
    steps.append({"title": "Praticar com flashcards", "detail": "Reserve 10 minutos por dia para os cartões pendentes de revisão."})
    return {"intro": "Este plano é uma sugestão de estudo baseada nas suas últimas atividades — use-o como guia.",
            "steps": steps}


# ---------------------------------------------------------------- Chat com IA (aba "Chat com IA")

CHAT_SYSTEM = {
    "aluno": ("Você é um tutor de estudos paciente e encorajador de uma plataforma educacional brasileira. "
              "Explique com linguagem simples, use exemplos e faça perguntas que ajudem o estudante a pensar. "
              "Não faça provas ou trabalhos avaliativos pelo aluno: oriente o raciocínio passo a passo."),
    "professor": ("Você é um assistente pedagógico de professores brasileiros. Ajude a planejar aulas, criar "
                  "atividades, rubricas, exemplos e explicações, alinhados à BNCC quando fizer sentido."),
    "secretaria": ("Você é um assistente da secretaria escolar de uma instituição brasileira. Ajude a redigir "
                   "comunicados, declarações, respostas a chamados e a organizar rotinas administrativas, "
                   "com linguagem formal e clara. Nunca invente dados de alunos."),
    "gestor": ("Você é um assistente de gestão escolar. Ajude com planejamento, indicadores, comunicação com "
               "famílias e equipe, organização do calendário e políticas da instituição."),
    "admin": ("Você é um assistente do administrador de uma plataforma educacional SaaS. Ajude com gestão de "
              "clientes (instituições), cobrança, suporte, comunicação e análise de uso."),
}


def conversar(papel: str, historico: list[dict], model: str | None = None) -> tuple[str, dict]:
    """Chat livre. `historico` = [{"role": "user"|"assistant", "content"}] (o último é a pergunta)."""
    p = provedor()
    model = _modelo(p, model)
    system = (CHAT_SYSTEM.get(papel, CHAT_SYSTEM["aluno"]) +
              " Responda sempre em português do Brasil, de forma organizada (use listas quando ajudar).")
    msgs = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": _s(m["content"])[:6000]} for m in historico[-12:] if _s(m.get("content"))]
    chars_in = sum(len(m["content"]) for m in msgs)
    t0 = time.time()
    try:
        out = _s(p.conversar(msgs, model, 0.6, TIMEOUT))
        if not out:
            raise RuntimeError("Resposta vazia do modelo")
        return out, {"provider": p.nome, "model": model, "ms": int((time.time() - t0) * 1000),
                     "chars_in": chars_in, "chars_out": len(out), "ok": True, "error": None}
    except Exception as e:  # noqa: BLE001 — sem IA, o chat avisa em vez de quebrar
        log.warning("Chat com IA falhou (%s, modelo %s): %s", p.nome, model or "(padrão)", e)
        msg = ("Não consegui falar com a IA agora. " +
               ("Confira o link e a chave da API nas configurações, ou alterne para a IA local (Ollama)."
                if p.nome == "nuvem" else
                "Verifique se o Ollama está instalado e rodando no servidor, ou alterne para a IA em nuvem.") +
               f"\n\nDetalhe: {explicar_erro(str(e))}")
        return msg, {"provider": "simulada", "model": "local", "ms": int((time.time() - t0) * 1000),
                     "chars_in": chars_in, "chars_out": len(msg), "ok": False, "error": str(e)[:300]}


# ---------------------------------------------------------------- Estúdio de aprendizado gamificado
#
# Formatos de `content` por tipo de jogo:
#   memoria           {"pairs":[{"term","definition"}]}
#   quiz              {"questions":[{"question","options":[4],"answer":int,"explanation"}]}
#   verdadeiro_falso  {"statements":[{"statement","answer":bool,"explanation"}]}
#   completar         {"sentences":[{"text" (com ___),"answer","options":[str],"explanation"}]}
#   adivinhacao       {"riddles":[{"answer","category","hints":[str]}]}
#   programacao       {"language", "challenges":[{"prompt","code","options":[str],"answer":int,"explanation"}]}

GAME_KINDS = ("memoria", "quiz", "verdadeiro_falso", "completar", "adivinhacao", "programacao")
GAME_LABEL = {"memoria": "Jogo da memória", "quiz": "Quiz relâmpago", "verdadeiro_falso": "Verdadeiro ou falso",
              "completar": "Complete a frase", "adivinhacao": "Adivinhe o conceito", "programacao": "Desafio de programação"}

_Q4 = {"type": "array", "items": S_STR, "minItems": 2}
GAME_SCHEMAS = {
    "memoria": {"type": "object", "required": ["pairs"], "properties": {"pairs": _arr(
        {"type": "object", "required": ["term", "definition"], "properties": {"term": S_STR, "definition": S_STR}})}},
    "quiz": {"type": "object", "required": ["questions"], "properties": {"questions": _arr(
        {"type": "object", "required": ["question", "options", "answer", "explanation"],
         "properties": {"question": S_STR, "options": _Q4, "answer": {"type": "integer"}, "explanation": S_STR}})}},
    "verdadeiro_falso": {"type": "object", "required": ["statements"], "properties": {"statements": _arr(
        {"type": "object", "required": ["statement", "answer", "explanation"],
         "properties": {"statement": S_STR, "answer": {"type": "boolean"}, "explanation": S_STR}})}},
    "completar": {"type": "object", "required": ["sentences"], "properties": {"sentences": _arr(
        {"type": "object", "required": ["text", "answer", "options", "explanation"],
         "properties": {"text": S_STR, "answer": S_STR, "options": _Q4, "explanation": S_STR}})}},
    "adivinhacao": {"type": "object", "required": ["riddles"], "properties": {"riddles": _arr(
        {"type": "object", "required": ["answer", "category", "hints"],
         "properties": {"answer": S_STR, "category": S_STR, "hints": _arr(S_STR, 3)}})}},
    "programacao": {"type": "object", "required": ["language", "challenges"], "properties": {
        "language": S_STR, "challenges": _arr(
            {"type": "object", "required": ["prompt", "code", "options", "answer", "explanation"],
             "properties": {"prompt": S_STR, "code": S_STR, "options": _Q4, "answer": {"type": "integer"},
                            "explanation": S_STR}})}},
}

_GAME_TASK = {
    "memoria": ("Crie um JOGO DA MEMÓRIA com {n} pares. 'term' é um conceito curto (até 4 palavras) e 'definition' "
                "uma explicação curta (até 14 palavras) que só combine com aquele termo. Sem repetir conceitos."),
    "quiz": ("Crie um QUIZ RELÂMPAGO (estilo Kahoot) com {n} perguntas curtas e diretas (até 20 palavras), cada uma com "
             "exatamente 4 alternativas curtas e só uma correta em 'answer' (índice 0 a 3). As erradas devem ser "
             "plausíveis. 'explanation' explica a resposta em 1 frase."),
    "verdadeiro_falso": ("Crie {n} afirmações de VERDADEIRO OU FALSO sobre pontos diferentes do conteúdo (metade "
                         "verdadeiras, metade falsas; as falsas trocam um detalhe importante). 'explanation' corrige "
                         "ou confirma a afirmação em 1 frase."),
    "completar": ("Crie {n} frases para COMPLETAR. Em 'text', escreva uma frase do conteúdo com UMA palavra ou expressão "
                  "importante trocada por ___ (três sublinhados). 'answer' é o que falta; 'options' tem 4 opções "
                  "(incluindo a correta, exatamente igual a 'answer'). 'explanation' em 1 frase."),
    "adivinhacao": ("Crie {n} desafios de ADIVINHE O CONCEITO. 'answer' é um conceito do conteúdo (1 a 3 palavras); "
                    "'category' diz o tipo (ex.: 'personagem', 'fórmula', 'processo'); 'hints' tem 4 dicas, da mais "
                    "difícil para a mais fácil, sem nunca escrever a resposta nas dicas."),
    "programacao": ("Crie {n} DESAFIOS DE PROGRAMAÇÃO em forma de jogo, ligados ao conteúdo (se o conteúdo não for de "
                    "programação, crie desafios simples que modelem o conceito em código, por exemplo calcular uma "
                    "fórmula ou classificar algo). Varie entre: completar a lacuna ___ no código, prever a saída e "
                    "achar o erro. 'language' é a linguagem (prefira Python, ou a do conteúdo). 'prompt' é o enunciado "
                    "curto; 'code' é o trecho de código (até 12 linhas); 'options' tem 4 opções; 'answer' o índice da "
                    "correta; 'explanation' em 1 ou 2 frases."),
}
_GAME_COUNT = {"memoria": 6, "quiz": 8, "verdadeiro_falso": 10, "completar": 8, "adivinhacao": 6, "programacao": 6}


def _norm_options(opts, answer) -> tuple[list[str], int] | None:
    raw = [_s(o) for o in (opts or [])]
    try:
        ans = int(answer)
    except (TypeError, ValueError):
        return None
    if not 0 <= ans < len(raw) or not raw[ans]:
        return None
    right = raw[ans]
    clean = _unique([o for o in raw if o])[:5]
    if len(clean) < 2 or right not in clean:
        return None
    return clean, clean.index(right)


def normalize_game(kind: str, raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if kind == "memoria":
        pairs = [{"term": _s(p.get("term"))[:60], "definition": _s(p.get("definition"))[:160]}
                 for p in raw.get("pairs", []) if isinstance(p, dict) and _s(p.get("term")) and _s(p.get("definition"))]
        pairs = _unique(pairs, key=lambda p: p["term"])[:10]
        return {"pairs": pairs} if len(pairs) >= 3 else None
    if kind == "quiz":
        qs = []
        for q in raw.get("questions", []):
            if not isinstance(q, dict) or not _s(q.get("question")):
                continue
            o = _norm_options(q.get("options"), q.get("answer"))
            if o:
                opts, ans = _shuffle_options(_s(q["question"]), *o)
                qs.append({"question": _s(q["question"]), "options": opts, "answer": ans,
                           "explanation": _s(q.get("explanation"))})
        qs = _unique(qs, key=lambda q: q["question"])[:15]
        return {"questions": qs} if qs else None
    if kind == "verdadeiro_falso":
        st = [{"statement": _s(x.get("statement")), "answer": bool(x.get("answer")), "explanation": _s(x.get("explanation"))}
              for x in raw.get("statements", []) if isinstance(x, dict) and _s(x.get("statement"))
              and isinstance(x.get("answer"), (bool, int))]
        st = _unique(st, key=lambda x: x["statement"])[:15]
        return {"statements": st} if st else None
    if kind == "completar":
        out = []
        for x in raw.get("sentences", []):
            if not isinstance(x, dict):
                continue
            text, ans = _s(x.get("text")), _s(x.get("answer"))
            if "___" not in text or not ans:
                continue
            opts = _unique([_s(o) for o in x.get("options") or [] if _s(o)])
            if ans not in opts:
                opts = opts[:3] + [ans]
            opts = opts[:5]
            random.Random(text).shuffle(opts)
            out.append({"text": text, "answer": ans, "options": opts, "explanation": _s(x.get("explanation"))})
        out = _unique(out, key=lambda x: x["text"])[:15]
        return {"sentences": out} if out else None
    if kind == "adivinhacao":
        out = []
        for x in raw.get("riddles", []):
            if not isinstance(x, dict) or not _s(x.get("answer")):
                continue
            ans = _s(x["answer"])
            hints = [h for h in (_s(h) for h in x.get("hints") or []) if h and ans.lower() not in h.lower()][:5]
            if len(hints) >= 2:
                out.append({"answer": ans[:60], "category": _s(x.get("category")) or "conceito", "hints": hints})
        out = _unique(out, key=lambda x: x["answer"])[:10]
        return {"riddles": out} if out else None
    if kind == "programacao":
        out = []
        for x in raw.get("challenges", []):
            if not isinstance(x, dict) or not _s(x.get("prompt")):
                continue
            o = _norm_options(x.get("options"), x.get("answer"))
            if o:
                opts, ans = _shuffle_options(_s(x["prompt"]) + _s(x.get("code")), *o)
                out.append({"prompt": _s(x["prompt"]), "code": str(x.get("code") or "").strip("\n")[:1500],
                            "options": opts, "answer": ans, "explanation": _s(x.get("explanation"))})
        return {"language": _s(raw.get("language")) or "Python", "challenges": out[:10]} if out else None
    return None


def learning_game(kind: str, title: str, text: str, level: str = "", model: str | None = None):
    """Gera um jogo de aprendizado a partir de um conteúdo. Devolve (content, meta)."""
    if kind not in GAME_KINDS:
        raise ValueError(f"jogo desconhecido: {kind}")
    task = _GAME_TASK[kind].format(n=_GAME_COUNT[kind])
    prompt = (f"Tema: \"{title}\"\nNível: {level or 'adequado a estudantes da educação básica'}\n"
              f"Tarefa: {task}\nUse apenas o conteúdo abaixo; se ele for só um tema curto, use conhecimento escolar "
              f"correto e consolidado sobre o tema.\n\nConteúdo:\n\"\"\"\n{_clip(text)}\n\"\"\"")
    return _run(prompt, GAME_SCHEMAS[kind], model, lambda raw: normalize_game(kind, raw),
                lambda: game_fallback(kind, title, text), temperature=0.5)


def game_fallback(kind: str, title: str, text: str) -> dict:
    """Jogos sem IA, montados a partir das frases e palavras-chave do próprio conteúdo."""
    sents = _sentences(PAGE_MARK_RE.sub("", text or "")) or [f"{title} é o tema deste estudo."]
    kws = _keywords(text, 14) or [title]
    rng = random.Random(title + kind)
    with_kw = [(k, next((s for s in sents if k.lower() in s.lower()), None)) for k in kws]
    with_kw = [(k, s) for k, s in with_kw if s]
    if kind == "memoria":
        pairs = [{"term": k, "definition": re.sub(re.escape(k), "___", s, flags=re.I)[:150]} for k, s in with_kw[:6]]
        while len(pairs) < 3:
            pairs.append({"term": f"Ideia {len(pairs) + 1}", "definition": sents[len(pairs) % len(sents)][:150]})
        return {"pairs": pairs}
    if kind in ("quiz", "completar"):
        items = []
        for k, s in with_kw[:8]:
            others = [w for w in kws if w.lower() != k.lower() and w.lower() not in s.lower()]
            if len(others) < 3:
                continue
            opts = rng.sample(others, 3) + [k]
            rng.shuffle(opts)
            lacuna = re.sub(re.escape(k), "___", s, count=1, flags=re.I)[:220]
            if kind == "quiz":
                items.append({"question": f"Qual palavra completa: “{lacuna}”?", "options": opts,
                              "answer": opts.index(k), "explanation": s})
            else:
                items.append({"text": lacuna, "answer": k, "options": opts, "explanation": s})
        if not items:
            k = kws[0]
            if kind == "quiz":
                items = [{"question": "Qual é o tema principal estudado?", "options": [title, "Outro assunto", "Nenhum", "Não sei"],
                          "answer": 0, "explanation": f"O tema é {title}."}]
            else:
                items = [{"text": "O tema deste estudo é ___.", "answer": title, "options": [title, k, "Outro", "Nenhum"],
                          "explanation": f"O tema é {title}."}]
        return {"questions": items} if kind == "quiz" else {"sentences": items}
    if kind == "verdadeiro_falso":
        st = []
        for i, (k, s) in enumerate(with_kw[:10]):
            other = next((w for w in kws if w.lower() != k.lower() and w.lower() not in s.lower()), None)
            if i % 2 and other:
                st.append({"statement": re.sub(re.escape(k), other, s, count=1, flags=re.I)[:220], "answer": False,
                           "explanation": f"O correto é: {s}"})
            else:
                st.append({"statement": s[:220], "answer": True, "explanation": "A afirmação está no conteúdo estudado."})
        return {"statements": st or [{"statement": f"Este estudo é sobre {title}.", "answer": True, "explanation": ""}]}
    if kind == "adivinhacao":
        rid = []
        for k, s in with_kw[:6]:
            frase = re.sub(re.escape(k), "___", s, flags=re.I)[:200]
            rid.append({"answer": k, "category": "conceito do conteúdo",
                        "hints": [frase, f"Tem {len(k)} letras.", f"Começa com “{k[0].upper()}”.", f"Termina com “{k[-1]}”."]})
        return {"riddles": rid or [{"answer": title, "category": "tema",
                                    "hints": ["É o assunto deste estudo.", f"Tem {len(title)} caracteres.", f"Começa com “{title[0]}”."]}]}
    if kind == "programacao":
        # sem IA: desafios de lógica em Python, montados com termos do conteúdo
        termos = [k.lower() for k in kws[:4]] or ["estudo"]
        ch = [
            {"prompt": "Qual é a saída do código?", "code": f"conceitos = {termos!r}\nprint(len(conceitos))",
             "options": [str(len(termos)), str(len(termos) + 1), "0", "Erro"], "answer": 0,
             "explanation": "len() devolve a quantidade de itens da lista."},
            {"prompt": "Complete a lacuna para mostrar o primeiro conceito.", "code": f"conceitos = {termos!r}\nprint(conceitos[___])",
             "options": ["0", "1", "-0.5", "'primeiro'"], "answer": 0, "explanation": "Em Python, as listas começam no índice 0."},
            {"prompt": "Qual linha tem erro?", "code": f'nota = 7\nif nota >= 6\n    print("Aprovado em {termos[0]}")',
             "options": ["Linha 1", "Linha 2: faltam os dois-pontos", "Linha 3", "Não há erro"], "answer": 1,
             "explanation": "Em Python, o if termina com dois-pontos (:)."},
            {"prompt": "Qual é a saída do código?",
             "code": "pontos = 0\nfor acerto in [True, False, True]:\n    if acerto:\n        pontos += 10\nprint(pontos)",
             "options": ["20", "30", "10", "0"], "answer": 0, "explanation": "Só os dois acertos somam 10 pontos cada."},
        ]
        return {"language": "Python", "challenges": ch}
    raise ValueError(kind)
