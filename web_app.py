"""
FastAPI Web Application & Dashboard for NSE Market Data Downloader.

Provides:
  • Interactive single-page dashboard with glassmorphism UI
  • Real-time stock search and filtering across all 4 datasets
  • One-click live ingestion trigger
  • Direct CSV downloads for each dataset
  • REST API endpoints for data integration
"""

from __future__ import annotations

import glob
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import DATASETS, StorageConfig
from pipeline import Pipeline

app = FastAPI(
    title="NSE Market Data Live Dashboard",
    description="Live analytical dashboard & REST APIs for NSE India Market Data",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
os.makedirs(WEB_DIR, exist_ok=True)


def get_latest_csv(dataset_key: str) -> Optional[str]:
    """Return the absolute path of the newest CSV file for a given dataset."""
    storage_cfg = StorageConfig()
    pattern = os.path.join(storage_cfg.output_dir, f"{dataset_key}_*.csv")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# ──────────────────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Return status, record counts, and timestamps for all datasets."""
    storage_cfg = StorageConfig()
    status: Dict[str, Any] = {}
    total_records = 0

    for key, ds in DATASETS.items():
        csv_path = get_latest_csv(key)
        if csv_path and os.path.exists(csv_path):
            mtime = os.path.getmtime(csv_path)
            size = os.path.getsize(csv_path)
            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig")
                rec_count = len(df)
            except Exception:
                rec_count = 0

            total_records += rec_count
            status[key] = {
                "name": ds.name,
                "available": True,
                "filename": os.path.basename(csv_path),
                "record_count": rec_count,
                "size_kb": round(size / 1024, 1),
                "updated_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        else:
            status[key] = {
                "name": ds.name,
                "available": False,
                "filename": None,
                "record_count": 0,
                "size_kb": 0,
                "updated_at": None,
            }

    return {
        "status": "ready",
        "datasets": status,
        "total_records": total_records,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/data/{dataset_key}")
def get_dataset_data(dataset_key: str) -> Dict[str, Any]:
    """Return parsed JSON records for the requested dataset."""
    if dataset_key not in DATASETS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown dataset '{dataset_key}'. Valid: {list(DATASETS.keys())}",
        )

    csv_path = get_latest_csv(dataset_key)
    if not csv_path or not os.path.exists(csv_path):
        raise HTTPException(
            status_code=404,
            detail=f"No CSV file found for '{dataset_key}'. Please trigger ingestion.",
        )

    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df = df.where(pd.notnull(df), None)
        return {
            "dataset_key": dataset_key,
            "name": DATASETS[dataset_key].name,
            "filename": os.path.basename(csv_path),
            "total": len(df),
            "columns": list(df.columns),
            "records": df.to_dict(orient="records"),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read dataset: {exc}",
        ) from exc


@app.get("/api/download/{dataset_key}")
def download_csv(dataset_key: str) -> FileResponse:
    """Download the date-stamped CSV file directly."""
    if dataset_key not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    csv_path = get_latest_csv(dataset_key)
    if not csv_path or not os.path.exists(csv_path):
        raise HTTPException(
            status_code=404, detail=f"No file available for '{dataset_key}'."
        )

    return FileResponse(
        csv_path,
        media_type="text/csv",
        filename=os.path.basename(csv_path),
    )


@app.post("/api/trigger")
def trigger_ingestion() -> Dict[str, Any]:
    """Execute live data ingestion pipeline across all 4 datasets."""
    try:
        pipeline = Pipeline()
        report = pipeline.run()
        return {
            "success": report.failed == 0,
            "total": len(report.results),
            "succeeded": report.succeeded,
            "failed": report.failed,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "results": [
                {
                    "key": r.dataset_key,
                    "name": r.dataset_name,
                    "success": r.success,
                    "records": r.record_count,
                    "filepath": r.filepath,
                    "error": r.error,
                    "duration_seconds": r.duration_seconds,
                }
                for r in report.results
            ],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Ingestion failed: {exc}"
        ) from exc


# ──────────────────────────────────────────────────────────────────────
# Static Files & Dashboard HTML
# ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the single-page application dashboard."""
    index_file = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h2>NSE Dashboard loading... Please ensure index.html exists in web/</h2>"
    )


# Mount static assets (CSS, JS)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the uvicorn development server."""
    import uvicorn
    print(f"\n========================================================")
    print(f"  NSE Market Data Live Dashboard running at:")
    print(f"  http://{host}:{port}")
    print(f"========================================================\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
