"""
ICH eCTD module/section structure.

Reference: ICH M4 Common Technical Document for the Registration of Pharmaceuticals
for Human Use — Organisation; ICH M4Q (Quality), M4S (Safety), M4E (Efficacy).

This is a representative subset (~25 of the ~38 leaf sections in a full NDA CTD).
Production deployment would load the full ICH-published structure including
regional addenda for Module 1 (FDA Module 1, EMA Module 1, PMDA, NMPA).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CTDSection:
    id: str
    title: str
    module: int
    description: str
    typical_source_docs: tuple[str, ...]  # which doc types feed this section


# Module 2 — CTD Summaries
M2_SECTIONS = (
    CTDSection("M2.2", "Introduction", 2,
               "Brief introduction to the pharmaceutical, including its proposed use.",
               ("ib", "protocol")),
    CTDSection("M2.3", "Quality Overall Summary", 2,
               "Summary of CMC information for the drug substance and drug product.",
               ("cmc",)),
    CTDSection("M2.4", "Nonclinical Overview", 2,
               "Integrated critical assessment of pharmacology, PK, and toxicology.",
               ("nonclinical",)),
    CTDSection("M2.5", "Clinical Overview", 2,
               "Critical analysis of clinical data; benefit-risk assessment.",
               ("csr", "protocol", "sap")),
    CTDSection("M2.6.1", "Pharmacology Written Summary", 2,
               "Written summary of nonclinical pharmacology studies.",
               ("nonclinical",)),
    CTDSection("M2.6.2", "Pharmacokinetics Written Summary", 2,
               "Written summary of nonclinical PK studies.",
               ("nonclinical",)),
    CTDSection("M2.7.1", "Biopharmaceutic Studies Summary", 2,
               "Summary of biopharmaceutic and bioavailability studies.",
               ("csr",)),
    CTDSection("M2.7.2", "Clinical Pharmacology Studies Summary", 2,
               "Summary of clinical pharmacology studies (PK, PD, intrinsic/extrinsic factors).",
               ("csr", "sap")),
    CTDSection("M2.7.3", "Summary of Clinical Efficacy", 2,
               "Pooled efficacy across studies; primary and secondary endpoints.",
               ("csr", "sap")),
    CTDSection("M2.7.4", "Summary of Clinical Safety", 2,
               "Pooled safety; common AEs, SAEs, deaths, lab abnormalities.",
               ("csr",)),
)

# Module 3 — Quality
M3_SECTIONS = (
    CTDSection("M3.2.S", "Drug Substance", 3,
               "Manufacture, characterisation, and controls of the drug substance.",
               ("cmc",)),
    CTDSection("M3.2.P", "Drug Product", 3,
               "Description, manufacture, and controls of the drug product.",
               ("cmc",)),
    CTDSection("M3.2.A", "Appendices", 3,
               "Facilities/equipment, adventitious agents safety evaluation.",
               ("cmc",)),
    CTDSection("M3.2.R", "Regional Information", 3,
               "Region-specific quality content (e.g., FDA executed batch records).",
               ("cmc",)),
)

# Module 4 — Nonclinical Study Reports
M4_SECTIONS = (
    CTDSection("M4.2.1", "Pharmacology", 4,
               "Primary, secondary, and safety pharmacology study reports.",
               ("nonclinical",)),
    CTDSection("M4.2.2", "Pharmacokinetics", 4,
               "Analytical methods, absorption, distribution, metabolism, excretion.",
               ("nonclinical",)),
    CTDSection("M4.2.3", "Toxicology", 4,
               "Single-dose, repeat-dose, genotox, carcinogenicity, reproductive tox.",
               ("nonclinical",)),
)

# Module 5 — Clinical Study Reports
M5_SECTIONS = (
    CTDSection("M5.2", "Tabular Listing of All Clinical Studies", 5,
               "Tabular index of all clinical studies in the submission.",
               ("csr", "protocol")),
    CTDSection("M5.3.1", "Reports of Biopharmaceutic Studies", 5,
               "Bioavailability and comparative BA/BE study reports.",
               ("csr",)),
    CTDSection("M5.3.3", "Reports of Human PK Studies", 5,
               "Healthy subject PK, patient PK, intrinsic/extrinsic factor PK.",
               ("csr",)),
    CTDSection("M5.3.5", "Reports of Efficacy and Safety Studies", 5,
               "Controlled clinical study reports relevant to the claimed indication.",
               ("csr",)),
)

ALL_SECTIONS: tuple[CTDSection, ...] = M2_SECTIONS + M3_SECTIONS + M4_SECTIONS + M5_SECTIONS

SECTIONS_BY_ID: dict[str, CTDSection] = {s.id: s for s in ALL_SECTIONS}


def get_section(section_id: str) -> CTDSection | None:
    return SECTIONS_BY_ID.get(section_id)


def sections_for_source_type(doc_type: str) -> list[CTDSection]:
    """Return CTD sections that typically draw from a given source doc type."""
    return [s for s in ALL_SECTIONS if doc_type in s.typical_source_docs]
