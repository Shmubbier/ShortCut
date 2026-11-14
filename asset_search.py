"""Keyless, failure-tolerant discovery and validated import for media assets."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import mimetypes
import os
import re
import struct
import urllib.parse
import urllib.request

MAX_IMAGE = 20_000_000
MAX_VIDEO = 200_000_000
MAX_MODEL = 80_000_000
UA = "Blockcut/1.0 (asset discovery; contact: demo project)"


def _json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(5_000_000))


def _get(url, cap, total=20.0):
    """Download with a size cap and a hard total-time cap (urlopen's timeout is per read, so a slow trickle never fires it)."""
    import time
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=10) as r:
        chunks, size = [], 0
        while chunk := r.read(256 * 1024):
            chunks.append(chunk); size += len(chunk)
            if size > cap:
                raise ValueError("asset exceeds size limit")
            if time.monotonic() - started > total:
                raise TimeoutError(f"download took over {total:.0f} s")
        return b"".join(chunks), r.headers.get_content_type()


def _candidate(kind, url, preview, title, page, license="", author="", width=None, height=None, duration=None, fmt="", provider="unknown"):
    if not url or not url.startswith("https://"):
        return None
    return {"kind": kind, "url": url, "preview_url": preview or url, "title": str(title or "Untitled")[:180],
            "source_page": page or url, "license": license or "Unknown; check source terms", "author": author or "",
            "width": width, "height": height, "duration": duration, "format": fmt, "provider": provider}


def _commons(q, kind, limit):
    params = {"action":"query", "format":"json", "generator":"search", "gsrsearch":q,
              "gsrnamespace":"6", "gsrlimit":str(limit * 2), "prop":"imageinfo", "iiprop":"url|size|extmetadata",
              "iiurlwidth":"1280"}
    data = _json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    out=[]
    for p in (data.get("query",{}).get("pages",{}) or {}).values():
        info=(p.get("imageinfo") or [{}])[0]; original=info.get("url",""); ext=original.lower().split("?")[0].rsplit(".",1)[-1]
        if (kind == "image" and ext not in ("jpg","jpeg","png","webp")
                or kind == "video" and ext not in ("mp4","webm")
                or kind == "model" and ext != "glb"):
            continue
        m=info.get("extmetadata",{}); val=lambda k: re.sub("<[^>]+>","",(m.get(k) or {}).get("value",""))[:250]
        # Images: fetch Commons' 1280 px thumbnail (~20x smaller than the original, plenty for a video frame).
        url = info.get("thumburl") or original if kind == "image" else original
        c=_candidate(kind, url, info.get("thumburl",original), p.get("title",""), "https://commons.wikimedia.org/wiki/"+urllib.parse.quote(p.get("title","")), val("LicenseShortName"), val("Artist"), info.get("width"), info.get("height"), None, ext, "Wikimedia Commons")
        if c: out.append(c)
    return out


def _openverse(q, kind, limit):
    endpoint = "images" if kind == "image" else "audio" if kind == "video" else None
    if not endpoint: return []
    # Only licences that allow modification (cropping/editing into a video is a derivative: no ND), no mature results.
    # Anonymous Openverse is slow and rate-limited, hence the longer timeout and one request per search (see search()).
    args={"q":q,"page_size":limit*2,"license_type":"modification","mature":"false"}
    data=_json("https://api.openverse.org/v1/"+endpoint+"/?"+urllib.parse.urlencode(args), timeout=14)
    out=[]
    for x in data.get("results",[]):
        u=x.get("url",""); typ=(x.get("filetype") or u.rsplit(".",1)[-1]).lower()
        if kind == "video" and typ not in ("mp4","webm"): continue
        c=_candidate(kind,u,x.get("thumbnail"),x.get("title"),x.get("foreign_landing_url"),x.get("license"),x.get("creator"),x.get("width"),x.get("height"),x.get("duration"),typ,"Openverse")
        if c: out.append(c)
    return out


def _nasa(q, kind, limit):
    if kind not in ("image","video"): return []
    data=_json("https://images-api.nasa.gov/search?"+urllib.parse.urlencode({"q":q,"media_type":"image,video","page_size":limit*2}))
    out=[]
    for x in data.get("collection",{}).get("items",[]):
        d=(x.get("data") or [{}])[0]; links=x.get("links") or []; preview=next((a.get("href") for a in links if a.get("rel")=="preview"),"")
        typ=d.get("media_type"); k="video" if typ=="video" else "image"
        if k!=kind: continue
        if kind=="video":
            try:
                assets=_json(d.get("href","")); u=next((a for a in assets if a.lower().split("?")[0].endswith((".mp4",".webm"))),"")
            except Exception: continue
            preview=u
        else: u=preview
        c=_candidate(kind,u,preview,d.get("title"),"https://images.nasa.gov/details/"+d.get("nasa_id",""),"Public domain","NASA",None,None,None,"mp4" if kind=="video" else "image","NASA")
        if c: out.append(c)
    return out


