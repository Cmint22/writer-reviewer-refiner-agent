import inspect

import pytest

from app.agents.refiner import RefinerAgent
from app.schemas import ItemResult, ReviewReport


def _report(failed_ids=()):
    results = []
    for rid, kind in [("R1", "rule"), ("R2", "rule"), ("L1", "llm"), ("L2", "llm")]:
        results.append(
            ItemResult(
                id=rid,
                description=f"desc-{rid}",
                kind=kind,
                passed=rid not in failed_ids,
                comment=f"comment-{rid}",
            )
        )
    return ReviewReport(topic="t", results=results)


class Boom:
    def chat(self, s, u):
        raise AssertionError("LLM must not be called")


class Spy:
    def __init__(self, reply="# Final\n\ntext"):
        self.reply, self.user_prompts = reply, []

    def chat(self, system_prompt, user_prompt):
        self.user_prompts.append(user_prompt)
        return self.reply


def test_refiner_signature_is_draft_and_review_only():
    # No handle on the Reviewer or the request -> cannot start another review round.
    assert list(inspect.signature(RefinerAgent.run).parameters) == ["self", "draft", "review"]


def test_all_passed_returns_draft_unchanged_without_calling_the_llm(good_draft):
    final = RefinerAgent(Boom()).run(good_draft, _report(failed_ids=()))
    assert final.refined is False
    assert final.content == good_draft.content


def test_prompt_contains_only_failed_items(good_draft):
    spy = Spy()
    RefinerAgent(spy).run(good_draft, _report(failed_ids=("R2", "L2")))
    prompt = spy.user_prompts[0]
    failed_part = prompt.split("=== FAILED ITEMS ===")[1]
    assert "[R2]" in failed_part and "[L2]" in failed_part
    assert "comment-R2" in failed_part and "comment-L2" in failed_part
    assert "[R1]" not in failed_part and "[L1]" not in failed_part
    assert good_draft.content in prompt


def test_refiner_returns_refined_content(good_draft):
    final = RefinerAgent(Spy("```markdown\n# Final\n\nok\n```")).run(good_draft, _report(("R1",)))
    assert final.refined is True
    assert final.content == "# Final\n\nok"


def test_refiner_rejects_empty_output(good_draft):
    with pytest.raises(RuntimeError):
        RefinerAgent(Spy("  ")).run(good_draft, _report(("R1",)))


def test_failed_item_without_comment_gets_keep_as_is_hint():
    report = ReviewReport(
        topic="t",
        results=[ItemResult(id="L1", description="d", kind="llm", passed=False, comment="")],
    )
    assert "giữ nguyên" in report.failed_items_block()
