from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.version import APP_VERSION
from backend.models.entities import AuditLog, Permission, Project, Role, SystemSetting, User
from backend.schemas.dto import SystemOverviewOut


def build_system_overview(db: Session) -> SystemOverviewOut:
    return SystemOverviewOut(
        api_name="AI 测试平台 API",
        api_version=APP_VERSION,
        project_count=db.query(func.count(Project.id)).scalar() or 0,
        user_count=db.query(func.count(User.id)).scalar() or 0,
        role_count=db.query(func.count(Role.id)).scalar() or 0,
        permission_count=db.query(func.count(Permission.id)).scalar() or 0,
        setting_count=db.query(func.count(SystemSetting.id)).scalar() or 0,
        log_count=db.query(func.count(AuditLog.id)).scalar() or 0,
    )
