from aiogram import Router
from app.handlers.start import router as start_router
from app.handlers.trial import router as trial_router
from app.handlers.tariffs import router as tariffs_router

router = Router()
router.include_router(start_router)
router.include_router(trial_router)
router.include_router(tariffs_router)
