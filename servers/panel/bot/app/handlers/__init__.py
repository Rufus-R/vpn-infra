from aiogram import Router
from app.handlers.start import router as start_router
from app.handlers.trial import router as trial_router
from app.handlers.tariffs import router as tariffs_router
from app.handlers.support import router as support_router
from app.handlers.subscriptions import router as subscriptions_router
from app.handlers.admin import router as admin_router

router = Router()
router.include_router(start_router)
router.include_router(trial_router)
router.include_router(tariffs_router)
router.include_router(support_router)
router.include_router(subscriptions_router)
router.include_router(admin_router)
