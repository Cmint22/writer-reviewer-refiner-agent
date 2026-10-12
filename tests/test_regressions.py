"""
Regression tests for the defects the Reviewer (a small LLM) let through in the real runs.

Every sample below is taken from the actual terminal log: before R5-R8 existed, the
Reviewer returned 8/8 for all of them. These tests pin down that CODE now catches each
one, whatever the LLM says.
"""
import json

import pytest

from app.agents.reviewer import ReviewerAgent, is_vietnamese
from app.agents.refiner import RefinerAgent
from app.agents.writer import WriterAgent
from app.checklist import (
    check_command_order,
    check_hardcoded_secrets,
    check_invisible_chars,
    check_title_matches_topic,
    run_rule_checks,
)
from app.schemas import Draft, TutorialRequest
from app.textutil import find_invisible_chars, sanitize_text
from tests.conftest import GOOD_TUTORIAL

TOPIC_VENV = "Tạo môi trường ảo (virtual environment) và cài thư viện cho dự án Python"
TOPIC_GIT_WIN = "Cài đặt Git trên Windows"


def _doc(title="Tiêu đề", prep="- Có Python.", steps="1. A.\n2. B.\n3. C.", verify="Ok.", errors="- Lỗi."):
    return (
        f"# {title}\n\n## Mục tiêu\nx\n\n## Chuẩn bị\n{prep}\n\n## Các bước\n{steps}\n\n"
        f"## Kiểm tra kết quả\n{verify}\n\n## Lỗi thường gặp\n{errors}\n"
    )


def _all_llm_pass():
    return json.dumps([{"id": i, "passed": True, "comment": "Đạt."} for i in ("L1", "L2", "L3", "L4")])


class FixedReply:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, system_prompt, user_prompt):
        return self.reply


# --- Topic 1: title hallucination ("Môi Trường Ẩn") ---------------------------------


def test_r5_catches_hallucinated_title_word():
    text = GOOD_TUTORIAL.replace("# Tạo môi trường ảo Python", "# Tạo Môi Trường Ẩn Và Cài Thư Viện Cho Dự Án Python")
    ok, comment = check_title_matches_topic(text, TOPIC_VENV)
    assert not ok and "'ẩn'" in comment


def test_r5_accepts_a_shortened_title_and_generic_words():
    ok, _ = check_title_matches_topic(_doc("Hướng dẫn tạo môi trường ảo và cài thư viện Python").replace("x\n", "môi trường ảo\n", 1), TOPIC_VENV)
    assert ok


def test_r5_is_not_fooled_by_decomposed_unicode():
    # 'ảo' typed as a + combining hook above (NFD) is still the topic's word, with or without sanitising.
    nfd = "# Tạo môi trường a\u0309o\n"
    assert check_title_matches_topic(nfd, "Tạo môi trường ảo")[0]
    assert check_title_matches_topic(sanitize_text(nfd), "Tạo môi trường ảo")[0]


def test_reviewer_marks_r5_failed_even_when_llm_says_everything_passes():
    bad = _doc("Tạo Môi Trường Ẩn Và Cài Thư Viện Python").replace("x\n", "Tạo môi trường ảo.\n", 1)
    draft = Draft(topic=TOPIC_VENV, audience="người mới", max_words=350, content=bad)
    report = ReviewerAgent(FixedReply(_all_llm_pass())).run(draft)
    assert {r.id for r in report.failed} == {"R5"}


# --- Topic 1: zero-width space ----------------------------------------------------------


def test_r6_detects_zero_width_space_and_names_it():
    text = GOOD_TUTORIAL.replace("2. Chạy", "\u200b2. Chạy")
    ok, comment = check_invisible_chars(text)
    assert not ok and "U+200B" in comment and "dòng" in comment


@pytest.mark.parametrize("ch", ["\u200b", "\u200c", "\ufeff", "\u00a0", "\u2060", "\u202f", "\x07"])
def test_sanitize_removes_every_kind_of_invisible_character(ch):
    dirty = f"1.{ch} Chạy lệnh{ch}"
    clean = sanitize_text(dirty)
    assert find_invisible_chars(clean) == []
    assert "Chạy lệnh" in clean


