"""Rate limiter service using Firestore token buckets and daily counters.

Implements:
- Per-session jobs/min bucket (cost = number_of_files)
- Per-session files/min bucket (cost = number_of_files)
- Per-session retries/min bucket (cost = 1)
- Per-session daily jobs counter (CET fixed +1)
- Global daily jobs counter (CET fixed +1)
- Optional per-IP backstop bucket

All limits and caps are configured via Settings (see config.py RL_* keys).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from google.cloud import firestore

from ..config import get_settings


@dataclass
class RLHeaders:
    retry_after: int
    limit: int
    remaining: int
    reset_epoch: int

    def to_http(self) -> Dict[str, str]:
        return {
            "Retry-After": str(self.retry_after),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }


class RateLimiterService:
    def __init__(self) -> None:
        self.settings = get_settings()
        # Respect explicit database when provided
        if getattr(self.settings, "FIRESTORE_DATABASE_ID", ""):
            self.client = firestore.Client(
                project=self.settings.GCP_PROJECT or None,
                database=self.settings.FIRESTORE_DATABASE_ID,
            )
        else:
            self.client = firestore.Client()
        self._rl = self.client.collection("rl")
        self._daily = self.client.collection("rl_daily")

    # --- Helpers ---
    def _now(self) -> float:
        return time.time()

    def _now_cet_date_str(self) -> str:
        # CET fixed +1 minute offset, ignoring DST by design
        offset_min = int(self.settings.RL_TZ_OFFSET_MINUTES)
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc + timedelta(minutes=offset_min)
        return now_cet.date().isoformat()

    def _sec_until_cet_midnight(self) -> int:
        offset_min = int(self.settings.RL_TZ_OFFSET_MINUTES)
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc + timedelta(minutes=offset_min)
        tomorrow_cet = (now_cet + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(1, int((tomorrow_cet - now_cet).total_seconds()))

    # --- Token bucket transactional consume ---
    def _consume_tokens(
        self,
        key: str,
        capacity: int,
        refill_per_sec: float,
        cost: int,
    ) -> Tuple[bool, RLHeaders]:
        if cost <= 0:
            return True, RLHeaders(0, capacity, capacity, int(self._now()))

        doc = self._rl.document(key)
        now = self._now()

        @firestore.transactional
        def txn(tx: firestore.Transaction) -> Tuple[bool, RLHeaders]:
            snap = doc.get(transaction=tx)
            data = snap.to_dict() or {}
            tokens = float(data.get("tokens", float(capacity)))
            updated_at = float(data.get("updatedAt", now))
            elapsed = max(0.0, now - updated_at)
            # accrue
            tokens = min(float(capacity), tokens + elapsed * float(refill_per_sec))
            if tokens + 1e-9 >= float(cost):
                tokens_after = tokens - float(cost)
                tx.set(
                    doc,
                    {"tokens": tokens_after, "updatedAt": now, "capacity": int(capacity), "refillPerSec": float(refill_per_sec)},
                    merge=True,
                )
                # Remaining rounded down for header semantics
                remaining = int(math.floor(tokens_after))
                reset_s = int(now + math.ceil((float(capacity) - tokens_after) / float(refill_per_sec))) if refill_per_sec > 0 else int(now)
                return True, RLHeaders(0, int(capacity), remaining, reset_s)
            else:
                need = float(cost) - tokens
                retry_after = int(math.ceil(need / float(refill_per_sec))) if refill_per_sec > 0 else 60
                remaining = int(max(0.0, math.floor(tokens)))
                reset_s = int(now + math.ceil((float(capacity) - tokens) / float(refill_per_sec))) if refill_per_sec > 0 else int(now)
                return False, RLHeaders(retry_after, int(capacity), remaining, reset_s)

        tx = self.client.transaction()
        return txn(tx)

    # --- Daily counters (CET fixed +1) ---
    def _increment_daily(self, key: str, limit: int, cost: int) -> Tuple[bool, RLHeaders]:
        date_key = self._now_cet_date_str()
        doc = self._daily.document(f"{key}:{date_key}")
        now_epoch = int(self._now())
        ttl = self._sec_until_cet_midnight()

        @firestore.transactional
        def txn(tx: firestore.Transaction) -> Tuple[bool, RLHeaders]:
            snap = doc.get(transaction=tx)
            data = snap.to_dict() or {}
            used = int(data.get("used", 0))
            new_used = used + int(cost)
            if new_used > int(limit):
                # Deny; include retry after until next CET midnight
                headers = RLHeaders(retry_after=ttl, limit=int(limit), remaining=max(0, int(limit) - used), reset_epoch=now_epoch + ttl)
                return False, headers
            tx.set(doc, {"used": new_used, "limit": int(limit), "updatedAt": now_epoch}, merge=True)
            remaining = int(limit) - new_used
            headers = RLHeaders(retry_after=0, limit=int(limit), remaining=max(0, remaining), reset_epoch=now_epoch + ttl)
            return True, headers

        tx = self.client.transaction()
        return txn(tx)

    # --- Public enforcement methods ---
    def enforce_upload(self, session_id: str, files_count: int, client_ip: Optional[str] = None) -> None:
        if not self.settings.RL_ENABLED:
            return
        files_count = max(1, int(files_count))

        # Per-session jobs/min (authoritative)
        ok, hdr = self._consume_tokens(
            key=f"sess:{session_id}:jobs_per_min",
            capacity=self.settings.RL_JOBS_PER_MIN_CAP,
            refill_per_sec=float(self.settings.RL_JOBS_PER_MIN_CAP) / 60.0,
            cost=files_count,
        )
        if not ok:
            raise HTTPException(status_code=429, detail=f"Rate limit: max {self.settings.RL_JOBS_PER_MIN_CAP} jobs/min per session", headers=hdr.to_http())

        # Per-session files/min (secondary burst control)
        ok, hdr = self._consume_tokens(
            key=f"sess:{session_id}:files_per_min",
            capacity=self.settings.RL_FILES_PER_MIN_CAP,
            refill_per_sec=float(self.settings.RL_FILES_PER_MIN_CAP) / 60.0,
            cost=files_count,
        )
        if not ok:
            raise HTTPException(status_code=429, detail=f"Rate limit: max {self.settings.RL_FILES_PER_MIN_CAP} files/min per session", headers=hdr.to_http())

        # Per-IP backstop (optional)
        if self.settings.RL_USE_IP_FALLBACK and client_ip:
            ok, hdr = self._consume_tokens(
                key=f"ip:{client_ip}:jobs_per_min",
                capacity=self.settings.RL_IP_PER_MIN_CAP,
                refill_per_sec=float(self.settings.RL_IP_PER_MIN_CAP) / 60.0,
                cost=files_count,
            )
            if not ok:
                raise HTTPException(status_code=429, detail="Too many requests from your network. Please slow down.", headers=hdr.to_http())

        # Global daily cap first to avoid counting session when global is exceeded
        ok, hdr = self._increment_daily(key="global", limit=self.settings.RL_DAILY_GLOBAL, cost=files_count)
        if not ok:
            raise HTTPException(status_code=429, detail="Service is at today\'s capacity. Please try again tomorrow.", headers=hdr.to_http())

        # Daily per-session cap
        ok, hdr = self._increment_daily(key=f"sess:{session_id}:daily_jobs", limit=self.settings.RL_DAILY_PER_SESSION, cost=files_count)
        if not ok:
            raise HTTPException(status_code=429, detail=f"Daily limit reached ({self.settings.RL_DAILY_PER_SESSION} jobs). Try again tomorrow (CET).", headers=hdr.to_http())

    def enforce_retry(self, session_id: str, client_ip: Optional[str] = None) -> None:
        if not self.settings.RL_ENABLED:
            return
        # Per-session retries/min
        ok, hdr = self._consume_tokens(
            key=f"sess:{session_id}:retries_per_min",
            capacity=self.settings.RL_RETRY_PER_MIN_CAP,
            refill_per_sec=float(self.settings.RL_RETRY_PER_MIN_CAP) / 60.0,
            cost=1,
        )
        if not ok:
            raise HTTPException(status_code=429, detail=f"Retry rate limit: max {self.settings.RL_RETRY_PER_MIN_CAP}/min per session", headers=hdr.to_http())
        # IP backstop (lighter)
        if self.settings.RL_USE_IP_FALLBACK and client_ip:
            ok, hdr = self._consume_tokens(
                key=f"ip:{client_ip}:retries_per_min",
                capacity=max(10, int(self.settings.RL_IP_PER_MIN_CAP / 2)),
                refill_per_sec=max(10.0, float(self.settings.RL_IP_PER_MIN_CAP) / 120.0),
                cost=1,
            )
            if not ok:
                raise HTTPException(status_code=429, detail="Too many retry requests from your network. Please slow down.", headers=hdr.to_http())
