from fastapi import APIRouter
from web.home.router import router as home_router
from web.files.router import router as files_router
from web.folders.router import router as folders_router
from web.storage.router import router as storage_router
from web.auth.router import router as auth_router
from web.admin.router import router as admin_router

router = APIRouter()
router.include_router(home_router)
router.include_router(files_router)
router.include_router(folders_router)
router.include_router(storage_router)
router.include_router(auth_router)
router.include_router(admin_router)