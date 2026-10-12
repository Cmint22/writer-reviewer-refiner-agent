import inspect
import json

from app.agents.reviewer import ReviewerAgent, parse_llm_verdicts
from app.schemas import ReviewReport
from tests.fakes import FakeLLMClient


class FixedReply:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, system_prompt, user_prompt):
        return self.reply


def _all_llm_pass():
    return json.dumps([{"id": i, "passed": True, "comment": "ok"} for i in ("L1", "L2", "L3", "L4")])


def test_reviewer_signature_takes_only_the_draft():
    assert list(inspect.signature(ReviewerAgent.run).parameters) == ["self", "draft"]


def test_good_draft_with_all_llm_items_passing_is_all_passed(good_draft):
    report = ReviewerAgent(FixedReply(_all_llm_pass())).run(good_draft)
    assert isinstance(report, ReviewReport)
    assert [r.id for r in report.results] == [f"R{i}" for i in range(1, 9)] + ["L1", "L2", "L3", "L4"]
    assert report.all_passed and report.passed_count == report.total == 12


def test_reviewer_finds_real_defects_in_the_fake_writers_draft(request_obj):
    from app.agents.writer import WriterAgent

    llm = FakeLLMClient()
    draft = WriterAgent(llm).run(request_obj)
    report = ReviewerAgent(llm).run(draft)
    assert {r.id for r in report.failed} == {"R2", "L2"}
    assert "Lỗi thường gặp" in next(r for r in report.results if r.id == "R2").comment


def test_reviewer_uses_one_llm_call_and_does_not_modify_draft(good_draft):
    llm = FakeLLMClient()
    before = good_draft.content
    ReviewerAgent(llm).run(good_draft)
    assert llm.calls == ["reviewer"]
    assert good_draft.content == before


def test_reviewer_marks_rule_items_by_code_even_if_llm_says_otherwise(good_draft):
    # The LLM is only asked about L-items; an R-item in its reply must be ignored.
    reply = json.dumps([{"id": "R2", "passed": False, "comment": "x"}]) 
    report = ReviewerAgent(FixedReply(reply)).run(good_draft)
    assert next(r for r in report.results if r.id == "R2").passed is True


def test_reviewer_fails_closed_on_garbage_reply(good_draft):
    report = ReviewerAgent(FixedReply("xin lỗi, tôi không biết")).run(good_draft)
    llm_results = [r for r in report.results if r.kind == "llm"]
    assert len(llm_results) == 4 and not any(r.passed for r in llm_results)
    assert all("không trả về đánh giá hợp lệ" in r.comment for r in llm_results)
    assert all(r.passed for r in report.results if r.kind == "rule")  # rules unaffected


def test_reviewer_fails_closed_only_for_missing_items(good_draft):
    reply = json.dumps([{"id": "L1", "passed": True, "comment": "ok"}])
    report = ReviewerAgent(FixedReply(reply)).run(good_draft)
    by_id = {r.id: r for r in report.results}
    assert by_id["L1"].passed and not by_id["L2"].passed


def test_parse_tolerates_fences_prose_and_string_booleans():
    raw = 'Đây là kết quả:\n```json\n[{"id": "L1", "passed": "true", "comment": "ok"}, {"id": "L2", "passed": "false"}]\n```'
    assert parse_llm_verdicts(raw) == {"L1": (True, "ok"), "L2": (False, "")}


def test_parse_ignores_unknown_ids_duplicates_and_junk():
    raw = json.dumps([
        {"id": "L9", "passed": True},
        {"id": "L1", "passed": True, "comment": "first"},
        {"id": "L1", "passed": False, "comment": "dup"},
        "junk",
        {"id": "L3", "passed": 5},
    ])
    assert parse_llm_verdicts(raw) == {"L1": (True, "first")}
    assert parse_llm_verdicts("not json") == {}
    assert parse_llm_verdicts('{"id": "L1"}') == {}