def test_writer_and_refiner_output_is_sanitised(request_obj, good_draft):
    dirty = "\ufeff" + GOOD_TUTORIAL.replace("2. Chạy", "\u200b2. Chạy")
    draft = WriterAgent(FixedReply(dirty)).run(request_obj)
    assert find_invisible_chars(draft.content) == []

    from tests.test_refiner import _report

    final = RefinerAgent(FixedReply(dirty)).run(good_draft, _report(("R1",)))
    assert find_invisible_chars(final.content) == []


def test_sanitize_keeps_normal_text_and_newlines_unchanged():
    assert sanitize_text(GOOD_TUTORIAL) == GOOD_TUTORIAL


# --- Topic 2: git push without git init / add / commit ---------------------------------------


GIT_MISSING_INIT = _doc(
    "Tạo Repository GitHub và Đẩy Code lên",
    prep="Có tài khoản GitHub.",
    steps=(
        '1. Truy cập github.com và chọn "New repository".\n'
        "2. Đặt tên repository.\n"
        "3. Kết nối với remote bằng lệnh `git remote add origin <url>`.\n"
        "4. Đẩy code bằng lệnh `git push -u origin main`."
    ),
)


def test_r7_catches_missing_git_init_and_commit():
    ok, comment = check_command_order(GIT_MISSING_INIT, "Tạo repository mới trên GitHub và đẩy code đầu tiên")
    assert not ok
    assert "git init" in comment and "git commit" in comment
    assert "Bước 3" in comment and "Bước 4" in comment


def test_r7_accepts_the_full_git_sequence():
    steps = (
        "1. Khởi tạo repository: `git init`.\n"
        "2. Thêm file: `git add .`.\n"
        '3. Tạo commit: `git commit -m "first commit"`.\n'
        "4. Kết nối remote: `git remote add origin <url>`.\n"
        "5. Đẩy code: `git push -u origin main`."
    )
    assert check_command_order(_doc("Đẩy code", steps=steps), "đẩy code")[0]


def test_r7_understands_chained_commands_and_fenced_blocks():
    steps = "1. Khởi tạo và commit.\n```bash\ngit init\ngit add . && git commit -m \"x\"\n```\n2. Push: `git push`.\n3. Xong."
    assert check_command_order(_doc("Đẩy code", steps=steps), "đẩy code")[0]
    assert not check_command_order(_doc("Đẩy code", steps="1. Commit: `git add . && git commit -m x`.\n2. B.\n3. C."), "x")[0]


def test_r7_activate_needs_the_venv_to_be_created_first():
    bad = _doc("Venv", steps="1. Kích hoạt: `source venv/bin/activate`.\n2. A.\n3. B.")
    ok, comment = check_command_order(bad)
    assert not ok and "tạo môi trường ảo" in comment


# --- Topic 4: version check before install, git status outside a repository ----------------------


GIT_WIN_BAD_ORDER = _doc(
    "Cài đặt Git trên Windows",
    prep="- Windows 10 hoặc 11.",
    steps=(
        "1. Mở Command Prompt (cmd) và gõ `git --version` để kiểm tra.\n"
        "2. Truy cập trang web https://git-scm.com\n"
        "3. Tải và cài đặt Git từ trang chủ.\n"
        "4. Xác nhận cài đặt thành công bằng lệnh `git version`."
    ),
    verify="Mở Git Bash hoặc PowerShell và gõ `git status` để xem trạng thái file.",
)


def test_r7_catches_version_check_before_the_install_step():
    ok, comment = check_command_order(GIT_WIN_BAD_ORDER, TOPIC_GIT_WIN)
    assert not ok
    assert "Bước 1" in comment and "trước khi có bước tải/cài đặt" in comment
    assert "Bước 4" not in comment  # the version check AFTER the install step is fine


def test_r7_flags_git_status_as_an_install_check_outside_a_repository():
    ok, comment = check_command_order(GIT_WIN_BAD_ORDER, TOPIC_GIT_WIN)
    assert "git status" in comment and "git --version" in comment


def test_r7_accepts_install_then_verify():
    good = _doc(
        "Cài đặt Git trên Windows",
        steps=(
            "1. Truy cập https://git-scm.com và tải bộ cài đặt Git cho Windows.\n"
            "2. Chạy file vừa tải và cài đặt Git với tuỳ chọn mặc định.\n"
            "3. Mở Command Prompt mới và gõ `git --version`."
        ),
        verify="Lệnh `git --version` in ra số phiên bản.",
    )
    assert check_command_order(good, TOPIC_GIT_WIN)[0]


