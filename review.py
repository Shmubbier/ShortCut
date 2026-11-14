"""Hosted-review gate: reviewer code, expiry, daily cap, brute-force limiter, usage log.

Env is read on every call. Client addresses live in memory only. Secrets are never logged.
"""
import csv
import hmac
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BAD_CODE = "That code isn't valid or has expired"
MAX_TRIES, LOCK_SECONDS = 5, 60
_FIELDS = ["time", "name", "action", "topic", "ok", "seconds"]

_lock = threading.Lock()      # guards limiter + cap
_log_lock = threading.Lock()  # guards log file
_fails: dict = {}             # client -> (count, locked_until monotonic)
_cap = {"day": None, "n": 0}
_warned = False


def _reset():
    global _warned
    with _lock:
        _fails.clear()
        _cap.update(day=None, n=0)
    _warned = False


def active() -> bool:
    return bool(os.environ.get("REVIEWER_CODE"))


def hosted() -> bool:
    """Only an explicit flag (set by the Dockerfile) or Railway's own variables. PORT alone is not proof: the laptop may set it."""
    if os.environ.get("REVIEW_HOSTED") == "1":
        return True
    return any(os.environ.get(k) for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"))


def locked_down() -> bool:
    """Hosted without a reviewer code: fail closed (every gated route answers locked)."""
    return hosted() and not active()


def expires_at():
    global _warned
    raw = os.environ.get("REVIEW_EXPIRES_AT", "")
    try:
        d = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if d.tzinfo is not None:
            return d
    except ValueError:
        pass
    if not _warned:
        _warned = True
        print("review: REVIEW_EXPIRES_AT missing, invalid or without timezone; treating as expired")
    return datetime.min.replace(tzinfo=timezone.utc)


def is_open(now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    return active() and now < expires_at()


ADMIN_TAG = "Admin · "


def is_admin_code(code: str) -> bool:
    """The owner's own reviewer code (env ADMIN_REVIEW_CODE): unlocks like the panelists' code, logged as "Admin · <name>",
    and not counted against the daily cap."""
    admin = os.environ.get("ADMIN_REVIEW_CODE", "")
    return bool(admin) and hmac.compare_digest((code or "").encode(), admin.encode())


def guest_label(code: str) -> str:
    """GUEST_REVIEW_CODES="Peter=code1;Other=code2": personal codes whose visits are logged as "Peter · name"."""
    found = ""
    for pair in os.environ.get("GUEST_REVIEW_CODES", "").split(";"):
        label, _, secret = pair.partition("=")
        if label.strip() and secret.strip() and hmac.compare_digest((code or "").encode(), secret.strip().encode()):
            found = label.strip()[:20]
    return found


def check(code: str, name: str, client: str):
    clean = (name or "").strip()
    if not 2 <= len(clean) <= 40:
        return False, "Enter your name (2-40 characters)"
    with _lock:
        count, until = _fails.get(client, (0, 0.0))
        if until > time.monotonic():
            return False, BAD_CODE
        if until:  # lock elapsed
            count = 0
        admin = is_admin_code(code)
        guest = "" if admin else guest_label(code)
        if not admin and "·" in clean:  # code labels ("Admin · ", "Peter · ") can't be typed in by hand
            return False, "Enter your name (2-40 characters)"
        ok = is_open() and (admin or bool(guest) or hmac.compare_digest(
            (code or "").encode(), os.environ.get("REVIEWER_CODE", "").encode()))
        if ok:
            _fails.pop(client, None)
            return True, (ADMIN_TAG + clean if admin else f"{guest} · {clean}" if guest else clean)
        count += 1
        _fails[client] = (count, time.monotonic() + LOCK_SECONDS if count >= MAX_TRIES else 0.0)
    return False, BAD_CODE


def allow_action() -> bool:
    try:
        cap = int(os.environ.get("REVIEW_DAILY_CAP", "80"))
    except ValueError:
        cap = 80
    today = datetime.now(timezone.utc).date()
    with _lock:
        if _cap["day"] != today:
            _cap.update(day=today, n=0)
        if _cap["n"] >= cap:
            return False
        _cap["n"] += 1
        return True


def _log_path() -> Path:
    return Path(os.environ.get("REVIEW_DATA_DIR", "/data")) / "review-log.jsonl"


def log(name, action, topic, ok, seconds) -> None:
    entry = {"time": datetime.now(timezone.utc).isoformat(), "name": name, "action": action,
             "topic": (topic or "")[:120], "ok": bool(ok), "seconds": round(float(seconds), 2)}
    path = _log_path()
    with _log_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def read_log() -> list:
    try:
        lines = _log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for l in reversed(lines):
        try:
            d = json.loads(l)
        except ValueError:  # a truncated or corrupt line must not blank /admin or the CSV
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def log_csv() -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=_FIELDS)
    w.writeheader()
    w.writerows(read_log())
    return out.getvalue()


def _auth_path() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"


def expire_credentials() -> bool:
    """True when a sign-in file was removed. Never touches the ~/.codex default: CODEX_HOME must be set explicitly."""
    if not os.environ.get("CODEX_HOME") or not (active() or hosted()) or is_open():
        return False
    p = _auth_path()
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False


def seed_credentials() -> None:
    p, blob = _auth_path(), os.environ.get("CODEX_AUTH_JSON")
    if is_open() and blob and not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(blob)
