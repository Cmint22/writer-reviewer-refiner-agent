#!/usr/bin/env python3
"""
Single-command End-to-End runner.

Usage:
    python e2e_runner.py                         # runs ALL demo topics below
    python e2e_runner.py --topic "..."           # runs exactly ONE custom topic
    python e2e_runner.py --output-dir ./my_out   # change where deliverables go

What it does, per topic:
    1. Writer   -> first draft
    2. Reviewer -> checklist report (ONE review round)
    3. Refiner  -> final tutorial (fixes only failed items)
    4. Saves outputs/<slug>/: 01_draft.md, 02_review_checklist.md/.json,
       03_final.md, trace.json

Needs a real LLM: LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL) in the
environment or .env — there is no mock/offline mode in the app.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.artifacts import save_artifacts
from app.config import settings
from app.pipeline import WriterReviewerRefinerPipeline
from app.schemas import MAX_MAX_WORDS, MIN_MAX_WORDS, PipelineResult, TutorialRequest

DEMO_TOPICS = [
    "Tạo môi trường ảo (virtual environment) và cài thư viện cho dự án Python",
    "Tạo repository mới trên GitHub và đẩy code đầu tiên lên từ máy tính",
    "Gọi API OpenAI-compatible đầu tiên bằng Python với thư viện openai",
]


def run_one(pipeline: WriterReviewerRefinerPipeline, request: TutorialRequest, out_dir: Path) -> PipelineResult:
    print(f"Topic       : {request.topic}")
    print("-" * 80)
    result = pipeline.run(request)

    print("\n### DRAFT (Writer) ###\n")
    print(result.draft.content)

    print("\n" + "=" * 80)
    print(f"### CHECKLIST (Reviewer): {result.review.passed_count}/{result.review.total} đạt ###")
    print("=" * 80)
    for r in result.review.results:
        print(f"[{'ĐẠT' if r.passed else 'CHƯA ĐẠT':8}] {r.id} ({r.kind}) {r.comment}")

    print("\n" + "=" * 80)
    print(f"### FINAL (Refiner) — refined={result.final.refined} ###")
    print("=" * 80 + "\n")
    print(result.final.content)

    print("\n" + "-" * 80)
    failed_rules = [r for r in result.post_check if not r.passed]
    if failed_rules:
        print("WARNING: rule(s) still failing after refinement (no 2nd review round by design):")
        for r in failed_rules:
            print(f"  {r.id}: {r.comment}")
    else:
        print("OK: all code-checkable rules (R1-R8) pass on the final text.")

    paths = save_artifacts(result, out_dir)
    print(f"Saved to: {paths['final'].parent}")
    return result


def _max_words(value: str) -> int:
    """argparse type: reject a limit that TutorialRequest would reject, with a clear message."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' không phải số nguyên") from None
    if not MIN_MAX_WORDS <= n <= MAX_MAX_WORDS:
        raise argparse.ArgumentTypeError(
            f"--max-words phải nằm trong khoảng {MIN_MAX_WORDS}–{MAX_MAX_WORDS} (nhận được {n}). "
            f"Muốn ép R4 trượt, dùng giá trị gần {MIN_MAX_WORDS} với bài dài hơn {MIN_MAX_WORDS} từ."
        )
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Writer-Reviewer-Refiner pipeline end-to-end.")
    parser.add_argument("--topic", "-t", default=None, help="Run exactly this ONE topic instead of the demo set.")
    parser.add_argument("--audience", "-a", default="người mới bắt đầu", help="Target reader.")
    parser.add_argument(
        "--max-words", "-w", type=_max_words, default=350,
        help=f"Length limit (prose words), {MIN_MAX_WORDS}-{MAX_MAX_WORDS}.",
    )
    parser.add_argument(
        "--output-dir", "-o", default=str(Path(__file__).parent / "outputs"),
        help="Directory to save deliverables into (default: ./outputs).",
    )
    args = parser.parse_args()

    if not settings.llm_api_key:
        print(
            "ERROR: LLM_API_KEY is not set. Configure it (and LLM_BASE_URL / LLM_MODEL) "
            "in your environment or .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    topics = [args.topic] if args.topic else DEMO_TOPICS
    print("=" * 80)
    print("WRITER-REVIEWER-REFINER MULTI-AGENT — E2E RUN")
    print("=" * 80)
    print(f"LLM model   : {settings.llm_model}")
    print(f"Reviewer    : {settings.reviewer_model or settings.llm_model}")
    print(f"LLM base URL: {settings.llm_base_url}")
    print(f"Topics      : {len(topics)}  | review rounds per topic: 1")
    print("-" * 80)

    pipeline = WriterReviewerRefinerPipeline()
    out_dir = Path(args.output_dir)
    any_failed = False
    for i, topic in enumerate(topics, start=1):
        print(f"\n{'#' * 80}\n# TOPIC {i}/{len(topics)}\n{'#' * 80}")
        request = TutorialRequest(topic=topic, audience=args.audience, max_words=args.max_words)
        result = run_one(pipeline, request, out_dir)
        any_failed = any_failed or any(not r.passed for r in result.post_check)

    print("\n" + "=" * 80)
    print(f"DONE — {len(topics)} topic(s) run.")
    if any_failed:
        print("At least one final text still fails a code-checkable rule — see above / checklist files.")
        sys.exit(1)
    print("All final texts pass the code-checkable rules.")


if __name__ == "__main__":
    main()
