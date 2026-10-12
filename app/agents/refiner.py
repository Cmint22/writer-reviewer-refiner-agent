"""
Refiner Agent.

Responsibility (and ONLY responsibility):
  - Take the Writer's draft and the Reviewer's ReviewReport.
  - Produce the FINAL tutorial by fixing exactly the items that failed.

Constraints enforced in code (not only in the prompt):
  - `run(draft, review)` is the whole interface: the Refiner cannot call the
    Reviewer, so it cannot start another review round.
  - If nothing failed, the draft is returned unchanged WITHOUT calling the LLM,
    so a clean draft is never "improved" into something unreviewed.
  - Only the failed items are shown to the LLM, so it has no reason to touch
    the parts that already passed.
"""
from __future__ import annotations

from app.agents.writer import strip_outer_code_fence
from app.llm_client import LLMClient
from app.schemas import Draft, FinalTutorial, ReviewReport
from app.textutil import sanitize_text

REFINER_SYSTEM_PROMPT = """\
Bạn là REFINER AGENT trong một hệ thống multi-agent (Writer -> Reviewer -> Refiner).

NHIỆM VỤ DUY NHẤT của bạn: sửa BẢN NHÁP để khắc phục các mục CHƯA ĐẠT mà Reviewer đã chỉ ra,
rồi trả về BẢN HOÀN CHỈNH.

QUY TẮC BẮT BUỘC:
1. Chỉ sửa những gì cần thiết để các mục chưa đạt được khắc phục. GIỮ NGUYÊN các phần khác của
   bản nháp (nội dung, thứ tự, văn phong).
2. Làm theo nhận xét của Reviewer. Nếu một mục không có hướng dẫn sửa cụ thể, giữ nguyên phần liên quan.
3. Không thêm thông tin kỹ thuật mới không liên quan tới các mục cần sửa.
4. Vẫn tuân thủ giới hạn độ dài và cấu trúc: tiêu đề '# ...', các mục '## ...' theo thứ tự
   Mục tiêu, Chuẩn bị, Các bước (danh sách đánh số), Kiểm tra kết quả, Lỗi thường gặp.
5. Khi nhận xét yêu cầu thêm hoặc đổi chỗ một bước: đặt bước đúng vị trí, đánh số lại liên tục
   (1, 2, 3, ...), giữ tối đa 8 bước và không vượt giới hạn độ dài (rút gọn phần khác nếu cần).
6. Khi nhận xét nêu một từ sai trong tiêu đề: sửa đúng từ đó bằng thuật ngữ trong chủ đề, giữ nguyên phần còn lại.
7. Không bao giờ viết giá trị khóa API trực tiếp vào mã; đọc từ biến môi trường. Chỉ dùng ký tự văn bản thông
   thường (không ký tự ẩn, không khoảng trắng đặc biệt).
8. CHỈ trả về toàn văn bài hướng dẫn Markdown đã sửa — không lời dẫn, không liệt kê các thay đổi,
   không bọc toàn bộ bài trong khối code.
"""

REFINER_USER_PROMPT_TEMPLATE = """\
CHỦ ĐỀ: {topic}
ĐỐI TƯỢNG NGƯỜI ĐỌC: {audience}
GIỚI HẠN ĐỘ DÀI: tối đa {max_words} từ (không tính khối code)

=== DRAFT ===
{content}
=== END DRAFT ===

=== FAILED ITEMS ===
{failed_block}
=== END FAILED ITEMS ===

Hãy trả về bản hoàn chỉnh theo đúng quy tắc trong system prompt.
"""


class RefinerAgent:
    """Wraps an LLMClient to perform the Refiner role."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def run(self, draft: Draft, review: ReviewReport) -> FinalTutorial:
        if review.all_passed:
            return FinalTutorial(topic=draft.topic, content=draft.content, refined=False)

        user_prompt = REFINER_USER_PROMPT_TEMPLATE.format(
            topic=draft.topic,
            audience=draft.audience,
            max_words=draft.max_words,
            content=draft.content,
            failed_block=review.failed_items_block(),
        )
        raw = self._llm.chat(REFINER_SYSTEM_PROMPT, user_prompt)
        content = sanitize_text(strip_outer_code_fence(raw)).strip()
        if not content:
            raise RuntimeError("Refiner returned an empty final tutorial.")
        return FinalTutorial(topic=draft.topic, content=content, refined=True)
