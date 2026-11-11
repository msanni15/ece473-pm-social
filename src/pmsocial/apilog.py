"""HTTP helper with retries, rate limiting, and an append-only request log.

Every request is recorded in logs/api_requests.jsonl so the validation report
can cite actual response codes and item counts.
"""
import json
import threading
import time
from datetime import datetime, timezone

import requests

from .config import LOGS

_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = "ECE473-research-pipeline/1.0 (academic project)"
_last_call: dict[str, float] = {}


def _log(entry: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with _lock, open(LOGS / "api_requests.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def _throttle(source: str, min_interval: float) -> None:
    with _lock:
        wait = _last_call.get(source, 0) + min_interval - time.monotonic()
        _last_call[source] = max(time.monotonic(), _last_call.get(source, 0) + min_interval)
    if wait > 0:
        time.sleep(wait)


def get(url: str, params: dict | None = None, *, source: str, min_interval: float = 0.0,
        retries: int = 4, timeout: float = 60, count_fn=None, as_json: bool = True):
    """GET with retry/backoff. Returns parsed JSON (or bytes), or None on permanent failure.

    count_fn(payload) -> int gives the logged item count.
    """
    for attempt in range(retries):
        _throttle(source, min_interval)
        status, err, payload = None, None, None
        try:
            r = _session.get(url, params=params, timeout=timeout)
            status = r.status_code
            if status == 200:
                payload = r.json() if as_json else r.content
        except (requests.RequestException, ValueError) as e:
            err = repr(e)[:200]
        n = None
        if payload is not None and count_fn is not None:
            try:
                n = count_fn(payload)
            except Exception:
                n = None
        _log({"ts": datetime.now(timezone.utc).isoformat(), "source": source, "url": url,
              "params": params, "status": status, "n_items": n, "attempt": attempt, "error": err})
        if payload is not None:
            return payload
        if status in (400, 401, 403, 404):
            return None  # not retryable
        time.sleep(min(2 ** attempt * 2, 30))
    return None
