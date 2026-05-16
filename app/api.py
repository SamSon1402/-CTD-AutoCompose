"""
HTTP API routes.

REST-ish: resources are submissions / sources / sections / compliance.
Action endpoints (e.g. `/sections/{id}/draft`) deviate from pure REST because
section drafting is a long-running, non-idempotent-in-effect operation,
not a state change on a resource.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.ctd import ALL_SECTIONS, get_section
from app.drafter import draft_all_sections, draft_section
from app.schemas import (
    ComplianceIssue,
    ComplianceReport,
    Section,
    SectionDraftRequest,
    SectionStatus,
    Source,
    SourceCreate,
    Submission,
    SubmissionCreate,
    SubmissionStatus,
)
from app.store import store


router = APIRouter()


# ============ Health ============

@router.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "ctd-autocompose"}


@router.get("/health/ready", tags=["health"])
async def ready():
    # Production: ping LLM provider + DB
    return {"status": "ready", "llm_provider_ok": True, "store_ok": True}


# ============ Submissions ============

@router.post(
    "/submissions",
    response_model=Submission,
    status_code=status.HTTP_201_CREATED,
    tags=["submissions"],
)
async def create_submission(payload: SubmissionCreate):
    sub = Submission(**payload.model_dump(), sections_total=len(ALL_SECTIONS))
    store.create_submission(sub)
    # Pre-create section shells so clients can poll status from t=0
    for s in ALL_SECTIONS:
        store.put_section(sub.id, Section(
            id=s.id, title=s.title, module=s.module, status=SectionStatus.PENDING,
        ))
    return sub


@router.get("/submissions", response_model=list[Submission], tags=["submissions"])
async def list_submissions():
    return store.list_submissions()


@router.get("/submissions/{submission_id}", response_model=Submission, tags=["submissions"])
async def get_submission(submission_id: UUID):
    sub = store.get_submission(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    return sub


@router.delete(
    "/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["submissions"],
)
async def delete_submission(submission_id: UUID):
    if not store.delete_submission(submission_id):
        raise HTTPException(404, "Submission not found")
    return None


# ============ Sources ============

@router.post(
    "/submissions/{submission_id}/sources",
    response_model=Source,
    status_code=status.HTTP_201_CREATED,
    tags=["sources"],
)
async def ingest_source(submission_id: UUID, payload: SourceCreate):
    if not store.get_submission(submission_id):
        raise HTTPException(404, "Submission not found")
    src = Source(
        **payload.model_dump(),
        submission_id=submission_id,
        pages=max(1, len(payload.content) // 3000),
        chunks=max(1, len(payload.content) // 800),
    )
    store.add_source(src)
    return src


@router.get(
    "/submissions/{submission_id}/sources",
    response_model=list[Source],
    tags=["sources"],
)
async def list_sources(submission_id: UUID):
    if not store.get_submission(submission_id):
        raise HTTPException(404, "Submission not found")
    return store.list_sources(submission_id)


# ============ Sections ============

@router.get(
    "/submissions/{submission_id}/sections",
    response_model=list[Section],
    tags=["sections"],
)
async def list_sections(submission_id: UUID):
    if not store.get_submission(submission_id):
        raise HTTPException(404, "Submission not found")
    return store.list_sections(submission_id)


@router.get(
    "/submissions/{submission_id}/sections/{section_id}",
    response_model=Section,
    tags=["sections"],
)
async def get_section_endpoint(submission_id: UUID, section_id: str):
    section = store.get_section(submission_id, section_id)
    if not section:
        raise HTTPException(404, f"Section {section_id} not found for this submission")
    return section


@router.post(
    "/submissions/{submission_id}/sections/{section_id}/draft",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sections"],
)
async def trigger_section_draft(
    submission_id: UUID,
    section_id: str,
    payload: SectionDraftRequest,
    background: BackgroundTasks,
):
    sub = store.get_submission(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if not get_section(section_id):
        raise HTTPException(400, f"Unknown CTD section: {section_id}")
    if sub.status == SubmissionStatus.DRAFT:
        sub.status = SubmissionStatus.DRAFTING
        store.update_submission(sub)
    background.add_task(draft_section, submission_id, section_id, payload.additional_context)
    return {"status": "queued", "section_id": section_id}


@router.post(
    "/submissions/{submission_id}/draft-all",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sections"],
)
async def trigger_full_submission_draft(submission_id: UUID, background: BackgroundTasks):
    sub = store.get_submission(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    sub.status = SubmissionStatus.DRAFTING
    store.update_submission(sub)
    section_ids = [s.id for s in ALL_SECTIONS]
    background.add_task(draft_all_sections, submission_id, section_ids)
    return {"status": "queued", "sections_total": len(section_ids)}


@router.post(
    "/submissions/{submission_id}/sections/{section_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sections"],
)
async def regenerate_section(
    submission_id: UUID,
    section_id: str,
    payload: SectionDraftRequest,
    background: BackgroundTasks,
):
    """Re-draft a section, optionally incorporating reviewer feedback."""
    if not store.get_submission(submission_id):
        raise HTTPException(404, "Submission not found")
    background.add_task(draft_section, submission_id, section_id, payload.reviewer_feedback)
    return {
        "status": "queued",
        "section_id": section_id,
        "with_feedback": bool(payload.reviewer_feedback),
    }


# ============ Compliance ============

@router.get(
    "/submissions/{submission_id}/compliance",
    response_model=ComplianceReport,
    tags=["compliance"],
)
async def validate_compliance(submission_id: UUID):
    """
    Validate submission against ICH eCTD rules.

    Prototype: 5 illustrative rules. Production: full ICH M4 + regional addenda.
    """
    sub = store.get_submission(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")

    issues: list[ComplianceIssue] = []
    sections = store.list_sections(submission_id)
    sources = store.list_sources(submission_id)

    # Rule 1: drafted sections must have at least one citation
    for s in sections:
        if s.status == SectionStatus.DRAFTED and not s.citations:
            issues.append(ComplianceIssue(
                section_id=s.id, severity="error", rule_id="ICH-M4-CITATION-001",
                message="Drafted section has no citations to source documents",
            ))

    # Rule 2: M2.5 Clinical Overview required
    m25 = next((s for s in sections if s.id == "M2.5"), None)
    if m25 and m25.status != SectionStatus.DRAFTED:
        issues.append(ComplianceIssue(
            section_id="M2.5", severity="error", rule_id="ICH-M4-CLINICAL-OVERVIEW",
            message="Clinical Overview (M2.5) is required and not yet drafted",
        ))

    # Rule 3: warn if no sources ingested
    if not sources:
        issues.append(ComplianceIssue(
            section_id="*", severity="warning", rule_id="CTD-AUTOCOMPOSE-NO-SOURCES",
            message="No source documents ingested for this submission",
        ))

    # Rule 4: Module 3 needs at least one CMC source
    if not [s for s in sources if s.doc_type.value == "cmc"]:
        issues.append(ComplianceIssue(
            section_id="M3", severity="warning", rule_id="ICH-M4Q-NO-CMC-SOURCE",
            message="No CMC source documents ingested; Module 3 will not draft",
        ))

    # Rule 5: citation-density sanity check (info)
    for s in sections:
        if len(s.citations) > 50:
            issues.append(ComplianceIssue(
                section_id=s.id, severity="info",
                rule_id="CTD-AUTOCOMPOSE-CITATION-DENSITY",
                message=f"High citation count ({len(s.citations)}); reviewer should verify",
            ))

    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    score = max(0.0, 100 - 10 * errors - 2 * warnings)

    return ComplianceReport(
        submission_id=submission_id,
        checked_at=datetime.now(timezone.utc),
        sections_checked=len(sections),
        issues=issues,
        overall_score=score,
        blocking=errors > 0,
    )
