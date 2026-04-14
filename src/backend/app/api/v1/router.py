from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.captain import router as captain_router
from app.api.v1.dial import router as dial_router
from app.api.v1.execution import router as execution_router
from app.api.v1.git import router as git_router
from app.api.v1.health import router as health_router
from app.api.v1.vivre_cards import router as vivre_cards_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(auth_router)
v1_router.include_router(dial_router)
v1_router.include_router(vivre_cards_router)
v1_router.include_router(execution_router)
v1_router.include_router(git_router)
v1_router.include_router(captain_router)
