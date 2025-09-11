#!/usr/bin/env python3
"""
Collect preprocessing impact metrics from Firestore without modifying the backend.

What it does
- Queries the `jobs` collection by date range or session IDs
- Computes per-job durations from existing stage timestamps
  - ms_uploaded_to_done = done - uploaded
  - ms_processing_to_llm = llm - processing
  - ms_llm_to_done = done - llm
- Extracts preprocess stats (enabled, tableDetected, reduction) and OCR method
- Exports per-job CSV and a small summary CSV grouped by preprocess.enabled

Requirements
- google-cloud-firestore
- A service account or ADC with read access to the Firestore database

Usage examples (PowerShell)
# Auth
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\sa.json"

# By date range (inclusive, local date assumed)
python scripts/collect_preprocess_metrics.py --start 2025-09-01 --end 2025-09-30

# By specific sessions (comma-separated)
python scripts/collect_preprocess_metrics.py --sessions 123,456,789

# Specify GCP project or Firestore database id if needed
python scripts/collect_preprocess_metrics.py --project ai-invoice-scan --database "(default)"
"""
from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from google.cloud import firestore


@dataclass
class JobMetrics:
    job_id: str
    session_id: str
    filename: str
    status: str
    ocr_method: str
    page_count: Optional[int]
    preprocess_enabled: Optional[bool]
    preprocess_reduction: Optional[float]
    preprocess_table: Optional[bool]
    created_at: Optional[datetime]
    uploaded_at: Optional[datetime]
    queued_at: Optional[datetime]
    processing_at: Optional[datetime]
    llm_at: Optional[datetime]
    done_at: Optional[datetime]
    ms_uploaded_to_done: Optional[float]
    ms_processing_to_llm: Optional[float]
    ms_llm_to_done: Optional[float]


def _to_dt(val) -> Optional[datetime]:
    if not val:
        return None
    # Firestore returns google.cloud.firestore_v1._helpers.TimestampWithTZ or datetime
    if isinstance(val, datetime):
        # ensure timezone-aware
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    try:
        # best effort
        return datetime.fromtimestamp(float(val), tz=timezone.utc)
    except Exception:
        return None


def _ms(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() * 1000.0


def fetch_jobs_by_sessions(client: firestore.Client, sessions: List[str]) -> Iterable[Dict]:
    col = client.collection("jobs")
    for sid in sessions:
        q = col.where("sessionId", "==", sid).order_by("createdAt")
        for doc in q.stream():
            yield doc.to_dict()


def fetch_jobs_by_date_range(client: firestore.Client, start: datetime, end: datetime) -> Iterable[Dict]:
    col = client.collection("jobs")
    q = col.where("createdAt", ">=", start).where("createdAt", "<=", end).order_by("createdAt")
    for doc in q.stream():
        yield doc.to_dict()


def compute_metrics(raw: Dict) -> JobMetrics:
    stages = raw.get("stages", {}) or {}
    uploaded = _to_dt(stages.get("uploaded"))
    queued = _to_dt(stages.get("queued"))
    processing = _to_dt(stages.get("processing"))
    llm = _to_dt(stages.get("llm"))
    done = _to_dt(stages.get("done"))
    created = _to_dt(raw.get("createdAt"))

    pre = raw.get("preprocess", {}) or {}
    reduction = pre.get("reduction")
    try:
        reduction = float(reduction) if reduction is not None else None
    except Exception:
        reduction = None

    return JobMetrics(
        job_id=raw.get("jobId", ""),
        session_id=raw.get("sessionId", ""),
        filename=raw.get("filename", ""),
        status=raw.get("status", ""),
        ocr_method=raw.get("ocrMethod", ""),
        page_count=raw.get("pageCount"),
        preprocess_enabled=pre.get("enabled"),
        preprocess_reduction=reduction,
        preprocess_table=pre.get("tableDetected"),
        created_at=created,
        uploaded_at=uploaded,
        queued_at=queued,
        processing_at=processing,
        llm_at=llm,
        done_at=done,
        ms_uploaded_to_done=_ms(uploaded, done),
        ms_processing_to_llm=_ms(processing, llm),
        ms_llm_to_done=_ms(llm, done),
    )


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(p * (len(values) - 1)))))
    return values[k]


def summarize(group: List[JobMetrics]) -> Dict[str, Optional[float]]:
    def _clean(xs):
        return [x for x in xs if x is not None]

    red = _clean([j.preprocess_reduction for j in group])
    u2d = _clean([j.ms_uploaded_to_done for j in group])
    p2l = _clean([j.ms_processing_to_llm for j in group])
    l2d = _clean([j.ms_llm_to_done for j in group])

    def avg(xs: List[float]) -> Optional[float]:
        return sum(xs) / len(xs) if xs else None

    return {
        "count": float(len(group)),
        "avg_reduction": avg(red),
        "p50_reduction": percentile(red, 0.5),
        "p95_reduction": percentile(red, 0.95),
        "avg_uploaded_to_done_ms": avg(u2d),
        "p50_uploaded_to_done_ms": percentile(u2d, 0.5),
        "p95_uploaded_to_done_ms": percentile(u2d, 0.95),
        "avg_processing_to_llm_ms": avg(p2l),
        "avg_llm_to_done_ms": avg(l2d),
    }


