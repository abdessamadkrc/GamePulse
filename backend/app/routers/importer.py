"""Import endpoints used by the browser's Import page.

  GET  /api/import/state          is importing allowed / is a job running
  POST /api/import/upload         multipart files -> detected tables + column mappings + previews
  POST /api/import/validate       dry run: errors and warnings, nothing is changed
  POST /api/import/run            start the import (background job)
  GET  /api/import/status/{id}    poll a job
  POST /api/import/demo           (re)generate the synthetic demo dataset
  GET  /api/import/sample.zip     example CSV files in the expected format

Set ALLOW_IMPORT=0 to switch all of this off (e.g. on a public deployment).
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..db import jsonable
from ..services import importer as imp

router = APIRouter(prefix="/api/import")


def allowed() -> bool:
    return os.getenv("ALLOW_IMPORT", "1") == "1"


def _guard() -> None:
    if not allowed():
        raise HTTPException(403, "Importing data is disabled on this server (ALLOW_IMPORT=0).")


class FileSpec(BaseModel):
    filename: str
    table: str = Field(description="players, sessions, matches, purchases, events, experiments, experiment_catalog, devices or ignore")
    mapping: dict[str, str | None] = {}


class RunRequest(BaseModel):
    session_id: str
    files: list[FileSpec]
    options: dict[str, Any] = {}


class DemoRequest(BaseModel):
    players: int = Field(52_000, ge=1_000, le=200_000)


@router.get("/state")
def state():
    return {"allowed": allowed(), "busy": imp.busy(), "job": imp.current_job()}


@router.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    _guard()
    if imp.busy():
        raise HTTPException(409, "An import is already running.")
    if not files:
        raise HTTPException(400, "No files received.")
    sid, folder = imp.new_session_dir()
    total = 0
    for f in files:
        name = imp.safe_name(f.filename or "file.csv")
        low = name.lower()
        if not low.endswith((".csv", ".tsv", ".txt", ".zip")):
            raise HTTPException(400, f"{name}: only .csv, .tsv, .txt or .zip files are supported.")
        target = folder / name
        with open(target, "wb") as out:
            while chunk := await f.read(1 << 20):
                total += len(chunk)
                if total > imp.MAX_UPLOAD_BYTES:
                    imp.shutil_cleanup(sid)
                    raise HTTPException(413, f"Upload is larger than {imp.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
                out.write(chunk)
        if low.endswith(".zip"):
            try:
                imp.extract_zip(target, folder)
            except ValueError as exc:
                imp.shutil_cleanup(sid)
                raise HTTPException(400, f"{name}: {exc}") from exc
            target.unlink(missing_ok=True)
    inspected = []
    for p in sorted(folder.iterdir()):
        try:
            inspected.append(imp.inspect_file(p))
        except Exception as exc:  # noqa: BLE001
            inspected.append({"filename": p.name, "error": f"Could not read this file as a table: {exc}", "rows": 0,
                              "columns": [], "table": None, "mapping": {}, "preview": []})
    return jsonable({
        "session_id": sid, "files": inspected,
        "tables": [{"value": t, "label": imp.TABLE_LABEL[t], "required": imp.REQUIRED.get(t, []), "columns": imp.COLUMNS[t]} for t in imp.COLUMNS],
    })


def _specs(req: RunRequest) -> list[dict[str, Any]]:
    return [f.model_dump() for f in req.files]


@router.post("/validate")
def validate(req: RunRequest):
    _guard()
    try:
        res = imp.validate_specs(req.session_id, _specs(req), req.options)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return jsonable({"ok": not res.errors, "errors": res.errors, "warnings": res.warnings, "stats": res.stats})


@router.post("/run")
def run(req: RunRequest):
    _guard()
    try:
        imp.session_dir(req.session_id)
        job = imp.start_import(req.session_id, _specs(req), req.options)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"job_id": job.id}


@router.post("/demo")
def demo(req: DemoRequest):
    _guard()
    try:
        job = imp.start_demo(req.players)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"job_id": job.id}


@router.get("/status/{job_id}")
def status(job_id: str):
    job = imp.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    return jsonable(job.public())


@router.get("/sample.zip")
def sample():
    return Response(imp.sample_zip(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="gamepulse-sample-csvs.zip"'})
