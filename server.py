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
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

from pydantic import BaseModel

import music

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
over it: natural spoken sentences, 8-30 words, adds to the on-screen text instead of reading it out).
`importance` sets how long a beat lingers: 3 = key beat (the hook, the biggest number, the payoff; give it room),
2 = normal, 1 = quick connective beat (keep it brisk). Most segments are 2; use 3 for at most a third of them.
Match line length to importance: key beats can carry a longer voiceover, quick beats a short one.
A segment with `length` (seconds) has a length the user fixed: fit its voiceover to about 2.5 spoken words per second."""

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
    importance: Literal[1, 2, 3]  # 1 quick, 2 normal, 3 key beat: scales how long the segment holds
    prop_json: str  # 3D recipe JSON, "" for none, "keep" to leave the current prop unchanged


MUSIC = music.ensure_library()  # renders the original loops on first start (~5 s)
MUSIC_BY_ID = {m["id"]: m for m in MUSIC}
StyleId = Literal["editorial", "pixel", "2d", "3d"]
PaletteId = Literal["paper", "ube", "jeepney", "pop", "night", "arcade", "mono"]  # keep in sync with web/src/video/theme.ts
MusicId = Literal[tuple(MUSIC_BY_ID)]  # type: ignore[valid-type]

DIRECTION_GUIDE = """Visual + sound direction (the `direction` field):
Styles: editorial = paper-magazine collage (explainers, culture, food, history, news);
2d = flat bouncy motion graphics (playful, lifestyle, how-to, kids, upbeat brands);
pixel = retro 8-bit (games, internet culture, nostalgia, tech); 3d = low-poly 3D props (games, products, objects, places).
Palettes: paper (cream, ink, red), ube (purples), jeepney (yellow, blue, red; Filipino street), pop (bright flat colours),
night (dark, moody), arcade (dark retro neon), mono (black and white).
Music library (id: title, mood, bpm):
""" + "\n".join(f"- {m['id']}: {m['title']}, {m['mood']}, {m['bpm']} bpm" for m in MUSIC) + """
Pick the style, palette and track that best fit the topic and tone; list 2 runner-up styles and 2-3 runner-up tracks
you'd also consider (not repeating the pick), and say why in one short line each."""


class Direction(BaseModel):
    style: StyleId
    palette: PaletteId
    style_alternatives: list[StyleId]
    style_why: str
    music: MusicId
    music_alternatives: list[MusicId]
    music_why: str


class Script(BaseModel):
    title: str
    direction: Direction
    scenes: list[Scene]
    note: str  # one short sentence to the user about what you did


def direction_fields(d: Direction, volume: float = 0.5) -> dict:
    """Claude's picks -> plan fields; the runners-up become the recommendations shown in the editor."""
    alts = [x for x in d.style_alternatives if x != d.style][:2]
    malts = [x for x in d.music_alternatives if x != d.music][:3]
    return {"style": d.style, "theme": {"palette": d.palette}, "styleOptions": [d.style, *alts], "styleWhy": d.style_why,
            "music": {**MUSIC_BY_ID[d.music], "volume": volume}, "musicOptions": [d.music, *malts], "musicWhy": d.music_why}


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


def claude_code_bin() -> str | None:
    """The Claude Code CLI: CLAUDE_CODE_BIN, `claude` on PATH, or the copy bundled with the Claude desktop app."""
    found = os.environ.get("CLAUDE_CODE_BIN") or shutil.which("claude")
    if found:
        return found
    bundled = sorted(Path(os.environ.get("LOCALAPPDATA", "")).glob("Claude-Data/*/claude-code/*/*/claude.exe"),
                     key=lambda p: p.stat().st_mtime)
    return str(bundled[-1]) if bundled else None


_cli_ok: tuple[float, bool] = (0.0, False)


def backend() -> str | None:
    """'api' (ANTHROPIC_API_KEY), 'cli' (signed-in Claude Code), or None for demo mode."""
    global _cli_ok
    load_env()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    if time.time() - _cli_ok[0] > 60:  # `auth status` takes ~1 s; re-check at most once a minute
        b = claude_code_bin()
        ok = False
        if b:
            try:
                r = subprocess.run([b, "auth", "status"], capture_output=True, text=True, timeout=30)
                ok = json.loads(r.stdout or "{}").get("loggedIn") is True
            except Exception as e:
                print("claude code check failed:", repr(e)[:200])
        _cli_ok = (time.time(), ok)
    return "cli" if _cli_ok[1] else None