def _polyfork(q, limit):
    """Free low-poly GLBs from Polyfork (no key), each with a rendered thumbnail for the library."""
    data=_json("https://polyfork.dev/api/assets?"+urllib.parse.urlencode({"q":q,"free":"1","max_triangles":"5000","per_page":limit}))
    return [c for x in data.get("assets",[]) if x.get("free",True) and x.get("id")
            if (c:=_candidate("model","https://polyfork.dev/cdn/"+urllib.parse.quote(x["id"])+".glb",x.get("thumbnail"),x.get("title"),
                              x.get("page") or "https://polyfork.dev/asset/"+x["id"],"Polyfork free asset (see source)","Polyfork",fmt="glb",provider="Polyfork"))]


# Sites whose image results are article preview cards (a title on a blank page), not photos.
CARD_SITES = re.compile(r"grokipedia\.com", re.I)


def flatness(raw: bytes) -> float:
    """Share of the image covered by its single most common (coarse) colour. Text cards and logos on a plain background
    score 0.95+; photos and illustrations stay under ~0.6 (measured on the asset bucket)."""
    import io
    import av
    import numpy as np
    with av.open(io.BytesIO(raw)) as c:
        f = next(c.decode(video=0)).to_ndarray(format="rgb24")
    q = f[::max(1, f.shape[0] // 120), ::max(1, f.shape[1] // 120)].reshape(-1, 3).astype(int) // 16
    return float(np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)[1].max() / len(q))


def _ddg(q, limit):
    try:
        from ddgs import DDGS
        return [c for x in DDGS().images(q,max_results=limit*2) if x.get("image")
                and not CARD_SITES.search(f"{x.get('url','')} {x.get('image','')}")
                if (c:=_candidate("image",x.get("image"),x.get("image"),x.get("title"),x.get("url"),"Unknown; check source terms",x.get("source"),fmt="image",provider="DuckDuckGo"))]
    except Exception as e:
        print("asset search ddg:",repr(e)[:180]); return []


STOP = set("the and for with from about into what why how are was its this that video short reel some most best top facts story "
           "history guide explained explainer love make made".split())


def keywords(q: str) -> list:
    return [w for w in dict.fromkeys(re.findall(r"[a-z0-9]+", q.lower())) if len(w) > 2 and w not in STOP]


def on_topic(cands, q, text=lambda c: f"{c['title']} {urllib.parse.unquote(c['source_page'])}"):
    """Keep candidates whose title/page mention every core word of the topic, best matches first. Core words are the
    keywords that appear in at least half as many candidates as the most common one: "kenny rogers" needs both words,
    "why filipinos love ube" just "ube" (titles say "Philippines", not "Filipinos")."""
    words = keywords(q)
    if not words: return list(cands)
    texts = [text(c).lower() for c in cands]
    df = {w: sum(w in t for t in texts) for w in words}
    top = max(df.values())
    if not top: return []
    core = [w for w in words if df[w] * 2 >= top]
    keep = [(sum(w in t for w in words), c) for c, t in zip(cands, texts) if all(w in t for w in core)]
    return [c for _, c in sorted(keep, key=lambda x: -x[0])]


def search(query, kinds=("image","video","model"), limit=8):
    """Search independent public sources concurrently; return normalized, un-downloaded candidates."""
    q=" ".join(str(query).split())[:160]
    if not q: raise ValueError("Type a topic to search for assets")
    limit=max(1,min(int(limit),20)); variants=[q]  # no single-word / padded variants: they pulled in "Sean Kenny" for "kenny rogers"
    tasks=[]
    for kind in kinds:
        if kind not in ("image","video","model"): continue
        for variant in variants:
            tasks.append((kind,"Wikimedia",lambda v=variant,k=kind:_commons(v,k,limit)))
            if variant==q: tasks.append((kind,"Openverse",lambda v=variant,k=kind:_openverse(v,k,limit)))
            if kind in ("image","video"): tasks.append((kind,"NASA",lambda v=variant,k=kind:_nasa(v,k,limit)))
            if kind=="image": tasks.append((kind,"DuckDuckGo",lambda v=variant:_ddg(v,limit)))
            if kind=="model" and variant==q: tasks.append((kind,"Polyfork",lambda v=variant:_polyfork(v,limit)))
    results=[]
    pool=concurrent.futures.ThreadPoolExecutor(max_workers=12)
    futures={pool.submit(fn):(kind,src) for kind,src,fn in tasks}
    try:
        for f in concurrent.futures.as_completed(futures, timeout=12):  # slow sources are left behind, not waited on
            kind,src=futures[f]
            try:
                rows=f.result(); print(f"asset_search {src} [{kind}]: {len(rows)}", flush=True)
                results.extend(rows)
            except Exception as e: print(f"asset_search {src} [{kind}] failed: {str(e)[:160]}", flush=True)
    except concurrent.futures.TimeoutError:
        print("asset_search: slow sources skipped:", sorted({futures[f][1] for f in futures if not f.done()}), flush=True)
    pool.shutdown(wait=False, cancel_futures=True)
    media=on_topic([c for c in results if c["kind"]!="model"], q)  # Polyfork models keep their own strict matcher
    results=media+[c for c in results if c["kind"]=="model"]
    buckets={}; seen=set()
    for c in results:
        k=(c["kind"],c["url"])
        if k in seen: continue
        seen.add(k); buckets.setdefault((c["kind"],c["provider"]),[]).append(c)
    # Interleave providers so a large Commons catalogue does not crowd all other sources out.
    unique=[]; counts={}
    while True:
        advanced=False
        for (kind,provider),items in buckets.items():
            if items and counts.get(kind,0)<limit:
                unique.append(items.pop(0)); counts[kind]=counts.get(kind,0)+1; advanced=True
        if not advanced: break
    return unique


def fetch(candidate):
    """Fetch and sniff candidate bytes, returning (bytes, mime, extension); caller stores attribution."""
    kind=candidate.get("kind"); url=candidate.get("url","")
    if not url.startswith("https://"): raise ValueError("Only HTTPS asset URLs are allowed")
    cap={"image":MAX_IMAGE,"video":MAX_VIDEO,"model":MAX_MODEL}.get(kind)
    if not cap: raise ValueError("Unsupported asset type")
    raw,mime=_get(url,cap)
    if kind=="image":
        if len(raw)<16 or not (raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"\x89PNG\r\n\x1a\n") or raw[:4]==b"RIFF" and raw[8:12]==b"WEBP"):
            raise ValueError("Downloaded file is not a supported image")
        width=height=0
        if raw.startswith(b"\x89PNG"):
            width,height=struct.unpack(">II",raw[16:24])
        elif raw.startswith(b"RIFF") and raw[12:16]==b"VP8X" and len(raw)>=30:
            width=1+int.from_bytes(raw[24:27],"little"); height=1+int.from_bytes(raw[27:30],"little")
        elif raw.startswith(b"RIFF") and raw[12:16]==b"VP8 " and len(raw)>=30 and raw[23:26]==b"\x9d\x01\x2a":
            width=int.from_bytes(raw[26:28],"little") & 0x3fff; height=int.from_bytes(raw[28:30],"little") & 0x3fff
        elif raw.startswith(b"RIFF") and raw[12:16]==b"VP8L" and len(raw)>=25 and raw[20]==0x2f:
            b1,b2,b3,b4=raw[21:25]; width=1+b1+((b2&0x3f)<<8); height=1+(b2>>6)+(b3<<2)+((b4&0x0f)<<10)
        elif raw.startswith(b"\xff\xd8"):
            i=2
            while i+9<len(raw):
                if raw[i]!=0xff: i+=1; continue
                marker=raw[i+1]; i+=2
                if marker in (0xD8,0xD9) or 0xD0<=marker<=0xD7: continue
                size=int.from_bytes(raw[i:i+2],"big")
                if marker in tuple(range(0xC0,0xC4))+tuple(range(0xC5,0xC8))+tuple(range(0xC9,0xCC))+tuple(range(0xCD,0xD0)):
                    height,width=struct.unpack(">HH",raw[i+3:i+7]); break
                i+=size
        try:
            flat = flatness(raw)
        except Exception:
            flat = 0.0  # undecodable here: leave it to the dimension checks
        if flat > 0.8:
            raise ValueError(f"Looks like a text card or logo, not a photo (flatness {flat:.2f})")
        if not width or not height or width<128 or height<128 or width>20000 or height>20000:
            raise ValueError("Image dimensions are missing or outside supported limits")
        ext={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}.get(mime)
        if not ext: ext={"jpg":"jpg","jpeg":"jpg","png":"png","webp":"webp"}.get(candidate.get("format",""))
    elif kind=="model":
        if len(raw)<20 or raw[:4]!=b"glTF" or struct.unpack("<I",raw[4:8])[0]!=2 or struct.unpack("<I",raw[8:12])[0]!=len(raw): raise ValueError("Invalid GLB v2 file")
        ext="glb"; mime="model/gltf-binary"
    else:
        if not (raw[4:8]==b"ftyp" or raw.startswith(b"\x1aE\xdf\xa3")): raise ValueError("Downloaded file is not MP4/WebM")
        ext="mp4" if raw[4:8]==b"ftyp" else "webm"; mime="video/mp4" if ext=="mp4" else "video/webm"
    if not ext: raise ValueError("Unrecognized asset format")
    return raw,mime,ext
