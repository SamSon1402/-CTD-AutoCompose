"""Pydantic request/response schemas."""
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============ Enums ============

class SourceDocType(str, Enum):
    CSR = "csr"               # Clinical Study Report
    PROTOCOL = "protocol"     # Clinical Protocol
    SAP = "sap"               # Statistical Analysis Plan
    IB = "ib"                 # Investigator Brochure
    CMC = "cmc"               # Chemistry, Manufacturing & Controls
    NONCLINICAL = "nonclinical"
    LITERATURE = "literature"


class SectionStatus(str, Enum):
    PENDING = "pending"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    REVIEWED = "reviewed"
    FAILED = "failed"


class SubmissionStatus(str, Enum):
    DRAFT = "draft"
    DRAFTING = "drafting"
    READY_FOR_REVIEW = "ready_for_review"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"


class RegionalAuthority(str, Enum):
    FDA = "fda"     # USA
    EMA = "ema"     # Europe
    PMDA = "pmda"   # Japan
    NMPA = "nmpa"   # China


# ============ Submission ============

class SubmissionCreate(BaseModel):
    submission_id: str = Field(
        ...,
        description="Sponsor's submission identifier",
        examples=["NDA-2026-08471"],
    )
    compound: str = Field(..., examples=["BVL-2188"])
    indication: str = Field(..., examples=["Moderate-to-severe atopic dermatitis"])
    authority: RegionalAuthority = RegionalAuthority.FDA
    submission_type: Literal["nda", "bla", "maa", "anda", "j_nda"] = "nda"


class Submission(SubmissionCreate):
    id: UUID = Field(default_factory=uuid4)
    status: SubmissionStatus = SubmissionStatus.DRAFT
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    sections_total: int = 0
    sections_drafted: int = 0
    citations_traced: int = 0


# ============ Source documents ============

class SourceCreate(BaseModel):
    title: str
    doc_type: SourceDocType
    content: str = Field(
        ...,
        description="Document text (UTF-8). Production endpoint accepts multipart file upload.",
    )
    version: str | None = None


class Source(SourceCreate):
    id: UUID = Field(default_factory=uuid4)
    submission_id: UUID
    pages: int | None = None
    chunks: int = 0  # number of indexed evidence chunks
    ingested_at: datetime = Field(default_factory=_now)


# ============ Sections ============

class Citation(BaseModel):
    source_id: UUID
    source_title: str
    chunk_id: str
    excerpt: str = Field(..., max_length=500)
    confidence: float = Field(..., ge=0, le=1)


class Section(BaseModel):
    id: str = Field(..., description="ICH eCTD section ID", examples=["M2.5"])
    title: str
    module: int = Field(..., ge=1, le=5)
    status: SectionStatus = SectionStatus.PENDING
    content: str | None = None
    citations: list[Citation] = []
    drafted_at: datetime | None = None
    drafted_by_model: str | None = None
    reviewer_notes: str | None = None


class SectionDraftRequest(BaseModel):
    """Optional knobs the user can pass when triggering a draft."""
    reviewer_feedback: str | None = None
    additional_context: str | None = None
    target_word_count: int | None = Field(default=None, ge=100, le=10_000)


# ============ Compliance ============

class ComplianceIssue(BaseModel):
    section_id: str
    severity: Literal["error", "warning", "info"]
    rule_id: str = Field(..., examples=["ICH-M4Q-R1-3.2.S.4.2"])
    message: str


class ComplianceReport(BaseModel):
    submission_id: UUID
    checked_at: datetime
    sections_checked: int
    issues: list[ComplianceIssue]
    overall_score: float = Field(..., ge=0, le=100)
    blocking: bool