def ask_cli(prompt: str, schema, research: bool):
    """Same prompt and schema as the API path, answered by headless Claude Code on the user's own sign-in.
    Runs in an empty temp folder with no tools except web research, so it can't touch this project."""
    args = [claude_code_bin(), "-p", "--output-format", "json", "--no-session-persistence",
            "--json-schema", json.dumps(schema.model_json_schema())]
    args += ["--allowed-tools", "WebSearch", "WebFetch"] if research else ["--disallowed-tools", "WebSearch", "WebFetch"]
    if research:
        prompt += "\n\nFirst use web search to find current, concrete facts and numbers on the topic, then answer."
    with tempfile.TemporaryDirectory() as tmp:  # prompt goes on stdin: 3D prompts exceed Windows' command-line limit
        r = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=tmp)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Claude Code failed: {(r.stderr or r.stdout)[:300]}")
    if d.get("is_error"):
        raise RuntimeError(f"Claude Code: {d.get('result')}")
    out = d.get("structured_output")
    return schema.model_validate(out) if out is not None else schema.model_validate_json(d.get("result", ""))


def ask(prompt: str, schema, research: bool = False):
    if backend() == "cli":
        return ask_cli(prompt, schema, research)
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
        c = {k: s.get(k) for k in ("kind", "headline", "sub", "value", "transition", "effects", "asset", "purpose", "voiceover", "importance", "length")}
        if s.get("prop"):
            c["prop"] = json.dumps(s["prop"]) if i == full_prop_index else f"<3D prop '{s['prop'].get('name')}'; return \"keep\" to keep it>"
        scenes.append(c)
    current = {"style": plan.get("style"), "palette": (plan.get("theme") or {}).get("palette"), "music": (plan.get("music") or {}).get("id")}
    return json.dumps({"title": plan["title"], "direction": current, "scenes": scenes}, ensure_ascii=False)


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


def prop_text(style: str) -> str:
    return PROP_GUIDE if style == "3d" else "Set `prop_json` to \"\" everywhere (not the 3D style)."


def style_text(style: str) -> str:
    if style == "auto":
        return f"{DIRECTION_GUIDE}\nChoose the style yourself.\n{PROP_GUIDE}\nWrite prop_json ONLY if you choose the 3d style; otherwise set it to \"\" everywhere."
    fixed = f"{DIRECTION_GUIDE}\nThe user chose the {style} style: set direction.style to \"{style}\" (still pick palette and music)."
    return f"{fixed}\n{PROP_GUIDE}" if style == "3d" else f"{fixed}\nSet `prop_json` to \"\" everywhere (not the 3D style)."


def load_env() -> None:
    """Read KEY=value lines from .env (git-ignored) on each request, so adding the API key needs no restart."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def create(body: dict) -> dict:
    topic = body.get("topic", "").strip()
    if not topic:
        raise ValueError("Describe what the video is about")
    meta = {"style": body.get("style", "auto"), "pace": body.get("pace", "punchy"), "aspect": body.get("aspect", "9:16")}
    mode = backend()
    if not mode:
        sample = find_sample(topic)
        if sample:  # the sample brings its own style and music; the user's chosen format still applies
            return {**meta, **sample, "aspect": meta["aspect"], "research": ""}
        style = "editorial" if meta["style"] == "auto" else meta["style"]
        return {**demo_plan(topic, body.get("assets", []), style), **meta, "style": style, **demo_direction(style), "research": ""}
    notes = research(topic) if mode == "api" else ""  # the CLI path researches with Claude Code's own web search
    fmt = "vertical short-form reel" if meta["aspect"] in ("9:16", "4:5") else "horizontal video"
    look = "a visual style you choose (see direction below)" if meta["style"] == "auto" else f"the {meta['style']} visual style"
    s = ask(f"""Plan a {meta['pace']}-paced {fmt} ({meta['aspect']}, 6-8 segments) in {look}.
