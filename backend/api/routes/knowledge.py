from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import KnowledgeChunk, Project
from backend.schemas.dto import KnowledgeChunkOut, KnowledgeIn, KnowledgeSearchOut
from backend.services.audit_service import log_action
from backend.services.rag_service import ingest_knowledge, search_knowledge_with_scores

router = APIRouter(prefix="/projects", tags=["knowledge"])


@router.post(
    "/{project_id}/knowledge/chunks",
    response_model=list[KnowledgeChunkOut],
    dependencies=[Depends(require_permission("knowledge.write"))],
)
def add_knowledge_chunks(
    body: KnowledgeIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[KnowledgeChunk]:
    chunks = ingest_knowledge(
        db,
        project_id=project.id,
        source=body.source,
        title=body.title,
        content=body.content,
        tags=body.tags,
    )
    log_action(
        db,
        module="knowledge",
        action="knowledge.ingested",
        message=f"ingested {len(chunks)} chunks for project #{project.id}",
        detail={"project_id": project.id, "count": len(chunks), "source": body.source},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return chunks


@router.get(
    "/{project_id}/knowledge/search",
    response_model=KnowledgeSearchOut,
    dependencies=[Depends(require_permission("knowledge.read"))],
)
def search_knowledge(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> KnowledgeSearchOut:
    hits = search_knowledge_with_scores(db, project_id=project.id, query=q, top_k=top_k)
    return KnowledgeSearchOut(query=q, hits=hits)


@router.get(
    "/{project_id}/knowledge/chunks",
    response_model=list[KnowledgeChunkOut],
    dependencies=[Depends(require_permission("knowledge.read"))],
)
def list_knowledge_chunks(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[KnowledgeChunk]:
    return (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.project_id == project.id)
        .order_by(KnowledgeChunk.id.desc())
        .all()
    )


@router.delete(
    "/{project_id}/knowledge/chunks/{chunk_id}",
    response_model=dict,
    dependencies=[Depends(require_permission("knowledge.write"))],
)
def delete_knowledge_chunk(
    chunk_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    chunk = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.project_id == project.id, KnowledgeChunk.id == chunk_id)
        .one_or_none()
    )
    if not chunk:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="chunk not found")
    db.delete(chunk)
    db.commit()
    log_action(
        db,
        module="knowledge",
        action="knowledge.deleted",
        message=f"deleted knowledge chunk #{chunk_id}",
        detail={"project_id": project.id, "chunk_id": chunk_id},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return {"ok": True, "deleted_id": chunk_id}