def write_csv_jobs(path: Path, rows: List[JobMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "jobId",
            "sessionId",
            "filename",
            "status",
            "ocrMethod",
            "pageCount",
            "preprocess.enabled",
            "preprocess.reduction",
            "preprocess.tableDetected",
            "stages.uploaded",
            "stages.processing",
            "stages.llm",
            "stages.done",
            "ms.uploaded_to_done",
            "ms.processing_to_llm",
            "ms.llm_to_done",
        ])
        for j in rows:
            w.writerow([
                j.job_id,
                j.session_id,
                j.filename,
                j.status,
                j.ocr_method,
                j.page_count if j.page_count is not None else "",
                j.preprocess_enabled if j.preprocess_enabled is not None else "",
                f"{j.preprocess_reduction:.3f}" if j.preprocess_reduction is not None else "",
                j.preprocess_table if j.preprocess_table is not None else "",
                j.uploaded_at.isoformat() if j.uploaded_at else "",
                j.processing_at.isoformat() if j.processing_at else "",
                j.llm_at.isoformat() if j.llm_at else "",
                j.done_at.isoformat() if j.done_at else "",
                f"{j.ms_uploaded_to_done:.0f}" if j.ms_uploaded_to_done is not None else "",
                f"{j.ms_processing_to_llm:.0f}" if j.ms_processing_to_llm is not None else "",
                f"{j.ms_llm_to_done:.0f}" if j.ms_llm_to_done is not None else "",
            ])


def write_csv_summary(path: Path, summary: Dict[str, Dict[str, Optional[float]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # header
        keys = [
            "count",
            "avg_reduction",
            "p50_reduction",
            "p95_reduction",
            "avg_uploaded_to_done_ms",
            "p50_uploaded_to_done_ms",
            "p95_uploaded_to_done_ms",
            "avg_processing_to_llm_ms",
            "avg_llm_to_done_ms",
        ]
        w.writerow(["group"] + keys)
        for group_name, stats in summary.items():
            row = [group_name] + [stats.get(k, "") if stats.get(k) is not None else "" for k in keys]
            w.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect preprocessing impact metrics from Firestore")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--sessions", type=str, help="Comma-separated list of session IDs to include")
    g.add_argument("--start", type=str, help="Start date (YYYY-MM-DD, inclusive)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD, inclusive); required with --start")
    parser.add_argument("--project", type=str, default=os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "")))
    parser.add_argument("--database", type=str, default=os.getenv("FIRESTORE_DATABASE_ID", "(default)"))
    parser.add_argument("--output-dir", type=str, default="analysis")

    args = parser.parse_args()

    if args.start and not args.end:
        parser.error("--end is required when --start is provided")

    client = firestore.Client(project=args.project or None, database=args.database)

    docs: List[Dict] = []
    if args.sessions:
        sessions = [s.strip() for s in args.sessions.split(",") if s.strip()]
        docs = list(fetch_jobs_by_sessions(client, sessions))
    else:
        # Date range: interpret as local date boundaries, convert to UTC
        start_local = datetime.strptime(args.start, "%Y-%m-%d")
        end_local = datetime.strptime(args.end, "%Y-%m-%d")
        # Inclusive end: add 1 day and subtract epsilon
        start = start_local.replace(tzinfo=timezone.utc)
        end = (end_local + timedelta(days=1)).replace(tzinfo=timezone.utc)
        docs = list(fetch_jobs_by_date_range(client, start, end))

    jobs: List[JobMetrics] = [compute_metrics(d) for d in docs if d]

    # Group by preprocess.enabled
    group_yes = [j for j in jobs if j.preprocess_enabled is True]
    group_no = [j for j in jobs if j.preprocess_enabled is False]
    group_unknown = [j for j in jobs if j.preprocess_enabled not in (True, False)]

    summary = {
        "preprocess=true": summarize(group_yes),
        "preprocess=false": summarize(group_no),
        "preprocess=unknown": summarize(group_unknown),
    }

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path(args.output_dir)
    write_csv_jobs(outdir / f"jobs-{ts}.csv", jobs)
    write_csv_summary(outdir / f"summary-{ts}.csv", summary)

    # Print human-friendly summary
    print("Collected jobs:", len(jobs))
    for name, stats in summary.items():
        print(f"\nGroup: {name}")
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
