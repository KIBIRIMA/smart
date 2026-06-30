"""Point d'entrée FastAPI — Smart Transport AI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("startup").info("Smart Transport AI — API démarrée (%s)", settings.APP_ENV)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Plateforme d'optimisation logistique — Accès Industrie",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}
