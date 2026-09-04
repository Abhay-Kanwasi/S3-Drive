from fastapi import APIRouter

from api.endpoints import (
    boto_services, browse, uam_services, admin, groups, users, audit,
    viewer, files, notifications, otp, approval, unonboard, stars,
)

api_router = APIRouter()
api_router.include_router(boto_services.router, prefix="/services", tags=["services"])
api_router.include_router(browse.router, prefix="/browse", tags=["browse"])
api_router.include_router(uam_services.router, prefix="/uam", tags=["uam"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(groups.router, prefix="/admin", tags=["groups"])
api_router.include_router(users.router, prefix="/admin", tags=["users"])
api_router.include_router(audit.router, prefix="/admin", tags=["audit"])
api_router.include_router(otp.router, prefix="/admin", tags=["otp"])
api_router.include_router(approval.router, prefix="/admin", tags=["approval"])
api_router.include_router(unonboard.router, prefix="/admin", tags=["unonboard"])
api_router.include_router(viewer.router, prefix="/viewer", tags=["viewer"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(stars.router, prefix="/stars", tags=["stars"])
