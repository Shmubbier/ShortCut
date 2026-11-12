"""Polyfork catalogue lookup and local GLB cache for generated 3D segments."""
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
STORE = ROOT / "web" / "public" / "models3d"
CACHE = ROOT / ".cache" / "polyfork"
BASE = "https://polyfork.dev"


def _get(url: str, timeout: float = 7.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Blockcut/0.1"})
    with urllib.request.urlopen(req, timeout=min(8, timeout)) as r:
        return r.read()


def _queries(query: str, cls: str | None):
    words = re.findall(r"[\w-]+", query.lower())
    choices = [" ".join(words[:i]) for i in range(min(3, len(words)), 0, -1)]
    inferred = cls or ("vehicle" if any(w in words for w in ("bus", "jeepney", "car", "truck")) else
                       "building" if any(w in words for w in ("windmill", "house", "tower")) else
                       "prop" if any(w in words for w in ("basket", "fruit", "food")) else None)
    return [(q, None) for q in choices] + ([ ("", inferred) ] if inferred else [])


def _score(row: dict, query: str):
    terms = set(re.findall(r"[\w-]+", query.lower()))
    title = str(row.get("title") or row.get("name") or "").lower()
    title_terms = set(re.findall(r"[\w-]+", title))
    description = str(row.get("description", "")).lower()
    desc_terms = set(re.findall(r"[\w-]+", description))
    tris = row.get("triangles") or row.get("triangle_count") or 999999
    normalized_query = " ".join(re.findall(r"[\w-]+", query.lower()))
    return len(terms & title_terms) * 1000 + len(terms & desc_terms) * 100 + (2500 if title.strip() == normalized_query else 0) + (500 if normalized_query and normalized_query in title else 0) - int(tris) / 100000


def resolve(query: str, cls: str | None = None, want: str = "", deadline: float | None = None):
    """Find and cache best free match; each HTTP request is capped at 8s."""
    started = time.monotonic()
    deadline = deadline or started + 20
    cachekey = hashlib.sha256(("v3|" + query + "|" + str(cls) + "|" + want).encode()).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{cachekey}.json"
    if cached.exists():
        try:
            info = json.loads(cached.read_text(encoding="utf-8"))
            if str(info.get("license", "")).startswith("Polyfork free asset"):
                try:
                    detail = json.loads(_get(BASE + f"/api/assets/{urllib.parse.quote(str(info['id']))}"))
                    info["license"] = detail.get("license") or detail.get("licence") or info["license"]
                    info["credit"] = detail.get("credit") or info.get("credit") or "Polyfork"
                    cached.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
            glb = STORE / Path(info["url"]).name
            glb.with_name(glb.name + ".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            return info
        except Exception:
            pass
    queries = _queries(query, cls)
    rows_by_query = {}
    def search(item):
        q, category = item
        args = {"free": "1", "max_triangles": "5000", "per_page": "30"}
        if q: args["q"] = q
        if category: args["class"] = category
        data = json.loads(_get(BASE + "/api/assets?" + urllib.parse.urlencode(args), max(.1, min(8, deadline-time.monotonic()))))
        return item, data.get("assets", data.get("results", data.get("items", [])))
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queries) or 1)) as pool:
        futures = [pool.submit(search, x) for x in queries]
        for f in concurrent.futures.as_completed(futures, timeout=max(.1, deadline-time.monotonic())):
            try:
                key, rows = f.result(); rows_by_query[key] = rows
            except Exception:
                pass
    rows = [row for group in rows_by_query.values() for row in group if row.get("free", True)]
    if not rows:
        return None
    rows.sort(key=lambda r: _score(r, query), reverse=True)
    row = rows[0]
    ident = row.get("id") or row.get("slug")
    if not ident or _score(row, query) < 100:
        return None
    title = row.get("title") or row.get("name") or ident
    source = f"{BASE}/asset/{ident}"
    model_id = ident
    variant = None
    if want and row.get("remixable") and time.monotonic() < deadline:
        try:
            variant = json.loads(_get(BASE + f"/api/assets/{urllib.parse.quote(ident)}/variant?" + urllib.parse.urlencode({"want": want}), max(.1, min(8, deadline-time.monotonic()))))
            if variant.get("confidence") in ("high", "medium"):
                model_id = variant.get("id", ident)
        except Exception:
            pass
    try:
        detail = json.loads(_get(BASE + f"/api/assets/{urllib.parse.quote(str(ident))}", max(.1, min(8, deadline-time.monotonic()))))
        if isinstance(detail, dict): row = {**row, **detail}
    except Exception:
        pass
    STORE.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^a-zA-Z0-9_-]", "-", str(model_id)) + ".glb"
    glb = STORE / filename
    sidecar = glb.with_name(glb.name + ".json")
    if not glb.exists():
        glb_url = (variant or {}).get("glb") if model_id != ident else None
        data = _get(glb_url if isinstance(glb_url, str) and glb_url.startswith("https://") else BASE + f"/cdn/{urllib.parse.quote(str(model_id))}.glb", max(.1, min(8, deadline-time.monotonic())))
        glb.write_bytes(data)
    license_name = row.get("license") or row.get("licence") or "Polyfork free asset (see source)"
    info = {"url": f"/models3d/{filename}", "id": model_id, "title": title, "source": source, "license": license_name,
            "credit": row.get("credit") or row.get("author") or "Polyfork", "triangles": row.get("triangles") or row.get("triangle_count"),
            "remix": variant.get("call") if variant else None, "remix_confidence": variant.get("confidence") if variant else None}
    sidecar.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    cached.write_text(json.dumps(info), encoding="utf-8")
    info["elapsed"] = round(time.monotonic() - started, 2)
    return info
