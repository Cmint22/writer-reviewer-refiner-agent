import inspect

from app.agents.reviewer import ReviewerAgent
from app.pipeline import MAX_REVIEW_ROUNDS, WriterReviewerRefinerPipeline
from app.schemas import PipelineResult, TutorialRequest
from tests.conftest import GOOD_TUTORIAL
from tests.fakes import FakeLLMClient


def test_end_to_end_defective_draft_is_reviewed_once_and_fixed(request_obj):
    llm = FakeLLMClient()
    result = WriterReviewerRefinerPipeline(llm_client=llm, llm_mode="fake").run(request_obj)

    assert isinstance(result, PipelineResult)
    assert result.llm_mode == "fake"
    # Exactly one call per role, in order: single review round.
    assert llm.calls == ["writer", "reviewer", "refiner"]
    assert result.review_rounds == MAX_REVIEW_ROUNDS == 1

    # The draft had two defects; the checklist caught them; the final fixes them.
    assert {r.id for r in result.review.failed} == {"R2", "L2"}
    assert result.final.refined is True
    assert "## Lỗi thường gặp" in result.final.content
    assert "`python -m venv .venv`" in result.final.content
    assert all(r.passed for r in result.post_check)

    # The three deliverables are distinct texts.
    assert result.draft.content != result.final.content


def test_clean_draft_skips_the_refiner_llm_call(request_obj):
    class CleanLLM(FakeLLMClient):
        def __init__(self):
            super().__init__(draft=GOOD_TUTORIAL)

    llm = CleanLLM()
    result = WriterReviewerRefinerPipeline(llm_client=llm).run(request_obj)
    assert llm.calls == ["writer", "reviewer"]  # no refiner call
    assert result.review.all_passed
    assert result.final.refined is False
    assert result.final.content == result.draft.content


def test_reviewer_is_called_exactly_once_even_if_refiner_output_is_still_bad(request_obj, monkeypatch):
    class StubbornLLM(FakeLLMClient):
        def _refine(self, user_prompt):  # type: ignore[override]
            return "# Vẫn thiếu mọi mục"

    count = {"n": 0}
    original = ReviewerAgent.run

    def counting_run(self, draft):
        count["n"] += 1
        return original(self, draft)

    monkeypatch.setattr(ReviewerAgent, "run", counting_run)
    llm = StubbornLLM()
    result = WriterReviewerRefinerPipeline(llm_client=llm).run(request_obj)

    assert count["n"] == 1 and llm.calls == ["writer", "reviewer", "refiner"]  # no retry loop
    # The code-only post-check honestly reports what is still wrong.
    assert any(not r.passed for r in result.post_check)
    assert result.review_rounds == 1


def test_post_check_runs_only_rule_items(request_obj):
    result = WriterReviewerRefinerPipeline(llm_client=FakeLLMClient()).run(request_obj)
    assert [r.id for r in result.post_check] == ["R1", "R2", "R3", "R4"]
    assert all(r.kind == "rule" for r in result.post_check)


def test_pipeline_run_takes_a_request_and_has_no_round_parameter():
    assert list(inspect.signature(WriterReviewerRefinerPipeline.run).parameters) == ["self", "request"]


def test_request_defaults():
    r = TutorialRequest(topic="Cài đặt Git")
    assert r.audience == "người mới bắt đầu" and r.max_words == 350
