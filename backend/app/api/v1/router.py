"""Agrège toutes les routes de l'API v1."""
from fastapi import APIRouter
from app.api.v1 import auth, entities, dashboard, optimizer, import_missions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(entities.router)
api_router.include_router(dashboard.router)
api_router.include_router(optimizer.router)
api_router.include_router(import_missions.router)
