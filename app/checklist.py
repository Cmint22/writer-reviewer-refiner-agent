"""
The evaluation checklist for a short tutorial.

Eight items, split by WHO can check them reliably:

  R1-R4  `rule`  — measurable, checked by plain Python (no LLM, fully
                   deterministic, re-runnable on the final text).
  L1-L4  `llm`   — qualitative, checked by the Reviewer agent (LLM).

Mixing both is deliberate: an LLM is a poor counter of words/steps and a
regex is a poor judge of "one action per step", so each kind of item goes
to the checker that is good at it.
"""
from __future__ import annotations

import re

from app.schemas import ChecklistItem, ItemResult

# --- Checklist definition ------------------------------------------------------

CHECKLIST: list[ChecklistItem] = [
    ChecklistItem(
        id="R1",
        kind="rule",
        description="Có tiêu đề cấp 1 (dòng bắt đầu bằng '# ').",
    ),
    ChecklistItem(
        id="R2",
        kind="rule",
        description=(
            "Có đủ 5 mục (heading '##'): Mục tiêu, Chuẩn bị, Các bước, "
            "Kiểm tra kết quả, Lỗi thường gặp."
        ),
    ),
    ChecklistItem(
        id="R3",
        kind="rule",
        description="Mục 'Các bước' là danh sách đánh số gồm từ 3 đến 8 bước.",
    ),
    ChecklistItem(
        id="R4",
        kind="rule",
        description="Độ dài không vượt quá giới hạn từ (không tính khối code).",
    ),
    ChecklistItem(
        id="L1",
        kind="llm",
        description="Mỗi bước chỉ yêu cầu MỘT hành động rõ ràng, viết ở thể mệnh lệnh.",
    ),
    ChecklistItem(
        id="L2",
        kind="llm",
        description="Mọi lệnh/đoạn mã/giá trị cụ thể được đặt trong định dạng code (khối code hoặc code inline), không mơ hồ.",
    ),
    ChecklistItem(
        id="L3",
        kind="llm",
        description="Ngôn ngữ phù hợp đối tượng người đọc; thuật ngữ khó được giải thích ở lần đầu xuất hiện.",
    ),
    ChecklistItem(
        id="L4",
        kind="llm",
        description="Nội dung bám sát chủ đề, ngắn gọn, không lan man hay thông tin thừa.",
    ),
]

RULE_ITEMS: list[ChecklistItem] = [c for c in CHECKLIST if c.kind == "rule"]
LLM_ITEMS: list[ChecklistItem] = [c for c in CHECKLIST if c.kind == "llm"]

# Required sections: label shown to the user -> keywords, any of which in a
# '##' heading counts as that section being present (case-insensitive).
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "Mục tiêu": ("mục tiêu",),
    "Chuẩn bị": ("chuẩn bị",),
    "Các bước": ("các bước", "thực hiện"),
    "Kiểm tra kết quả": ("kiểm tra", "kết quả"),
    "Lỗi thường gặp": ("lỗi", "sự cố"),
}
MIN_STEPS, MAX_STEPS = 3, 8

_H1_RE = re.compile(r"^# \S", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_STEP_RE = re.compile(r"^\s*\d+[.)]\s+\S", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


# --- Helpers ---------------------------------------------------------------------


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` ... ```)."""
    return _CODE_FENCE_RE.sub(" ", text)


def count_words(text: str) -> int:
    """Count whitespace-separated words, ignoring fenced code blocks."""
    return len(strip_code_blocks(text).split())


def _headings(text: str) -> list[str]:
    return [m.group(1) for m in _H2_RE.finditer(strip_code_blocks(text))]


def _section_body(text: str, keywords: tuple[str, ...]) -> str | None:
    """Return the body of the first '##' section whose heading has one of `keywords`."""
    clean = strip_code_blocks(text)
    matches = list(_H2_RE.finditer(clean))
    for i, m in enumerate(matches):
        if any(k in m.group(1).lower() for k in keywords):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(clean)
            return clean[m.end():end]
    return None


# --- Individual rule checks: each returns (passed, comment) ----------------------


def check_title(text: str) -> tuple[bool, str]:
    ok = bool(_H1_RE.search(strip_code_blocks(text)))
    return ok, "Có tiêu đề." if ok else "Thiếu tiêu đề cấp 1 ('# Tên bài hướng dẫn')."


def check_sections(text: str) -> tuple[bool, str]:
    headings = [h.lower() for h in _headings(text)]
    missing = [
        label
        for label, kws in REQUIRED_SECTIONS.items()
        if not any(k in h for h in headings for k in kws)
    ]
    if missing:
        return False, "Thiếu mục: " + ", ".join(missing) + "."
    return True, "Đủ 5 mục bắt buộc."


def check_steps_count(text: str) -> tuple[bool, str]:
    body = _section_body(text, REQUIRED_SECTIONS["Các bước"])
    if body is None:
        return False, "Không tìm thấy mục 'Các bước'."
    n = len(_STEP_RE.findall(body))
    if MIN_STEPS <= n <= MAX_STEPS:
        return True, f"Có {n} bước."
    return False, f"Có {n} bước đánh số; cần từ {MIN_STEPS} đến {MAX_STEPS} bước."


def check_length(text: str, max_words: int) -> tuple[bool, str]:
    n = count_words(text)
    if n <= max_words:
        return True, f"{n}/{max_words} từ."
    return False, f"{n} từ, vượt giới hạn {max_words} từ (cần rút gọn ít nhất {n - max_words} từ)."


# --- Public API ------------------------------------------------------------------


def run_rule_checks(text: str, max_words: int) -> list[ItemResult]:
    """Run R1-R4 on `text`. Pure function: no LLM, no side effects."""
    outcomes = {
        "R1": check_title(text),
        "R2": check_sections(text),
        "R3": check_steps_count(text),
        "R4": check_length(text, max_words),
    }
    results = []
    for item in RULE_ITEMS:
        passed, comment = outcomes[item.id]
        results.append(
            ItemResult(
                id=item.id,
                description=item.description,
                kind="rule",
                passed=passed,
                comment=comment,
            )
        )
    return results
