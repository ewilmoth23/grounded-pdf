from fastapi import APIRouter

from app.api.routes import conversations, documents, health, settings

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations", "messages"]
)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
