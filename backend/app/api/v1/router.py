from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    callbacks,
    users,
    companies,
    members,
    assets,
    digital_employees,
    tasks,
    approvals,
    video_projects,
    costs,
    connectors,
    analytics,
    publishing,
)

router = APIRouter()

router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(members.router, prefix="/companies", tags=["members"])
router.include_router(assets.router, prefix="/companies", tags=["assets"])
router.include_router(digital_employees.router, prefix="/companies", tags=["digital-employees"])
router.include_router(tasks.router, prefix="/companies", tags=["tasks"])
router.include_router(approvals.router, prefix="/companies", tags=["approvals"])
router.include_router(video_projects.router, prefix="/companies", tags=["video-projects"])
router.include_router(costs.router, prefix="/companies", tags=["costs"])
router.include_router(connectors.router, prefix="/companies", tags=["connectors"])
router.include_router(analytics.router, prefix="/companies", tags=["analytics"])
router.include_router(publishing.router, prefix="/companies", tags=["publishing"])
router.include_router(callbacks.router, tags=["callbacks"])
