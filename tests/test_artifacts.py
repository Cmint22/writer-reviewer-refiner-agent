import json

from app.artifacts import render_checklist_md, save_artifacts, slugify
from app.pipeline import WriterReviewerRefinerPipeline
from tests.fakes import FakeLLMClient


def test_slugify_handles_vietnamese():
    assert slugify("Tạo môi trường ảo (virtual environment)") == "tao-moi-truong-ao-virtual-environment"
    assert slugify("Đẩy code lên GitHub") == "day-code-len-github"
    assert slugify("!!!") == "tutorial"
    assert len(slugify("a" * 200)) <= 40


def test_save_artifacts_writes_the_three_deliverables(tmp_path, request_obj):
    result = WriterReviewerRefinerPipeline(llm_client=FakeLLMClient()).run(request_obj)
    paths = save_artifacts(result, tmp_path)

    assert set(paths) == {"draft", "checklist_md", "checklist_json", "final", "trace"}
    assert all(p.exists() for p in paths.values())
    assert paths["draft"].name == "01_draft.md"
    assert paths["final"].name == "03_final.md"
    assert paths["draft"].read_text(encoding="utf-8").strip() == result.draft.content
    assert paths["final"].read_text(encoding="utf-8").strip() == result.final.content

    review = json.loads(paths["checklist_json"].read_text(encoding="utf-8"))
    assert review["total"] == 12 and review["passed_count"] == 10
    trace = json.loads(paths["trace"].read_text(encoding="utf-8"))
    assert trace["review_rounds"] == 1


def test_checklist_markdown_has_table_and_states_the_single_round(request_obj):
    result = WriterReviewerRefinerPipeline(llm_client=FakeLLMClient()).run(request_obj)
    md = render_checklist_md(result)
    assert "| ID | Loại | Tiêu chí | Kết quả | Nhận xét |" in md
    assert md.count("CHƯA ĐẠT") == 2  # R2 and L2 on the draft; post-check is all green
    assert "10/12" in md
    assert "không phải vòng review thứ hai" in md
