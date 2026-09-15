"""FastAPI backend for the child digital-safety survey dashboard."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import loaders
from .analytics import SurveyData

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Child Digital Safety Survey API",
    description="Reads a Google Forms export (file or Drive link) and serves statistics.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE: dict[str, SurveyData | None] = {"data": None}


def store() -> SurveyData:
    if STATE["data"] is None:
        raise HTTPException(404, "No survey loaded yet. Upload a file or paste a Drive link.")
    return STATE["data"]


@app.on_event("startup")
def _load_default() -> None:
    df, name = loaders.default_dataframe()
    if df is not None:
        STATE["data"] = SurveyData(df, source=name)


def parse_filters(raw: str | None) -> dict[str, list[str]]:
    """filters is a JSON object: {"النوع": ["أنثى"], "كم عمرك؟": [...]}"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "filters must be a JSON object")
    return {k: v if isinstance(v, list) else [v] for k, v in parsed.items() if v}


# --------------------------------------------------------------- endpoints ---


@app.get("/api/health")
def health() -> dict[str, Any]:
    data = STATE["data"]
    return {"status": "ok", "loaded": data is not None, "source": data.source if data else None}


@app.get("/api/meta")
def meta() -> dict:
    return store().meta()


@app.get("/api/kpis")
def kpis(filters: str | None = Query(None)) -> dict:
    return {"kpis": store().kpis(parse_filters(filters))}


@app.get("/api/highlights")
def highlights(filters: str | None = Query(None)) -> dict:
    return {"highlights": store().highlights(parse_filters(filters))}


@app.get("/api/stats")
def stats(filters: str | None = Query(None)) -> dict:
    return store().stats(parse_filters(filters))


@app.get("/api/question/{question_id}")
def question(question_id: str, filters: str | None = Query(None)) -> dict:
    data = store()
    q = data.by_id.get(question_id)
    if not q:
        raise HTTPException(404, "Unknown question id")
    block = next(b for b in data.stats(parse_filters(filters))["blocks"] if b["id"] == question_id)
    return block


@app.get("/api/responses")
def responses(
    filters: str | None = Query(None),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
) -> dict:
    rows = store().rows(parse_filters(filters), search)
    start = (page - 1) * size
    return {
        "total": len(rows),
        "page": page,
        "size": size,
        "rows": rows[start : start + size],
    }


class DriveLink(BaseModel):
    link: str


@app.post("/api/source/drive")
async def load_drive(payload: DriveLink) -> dict:
    try:
        df = await loaders.read_link(payload.link)
    except Exception as exc:
        raise HTTPException(400, f"Could not read that link: {exc}")
    STATE["data"] = SurveyData(df, source=payload.link)
    return {"loaded": True, **STATE["data"].meta()}


@app.post("/api/source/upload")
async def load_upload(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        df = loaders.read_bytes(raw, file.filename or "")
    except Exception as exc:
        raise HTTPException(400, f"Could not read that file: {exc}")
    STATE["data"] = SurveyData(df, source=file.filename or "upload")
    return {"loaded": True, **STATE["data"].meta()}


@app.get("/api/export/summary.csv")
def export_summary(filters: str | None = Query(None)) -> StreamingResponse:
    data = store().stats(parse_filters(filters))
    records = [
        {"question": b["title"], "answer": opt["label"], "count": opt["count"], "percent": opt["percent"]}
        for b in data["blocks"]
        if b["type"] != "open"
        for opt in b["data"]
    ]
    buf = io.StringIO()
    pd.DataFrame(records).to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_summary.csv"},
    )


# ------------------------------------------------------------------- pages ---

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