def test_r7_does_not_flag_a_python_version_check_in_a_venv_tutorial():
    # 'cài thư viện' is not 'install python', so checking `python --version` first is fine.
    steps = "1. Kiểm tra Python: `python --version`.\n2. Tạo venv: `python -m venv venv`.\n3. Cài: `pip install requests`."
    assert check_command_order(_doc("Venv", steps=steps), TOPIC_VENV)[0]


# --- Topic 3: API key hard-coded although the preparation says to use an env variable ---------------


OPENAI_BAD = _doc(
    "Gọi API OpenAI-compatible đầu tiên bằng Python",
    prep="- Thiết lập biến môi trường `OPENAI_API_KEY` với giá trị key của bạn",
    steps='1. **Khởi tạo client**\n```python\nimport openai\n\nclient = openai.OpenAI(api_key="YOUR_API_KEY")\n```\n2. Gửi prompt.\n3. In kết quả.',
)


def test_r8_catches_hardcoded_key_and_suggests_the_documented_variable():
    ok, comment = check_hardcoded_secrets(OPENAI_BAD)
    assert not ok
    assert 'api_key="YOUR_API_KEY"' in comment and 'os.environ["OPENAI_API_KEY"]' in comment


def test_r8_accepts_env_based_code_and_shell_env_setup():
    good = OPENAI_BAD.replace('api_key="YOUR_API_KEY"', 'api_key=os.environ["OPENAI_API_KEY"]')
    assert check_hardcoded_secrets(good)[0]
    assert check_hardcoded_secrets(_doc(steps='1. Đặt biến:\n```powershell\n$env:OPENAI_API_KEY="sk-xxx"\nsetx OPENAI_API_KEY "sk-xxx"\n```\n2. A.\n3. B.'))[0]
    assert check_hardcoded_secrets(_doc(steps="1. Ghi vào `.env`:\n```\nOPENAI_API_KEY=\"sk-xxx\"\n```\n2. A.\n3. B."))[0]
    assert check_hardcoded_secrets(_doc(steps="1. Gọi `OpenAI()` để SDK tự đọc biến môi trường.\n2. A.\n3. B."))[0]


def test_r8_catches_inline_code_assignment():
    assert not check_hardcoded_secrets(_doc(steps='1. Đặt `api_key="abc123"` trong code.\n2. A.\n3. B.'))[0]


def test_reviewer_marks_r8_failed_even_when_llm_praises_the_code():
    draft = Draft(topic="Gọi API OpenAI", audience="người mới", max_words=350, content=OPENAI_BAD)
    report = ReviewerAgent(FixedReply(_all_llm_pass())).run(draft)
    assert "R8" in {r.id for r in report.failed}


# --- Topic 4: Reviewer answers in English -------------------------------------------------------


def test_is_vietnamese_detects_english_comments():
    assert not is_vietnamese("Each tutorial step requires a single clear action in imperative form.")
    assert not is_vietnamese("Language is accessible for beginners; technical terms like 'PATH' and 'khóa bảo mật' are explained in context.")
    assert is_vietnamese("Mỗi bước chỉ có một hành động rõ ràng.")
    assert is_vietnamese("Đạt.")
    assert is_vietnamese("Bước 2: đặt lệnh `python -m venv` trong khối code (venv).")
    assert is_vietnamese("")


def test_reviewer_replaces_english_comments_with_vietnamese(good_draft):
    reply = json.dumps([
        {"id": "L1", "passed": True, "comment": "Each tutorial step requires a single clear action in imperative form."},
        {"id": "L2", "passed": False, "comment": "Commands are not placed in code format and values are vague."},
        {"id": "L3", "passed": True, "comment": "Phù hợp người mới."},
        {"id": "L4", "passed": True, "comment": ""},
    ])
    report = ReviewerAgent(FixedReply(reply)).run(good_draft)
    by_id = {r.id: r for r in report.results}
    assert by_id["L1"].comment == "Đạt."
    assert by_id["L2"].comment.startswith("Chưa đạt.") and "Commands are not placed" in by_id["L2"].comment
    assert by_id["L2"].passed is False  # the verdict itself is never changed by the language guard
    assert by_id["L3"].comment == "Phù hợp người mới."
    assert all(is_vietnamese(r.comment.split("(bằng tiếng Anh):")[0]) for r in report.results)


