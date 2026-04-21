from fastapi import APIRouter

api_router = APIRouter()

from src.auth.router import router as auth_router
from src.health.router import router as health_router
from src.salesforce.router import router as salesforce_router

api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(salesforce_router)
