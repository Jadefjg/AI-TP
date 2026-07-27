from sqlalchemy.orm import Session

from backend.models.entities import (
    AiArtifact,
    AiCallLog,
    AiWorkbenchMessage,
    AiWorkbenchSession,
    ApiRegressionSet,
    AuditLog,
    CiWebhookConfig,
    CiWebhookDelivery,
    ExecutionJob,
    FunctionalCase,
    K6DispatchJob,
    KnowledgeChunk,
    Project,
    ProjectAiCredential,
    PromptFeedback,
    Recipient,
    ReportArtifact,
    RequirementReview,
    SecurityScanJob,
    TestPlan,
    TestRun,
    TestRunItem,
    TestSuite,
    test_suite_cases,
)


def delete_project(db: Session, project: Project) -> None:
    """Remove a project and all project-scoped rows (audit/AI logs keep rows with null project_id)."""
    pid = project.id

    db.query(K6DispatchJob).filter(K6DispatchJob.project_id == pid).delete(synchronize_session=False)
    db.query(SecurityScanJob).filter(SecurityScanJob.project_id == pid).delete(synchronize_session=False)
    db.query(AiArtifact).filter(AiArtifact.project_id == pid).delete(synchronize_session=False)
    db.query(CiWebhookDelivery).filter(CiWebhookDelivery.project_id == pid).delete(synchronize_session=False)

    run_ids = [row[0] for row in db.query(TestRun.id).filter(TestRun.project_id == pid).all()]
    if run_ids:
        db.query(TestRunItem).filter(TestRunItem.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(ReportArtifact).filter(ReportArtifact.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(ExecutionJob).filter(ExecutionJob.run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(TestRun).filter(TestRun.project_id == pid).delete(synchronize_session=False)

    suite_ids = [row[0] for row in db.query(TestSuite.id).filter(TestSuite.project_id == pid).all()]
    if suite_ids:
        db.execute(test_suite_cases.delete().where(test_suite_cases.c.suite_id.in_(suite_ids)))
    db.query(TestSuite).filter(TestSuite.project_id == pid).delete(synchronize_session=False)
    db.query(TestPlan).filter(TestPlan.project_id == pid).delete(synchronize_session=False)

    db.query(FunctionalCase).filter(FunctionalCase.project_id == pid).delete(synchronize_session=False)
    db.query(ApiRegressionSet).filter(ApiRegressionSet.project_id == pid).delete(synchronize_session=False)
    db.query(RequirementReview).filter(RequirementReview.project_id == pid).delete(synchronize_session=False)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.project_id == pid).delete(synchronize_session=False)

    session_ids = [row[0] for row in db.query(AiWorkbenchSession.id).filter(AiWorkbenchSession.project_id == pid).all()]
    if session_ids:
        db.query(AiWorkbenchMessage).filter(AiWorkbenchMessage.session_id.in_(session_ids)).delete(
            synchronize_session=False,
        )
    db.query(AiWorkbenchSession).filter(AiWorkbenchSession.project_id == pid).delete(synchronize_session=False)

    db.query(CiWebhookConfig).filter(CiWebhookConfig.project_id == pid).delete(synchronize_session=False)
    db.query(ProjectAiCredential).filter(ProjectAiCredential.project_id == pid).delete(synchronize_session=False)
    db.query(Recipient).filter(Recipient.project_id == pid).delete(synchronize_session=False)

    db.query(AuditLog).filter(AuditLog.project_id == pid).update({AuditLog.project_id: None}, synchronize_session=False)
    db.query(AiCallLog).filter(AiCallLog.project_id == pid).update({AiCallLog.project_id: None}, synchronize_session=False)
    db.query(PromptFeedback).filter(PromptFeedback.project_id == pid).update(
        {PromptFeedback.project_id: None},
        synchronize_session=False,
    )

    db.delete(project)
