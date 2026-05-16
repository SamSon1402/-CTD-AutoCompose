"""
LLM client abstraction.

Two providers wired up:
- `anthropic`: Claude (production)
- `mock`:      deterministic fixtures (local dev / tests / no API key)

Why an abstraction layer: enterprise pharma customers have data-residency and
sovereignty constraints. Some require on-prem inference (vLLM serving a local
Llama/Mistral). Keeping callers behind `LLMClient` lets us add providers
without touching the section drafter.

Production additions:
- Retry/backoff with `tenacity`
- Prompt caching (Anthropic) for the ICH system prompt (~70% token reduction)
- Streaming for WebSocket UX (drafted prose appears word-by-word)
- Per-customer model selection + budget caps
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from app.config import settings


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        """Single-shot completion. Returns the assistant's text."""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=settings.llm_temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate all text blocks (response may include multiple)
        return "".join(
            getattr(block, "text", "")
            for block in resp.content
        )


class MockClient(LLMClient):
    """Deterministic CTD-style content. Lets the API exercise end-to-end without an API key."""

    FIXTURES = {
        "M2.5": (
            "BVL-2188 is a novel selective inhibitor under investigation for the treatment "
            "of moderate-to-severe atopic dermatitis in adult patients. The clinical development "
            "program comprised 12 completed studies (n=2,847), including three pivotal Phase III "
            "trials. Pivotal efficacy was demonstrated [CITE:CSR-§11.4.1], with statistically "
            "significant improvement vs. placebo on the primary EASI-75 endpoint at Week 16 "
            "(p<0.0001). The safety profile was favourable, with adverse events consistent with "
            "the proposed mechanism as detailed in [CITE:PROTOCOL-§8.3]."
        ),
        "M2.7.3": (
            "Across the pivotal Phase III program, BVL-2188 met all primary and key secondary "
            "endpoints. The EASI-75 response rate was 68.4% at Week 16 vs 12.1% for placebo "
            "(Δ=56.3 pp; 95% CI: 48.7–63.9) per the pre-specified analysis [CITE:SAP-§6.2]. "
            "Sustained response through Week 52 was observed [CITE:CSR-§11.4.6]. "
            "Patient-reported outcomes (DLQI, NRS-Itch) supported the clinical benefit."
        ),
        "M2.7.4": (
            "The safety database includes 2,847 unique subjects exposed to BVL-2188 across all "
            "doses. Most common adverse events (≥5%) were nasopharyngitis (8.2%), headache (6.4%), "
            "and injection-site reaction (5.9%), all primarily mild-to-moderate in severity "
            "[CITE:CSR-§12.2.3]. No clinically meaningful imbalance in serious adverse events "
            "was observed. Hepatic safety monitoring per [CITE:PROTOCOL-§9.4] revealed no signal "
            "of drug-induced liver injury."
        ),
        "M3.2.S": (
            "BVL-2188 (chemical name: redacted per CMC confidentiality) is a small-molecule "
            "selective inhibitor with molecular formula C₂₂H₂₄N₆O₃. Manufacturing is conducted "
            "at two GMP-licensed facilities per [CITE:CMC-§3.2.S.2]. Characterisation includes "
            "X-ray diffraction, NMR (¹H, ¹³C), HRMS, and elemental analysis."
        ),
        "M4.2.3": (
            "The pivotal toxicology program included 26-week rat and 39-week dog studies at "
            "exposures up to 25× the proposed clinical dose. No adverse findings related to drug "
            "administration were observed below the NOAEL per [CITE:NONCLINICAL-TOX-014]. "
            "Genotoxicity battery (Ames, in vitro micronucleus, in vivo micronucleus) was negative "
            "per [CITE:NONCLINICAL-GEN-003]."
        ),
    }

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        # Detect which CTD section is being drafted from the prompt
        for section_id, fixture in self.FIXTURES.items():
            if section_id in user:
                return fixture
        return (
            "Section content drafted from source documents. The available data support the "
            "claims made in this section [CITE:CSR-§1] and are consistent with the broader "
            "clinical and nonclinical program [CITE:PROTOCOL-§1]."
        )


def get_llm_client() -> LLMClient:
    """Factory. Selects provider based on settings."""
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Either set the key or switch to LLM_PROVIDER=mock for local dev."
            )
        return AnthropicClient(settings.anthropic_api_key, settings.llm_model)
    return MockClient()
