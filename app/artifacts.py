"""
Write the three deliverables of a run to disk:

    01_draft.md              bản nháp (Writer)
    02_review_checklist.md   checklist đánh giá (Reviewer) — bảng đọc được
    02_review_checklist.json same data, machine-readable
    03_final.md              bản hoàn chỉnh (Refiner)
    trace.json               full PipelineResult
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.schemas import ItemResult, PipelineResult


def slugify(text: str, max_len: int = 40) -> str:
    """ASCII slug that handles Vietnamese diacritics (incl. 'đ')."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].strip("-")) or "tutorial"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _table(results: list[ItemResult]) -> str:
    rows = ["| ID | Loại | Tiêu chí | Kết quả | Nhận xét |", "|---|---|---|---|---|"]
    for r in results:
        kind = "code" if r.kind == "rule" else "LLM"
        mark = "ĐẠT" if r.passed else "CHƯA ĐẠT"
        rows.append(f"| {r.id} | {kind} | {_cell(r.description)} | {mark} | {_cell(r.comment)} |")
    return "\n".join(rows)


def render_checklist_md(result: PipelineResult) -> str:
    review = result.review
    parts = [
        f"# Checklist đánh giá — {result.request.topic}",
        "",
        f"Vòng review: {result.review_rounds} (giới hạn 1 vòng). "
        f"Kết quả trên bản nháp: **{review.passed_count}/{review.total}** mục đạt.",
        "",
        _table(review.results),
        "",
        "## Sau khi sửa (kiểm tra lại bằng code)",
        "",
        "Chỉ chạy lại các mục R1–R4 bằng code Python; không gọi LLM, không phải vòng review thứ hai.",
        "Các mục L1–L4 chỉ được đánh giá một lần, trên bản nháp.",
        "",
        _table(result.post_check),
        "",
    ]
    return "\n".join(parts)


def save_artifacts(result: PipelineResult, out_dir: Path) -> dict[str, Path]:
    """Save deliverables under `out_dir/<slug>/` and return {name: path}."""
    run_dir = Path(out_dir) / slugify(result.request.topic)
    run_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "draft": (run_dir / "01_draft.md", result.draft.content.rstrip() + "\n"),
        "checklist_md": (run_dir / "02_review_checklist.md", render_checklist_md(result)),
        "checklist_json": (
            run_dir / "02_review_checklist.json",
            result.review.model_dump_json(indent=2),
        ),
        "final": (run_dir / "03_final.md", result.final.content.rstrip() + "\n"),
        "trace": (run_dir / "trace.json", result.model_dump_json(indent=2)),
    }
    for path, text in files.values():
        path.write_text(text, encoding="utf-8")
    return {name: path for name, (path, _) in files.items()}
