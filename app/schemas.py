"""
Data contracts that flow through the pipeline:

    TutorialRequest -> [Writer] -> Draft -> [Reviewer] -> ReviewReport
                                     \\                       |
                                      \\--------> [Refiner] <-/  -> FinalTutorial

Keeping these as explicit Pydantic models (rather than free-form strings)
is what lets us enforce the architectural rules at the type level:

  * Reviewer only produces a ReviewReport — it has no field to carry a
    rewritten tutorial, so it cannot "silently fix" the draft.
  * Refiner is the only agent that produces the final text, and it only
    receives (Draft, ReviewReport).
  * There is exactly ONE ReviewReport per run (single review round).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field


class TutorialRequest(BaseModel):
    """What the user asks for: a short how-to tutorial on a topic."""

    topic: str = Field(..., min_length=3, description="Topic of the tutorial")
    audience: str = Field("người mới bắt đầu", description="Who the tutorial is written for")
    max_words: int = Field(
        350, ge=100, le=1200, description="Soft upper bound for the tutorial length (prose words)"
    )


class Draft(BaseModel):
    """Output of the Writer. Carries the length limit it was written against."""

    topic: str
    audience: str
    max_words: int
    content: str = Field(..., description="Tutorial in Markdown")


class ChecklistItem(BaseModel):
    """One evaluation criterion. `kind` says who checks it: code or the LLM reviewer."""

    id: str
    description: str
    kind: Literal["rule", "llm"]


class ItemResult(BaseModel):
    """Result of checking one checklist item against a tutorial text."""

    id: str
    description: str
    kind: Literal["rule", "llm"]
    passed: bool
    comment: str = ""


class ReviewReport(BaseModel):
    """
    The ONLY artifact the Reviewer produces and the Refiner consumes
    (besides the draft). Deliberately has no field for a revised text.
    """

    topic: str
    results: list[ItemResult] = Field(default_factory=list)

    @property
    def failed(self) -> list[ItemResult]:
        return [r for r in self.results if not r.passed]

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and not self.failed

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return len(self.results)

    def failed_items_block(self) -> str:
        """Render only the failed items for the Refiner prompt."""
        if not self.failed:
            return "(Không có mục nào chưa đạt.)"
        lines = []
        for r in self.failed:
            comment = r.comment.strip() or "(không có nhận xét cụ thể — giữ nguyên phần liên quan)"
            lines.append(f"- [{r.id}] {r.description}\n  Nhận xét của Reviewer: {comment}")
        return "\n".join(lines)


class FinalTutorial(BaseModel):
    """Output of the Refiner — the end product of the pipeline."""

    topic: str
    content: str
    refined: bool = Field(
        ..., description="False when the review had no failed items and the draft was kept as-is"
    )


class PipelineResult(BaseModel):
    """Full trace of one pipeline run: draft, checklist review, final text."""

    request: TutorialRequest
    draft: Draft
    review: ReviewReport
    final: FinalTutorial
    post_check: list[ItemResult] = Field(
        default_factory=list,
        description=(
            "Deterministic (code-only) rules re-run on the final text. This is NOT a second "
            "review round: no LLM is called and nothing is rewritten after it."
        ),
    )
    review_rounds: int = Field(1, description="Always 1 — the pipeline has a single review round")
    llm_mode: str = Field(..., description="Label of the LLM backend used (e.g. 'real')")
