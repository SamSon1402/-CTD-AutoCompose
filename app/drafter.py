"""
Section drafting orchestrator.

Pipeline per section:
1. Retrieve relevant evidence chunks (RAG) from indexed sources
2. Compose the LLM prompt with ICH section guidance + retrieved evidence
3. Call LLM (grounded generation — model must cite chunk IDs in output)
4. Parse [CITE:chunk-id] markers → structured Citation objects
5. Light post-validation (no orphan citations, non-empty section)
6. Persist via store, bump submission counters
"""
import asyncio
import re
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.ctd import get_section
from app.extractor import extract_chunks
from app.llm import get_llm_client
from app.schemas import Citation, Section, SectionStatus
from app.store import store


CITATION_PATTERN = re.compile(r"\[CITE:([^\]]+)\]")


SYSTEM_PROMPT = """You are CTD-AutoCompose, a regulatory affairs drafting assistant specialised in ICH eCTD submissions.

Rules:
- Produce content strictly grounded in the provided evidence chunks. Do not invent data.
- Every numeric or factual claim MUST be followed by an inline citation in the form [CITE:chunk-id].
- Use the formal register expected by FDA / EMA / PMDA reviewers (third person, past tense for studies, neutral tone).
- Use ICH terminology precisely (e.g., 'subject' for study participants; 'adverse event' not 'side effect').
- Do not include section numbering or headings — those are added by the orchestrator.
"""


def _retrieve_evidence(submission_id: UUID, section_id: str) -> list[dict]:
    """
    Retrieve evidence chunks relevant to a CTD section.

    Production: hybrid retrieval (BM25 + dense embedding similarity + section-type filter,
    optionally re-ranked by a GNN over the citation graph).
    Prototype: filter sources by doc_type matching the section's typical inputs.
    """
    meta = get_section(section_id)
    if not meta:
        return []

    sources = store.list_sources(submission_id)
    relevant = [s for s in sources if s.doc_type.value in meta.typical_source_docs]

    chunks: list[dict] = []
    for src in relevant:
        for ch in extract_chunks(src):
            chunks.append({**ch, "source_id": str(src.id), "source_title": src.title})
    return chunks


def _build_user_prompt(meta, chunks: list[dict], extra_context: str | None) -> str:
    chunks_text = "\n".join(
        f"[{c['chunk_id']}] ({c['kind']}, {c['page_ref']}) {c['text']}"
        for c in chunks
    ) or "No evidence available — flag missing source documents."

    parts = [
        f"# CTD Section to draft\n{meta.id} — {meta.title}",
        f"\n# Section description\n{meta.description}",
        f"\n# Evidence chunks (cite these by ID)\n{chunks_text}",
    ]
    if extra_context:
        parts.append(f"\n# Additional context from reviewer\n{extra_context}")
    parts.append(
        "\n# Output\nDraft the section content in regulator-ready prose. "
        "Cite evidence inline using [CITE:chunk-id]."
    )
    return "\n".join(parts)


def _parse_citations(content: str, chunks: list[dict]) -> list[Citation]:
    """Extract [CITE:chunk-id] markers into structured Citation objects."""
    lookup = {c["chunk_id"]: c for c in chunks}
    seen: set[str] = set()
    citations: list[Citation] = []
    for match in CITATION_PATTERN.finditer(content):
        chunk_id = match.group(1)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        chunk = lookup.get(chunk_id)
        if not chunk:
            # Orphan citation — production logs + flags this for review
            continue
        citations.append(Citation(
            source_id=UUID(chunk["source_id"]),
            source_title=chunk["source_title"],
            chunk_id=chunk_id,
            excerpt=chunk["text"][:500],
            confidence=0.92,  # placeholder; production: GNN-based confidence
        ))
    return citations


async def draft_section(
    submission_id: UUID,
    section_id: str,
    extra_context: str | None = None,
) -> Section:
    """Draft a single CTD section. Idempotent — re-running overwrites."""
    meta = get_section(section_id)
    if not meta:
        raise ValueError(f"Unknown CTD section: {section_id}")

    # Mark drafting in flight
    section = Section(
        id=section_id,
        title=meta.title,
        module=meta.module,
        status=SectionStatus.DRAFTING,
    )
    store.put_section(submission_id, section)

    try:
        chunks = _retrieve_evidence(submission_id, section_id)
        user_prompt = _build_user_prompt(meta, chunks, extra_context)

        llm = get_llm_client()
        content = await asyncio.wait_for(
            llm.complete(SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens),
            timeout=settings.section_draft_timeout_s,
        )

        citations = _parse_citations(content, chunks)

        section.status = SectionStatus.DRAFTED
        section.content = content
        section.citations = citations
        section.drafted_at = datetime.now(timezone.utc)
        section.drafted_by_model = settings.llm_model

    except asyncio.TimeoutError:
        section.status = SectionStatus.FAILED
        section.reviewer_notes = "LLM call timed out"
    except Exception as exc:  # pragma: no cover
        section.status = SectionStatus.FAILED
        section.reviewer_notes = f"Drafting failed: {exc}"

    store.put_section(submission_id, section)
    _bump_submission_counters(submission_id)
    return section


def _bump_submission_counters(submission_id: UUID) -> None:
    sub = store.get_submission(submission_id)
    if not sub:
        return
    sections = store.list_sections(submission_id)
    sub.sections_drafted = sum(1 for s in sections if s.status == SectionStatus.DRAFTED)
    sub.citations_traced = sum(len(s.citations) for s in sections)
    sub.updated_at = datetime.now(timezone.utc)
    store.update_submission(sub)


async def draft_all_sections(submission_id: UUID, section_ids: list[str]) -> None:
    """Draft sections concurrently, bounded by `max_concurrent_sections`."""
    sem = asyncio.Semaphore(settings.max_concurrent_sections)

    async def _bounded(sid: str):
        async with sem:
            await draft_section(submission_id, sid)

    await asyncio.gather(*(_bounded(sid) for sid in section_ids))
