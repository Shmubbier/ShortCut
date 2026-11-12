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


def _terms(text: str) -> list[str]:
    """Lower-case words with a simple plural strip, so 'baskets' matches 'basket'."""
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in re.findall(r"[a-z0-9]+", text.lower())]


def _queries(query: str, cls: str | None):
    """Full phrase, then the head noun alone (the catalogue is a word match). No class-only browsing: too loose."""
    words = _terms(query)
    return [(q, cls) for q in dict.fromkeys([" ".join(words), words[-1]] if words else [])]


def _head(words: list[str]) -> str:
    """Main noun of a title: last word before 'of'/'and'/'with' ('Basket of Humitas' -> basket,
    'Ice Axe and Crampon Set' -> axe), else the last word."""
    cut = next((i for i, w in enumerate(words) if i and w in ("of", "and", "with")), len(words))
    return words[cut - 1]


def _match(row: dict, query: str) -> int:
    """Strict: the title's main noun must BE the query's main noun ('bus' accepts 'Campus Shuttle Bus', rejects
    'Bus Shelter'). With describing words, one must appear in the title or description. Returns a score, 0 = reject."""
    terms = _terms(query)
    title_words = _terms(str(row.get("title") or row.get("name") or ""))
    if not terms or not title_words or _head(title_words) != terms[-1]:
        return 0
    title, desc, rest = set(title_words), set(_terms(str(row.get("description", "")))), set(terms[:-1])
    # 'fruit basket' must not become 'Laundry Basket': a describing word must be in the title or description
    # (search rows carry no description, so `_full` marks rows Polyfork itself counted as matching every word).
    if rest and not rest & (title | desc) and not row.get("_full"):
        return 0
    tris = row.get("triangles") or row.get("triangle_count") or 5000
    extra = len(title - set(terms))  # fewer unrelated title words = closer match
    return 1000 + 300 * len(rest & title) + 100 * len(rest & desc) - 40 * extra - int(tris) // 1000


def resolve(query: str, cls: str | None = None, want: str = "", deadline: float | None = None):
    """Find and cache best free match; each HTTP request is capped at 8s."""
    started = time.monotonic()
    deadline = deadline or started + 20
    cachekey = hashlib.sha256(("v7|" + query + "|" + str(cls) + "|" + want).encode()).hexdigest()
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
        rows = data.get("assets", data.get("results", data.get("items", [])))
        # Relevance-ranked: the first `full` rows matched every word. Only the full-phrase search counts (a one-word
        # head-noun search 'fully' matches everything with that noun).
        full = int(data.get("full_matches") or 0) if q == " ".join(_terms(query)) else 0
        return item, [{**r, "_full": i < full} for i, r in enumerate(rows)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queries) or 1)) as pool:
        futures = [pool.submit(search, x) for x in queries]
        for f in concurrent.futures.as_completed(futures, timeout=max(.1, deadline-time.monotonic())):
            try:
                key, rows = f.result(); rows_by_query[key] = rows
            except Exception:
                pass
    rows = [row for group in rows_by_query.values() for row in group if row.get("free", True)]
    rows = list({r.get("id"): r for r in sorted(rows, key=lambda r: bool(r.get("_full")))}.values())  # dedupe; _full copies sort last so they win
    if not rows:
        return None
    rows = [r for r in rows if _match(r, query)]
    if not rows:
        return None
    rows.sort(key=lambda r: _match(r, query), reverse=True)
    row = rows[0]
    ident = row.get("id") or row.get("slug")
    if not ident:
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
    thumb = glb.with_suffix(".png")
    if not thumb.exists() and str(row.get("thumbnail", "")).startswith("https://"):
        try: thumb.write_bytes(_get(row["thumbnail"], max(.1, min(8, deadline-time.monotonic()))))
        except Exception: pass
    info = {"url": f"/models3d/{filename}", "id": model_id, "title": title, "source": source, "license": license_name,
            "credit": row.get("credit") or row.get("author") or "Polyfork", "triangles": row.get("triangles") or row.get("triangle_count"),
            "thumbnail": f"/models3d/{thumb.name}" if thumb.exists() else None, "remix": variant.get("call") if variant else None, "remix_confidence": variant.get("confidence") if variant else None}
    sidecar.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    cached.write_text(json.dumps(info), encoding="utf-8")
    info["elapsed"] = round(time.monotonic() - started, 2)
    return info


def backfill_thumbnails(store: Path = STORE) -> None:
    """Fetch Polyfork's rendered preview for any stored GLB without a .png (models cached before thumbnails existed)."""
    def fetch(glb: Path):
        side = glb.with_name(glb.name + ".json")
        meta = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        source = str(meta.get("source", ""))
        if not source.startswith(BASE + "/asset/"):
            return
        asset = source.rsplit("/", 1)[-1]  # remixes use their base asset's render
        try:
            glb.with_suffix(".png").write_bytes(_get(f"{BASE}/files/{urllib.parse.quote(asset)}/renders/hero.png"))
        except Exception as e:
            print("thumbnail backfill failed:", glb.name, repr(e)[:100])
    missing = [g for g in store.glob("*.glb") if not g.with_suffix(".png").exists()] if store.exists() else []
    if missing:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(fetch, missing))


if __name__ == "__main__":  # offline self-check of the strict matcher
    m = lambda title, q, full=False: _match({"title": title, "_full": full}, q)
    assert _head(_terms("Basket of Humitas")) == "basket" and _head(_terms("Ice Axe and Crampon Set")) == "axe"
    assert m("City Bus", "bus") and not m("Bus Shelter", "bus")
    assert not m("Laundry Basket", "fruit basket") and m("Basket of Produce", "fruit basket", full=True)
    assert m("Ice Axe and Crampon Set", "ice axe") and not m("Hand Axe", "ice axe")
    assert m("Coffee Cup", "coffee cup") > m("Takeaway Coffee Cup", "coffee cup")
    print("polyfork matcher OK")