Topic / brief: {topic}

Research notes (may be empty; prefer concrete facts and numbers from here):
{notes or '(none)'}

{EDITING_GUIDE}
{bucket_text(body.get('assets', []))}
{style_text(meta['style'])}
Hook in the first segment, payoff in the last. Headlines short and punchy. No hashtags, no emojis.""", Script, research=True)
    d = s.direction
    if meta["style"] != "auto":  # respect a style the user picked even if the model drifted
        d = d.model_copy(update={"style": meta["style"]})
    return {"title": s.title, **meta, **direction_fields(d), "scenes": [to_scene(x) for x in s.scenes],
            "research": notes, "note": f"{s.note} Style: {d.style} ({d.style_why}) Music: {MUSIC_BY_ID[d.music]['title']} ({d.music_why})"}


def edit(body: dict) -> dict:
    plan, i, instr = body["plan"], body.get("index"), body.get("instruction", "").strip()
    if not instr:
        raise ValueError("Type what to change")
    if not backend():
        return demo_edit(plan, i, instr)
    common = f"{EDITING_GUIDE}\n{bucket_text(body.get('assets', []))}\n{prop_text(plan.get('style', 'editorial'))}"
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

{EDITING_GUIDE}
{bucket_text(body.get('assets', []))}
{DIRECTION_GUIDE}
{PROP_GUIDE}
Write prop_json only if direction.style is 3d (otherwise "").

Apply this instruction to the video: "{instr}"
Leave segments the instruction doesn't concern exactly as they are (prop_json "keep" for unchanged props).
Keep the current direction (style, palette, music) unless the instruction asks to change the look or the music.
Add, remove or reorder segments only if asked.""", Script)
    # Match returned segments to old ones by position so ids/audio survive; new segments get new ids.
    old = plan["scenes"]
    scenes = [to_scene(x, old[k] if k < len(old) and len(s.scenes) == len(old) else None) for k, x in enumerate(s.scenes)]
    vol = (plan.get("music") or {}).get("volume", 0.5)
    return {"plan": {**plan, **direction_fields(s.direction, vol), "title": s.title, "scenes": scenes}, "note": s.note}


SAMPLES = ROOT / "samples"


def find_sample(topic: str) -> dict | None:
    """Handmade sample videos for demo mode (samples/*.json), matched by keyword. Props come from `prop_file`."""
    t = topic.lower()
    for f in sorted(SAMPLES.glob("*.json")):
        if f.name.endswith(".prop.json"):
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        if not any(k in t for k in s.get("keywords", [])):
            continue
        scenes = []
        for sc in s["scenes"]:
            sc = dict(sc)
            pf = sc.pop("prop_file", None)
            prop = json.loads((SAMPLES / pf).resolve().read_text(encoding="utf-8")) if pf else None
            scenes.append({"asset": "", "audio": None, "words": [], **sc, "prop": prop})
        return {**{k: v for k, v in s.items() if k != "keywords"}, **demo_direction(s["style"], s.get("music")), "scenes": scenes,
                "note": f"Demo mode: loaded the handmade “{s['title']}” sample. Hit “Voice all segments” for narration + captions."}
    return None


STYLE_MUSIC = {"editorial": ("gentle-doc", "newsroom", "lofi-merienda"), "2d": ("sunny-pop", "tropical-ride", "lofi-merienda"),
               "pixel": ("pixel-quest", "sunny-pop", "tension"), "3d": ("epic-rise", "pixel-quest", "sunny-pop")}


def demo_direction(style: str, track: str | None = None) -> dict:
    """Music + recommendations without AI: a track that suits the style, the other style-fitting tracks as options."""
    opts = list(STYLE_MUSIC.get(style, STYLE_MUSIC["editorial"]))
    if track:
        opts = [track, *[o for o in opts if o != track]]
    return {"music": {**MUSIC_BY_ID[opts[0]], "volume": 0.5}, "musicOptions": opts, "musicWhy": "Matched to the style (demo mode).",
            "styleOptions": [style, *[x for x in ("editorial", "2d", "3d") if x != style][:2]], "styleWhy": "Demo mode."}


