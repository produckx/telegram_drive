from fastapi import APIRouter
from api.auth.router import router as auth_router
from api.files.router import router as files_router
from api.folders.router import router as folders_router
from api.storage.router import router as storage_router
from api.shares.router import router as shares_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(files_router)
router.include_router(folders_router)
router.include_router(storage_router)
router.include_router(shares_router)