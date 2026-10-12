"""
Test-only fake LLM client.

The application code (app/llm_client.py) always talks to a real,
OpenAI-compatible endpoint — it has no built-in mock/offline mode. This fake
exists purely so the test suite runs deterministically and offline.

It plays all three roles, told apart by the markers in the prompt:
  - "=== FAILED ITEMS ===" -> Refiner
  - "=== TUTORIAL ==="     -> Reviewer
  - otherwise              -> Writer

The fake Writer deliberately produces an imperfect draft (no 'Lỗi thường gặp'
section, and a command written outside a code block), so the Reviewer has
real defects to find and the Refiner has real defects to fix.
"""
from __future__ import annotations

import json
import re

BAD_DRAFT = """\
# Tạo môi trường ảo Python

## Mục tiêu
Tạo một môi trường ảo riêng cho dự án.

## Chuẩn bị
- Đã cài Python 3.10 trở lên.

## Các bước
1. Mở terminal tại thư mục dự án.
2. Gõ lệnh python -m venv .venv để tạo môi trường.
3. Kích hoạt môi trường bằng `source .venv/bin/activate`.

## Kiểm tra kết quả
Dấu nhắc lệnh hiện tiền tố `(.venv)`.
"""

_TROUBLESHOOTING = "\n## Lỗi thường gặp\n- Lệnh `python` không tìm thấy: thử `python3`.\n"


class FakeLLMClient:
    def __init__(self, draft: str = BAD_DRAFT):
        self._draft = draft
        self.calls: list[str] = []  # role of each call, in order

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if "=== FAILED ITEMS ===" in user_prompt:
            self.calls.append("refiner")
            return self._refine(user_prompt)
        if "=== TUTORIAL ===" in user_prompt:
            self.calls.append("reviewer")
            return self._review(user_prompt)
        self.calls.append("writer")
        return self._draft

    @staticmethod
    def _review(user_prompt: str) -> str:
        m = re.search(r"=== TUTORIAL ===\n(.*?)\n=== END TUTORIAL ===", user_prompt, re.DOTALL)
        tutorial = m.group(1) if m else ""
        # L2 fails when a numbered step mentions `python -m` without backticks.
        bad_step = next(
            (ln for ln in tutorial.splitlines() if re.match(r"\s*\d+\.", ln) and "python -m" in ln and "`" not in ln),
            None,
        )
        verdicts = [
            {"id": "L1", "passed": True, "comment": "Mỗi bước một hành động."},
            {
                "id": "L2",
                "passed": bad_step is None,
                "comment": "Đạt." if bad_step is None else "Bước 2: đặt lệnh trong khối code.",
            },
            {"id": "L3", "passed": True, "comment": "Phù hợp người mới."},
            {"id": "L4", "passed": True, "comment": "Bám sát chủ đề."},
        ]
        return json.dumps(verdicts, ensure_ascii=False)

    @staticmethod
    def _refine(user_prompt: str) -> str:
        m = re.search(r"=== DRAFT ===\n(.*?)\n=== END DRAFT ===", user_prompt, re.DOTALL)
        text = m.group(1) if m else ""
        failed = user_prompt.split("=== FAILED ITEMS ===")[1]
        if "[R2]" in failed:
            text = text.rstrip() + "\n" + _TROUBLESHOOTING
        if "[L2]" in failed:
            text = text.replace("Gõ lệnh python -m venv .venv", "Gõ lệnh `python -m venv .venv`")
        return text
