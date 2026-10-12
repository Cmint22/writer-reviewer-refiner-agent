"""
Writer Agent.

Responsibility (and ONLY responsibility):
  - Take a TutorialRequest (topic, audience, length limit).
  - Produce the FIRST DRAFT of a short Markdown tutorial.

The Writer does not see the evaluation checklist: checking is the
Reviewer's job. It only gets a format brief (the sections a tutorial
should have), so the draft is a genuine first attempt that the
Reviewer then tests independently.
"""
from __future__ import annotations

from app.llm_client import LLMClient
from app.schemas import Draft, TutorialRequest

WRITER_SYSTEM_PROMPT = """\
Bạn là WRITER AGENT trong một hệ thống multi-agent (Writer -> Reviewer -> Refiner).

NHIỆM VỤ DUY NHẤT của bạn: viết BẢN NHÁP một bài hướng dẫn ngắn bằng tiếng Việt, định dạng Markdown.

QUY TẮC:
1. Bài viết có tiêu đề cấp 1 ('# ...') và các mục cấp 2 ('## ...') theo thứ tự:
   Mục tiêu, Chuẩn bị, Các bước, Kiểm tra kết quả, Lỗi thường gặp.
2. Mục 'Các bước' là danh sách đánh số; mỗi bước một hành động.
3. Lệnh, đoạn mã, tên file, giá trị cụ thể viết trong khối code.
4. Tuân thủ giới hạn độ dài và văn phong phù hợp đối tượng người đọc.
5. CHỈ trả về nội dung bài hướng dẫn Markdown — không lời dẫn, không giải thích thêm,
   không bọc toàn bộ bài trong khối code.
"""

WRITER_USER_PROMPT_TEMPLATE = """\
CHỦ ĐỀ: {topic}
ĐỐI TƯỢNG NGƯỜI ĐỌC: {audience}
GIỚI HẠN ĐỘ DÀI: tối đa {max_words} từ (không tính khối code)

Hãy viết bản nháp bài hướng dẫn theo đúng quy tắc trong system prompt.
"""


def strip_outer_code_fence(text: str) -> str:
    """Remove a ```markdown ... ``` wrapper some LLMs put around the whole answer."""
    t = text.strip()
    lines = t.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower() in ("```markdown", "```md") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return t


class WriterAgent:
    """Wraps an LLMClient to perform the Writer role."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def run(self, request: TutorialRequest) -> Draft:
        user_prompt = WRITER_USER_PROMPT_TEMPLATE.format(
            topic=request.topic,
            audience=request.audience,
            max_words=request.max_words,
        )
        raw = self._llm.chat(WRITER_SYSTEM_PROMPT, user_prompt)
        content = strip_outer_code_fence(raw)
        if not content:
            raise RuntimeError("Writer returned an empty draft.")
        return Draft(
            topic=request.topic,
            audience=request.audience,
            max_words=request.max_words,
            content=content,
        )
