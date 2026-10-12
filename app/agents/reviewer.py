"""
Reviewer Agent.

Responsibility (and ONLY responsibility):
  - Evaluate the Writer's draft against the checklist (app/checklist.py).
  - Produce a ReviewReport: one pass/fail + comment per checklist item.

The Reviewer NEVER rewrites the draft. Its output type (`ReviewReport`)
has no field that could carry a revised text.

Two kinds of items are checked, by different checkers:
  - rule items (R1-R4): plain Python, deterministic (app/checklist.py).
  - llm items  (L1-L4): the LLM, asked to answer with a JSON array.

Fail-closed: if the LLM does not return a valid verdict for an item, that
item is marked as NOT passed (with an explicit comment) instead of being
silently treated as passed.
"""
from __future__ import annotations

import json
import re

from app.checklist import CHECKLIST, LLM_ITEMS, run_rule_checks
from app.llm_client import LLMClient
from app.schemas import Draft, ItemResult, ReviewReport

REVIEWER_SYSTEM_PROMPT = """\
Bạn là REVIEWER AGENT trong một hệ thống multi-agent (Writer -> Reviewer -> Refiner).

NHIỆM VỤ DUY NHẤT của bạn: kiểm tra bài hướng dẫn theo CHECKLIST được cung cấp và báo cáo
từng mục là đạt hay không đạt.

QUY TẮC BẮT BUỘC:
1. KHÔNG viết lại, KHÔNG sửa bài. Chỉ đánh giá.
2. Đánh giá từng mục độc lập, dựa trên đúng nội dung bài viết; không suy đoán ý định của tác giả.
3. Với mục KHÔNG ĐẠT, phần "comment" phải nêu cụ thể lỗi nằm ở đâu (ví dụ: số thứ tự bước, tên mục)
   và cần sửa thế nào, trong 1-2 câu ngắn. Với mục đạt, "comment" có thể để rất ngắn.
4. Chỉ đánh giá các mục có trong CHECKLIST, dùng đúng "id" đã cho.
5. Chỉ trả về MỘT mảng JSON hợp lệ, không có văn bản nào khác, không bọc trong khối code. Định dạng:
   [{"id": "L1", "passed": true, "comment": "..."}, {"id": "L2", "passed": false, "comment": "..."}]
"""

REVIEWER_USER_PROMPT_TEMPLATE = """\
CHỦ ĐỀ: {topic}
ĐỐI TƯỢNG NGƯỜI ĐỌC: {audience}

=== TUTORIAL ===
{content}
=== END TUTORIAL ===

=== CHECKLIST ===
{checklist_block}
=== END CHECKLIST ===

Hãy trả về mảng JSON đánh giá đúng theo quy tắc trong system prompt.
"""

_TRUE_STRINGS = {"true", "pass", "passed", "yes", "đạt"}


def _extract_json_array(raw: str) -> list | None:
    """Pull the first JSON array out of `raw` (tolerates ```json fences / stray prose)."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return None


def parse_llm_verdicts(raw: str) -> dict[str, tuple[bool, str]]:
    """Parse the LLM reply into {item_id: (passed, comment)}. Invalid entries are skipped."""
    verdicts: dict[str, tuple[bool, str]] = {}
    data = _extract_json_array(raw)
    if data is None:
        return verdicts
    valid_ids = {item.id for item in LLM_ITEMS}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id", "")).strip()
        passed = _to_bool(entry.get("passed"))
        if item_id in valid_ids and passed is not None and item_id not in verdicts:
            verdicts[item_id] = (passed, str(entry.get("comment", "")).strip())
    return verdicts


class ReviewerAgent:
    """Wraps an LLMClient to perform the Reviewer role. Output: ReviewReport only."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def run(self, draft: Draft) -> ReviewReport:
        # 1) Deterministic items, checked in code.
        rule_results = {r.id: r for r in run_rule_checks(draft.content, draft.max_words)}

        # 2) Qualitative items, judged by the LLM (a single call).
        checklist_block = "\n".join(f"- {item.id}: {item.description}" for item in LLM_ITEMS)
        user_prompt = REVIEWER_USER_PROMPT_TEMPLATE.format(
            topic=draft.topic,
            audience=draft.audience,
            content=draft.content,
            checklist_block=checklist_block,
        )
        verdicts = parse_llm_verdicts(self._llm.chat(REVIEWER_SYSTEM_PROMPT, user_prompt))

        # 3) Merge in checklist order; fail closed on any missing/invalid LLM verdict.
        results: list[ItemResult] = []
        for item in CHECKLIST:
            if item.kind == "rule":
                results.append(rule_results[item.id])
                continue
            if item.id in verdicts:
                passed, comment = verdicts[item.id]
            else:
                passed = False
                comment = "Reviewer không trả về đánh giá hợp lệ cho mục này; coi là chưa đạt."
            results.append(
                ItemResult(
                    id=item.id,
                    description=item.description,
                    kind="llm",
                    passed=passed,
                    comment=comment,
                )
            )
        return ReviewReport(topic=draft.topic, results=results)
