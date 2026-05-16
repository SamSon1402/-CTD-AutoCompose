"""
In-memory repository for the prototype.

Production: replace with async SQLAlchemy + Postgres + pgvector for embedding search.
Schema sketch in docs/schema.sql (not included in this prototype). Tables:

  submissions (id, sponsor_submission_id, compound, indication, ...)
  sources     (id, submission_id, doc_type, title, content_uri, ...)
  chunks      (id, source_id, text, embedding vector(1536), kind, page_ref)
  sections    (id, submission_id, ctd_id, status, content, model, drafted_at)
  citations   (section_id, chunk_id, excerpt, confidence)
"""
from collections import defaultdict
from uuid import UUID

from app.schemas import Section, Source, Submission


class InMemoryStore:
    """Thread-unsafe in-memory store. Fine for prototype, NOT for prod."""

    def __init__(self):
        self.submissions: dict[UUID, Submission] = {}
        self.sources: dict[UUID, list[Source]] = defaultdict(list)
        self.sections: dict[UUID, dict[str, Section]] = defaultdict(dict)

    # Lifecycle hooks — placeholder for prod connection pool
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    # ---- Submissions ----
    def create_submission(self, sub: Submission) -> Submission:
        self.submissions[sub.id] = sub
        return sub

    def get_submission(self, submission_id: UUID) -> Submission | None:
        return self.submissions.get(submission_id)

    def list_submissions(self) -> list[Submission]:
        return list(self.submissions.values())

    def update_submission(self, sub: Submission) -> Submission:
        self.submissions[sub.id] = sub
        return sub

    def delete_submission(self, submission_id: UUID) -> bool:
        if submission_id not in self.submissions:
            return False
        del self.submissions[submission_id]
        self.sources.pop(submission_id, None)
        self.sections.pop(submission_id, None)
        return True

    # ---- Sources ----
    def add_source(self, src: Source) -> Source:
        self.sources[src.submission_id].append(src)
        return src

    def list_sources(self, submission_id: UUID) -> list[Source]:
        return list(self.sources[submission_id])

    def get_source(self, submission_id: UUID, source_id: UUID) -> Source | None:
        return next((s for s in self.sources[submission_id] if s.id == source_id), None)

    # ---- Sections ----
    def put_section(self, submission_id: UUID, section: Section) -> Section:
        self.sections[submission_id][section.id] = section
        return section

    def get_section(self, submission_id: UUID, section_id: str) -> Section | None:
        return self.sections[submission_id].get(section_id)

    def list_sections(self, submission_id: UUID) -> list[Section]:
        return list(self.sections[submission_id].values())


# Module-level singleton — replace with FastAPI dependency injection in prod
store = InMemoryStore()
