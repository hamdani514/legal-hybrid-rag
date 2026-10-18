from fastapi import APIRouter
from modules.payment.controller import router as controller_router
from modules.payment.webhook import router as webhook_router

router = APIRouter(prefix="/api/payments", tags=["payments"])
router.include_router(controller_router)
router.include_router(webhook_router)

__all__ = ["router"]
