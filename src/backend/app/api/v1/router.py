from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.bedside_browser import router as bedside_browser_router
from app.api.v1.cabin import router as cabin_router
from app.api.v1.captain import router as captain_router
from app.api.v1.dial import router as dial_router
from app.api.v1.doctor import router as doctor_router
from app.api.v1.execution import router as execution_router
from app.api.v1.git import router as git_router
from app.api.v1.health import router as health_router
from app.api.v1.helmsman import router as helmsman_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.log_book import router as log_book_router
from app.api.v1.navigator import router as navigator_router
from app.api.v1.observation_deck import router as observation_deck_router
from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.return_bottle import router as return_bottle_router
from app.api.v1.sea_chest import router as sea_chest_router
from app.api.v1.shipwright import router as shipwright_router
from app.api.v1.standing_orders import router as standing_orders_router
from app.api.v1.triggers import router as triggers_router
from app.api.v1.vivre_cards import router as vivre_cards_router
from app.api.v1.voyages import router as voyages_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(auth_router)
v1_router.include_router(voyages_router)
v1_router.include_router(dial_router)
v1_router.include_router(vivre_cards_router)
v1_router.include_router(execution_router)
v1_router.include_router(git_router)
v1_router.include_router(captain_router)
v1_router.include_router(navigator_router)
v1_router.include_router(doctor_router)
v1_router.include_router(shipwright_router)
v1_router.include_router(helmsman_router)
v1_router.include_router(pipeline_router)
v1_router.include_router(return_bottle_router)
v1_router.include_router(observation_deck_router)
v1_router.include_router(log_book_router)
v1_router.include_router(standing_orders_router)
v1_router.include_router(sea_chest_router)
v1_router.include_router(triggers_router)
v1_router.include_router(bedside_browser_router)
v1_router.include_router(cabin_router)
v1_router.include_router(integrations_router)
