"""Blockcut API: topic -> research (ScrapeGraphAI) -> segmented video plan (Claude); per-segment AI edits;
asset bucket; voiceover (Edge TTS) + word-timed captions (Whisper).

POST /api/plan  {topic, style, pace, aspect, assets}                 -> plan
POST /api/edit  {plan, index: int|null, instruction, assets}        -> {plan, note}  (index = only touch that segment)
POST /api/voice {plan, index: int|null}                             -> {plan}        (voices one segment or all)
GET  /api/assets                  -> [{url, name}]   asset bucket (files in web/public/assets)
POST /api/assets/upload {name, data: dataURL} -> {url, name}
POST /api/assets/scrape {url}     -> [{url, name}]   images pulled from a web page
POST /api/assets/delete {url}
Scene shape: see web/src/video/Video.tsx (SceneData). Run: .venv/Scripts/python server.py  (port 8787; Vite proxies /api)
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import urllib.request
import uuid
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel

ROOT = Path(__file__).parent
ASSETS = ROOT / "web" / "public" / "assets"
MEDIA = ROOT / "web" / "public" / "media"  # generated voiceover audio
for d in (ASSETS, MEDIA):
    d.mkdir(parents=True, exist_ok=True)
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}  # no SVG: it can carry script
MAX_BYTES = 15_000_000
UA = "Mozilla/5.0 (compatible; Blockcut/0.1)"
DEFAULT_VOICE = "en-US-AndrewNeural"

Kind = Literal["title", "fact", "stat", "quote", "outro"]
Transition = Literal["cut", "whip", "zoom", "slide", "flash"]
Effect = Literal["shake", "punch", "invert", "typewriter", "highlight", "vignette"]

EDITING_GUIDE = """Segment kinds: title (hook), fact, stat (big number in `value`), quote (`sub` = who said it), outro (payoff).
Transitions INTO a segment: cut, whip (fast pan), zoom (punch-in), slide (slide up), flash (white flash).
Effects (0-2 per segment): shake (impact camera shake), punch (slow push-in), invert (dark/light swap for contrast),
typewriter (letters type on), highlight (marker swipe under headline), vignette (dark edges, moody).
Edit like a human editor: vary transitions, save shake/flash for the biggest beats, don't repeat the same effect back to back.
Every segment also has `purpose` (one line: what this beat does for the viewer) and `voiceover` (what the narrator says
over it: natural spoken sentences, 8-30 words, adds to the on-screen text instead of reading it out)."""

VOCAB = (ROOT / "bench3d" / "modelgen" / "VOCAB.md").read_text(encoding="utf-8")
EXAMPLE_PROP = (ROOT / "bench3d" / "modelgen" / "props" / "boar_rider.json").read_text(encoding="utf-8")
PROP_GUIDE = f"""3D STYLE: segments can carry a low-poly 3D prop, written as a JSON recipe in `prop_json` (a JSON string).
Give 2-4 segments a prop (the hook, the biggest stat, the payoff); set `prop_json` to "" for the rest.
Keep each prop 25-90 nodes, 5-10 flat colours, resting on y = 0; animate creatures and vehicles with joints + motion.
Props work for any topic: food, gadgets, landmarks, animals, game units, vehicles. For games, films and brands, build an
original prop that evokes the topic (its genre, an archetype, iconic shapes) rather than copying a specific copyrighted
character design or logo.

{VOCAB}

Example recipe (an original boar rider):
{EXAMPLE_PROP}"""


class Scene(BaseModel):
    kind: Kind
    headline: str  # max ~8 words
    sub: str  # supporting line, max ~14 words, "" if none
    value: str  # stat only, e.g. "73%"; "" otherwise
    transition: Transition
    effects: list[Effect]
    asset: str  # an asset url from the bucket, or ""
    purpose: str
    voiceover: str
    prop_json: str  # 3D recipe JSON, "" for none, "keep" to leave the current prop unchanged


class Script(BaseModel):
    title: str
    scenes: list[Scene]
    note: str  # one short sentence to the user about what you did


class SceneEdit(BaseModel):
    scene: Scene
    note: str


# ---------- Claude ----------

def research(topic: str) -> str:
    """Web research via ScrapeGraphAI SearchGraph. Returns "" on any failure so the demo never dies."""
    try:
        from scrapegraphai.graphs import SearchGraph

        graph = SearchGraph(
            prompt=f"List the most surprising facts, concrete statistics (with numbers) and short quotes about: {topic}",
            config={
                "llm": {"model": os.environ.get("SGAI_MODEL", "anthropic/claude-haiku-5-5"),
                        "api_key": os.environ.get("ANTHROPIC_API_KEY")},
                "max_results": 3,
                "headless": True,
            },
        )
        return json.dumps(graph.run(), ensure_ascii=False)[:8000]
    except Exception as e:  # ponytail: research is best-effort; Claude falls back to its own knowledge
        print("research failed:", e)
        return ""


def ask(prompt: str, schema):
    import anthropic

    # Streamed: 3D recipes make long outputs, and a non-streamed request that long can hit HTTP timeouts.
    with anthropic.Anthropic().messages.stream(
        model="claude-opus-5-5",
        max_tokens=64000,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("The plan came out too long; try fewer segments or simpler props")
    return msg.parsed_output


def bucket_text(assets: list) -> str:
    if not assets:
        return "Asset bucket: empty, so set `asset` to \"\" everywhere."
    rows = "\n".join(f"- {a['name']}: {a['url']}" for a in assets)
    return f"""Asset bucket (images shown as cutouts beside the text). Set `asset` to one of these urls exactly,
