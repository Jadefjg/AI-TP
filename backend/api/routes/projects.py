from fastapi import APIRouter, Depends, HTTPException
from pathlib import Path
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_user, require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import Project, Recipient, TestRun, User
from backend.schemas.dto import (
    ProjectAiCredentialIn,
    ProjectAiCredentialOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RecipientCreate,
    RecipientOut,
    RunOut,
)
from backend.services.audit_service import log_action
from backend.services.credential_service import credential_status, require_project_credential_access, upsert_project_credential
from backend.services.project_service import delete_project
from backend.services.repo_workspace import is_deployed_url, is_remote_repo
from backend.services.tenant_service import (
    assert_project_quota,
    filter_projects_for_user,
    get_organization,
    get_project_for_user,
    resolve_organization_id_for_user,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _normalize_repo_fields(
    *,
    repo_source: str | None,
    code_root: str | None,
    repo_branch: str | None,
) -> tuple[str, str, str | None]:
    source = (repo_source or "local").strip().lower()
    if source not in {"local", "remote", "deployed"}:
        raise HTTPException(status_code=400, detail="repo_source must be local, remote or deployed")
    root = (code_root or "").strip()
    if not root:
        raise HTTPException(status_code=400, detail="code_root is required")

    if source == "deployed":
        if not is_deployed_url(root):
            raise HTTPException(
                status_code=400,
                detail="已部署项目请填写 http(s) 运行地址（非 Git 仓库地址）",
            )
        return root, "deployed", None
    if source == "remote":
        if not is_remote_repo(root):
            raise HTTPException(
                status_code=400,
                detail="远程仓库 URL 格式不正确，请使用 git@ / ssh://，或带 .git / Git 托管域名的 http(s) 地址",
            )
        branch = (repo_branch or "main").strip() or "main"
        return root, "remote", branch

    if is_remote_repo(root) or is_deployed_url(root):
        raise HTTPException(
            status_code=400,
            detail="本地仓库请填写本机绝对路径；Git URL 请选远程仓库，运行地址请选已部署 URL",
        )
    path = Path(root).expanduser()
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail="本地仓库请填写绝对路径")
    branch = (repo_branch or "main").strip() or "main"
    return root, "local", branch


@router.post("", response_model=ProjectOut, dependencies=[Depends(require_permission("project.write"))])
def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    org_id = resolve_organization_id_for_user(user, body.organization_id)
    if org_id is None:
        from backend.services.tenant_service import seed_default_organization

        org_id = seed_default_organization(db).id
    org = get_organization(db, org_id)
    assert_project_quota(db, org)
    code_root, inferred_source, branch = _normalize_repo_fields(
        repo_source=body.repo_source,
        code_root=body.code_root,
        repo_branch=body.repo_branch,
    )

    row = Project(
        organization_id=org.id,
        name=body.name.strip(),
        description=body.description,
        code_root=code_root,
        repo_source=inferred_source,
        repo_branch=branch,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="projects",
        action="project.created",
        message=f"project {row.name} created",
        detail={"project_id": row.id, "organization_id": row.organization_id, "repo_source": row.repo_source},
        organization_id=row.organization_id,
        project_id=row.id,
    )
    return row


@router.get("", response_model=list[ProjectOut], dependencies=[Depends(require_permission("project.read"))])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Project]:
    query = filter_projects_for_user(db.query(Project), user)
    return query.order_by(Project.id.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_permission("project.read"))])
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Project:
    return get_project_for_user(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_permission("project.write"))])
