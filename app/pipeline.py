"""
Pipeline orchestrator.

    TutorialRequest
          |
          v
      [Writer]      -> Draft
          |
          v
      [Reviewer]    -> ReviewReport   (checklist, run exactly ONCE)
          |
          v
      [Refiner]     -> FinalTutorial  (fixes only the failed items)

This module is the single place where the three agents are wired together.
There is no loop: the Reviewer is called exactly once (`MAX_REVIEW_ROUNDS = 1`),
and the Refiner has no handle on the Reviewer, so a second review round is
structurally impossible, not just discouraged by a prompt.

After refining, the deterministic rules (R1-R4) are re-run in plain Python
and stored as `post_check`. That is a cheap report for the reader — it does
not call any LLM and triggers no further rewriting.
"""
from __future__ import annotations

from app.agents.refiner import RefinerAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.writer import WriterAgent
from app.checklist import run_rule_checks
from app.llm_client import LLMClient, get_llm_client
from app.schemas import PipelineResult, TutorialRequest

MAX_REVIEW_ROUNDS = 1


class WriterReviewerRefinerPipeline:
    def __init__(self, llm_client: LLMClient | None = None, llm_mode: str | None = None):
        self._llm = llm_client or get_llm_client()
        self.writer = WriterAgent(self._llm)
        self.reviewer = ReviewerAgent(self._llm)
        self.refiner = RefinerAgent(self._llm)
        # Always a real, network-backed LLM client in the app — no mock backend exists.
        self._llm_mode = llm_mode or "real"

    def run(self, request: TutorialRequest) -> PipelineResult:
        # Step 1: Writer -> first draft.
        draft = self.writer.run(request)

        # Step 2: Reviewer -> checklist report. Called exactly once (single review round).
        review = self.reviewer.run(draft)

        # Step 3: Refiner -> final text, fixing only the failed items.
        final = self.refiner.run(draft, review)

        # Step 4: code-only re-check of the measurable rules on the final text.
        post_check = run_rule_checks(final.content, draft.max_words)

        return PipelineResult(
            request=request,
            draft=draft,
            review=review,
            final=final,
            post_check=post_check,
            review_rounds=MAX_REVIEW_ROUNDS,
            llm_mode=self._llm_mode,
        )