or "" for a text-only segment. Match images to what the segment says; don't use every image on every segment.
{rows}"""


def context(plan: dict, full_prop_index=None) -> str:
    """Plan as Claude sees it: props are summarised (they're big) except the one being edited."""
    scenes = []
    for i, s in enumerate(plan["scenes"]):
        c = {k: s.get(k) for k in ("kind", "headline", "sub", "value", "transition", "effects", "asset", "purpose", "voiceover")}
        if s.get("prop"):
            c["prop"] = json.dumps(s["prop"]) if i == full_prop_index else f"<3D prop '{s['prop'].get('name')}'; return \"keep\" to keep it>"
        scenes.append(c)
    return json.dumps({"title": plan["title"], "style": plan.get("style"), "scenes": scenes}, ensure_ascii=False)


def to_scene(s: Scene, old: dict | None = None) -> dict:
    """Claude's segment -> stored segment: stable id, parsed prop, and voice audio kept only if the line didn't change."""
    old = old or {}
    d = s.model_dump()
    pj = d.pop("prop_json").strip()
    if pj == "keep":
        d["prop"] = old.get("prop")
    elif pj:
        try:
            d["prop"] = json.loads(pj)
        except json.JSONDecodeError as e:
            d["prop"] = None
            d["purpose"] = f"{d['purpose']} (3D prop was invalid JSON: {e.msg})"
    else:
        d["prop"] = None
    same_line = old.get("voiceover") == d["voiceover"]
    return {"id": old.get("id") or uuid.uuid4().hex[:8], **d,
            "audio": old.get("audio") if same_line else None, "words": old.get("words", []) if same_line else []}


def style_text(style: str) -> str:
    return PROP_GUIDE if style == "3d" else "Set `prop_json` to \"\" everywhere (not the 3D style)."


def create(body: dict) -> dict:
    topic = body.get("topic", "").strip()
    if not topic:
        raise ValueError("Describe what the video is about")
    meta = {"style": body.get("style", "editorial"), "pace": body.get("pace", "punchy"), "aspect": body.get("aspect", "9:16")}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {**demo_plan(topic, body.get("assets", []), meta["style"]), **meta, "research": ""}
    notes = research(topic)
    fmt = "vertical short-form reel" if meta["aspect"] in ("9:16", "4:5") else "horizontal video"
    s = ask(f"""Plan a {meta['pace']}-paced {fmt} ({meta['aspect']}, 6-8 segments) in the {meta['style']} visual style.
Topic / brief: {topic}

Research notes (may be empty; prefer concrete facts and numbers from here):
{notes or '(none)'}

{EDITING_GUIDE}
{bucket_text(body.get('assets', []))}
{style_text(meta['style'])}
Hook in the first segment, payoff in the last. Headlines short and punchy. No hashtags, no emojis.""", Script)
    return {"title": s.title, **meta, "scenes": [to_scene(x) for x in s.scenes], "research": notes, "note": s.note}


def edit(body: dict) -> dict:
    plan, i, instr = body["plan"], body.get("index"), body.get("instruction", "").strip()
    if not instr:
        raise ValueError("Type what to change")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return demo_edit(plan, i, instr)
    common = f"{EDITING_GUIDE}\n{bucket_text(body.get('assets', []))}\n{style_text(plan.get('style', 'editorial'))}"
    if i is not None:
        e = ask(f"""Current video plan (context only):
{context(plan, full_prop_index=i)}

{common}

The user selected segment {i + 1} ({plan['scenes'][i]['kind']}). Apply this instruction to THAT segment only:
"{instr}"
Return the revised segment. Keep every field the instruction doesn't ask to change exactly as it is
(for an unchanged 3D prop, return prop_json "keep").""", SceneEdit)
        scenes = [*plan["scenes"]]
        scenes[i] = to_scene(e.scene, scenes[i])
        return {"plan": {**plan, "scenes": scenes}, "note": e.note}
    s = ask(f"""Current video plan:
{context(plan)}

{common}

Apply this instruction to the video: "{instr}"
Leave segments the instruction doesn't concern exactly as they are (prop_json "keep" for unchanged props).
Add, remove or reorder segments only if asked.""", Script)
    # Match returned segments to old ones by position so ids/audio survive; new segments get new ids.
    old = plan["scenes"]
    scenes = [to_scene(x, old[k] if k < len(old) and len(s.scenes) == len(old) else None) for k, x in enumerate(s.scenes)]
    return {"plan": {**plan, "title": s.title, "scenes": scenes}, "note": s.note}


def demo_plan(topic: str, assets: list, style: str) -> dict:
    """No API key: placeholder content so the UI, renderer and voice pipeline still work (3D gets the example prop)."""
    rows = [("title", "cut", []), ("fact", "whip", ["highlight"]), ("stat", "zoom", ["shake"]),
            ("fact", "slide", ["typewriter"]), ("quote", "whip", ["vignette"]), ("outro", "flash", ["punch"])]
    pics = iter(a["url"] for a in assets)
    return {"title": topic, "note": "Demo mode: set ANTHROPIC_API_KEY for real content.", "scenes": [
        {"id": uuid.uuid4().hex[:8], "kind": k, "headline": f"{k} about {topic}"[:48], "sub": "Placeholder text, demo mode",
         "value": "42%" if k == "stat" else "", "transition": t, "effects": fx,
         "asset": next(pics, "") if k == "fact" else "",
         "prop": json.loads(EXAMPLE_PROP) if style == "3d" and k in ("title", "outro") else None,
         "purpose": f"Demo {k} beat", "voiceover": f"This is the {k} segment of a video about {topic}.",
         "audio": None, "words": []} for k, t, fx in rows]}


def demo_edit(plan: dict, i, instr: str) -> dict:
    if i is None:
        return {"plan": plan, "note": "Demo mode: whole-video edits need ANTHROPIC_API_KEY."}
    scenes = [*plan["scenes"]]
    scenes[i] = {**scenes[i], "headline": instr[:48]}
    return {"plan": {**plan, "scenes": scenes}, "note": f"Demo mode: set segment {i + 1}'s headline to your text."}


# ---------- Voiceover + captions ----------

_whisper = None


def whisper():
    """Whisper model, loaded from the local cache only, so a slow first download never blocks a request.
    Put it in models/faster-whisper-base/ (config.json, tokenizer.json, vocabulary.txt, model.bin from
    huggingface.co/Systran/faster-whisper-base; `curl -L -C - -o model.bin <url>` resumes on slow links)."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        # ponytail: CPU int8 'base' is ~1-2 s per line; set WHISPER_DEVICE=cuda + WHISPER_MODEL=small if cuDNN is installed
        local = ROOT / "models" / "faster-whisper-base"  # fetched with curl; see README note in whisper() docstring
        name = os.environ.get("WHISPER_MODEL") or (str(local) if (local / "model.bin").exists() else "base")
        _whisper = WhisperModel(name, device=os.environ.get("WHISPER_DEVICE", "cpu"), compute_type="int8", local_files_only=True)
    return _whisper


async def _tts(text: str, voice: str, path: Path) -> list:
    import edge_tts

    words, audio = [], bytearray()
    async for ch in edge_tts.Communicate(text, voice, boundary="WordBoundary").stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":  # offsets are in 100 ns ticks
            start = ch["offset"] / 1e7
            words.append({"text": ch["text"], "start": round(start, 2), "end": round(start + ch["duration"] / 1e7, 2)})
    path.write_bytes(audio)
    return words


def speak(text: str, voice: str) -> tuple[str, Path, list]:
    """Edge TTS -> mp3 + its own word timings, cached by (voice, text) so re-voicing unchanged lines is free."""
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:12]
    path, timing = MEDIA / f"vo-{key}.mp3", MEDIA / f"vo-{key}.json"
    if not (path.exists() and timing.exists()):
        for attempt in (1, 2):  # the free Edge voice service drops the odd connection; one retry covers it
            try:
                timing.write_text(json.dumps(asyncio.run(_tts(text, voice, path))))
                break
            except Exception:
                if attempt == 2:
                    raise
    return f"/media/{path.name}", path, json.loads(timing.read_text())


def captions(path: Path, voice: str, tts_words: list) -> tuple[list, str]:
    """Whisper word timestamps; falls back to the TTS engine's own timings if the model isn't available."""
    try:
        segs, _ = whisper().transcribe(str(path), word_timestamps=True, language="tl" if voice.startswith("fil-") else "en")
        words = [{"text": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
                 for seg in segs for w in (seg.words or []) if w.word.strip()]
        if words:
            return words, "whisper"
    except Exception as e:
        print("whisper unavailable, using TTS timings:", repr(e)[:200])
    return tts_words, "tts"


def voice(body: dict) -> dict:
    plan, i = body["plan"], body.get("index")
    v = plan.get("voice") or DEFAULT_VOICE
    scenes = [*plan["scenes"]]
    for k in ([i] if i is not None else range(len(scenes))):
        line = (scenes[k].get("voiceover") or "").strip()
        if not line:
            scenes[k] = {**scenes[k], "audio": None, "words": []}
            continue
        url, path, tts_words = speak(line, v)
        words, source = captions(path, v, tts_words)
        # Edge TTS mp3 is 48 kbit/s CBR, so size gives the exact length without decoding.
        duration = round(path.stat().st_size * 8 / 48_000, 2)
        scenes[k] = {**scenes[k], "audio": {"url": url, "duration": duration}, "words": words, "captionSource": source}
    return {"plan": {**plan, "scenes": scenes}}


# ---------- Asset bucket: files live in web/public/assets so Vite serves them at /assets/<file> ----------

def save_asset(raw: bytes, mime: str, name: str) -> dict:
    ext = EXT.get(mime.split(";")[0].strip().lower())
    if not ext:
        raise ValueError(f"Unsupported image type: {mime}")
    if len(raw) > MAX_BYTES:
        raise ValueError("Image too large (15 MB max)")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "image"
    fname = f"{slug}-{uuid.uuid4().hex[:6]}.{ext}"
    (ASSETS / fname).write_bytes(raw)
    return {"url": f"/assets/{fname}", "name": name[:60] or "image"}


def list_assets() -> list:
    files = sorted(ASSETS.glob("*"), key=lambda p: p.stat().st_mtime)
    return [{"url": f"/assets/{p.name}", "name": p.stem.rsplit("-", 1)[0].replace("-", " ")}
            for p in files if p.suffix[1:] in EXT.values()]


def upload(body: dict) -> dict:
    m = re.match(r"data:([^;,]+);base64,(.*)", body.get("data", ""), re.S)
    if not m:
        raise ValueError("Expected an image data URL")
    return save_asset(base64.b64decode(m.group(2)), m.group(1), Path(body.get("name", "image")).stem)


class ImgFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, str]] = []  # (src, alt)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property", a.get("name", "")) in ("og:image", "twitter:image") and a.get("content"):
            self.found.insert(0, (a["content"], "cover"))
        if tag == "img":
            srcset = [c.strip().split(" ")[0] for c in (a.get("srcset") or "").split(",") if c.strip()]
            src = (srcset[-1] if srcset else None) or a.get("data-src") or a.get("src")  # largest srcset candidate first
            if src and not src.startswith("data:"):
                self.found.append((src, a.get("alt") or ""))


def fetch(url: str, limit: int) -> tuple[bytes, str]:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Only http(s) URLs")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
        return r.read(limit + 1), r.headers.get("Content-Type", "")


def scrape(body: dict) -> list:
    page = body.get("url", "").strip()
    html, _ = fetch(page, 3_000_000)
    finder = ImgFinder()
    finder.feed(html.decode("utf-8", "replace"))
    out, seen = [], set()
    for src, alt in finder.found[:40]:  # ponytail: plain <img>/og:image only; JS-rendered galleries need ScrapeGraphAI/Playwright
        u = urljoin(page, src)
        if u in seen or urlparse(u).path.lower().endswith(".svg"):
            continue
        seen.add(u)
        try:
            raw, mime = fetch(u, MAX_BYTES)
            if len(raw) < 8_000:  # skip icons and tracking pixels
                continue
            out.append(save_asset(raw, mime, alt or Path(urlparse(u).path).stem))
        except Exception as e:
            print("skip", u, e)
        if len(out) >= 12:
            break
    if not out:
        raise ValueError("No usable images found on that page")
    return out


def delete_asset(body: dict) -> dict:
    p = ASSETS / Path(body.get("url", "")).name  # .name strips any ../ so we stay inside ASSETS
    if p.is_file():
        p.unlink()
    return {"ok": True}


ROUTES = {"/api/plan": create, "/api/edit": edit, "/api/voice": voice, "/api/assets/upload": upload,
          "/api/assets/scrape": scrape, "/api/assets/delete": delete_asset}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/assets":
            return self.send_error(404)
        self.reply(list_assets(), 200)

    def do_POST(self):
        fn = ROUTES.get(self.path)
        if not fn:
            return self.send_error(404)
        try:
            out, code = fn(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))), 200
        except Exception as e:
            print(f"{self.path} failed:", repr(e))
            out, code = {"error": str(e)}, 400
        self.reply(out, code)

    def reply(self, out, code):
        data = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print("Blockcut API on http://localhost:8787")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