def update_project(
    project_id: int,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = get_project_for_user(db, user, project_id)
    code_root, inferred_source, branch = _normalize_repo_fields(
        repo_source=body.repo_source,
        code_root=body.code_root,
        repo_branch=body.repo_branch,
    )
    project.name = body.name.strip()
    project.description = body.description
    project.code_root = code_root
    project.repo_source = inferred_source
    project.repo_branch = branch
    db.add(project)
    db.commit()
    db.refresh(project)
    log_action(
        db,
        module="projects",
        action="project.updated",
        message=f"project {project.name} updated",
        detail={"project_id": project.id, "repo_source": project.repo_source},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return project


@router.delete("/{project_id}", dependencies=[Depends(require_permission("project.write"))])
def remove_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_project_for_user(db, user, project_id)
    name = project.name
    org_id = project.organization_id
    delete_project(db, project)
    db.commit()
    log_action(
        db,
        module="projects",
        action="project.deleted",
        message=f"project {name} deleted",
        detail={"project_id": project_id, "organization_id": org_id},
        organization_id=org_id,
        project_id=None,
    )
    return {"deleted": True, "project_id": project_id}


@router.get(
    "/{project_id}/ai-credentials",
    response_model=ProjectAiCredentialOut,
    dependencies=[Depends(require_permission("settings.read"))],
)
def get_project_ai_credentials(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectAiCredentialOut:
    project = require_project_credential_access(db, user, project_id)
    return ProjectAiCredentialOut(project_id=project.id, **credential_status(db, project))


@router.put(
    "/{project_id}/ai-credentials",
    response_model=ProjectAiCredentialOut,
    dependencies=[Depends(require_permission("settings.write"))],
)
def put_project_ai_credentials(
    project_id: int,
    body: ProjectAiCredentialIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectAiCredentialOut:
    project = require_project_credential_access(db, user, project_id)
    upsert_project_credential(
        db,
        project=project,
        provider=body.provider,
        api_base_url=body.api_base_url,
        api_key=body.api_key,
        model_override=body.model_override,
        enabled=body.enabled,
    )
    log_action(
        db,
        module="projects",
        action="project.ai_credentials.updated",
        message=f"project #{project.id} BYOK updated",
        project_id=project.id,
        organization_id=project.organization_id,
    )
    return ProjectAiCredentialOut(project_id=project.id, **credential_status(db, project))


@router.get("/{project_id}/runs", response_model=list[RunOut], dependencies=[Depends(require_permission("run.read"))])
def list_project_runs(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[TestRun]:
    return (
        db.query(TestRun)
        .options(selectinload(TestRun.items))
        .filter(TestRun.project_id == project.id)
        .order_by(TestRun.id.desc())
        .all()
    )


@router.get(
    "/{project_id}/recipients",
    response_model=list[RecipientOut],
    dependencies=[Depends(require_permission("project.read"))],
)
def list_recipients(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[Recipient]:
    return (
        db.query(Recipient)
        .filter(Recipient.project_id == project.id)
        .order_by(Recipient.id.asc())
        .all()
    )


@router.post(
    "/{project_id}/recipients",
    response_model=RecipientOut,
    dependencies=[Depends(require_permission("project.write"))],
)
def add_recipient(
    body: RecipientCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> Recipient:
    row = Recipient(project_id=project.id, email=body.email, display_name=body.display_name)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="projects",
        action="project.recipient_added",
        message=f"recipient added to project #{project.id}",
        detail={"project_id": project.id, "recipient_id": row.id, "email": row.email},
        project_id=project.id,
        organization_id=project.organization_id,
    )
    return row


@router.delete(
    "/{project_id}/recipients/{recipient_id}",
    dependencies=[Depends(require_permission("project.write"))],
)
def delete_recipient(
    recipient_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(Recipient)
        .filter(Recipient.id == recipient_id, Recipient.project_id == project.id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="recipient not found")
    email = row.email
    db.delete(row)
    db.commit()
    log_action(
        db,
        module="projects",
        action="project.recipient_removed",
        message=f"recipient removed from project #{project.id}",
        detail={"project_id": project.id, "recipient_id": recipient_id, "email": email},
        project_id=project.id,
        organization_id=project.organization_id,
    )
    return {"ok": True}
