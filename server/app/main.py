"""EDU.AI — servidor da plataforma (API + site estático).

Rodar:  python -m uvicorn app.main:app --reload --port 8000   (dentro de server/)
Abrir:  http://localhost:8000          (landing)   ·   http://localhost:8000/app/   (plataforma)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import manutencao, seed
from .db import init_db
from .routes import (aluno, aprendizado, atendimento, calendario, chat, common, gestor, jogos, plataforma, professor,
                     secretaria)

WEB = Path(__file__).resolve().parents[2] / "web"


@asynccontextmanager
async def lifespan(_app):
    init_db()
    seed.run_if_empty()
    manutencao.iniciar()   # retoma processamentos interrompidos, retenção diária e resumos semanais
    yield


app = FastAPI(title="EDU.AI", version="1.0", lifespan=lifespan)
for r in (common, professor, aluno, jogos, gestor, plataforma, atendimento, calendario, chat, secretaria, aprendizado):
    app.include_router(r.router)
app.include_router(secretaria.docs_router)


@app.middleware("http")
async def no_stale_assets(request, call_next):
    """O navegador sempre confere se HTML/JS/CSS mudaram (evita telas antigas após atualizações)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    # cabeçalhos básicos de segurança
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.get("/app")
def app_redirect():
    return RedirectResponse("/app/")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
