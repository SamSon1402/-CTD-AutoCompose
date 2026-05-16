"""
Source-document evidence extractor.

STUBBED for this prototype: returns canned chunks per doc type so the rest of the
pipeline is exercisable end-to-end.

Production pipeline:
1. Parse PDF/DOCX → page text + table/figure extraction
   (Unstructured.io, Donut/table-transformer for tables, layoutparser for figures)
2. Chunk semantically — different strategies per doc type:
     - CSRs: section-aware (§11 efficacy, §12 safety, §16 appendices)
     - Protocols: numbered-section chunking (§8 study design, §9 safety monitoring)
     - SAPs: paragraph + table chunking
     - CMCs: structured 3.2.S.x / 3.2.P.x mapping
3. Embed chunks (e5-mistral-7b-instruct or text-embedding-3-large)
4. Persist in pgvector with metadata (doc_type, page_ref, kind, study_id)
5. Build evidence graph node per chunk (referenced by the citation GNN at retrieval)
"""
from app.schemas import Source, SourceDocType


def extract_chunks(source: Source) -> list[dict]:
    """
    Return evidence chunks for this source.

    Each chunk: {chunk_id, text, page_ref, kind}
    `kind` is the semantic class: 'efficacy_result' | 'ae_table' | 'study_design' | ...
    """
    fixtures: dict[SourceDocType, list[dict]] = {
        SourceDocType.CSR: [
            {
                "chunk_id": "CSR-§11.4.1",
                "kind": "efficacy_result",
                "text": "Primary endpoint EASI-75 at Week 16: 68.4% vs 12.1% placebo (p<0.0001).",
                "page_ref": "p.247",
            },
            {
                "chunk_id": "CSR-§11.4.6",
                "kind": "efficacy_result",
                "text": "Sustained response through Week 52: 71.2% in active arm.",
                "page_ref": "p.298",
            },
            {
                "chunk_id": "CSR-§12.2.3",
                "kind": "ae_table",
                "text": "Most common AEs (≥5%): nasopharyngitis 8.2%, headache 6.4%, ISR 5.9%.",
                "page_ref": "p.412",
            },
        ],
        SourceDocType.PROTOCOL: [
            {
                "chunk_id": "PROTOCOL-§8.3",
                "kind": "study_design",
                "text": "Randomised, double-blind, placebo-controlled trial; n=600 per arm.",
                "page_ref": "p.34",
            },
            {
                "chunk_id": "PROTOCOL-§9.4",
                "kind": "safety_monitoring",
                "text": "Hepatic function tests at baseline, Week 4, 16, 52; stopping rules per ALT >5×ULN.",
                "page_ref": "p.62",
            },
        ],
        SourceDocType.SAP: [
            {
                "chunk_id": "SAP-§6.2",
                "kind": "statistical_method",
                "text": "Primary analysis: MMRM with treatment, visit, and treatment-by-visit interaction.",
                "page_ref": "p.18",
            },
        ],
        SourceDocType.CMC: [
            {
                "chunk_id": "CMC-§3.2.S.2",
                "kind": "manufacturing",
                "text": "Drug substance manufactured at two GMP-licensed sites under current cGMP.",
                "page_ref": "p.12",
            },
        ],
        SourceDocType.NONCLINICAL: [
            {
                "chunk_id": "NONCLINICAL-TOX-014",
                "kind": "tox_study",
                "text": "26-week rat and 39-week dog studies; NOAEL established at 25× clinical dose.",
                "page_ref": "study TOX-014",
            },
            {
                "chunk_id": "NONCLINICAL-GEN-003",
                "kind": "genotox",
                "text": "Ames, in vitro micronucleus, in vivo micronucleus all negative.",
                "page_ref": "study GEN-003",
            },
        ],
    }
    return fixtures.get(source.doc_type, [
        {
            "chunk_id": f"{source.doc_type.value.upper()}-§1",
            "kind": "general",
            "text": source.content[:200],
            "page_ref": "p.1",
        },
    ])