def demo_plan(topic: str, assets: list, style: str) -> dict:
    """No API key: placeholder content so the UI, renderer and voice pipeline still work (3D gets the example prop)."""
    rows = [("title", "cut", []), ("fact", "whip", ["highlight"]), ("stat", "zoom", ["shake"]),
            ("fact", "slide", ["typewriter"]), ("quote", "whip", ["vignette"]), ("outro", "flash", ["punch"])]
    pics = iter(a["url"] for a in assets)
    return {"title": topic, "note": "Demo mode: add ANTHROPIC_API_KEY to .env, or sign in to Claude Code (claude auth login), for real content.", "scenes": [
        {"id": uuid.uuid4().hex[:8], "kind": k, "headline": f"{k} about {topic}"[:48], "sub": "Placeholder text, demo mode",
         "value": "42%" if k == "stat" else "", "transition": t, "effects": fx,
         "asset": next(pics, "") if k == "fact" else "",
         "prop": json.loads(EXAMPLE_PROP) if style == "3d" and k in ("title", "outro") else None,
         "purpose": f"Demo {k} beat", "importance": 3 if k in ("title", "stat", "outro") else 2, "voiceover": f"This is the {k} segment of a video about {topic}.",
         "audio": None, "words": []} for k, t, fx in rows]}


def demo_edit(plan: dict, i, instr: str) -> dict:
    if i is None:
        return {"plan": plan, "note": "Demo mode: whole-video edits need an API key or a Claude Code sign-in."}
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
        # We know the exact script, so keep Whisper's timings but the script's spelling when the words line up.
        if words and len(words) == len(tts_words):
            return [{**w, "text": t["text"]} for w, t in zip(words, tts_words)], "whisper"
        # ponytail: 'base' mishears Tagalog; trust the TTS timings there. A bigger WHISPER_MODEL would fix this.
        if words and not voice.startswith("fil-"):
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

def save_asset(raw: bytes, mime: str, name: str, source: str = "") -> dict:
    ext = EXT.get(mime.split(";")[0].strip().lower())
    if not ext:
        raise ValueError(f"Unsupported image type: {mime}")
    if len(raw) > MAX_BYTES:
        raise ValueError("Image too large (15 MB max)")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "image"
    fname = f"{slug}-{uuid.uuid4().hex[:6]}.{ext}"
    (ASSETS / fname).write_bytes(raw)
    meta = {"name": name[:60] or "image", "source": source}
    if source:  # where a found image came from, so it can be credited
        (ASSETS / f"{fname}.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"url": f"/assets/{fname}", **meta}


def list_assets() -> list:
    out = []
    for p in sorted(ASSETS.glob("*"), key=lambda p: p.stat().st_mtime):
        if p.suffix[1:] not in EXT.values():
            continue
        side = p.with_name(p.name + ".json")
        meta = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {"name": p.stem.rsplit("-", 1)[0].replace("-", " ")}
        out.append({"url": f"/assets/{p.name}", "source": "", **meta})
    return out


def upload(body: dict) -> dict:
    m = re.match(r"data:([^;,]+);base64,(.*)", body.get("data", ""), re.S)
    if not m:
        raise ValueError("Expected an image data URL")
    return save_asset(base64.b64decode(m.group(2)), m.group(1), Path(body.get("name", "image")).stem)


class ImgFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, str]] = []  # (src, alt); the page's og:image first, alt "cover"
        self.title, self._in_title = "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._in_title = tag == "title"
        if tag == "meta" and a.get("property", a.get("name", "")) in ("og:image", "twitter:image") and a.get("content"):
            self.found.insert(0, (a["content"], "cover"))
        if tag == "img":
            srcset = [c.strip().split(" ")[0] for c in (a.get("srcset") or "").split(",") if c.strip()]
            src = (srcset[-1] if srcset else None) or a.get("data-src") or a.get("src")  # largest srcset candidate first
            if src and not src.startswith("data:"):
                self.found.append((src, a.get("alt") or ""))

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


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


JUNK = re.compile(r"logo|icon|avatar|sprite|badge|placeholder|gravatar|pixel|emoji|spinner|button|banner|advert|/ads?/|1x1")


