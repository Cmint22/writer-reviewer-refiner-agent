import sys
from pathlib import Path

import pytest

# Make the project root importable as `app.*` when running `pytest` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import Draft, TutorialRequest  # noqa: E402

GOOD_TUTORIAL = """\
# Tạo môi trường ảo Python

## Mục tiêu
Tạo một môi trường ảo riêng cho dự án.

## Chuẩn bị
- Đã cài Python 3.10 trở lên.

## Các bước
1. Mở terminal tại thư mục dự án.
2. Chạy lệnh `python -m venv .venv`.
3. Kích hoạt môi trường bằng `source .venv/bin/activate`.

## Kiểm tra kết quả
Dấu nhắc lệnh hiện tiền tố `(.venv)`.

## Lỗi thường gặp
- Lệnh `python` không tìm thấy: thử `python3`.
"""


@pytest.fixture
def request_obj() -> TutorialRequest:
    return TutorialRequest(topic="Tạo môi trường ảo Python", audience="người mới bắt đầu", max_words=350)


@pytest.fixture
def good_draft() -> Draft:
    return Draft(topic="Tạo môi trường ảo Python", audience="người mới bắt đầu", max_words=350, content=GOOD_TUTORIAL)
