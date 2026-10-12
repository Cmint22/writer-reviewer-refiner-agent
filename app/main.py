"""
FastAPI entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000

Endpoints:
    GET  /health   -> liveness check + which LLM backend is configured
    POST /run      -> run Writer -> Reviewer -> Refiner for one tutorial topic
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.pipeline import WriterReviewerRefinerPipeline
from app.schemas import PipelineResult, TutorialRequest

app = FastAPI(
    title="Writer-Reviewer-Refiner Multi-Agent API",
    description="A minimal 3-agent pipeline that drafts, checklist-reviews (one round) and refines a short tutorial.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_mode": "real",
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
    }


@app.post("/run", response_model=PipelineResult)
def run_pipeline(payload: TutorialRequest) -> PipelineResult:
    try:
        pipeline = WriterReviewerRefinerPipeline()
        return pipeline.run(payload)
    except RuntimeError as e:  # missing LLM_API_KEY, or an agent returned empty output
        raise HTTPException(status_code=503, detail=str(e)) from e