def test_reviewer_prompt_demands_vietnamese_comments(good_draft):
    seen = {}

    class Spy:
        def chat(self, system_prompt, user_prompt):
            seen["system"], seen["user"] = system_prompt, user_prompt
            return _all_llm_pass()

    ReviewerAgent(Spy()).run(good_draft)
    assert "TIẾNG VIỆT" in seen["system"] and "TIẾNG VIỆT" in seen["user"]


# --- Pipeline: defects are caught by code and fixed by the Refiner, which IS now called --------------


def test_pipeline_sends_code_found_defects_to_the_refiner_even_if_the_llm_approves_everything():
    from app.pipeline import WriterReviewerRefinerPipeline

    class Approving:
        """Writes the bad Topic-3 draft, approves it in review, and 'fixes' what the Refiner is told."""

        def __init__(self):
            self.calls, self.refiner_prompt = [], ""

        def chat(self, system_prompt, user_prompt):
            if "=== FAILED ITEMS ===" in user_prompt:
                self.calls.append("refiner")
                self.refiner_prompt = user_prompt
                return OPENAI_BAD.replace('api_key="YOUR_API_KEY"', 'api_key=os.environ["OPENAI_API_KEY"]')
            if "=== TUTORIAL ===" in user_prompt:
                self.calls.append("reviewer")
                return _all_llm_pass()
            self.calls.append("writer")
            return OPENAI_BAD

    llm = Approving()
    req = TutorialRequest(topic="Gọi API OpenAI-compatible đầu tiên bằng Python", max_words=350)
    result = WriterReviewerRefinerPipeline(llm_client=llm).run(req)

    assert llm.calls == ["writer", "reviewer", "refiner"]  # Refiner is called, still one review round
    assert result.final.refined is True
    assert [r.id for r in result.review.failed] == ["R8"]
    assert "[R8]" in llm.refiner_prompt and "os.environ" in llm.refiner_prompt
    assert all(r.passed for r in result.post_check)


def test_post_check_uses_the_topic(request_obj):
    # R5 in the post-check needs the topic, so a final title that drifted is reported honestly.
    from app.pipeline import WriterReviewerRefinerPipeline
    from tests.fakes import FakeLLMClient

    class DriftingRefiner(FakeLLMClient):
        def _refine(self, user_prompt):  # type: ignore[override]
            return GOOD_TUTORIAL.replace("# Tạo môi trường ảo Python", "# Tạo môi trường ẩn Python")

    result = WriterReviewerRefinerPipeline(llm_client=DriftingRefiner()).run(request_obj)
    assert {r.id for r in result.post_check if not r.passed} == {"R5"}


# --- Reviewer on its own model (self-bias) ---------------------------------------------------------


def test_reviewer_can_use_a_separate_client():
    from app.pipeline import WriterReviewerRefinerPipeline
    from tests.fakes import FakeLLMClient

    writer_llm, reviewer_llm = FakeLLMClient(draft=GOOD_TUTORIAL), FakeLLMClient()
    req = TutorialRequest(topic="Tạo môi trường ảo Python")
    WriterReviewerRefinerPipeline(llm_client=writer_llm, reviewer_client=reviewer_llm).run(req)
    assert writer_llm.calls == ["writer"]
    assert reviewer_llm.calls == ["reviewer"]


def test_reviewer_client_falls_back_to_the_writer_client_without_reviewer_env():
    from app.config import Settings
    from app.llm_client import get_reviewer_llm_client

    sentinel = object()
    assert get_reviewer_llm_client(Settings(llm_api_key="k"), default=sentinel) is sentinel  # type: ignore[arg-type]


def test_reviewer_client_uses_the_reviewer_model_when_configured():
    from app.config import Settings
    from app.llm_client import OpenAICompatibleClient, get_reviewer_llm_client

    cfg = Settings(llm_api_key="k", llm_model="small", reviewer_model="big")
    client = get_reviewer_llm_client(cfg, default=object())  # type: ignore[arg-type]
    assert isinstance(client, OpenAICompatibleClient) and client._model == "big"


# --- Runner: --max-words outside the allowed range -------------------------------------------------


def test_max_words_below_the_allowed_minimum_gives_a_clear_error():
    import argparse

    import e2e_runner

    assert e2e_runner._max_words("100") == 100
    with pytest.raises(argparse.ArgumentTypeError, match="100"):
        e2e_runner._max_words("80")
    with pytest.raises(argparse.ArgumentTypeError):
        e2e_runner._max_words("abc")