def find_images(query: str, limit: int = 8) -> list:
    """Topic -> images: ScrapeGraphAI's web search finds relevant pages, then each page's cover image and captioned
    images are ranked by how well their caption/filename matches the query. Saves the best ones to the bucket,
    remembering the page each came from (for credits)."""
    from concurrent.futures import ThreadPoolExecutor

    from scrapegraphai.utils.research_web import search_on_web

    pages = search_on_web(query, max_results=5, timeout=20)
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}

    def candidates(page: str) -> list:
        try:
            html, _ = fetch(page, 2_000_000)
        except Exception as e:
            print("page skip", page, repr(e)[:120])
            return []
        f = ImgFinder()
        f.feed(html.decode("utf-8", "replace"))
        site = urlparse(page).netloc.removeprefix("www.")
        out = []
        for src, alt in f.found[:60]:
            u = urljoin(page, src)
            text = f"{alt} {Path(urlparse(u).path).stem}".lower()
            if urlparse(u).path.lower().endswith((".svg", ".gif")) or JUNK.search(text):
                continue
            cover = alt == "cover"
            score = 2 * sum(w in text for w in words) + (3 if cover else 0)
            if score:
                name = (f.title.split("|")[0].split(" - ")[0].strip() if cover else alt) or query
                out.append((score, u, name, page, site))
        return out

    with ThreadPoolExecutor(8) as ex:  # the venue network is slow; fetch pages and images in parallel
        ranked = sorted((c for cs in ex.map(candidates, pages) for c in cs), key=lambda c: -c[0])
        seen, picks = set(), []
        for c in ranked:
            if c[1] not in seen:
                seen.add(c[1])
                picks.append(c)

        def download(c):
            try:
                raw, mime = fetch(c[1], MAX_BYTES)
                return (c, raw, mime) if len(raw) > 15_000 and mime.split(";")[0] in EXT else None
            except Exception:
                return None

        varied, per_page = [], {}
        for c in picks:
            if per_page.get(c[3], 0) < 2:
                per_page[c[3]] = per_page.get(c[3], 0) + 1
                varied.append(c)
        saved, hashes = [], set()
        for got in ex.map(download, varied[: limit * 2]):  # at most 2 per page, so one site can't fill the bucket
            if not got or len(saved) >= limit:
                continue
            (score, u, name, page, site), raw, mime = got
            h = hashlib.sha1(raw).hexdigest()
            if h in hashes:  # same picture served from two pages
                continue
            hashes.add(h)
            short = " ".join(name.split())
            short = short if len(short) <= 34 else short[:34].rsplit(" ", 1)[0] + "…"
            saved.append(save_asset(raw, mime, f"{short} · {site}", source=page))
    return saved


def find(body: dict) -> list:
    q = body.get("query", "").strip()
    if not q:
        raise ValueError("Type a topic to search images for")
    out = find_images(q, int(body.get("limit", 8)))
    if not out:
        raise ValueError("No good images found for that topic; try different words")
    return out


def delete_asset(body: dict) -> dict:
    p = ASSETS / Path(body.get("url", "")).name  # .name strips any ../ so we stay inside ASSETS
    if p.is_file():
        p.unlink()
    p.with_name(p.name + ".json").unlink(missing_ok=True)
    return {"ok": True}


ROUTES = {"/api/plan": create, "/api/edit": edit, "/api/voice": voice, "/api/assets/upload": upload,
          "/api/assets/scrape": scrape, "/api/assets/find": find, "/api/assets/delete": delete_asset}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/assets":
            return self.reply(list_assets(), 200)
        if self.path == "/api/music":
            return self.reply(MUSIC, 200)
        # Serve the bucket and voiceovers too, so any front end (e.g. a worktree's dev server) can proxy them here.
        for prefix, folder in (("/assets/", ASSETS), ("/media/", MEDIA), ("/music/", music.OUT)):
            if self.path.startswith(prefix):
                p = folder / Path(unquote(urlparse(self.path).path)).name  # .name keeps us inside the folder
                if not p.is_file():
                    return self.send_error(404)
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
        self.send_error(404)

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
