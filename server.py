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
import threading
import time
import urllib.request
import uuid
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

from pydantic import BaseModel

import content_styles as cstyles
import music

ROOT = Path(__file__).parent
ASSETS = ROOT / "web" / "public" / "assets"
MEDIA = ROOT / "web" / "public" / "media"  # generated voiceover audio
FOOTAGE = ROOT / "web" / "public" / "footage"
RENDERS = ROOT / "web" / "public" / "renders"
for d in (ASSETS, MEDIA, FOOTAGE, RENDERS):
    d.mkdir(parents=True, exist_ok=True)
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}  # no SVG: it can carry script
MAX_BYTES = 15_000_000
MAX_FOOTAGE_BYTES = 200_000_000
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
A segment with `length` (seconds) has a length the user fixed: fit its voiceover to about 2.5 spoken words per second.
`title` is a 2-4 word name for the storyboard card. `role`: title (text/title card), image (built around a picture),
narration (voice-led), broll (short visual bridge), footage (only when the user supplied video clips).
An empty segment (no headline, no voiceover) is one the user inserted: fill it in to fit between its neighbours."""

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
    title: str  # 2-4 word segment name for the storyboard card, e.g. "The hook", "Price shock"
    role: Literal["footage", "image", "narration", "title", "broll"]  # content type; keep in sync with ROLES in Video.tsx
    prop_json: str  # 3D recipe JSON, "" for none, "keep" to leave the current prop unchanged


MUSIC = music.ensure_library()  # renders the original loops on first start (~5 s)
MUSIC_BY_ID = {m["id"]: m for m in MUSIC}
StyleId = Literal["editorial", "pixel", "2d", "3d"]
PaletteId = Literal["paper", "ube", "jeepney", "pop", "night", "arcade", "mono"]  # keep in sync with web/src/video/theme.ts
MusicId = Literal[tuple(MUSIC_BY_ID)]  # type: ignore[valid-type]

DIRECTION_GUIDE = """Visual + sound direction (the `direction` field):
Styles: editorial = paper-magazine collage (explainers, culture, food, history, news);
2d = flat bouncy motion graphics (playful, lifestyle, how-to, kids, upbeat brands);
pixel = retro 8-bit (games, internet culture, nostalgia, tech); 3d = low-poly 3D props built live.
PREFER 3d whenever the topic centres on concrete things that can be modelled: food, products, gadgets, animals, vehicles,
buildings and landmarks, game characters or units, tools. Use editorial or 2d mainly for abstract, data-heavy or people-centred topics.
Palettes: paper (cream, ink, red), ube (purples), jeepney (yellow, blue, red; Filipino street), pop (bright flat colours),
night (dark, moody), arcade (dark retro neon), mono (black and white).
Music library (id: title, mood, bpm):
""" + "\n".join(f"- {m['id']}: {m['title']}, {m['mood']}, {m['bpm']} bpm" for m in MUSIC) + """
Pick the style, palette and track that best fit the topic and tone; list 2 runner-up styles and 2-3 runner-up tracks
you'd also consider (not repeating the pick), and say why in one short line each."""


class Direction(BaseModel):
    content_style: str  # id from content_styles (explainer, story, listicle, clip, tutorial, showcase, news, comedy, documentary or a custom id)
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


class FootageScene(Scene):
    transcript_indices: list[int]


class FootageScript(BaseModel):
    title: str
    direction: Direction
    scenes: list[FootageScene]
    note: str


def direction_fields(d: Direction, volume: float = 0.5) -> dict:
    """Claude's picks -> plan fields; the runners-up become the recommendations shown in the editor."""
    alts = [x for x in d.style_alternatives if x != d.style][:2]
    malts = [x for x in d.music_alternatives if x != d.music][:3]
    content = d.content_style if cstyles.get_style(d.content_style) else "explainer"
    return {"contentStyle": content, "style": d.style, "theme": {"palette": d.palette}, "styleOptions": [d.style, *alts], "styleWhy": d.style_why,
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
        if "limit" in str(d.get("result", "")).lower():  # plan usage limit: stop trying for a while so demo mode answers fast
            global _cli_ok
            _cli_ok = (time.time() + 20 * 60, False)  # backend() re-checks only after this stamp is 60 s old
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
        c = {k: s.get(k) for k in ("kind", "title", "role", "headline", "sub", "value", "transition", "effects", "asset", "purpose", "voiceover", "importance", "length")}
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
    def offline(why: str = "") -> dict:
        sample = find_sample(topic)
        if sample:  # the sample brings its own style and music; the user's chosen format still applies
            out = {**meta, **sample, "aspect": meta["aspect"], "research": ""}
        else:
            style = "editorial" if meta["style"] == "auto" else meta["style"]
            out = {**demo_plan(topic, body.get("assets", []), style), **meta, "style": style, **demo_direction(style), "research": ""}
        return {**out, "note": f"{why} {out['note']}".strip()}

    mode = backend()
    if not mode:
        return offline()
    try:
        return generate(topic, meta, mode, body)
    except Exception as e:  # e.g. Claude Code's usage limit mid-demo: show a sample instead of a dead end
        print("generation failed, falling back offline:", repr(e)[:300])
        return offline(f"AI unavailable ({str(e)[:140]}).")


def generate(topic: str, meta: dict, mode: str, body: dict) -> dict:
    notes = research(topic) if mode == "api" else ""  # the CLI path researches with Claude Code's own web search
    fmt = "vertical short-form reel" if meta["aspect"] in ("9:16", "4:5") else "horizontal video"
    look = "a visual style you choose (see direction below)" if meta["style"] == "auto" else f"the {meta['style']} visual style"
    content = body.get("content") or "auto"
    chosen = cstyles.get_style(content)
    seg = (chosen or {}).get("segments", [6, 8])
    pref = (chosen or {}).get("visual") or {}
    hint = (f"\nThis content style prefers the {pref['style']} visual style" + (f" and the {pref['palette']} palette" if pref.get("palette") else "")
            + " unless the topic clearly needs another.") if pref.get("style") and meta["style"] == "auto" else ""
    s = ask(f"""Plan a {meta['pace']}-paced {fmt} ({meta['aspect']}, {seg[0]}-{seg[1]} segments) in {look}.
Topic / brief: {topic}

{cstyles.style_brief(content)}{hint}

Research notes (may be empty; prefer concrete facts and numbers from here):
{notes or '(none)'}

{EDITING_GUIDE}
{bucket_text(body.get('assets', []))}
{style_text(meta['style'])}
Follow the content style's structure (the hook and payoff take the form it describes). Headlines short. No hashtags, no emojis.""", Script, research=True)
    d = s.direction
    if meta["style"] != "auto":  # respect a style the user picked even if the model drifted
        d = d.model_copy(update={"style": meta["style"]})
    if chosen:
        d = d.model_copy(update={"content_style": chosen["id"]})
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
Keep the current direction (content style, visual style, palette, music) unless the instruction asks to change them
(e.g. "make it a story" changes direction.content_style and rewrites the script to that style).
{cstyles.style_brief(plan.get("contentStyle") or "explainer")}
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


async def _tts(text: str, voice: str, path: Path, rate: int = 0) -> list:
    import edge_tts

    words, audio = [], bytearray()
    async for ch in edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary="WordBoundary").stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":  # offsets are in 100 ns ticks
            start = ch["offset"] / 1e7
            words.append({"text": ch["text"], "start": round(start, 2), "end": round(start + ch["duration"] / 1e7, 2)})
    path.write_bytes(audio)
    return words


def speak(text: str, voice: str, rate: int = 0) -> tuple[str, Path, list]:
    """Edge TTS -> mp3 + its own word timings, cached by (voice, text) so re-voicing unchanged lines is free."""
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()[:12]
    path, timing = MEDIA / f"vo-{key}.mp3", MEDIA / f"vo-{key}.json"
    if not (path.exists() and timing.exists()):
        for attempt in (1, 2):  # the free Edge voice service drops the odd connection; one retry covers it
            try:
                timing.write_text(json.dumps(asyncio.run(_tts(text, voice, path, rate))))
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
    rate = max(-50, min(50, int(plan.get("voiceRate", 0))))
    scenes = [*plan["scenes"]]
    for k in ([i] if i is not None else range(len(scenes))):
        line = (scenes[k].get("voiceover") or "").strip()
        if not line:
            scenes[k] = {**scenes[k], "audio": None, "words": []}
            continue
        url, path, tts_words = speak(line, v, rate)
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


def topic_query(text: str) -> str:
    """A video prompt -> a short search topic. "Yo give me a topic on the epstein files, lighthearted style, dont forget
    images" -> "the epstein files". Style and format instructions don't belong in an image search."""
    t = re.split(r"[,.;:!?\n]|\s-\s", text.lower(), maxsplit=1)[0]
    t = re.sub(r"^\s*(yo|hey|hi|ok|okay|please|pls)\b[\s,]*", "", t)
    t = re.sub(r"^(can you |could you )?(give me|make|create|do|write|generate|explain|show)( me)?( a| an| the)?"
               r"( short| quick| fun| \d+\s*s(ec(ond)?s?)?)*( video| reel| topic| explainer| short| clip| story)?( on| about| for| of)?\s+", "", t)
    t = re.sub(r"^(a |an )?(video|reel|topic|explainer)( on| about| of)\s+", "", t)
    words = t.split()[:10]
    return " ".join(words) if words else text.strip()[:60]


def find_images(query: str, limit: int = 8) -> list:
    """Topic -> images: ScrapeGraphAI's web search finds relevant pages, then each page's cover image and captioned
    images are ranked by how well their caption/filename matches the query. If that search fails or comes up short
    (one flaky backend, e.g. a Wikipedia timeout, used to sink the whole step), DuckDuckGo image search tops it up.
    Saves the best ones to the bucket, remembering the page each came from (for credits)."""
    from concurrent.futures import ThreadPoolExecutor

    from scrapegraphai.utils.research_web import search_on_web

    query = topic_query(query)
    try:
        pages = search_on_web(query, max_results=5, timeout=20)
    except Exception as e:
        print("ScrapeGraphAI search failed, falling back to image search:", repr(e)[:160])
        pages = []
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}

    def image_search() -> list:
        try:
            from ddgs import DDGS

            hits = DDGS().images(query, max_results=limit * 2)
        except Exception as e:
            print("image search failed:", repr(e)[:160])
            return []
        return [(5, h["image"], h.get("title") or query, h.get("url", ""), h.get("source") or urlparse(h.get("url", "")).netloc.removeprefix("www."))
                for h in hits if h.get("image") and not urlparse(h["image"]).path.lower().endswith((".svg", ".gif"))]

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
        if len({c[1] for c in ranked}) < limit:  # ScrapeGraphAI pages came up short (or failed): top up from image search
            ranked += image_search()
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


def footage_path(url: str) -> Path:
    name = Path(unquote(urlparse(url).path)).name
    path = (FOOTAGE / name).resolve()
    if not name or not path.is_relative_to(FOOTAGE.resolve()) or not path.is_file():
        raise ValueError("Footage clip was not found; upload it again")
    return path


def upload_footage(body: dict) -> dict:
    match = re.match(r"data:([^;,]+);base64,(.*)", body.get("data", ""), re.S)
    if not match:
        raise ValueError("Expected a video data URL")
    mime = match.group(1).lower()
    extensions = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov", "video/x-m4v": ".mp4"}
    ext = extensions.get(mime)
    if not ext:
        raise ValueError("Supported video formats: MP4, WebM, MOV")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except Exception as e:
        raise ValueError("Invalid video data") from e
    if not raw or len(raw) > MAX_FOOTAGE_BYTES:
        raise ValueError("Video must be smaller than 200 MB")
    name = Path(body.get("name", "clip")).stem
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "clip"
    path = FOOTAGE / f"{slug}-{uuid.uuid4().hex[:8]}{ext}"
    path.write_bytes(raw)
    try:
        import av

        with av.open(str(path)) as container:
            duration = round(container.duration / 1_000_000, 3) if container.duration else 0
    except Exception as e:
        path.unlink(missing_ok=True)
        raise ValueError(f"Could not read this video file: {e}") from e
    if duration <= 0:
        path.unlink(missing_ok=True)
        raise ValueError("The video has no readable duration")
    return {"url": f"/footage/{path.name}", "name": path.name, "duration": duration}


def transcribe_footage(body: dict) -> dict:
    path = footage_path(body.get("url", ""))
    language = body.get("language")
    segments, _ = whisper().transcribe(str(path), word_timestamps=True, language=language or None, vad_filter=True)
    out = []
    for seg in segments:
        words = [{"text": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
                 for w in (seg.words or []) if w.word.strip()]
        text = seg.text.strip()
        if text:
            out.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text, "words": words})
    return {"segments": out}


def storyboard_footage(body: dict) -> dict:
    url = body.get("url", "")
    path = footage_path(url)
    transcript = body.get("transcript") or []
    if not transcript:
        raise ValueError("Transcribe the clip before building a storyboard")
    if len(transcript) > 1000:
        raise ValueError("Transcript is too long to storyboard in one pass")
    duration = body.get("duration")
    if not duration:
        import av
        with av.open(str(path)) as container:
            duration = container.duration / 1_000_000
    style = body.get("style", "editorial")
    if style not in ("editorial", "2d", "pixel", "3d"):
        style = "editorial"
    rows = [{"index": i, "start": float(x.get("start", 0)), "end": float(x.get("end", 0)), "text": str(x.get("text", ""))[:1200]}
            for i, x in enumerate(transcript)]
    if not backend():
        groups = [rows[round(k * len(rows) / 6):round((k + 1) * len(rows) / 6)] for k in range(6)]
        scenes = []
        for k, group in enumerate(g for g in groups if g):
            indices = [x["index"] for x in group]
            scenes.append({"kind": "title" if k == 0 else "outro" if k == 5 else "fact", "title": f"Clip beat {k + 1}",
                "headline": group[0]["text"][:64], "sub": "", "value": "", "transition": "cut", "effects": [],
                "asset": "", "purpose": "Footage transcript beat", "voiceover": " ".join(x["text"] for x in group),
                "importance": 2, "role": "footage", "transcript_indices": indices, "prop_json": "",
                "prop": json.loads(EXAMPLE_PROP) if style == "3d" and k in (0, len(groups) - 1) else None})
        direction = demo_direction(style)
        note = "Demo mode: built a basic storyboard from the clip transcript."
    else:
        made = ask(f"""Organize this existing video transcript into 4-8 chronological storyboard segments.
Do not invent speech. Each segment must reference the original transcript rows it contains using transcript_indices.
Groups must be contiguous, non-overlapping, in order, and cover all rows. Use the supplied timestamps as clip trim points.
Choose short on-screen headlines and suitable transitions/effects. Set every role to footage. Style is {style}.
Transcript rows (index, start/end seconds, exact text):
{json.dumps(rows, ensure_ascii=False)}
{EDITING_GUIDE}
{style_text(style)}""", FootageScript)
        scenes = [s.model_dump() for s in made.scenes]
        direction = direction_fields(made.direction)
        note = made.note
    scenes_out = []
    transcript_cursor = 0
    for i, scene in enumerate(scenes):
        proposed = sorted(set(int(x) for x in scene.pop("transcript_indices", []) if 0 <= int(x) < len(transcript)))
        fallback = min(transcript_cursor, len(transcript) - 1)
        high = len(transcript) - 1 if i == len(scenes) - 1 else max((x for x in proposed if x >= transcript_cursor), default=fallback)
        indices = list(range(transcript_cursor, min(high, len(transcript) - 1) + 1))
        transcript_cursor = indices[-1] + 1
        rows_used = [transcript[j] for j in indices]
        start = max(0.0, float(rows_used[0].get("start", 0)))
        end = min(float(duration), float(rows_used[-1].get("end", start + 1)))
        if end <= start:
            end = min(float(duration), start + 1)
        words = []
        for row in rows_used:
            for word in row.get("words", []):
                ws, we = float(word.get("start", 0)), float(word.get("end", 0))
                if we >= start and ws <= end:
                    words.append({"text": word.get("text", ""), "start": round(max(0, ws - start), 2), "end": round(max(0, we - start), 2)})
        prop_json = str(scene.pop("prop_json", "")).strip()
        if prop_json and prop_json != "keep":
            try:
                scene["prop"] = json.loads(prop_json)
            except json.JSONDecodeError:
                scene["prop"] = None
        scene.pop("transcript_indices", None)
        scene.update({"id": uuid.uuid4().hex[:8], "role": "footage", "voiceover": " ".join(x.get("text", "").strip() for x in rows_used),
                      "words": words, "audio": None, "length": round(end - start, 3),
                      "media": {"type": "video", "url": f"/footage/{path.name}", "name": path.name,
                                "trimStart": start, "trimEnd": end, "duration": duration}})
        scenes_out.append(scene)
    return {"title": body.get("title") or path.stem, "style": style, "pace": "punchy", "aspect": body.get("aspect", "9:16"),
            "captions": True, **direction, "scenes": scenes_out, "note": note}


RENDER_JOBS: dict[str, dict] = {}
STYLE_JOBS: dict[str, dict] = {}


def create_style_from_url(body: dict) -> dict:
    url = str(body.get("url", "")).strip()
    if not url:
        raise ValueError("A YouTube URL is required")
    jid = uuid.uuid4().hex[:12]
    STYLE_JOBS[jid] = {"status": "queued", "progress": 0, "stage": "queued"}
    def run():
        job = STYLE_JOBS[jid]
        try:
            job.update(status="running", progress=5, stage="reading metadata and captions")
            import style_ref
            style = style_ref.extract(url, ask, lambda pct, stage: job.update(progress=pct, stage=stage))
            job.update(status="done", progress=100, stage="style saved", style=style)
        except Exception as e:
            job.update(status="error", stage="failed", error=str(e)[:500])
    threading.Thread(target=run, daemon=True).start()
    return {"id": jid, **STYLE_JOBS[jid]}


def _absolute_media(plan: dict) -> dict:
    base = "http://127.0.0.1:8787"
    def fix(value):
        if isinstance(value, dict):
            return {k: fix(v) for k, v in value.items()}
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, str) and value.startswith(("/assets/", "/media/", "/music/", "/footage/")):
            return base + value
        return value
    return fix(plan)


def render(body: dict) -> dict:
    plan = body.get("plan")
    if not isinstance(plan, dict) or not plan.get("scenes"):
        raise ValueError("A video plan with at least one segment is required")
    rid = uuid.uuid4().hex[:12]
    props = ROOT / "web" / "out" / f"{rid}.json"
    target = RENDERS / f"{rid}.mp4"
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text(json.dumps(_absolute_media(plan), ensure_ascii=False), encoding="utf-8")
    RENDER_JOBS[rid] = {"status": "queued", "progress": 0, "url": None}
    def run():
        job = RENDER_JOBS[rid]
        try:
            job["status"] = "rendering"
            cli = ROOT / "web" / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
            node = shutil.which("node")
            if not node or not cli.is_file():
                raise RuntimeError("Remotion CLI is not installed; run npm install in web/")
            proc = subprocess.Popen([node, str(cli), "render", "src/video/index.tsx", "Main", str(target),
                                     f"--props={props}", "--gl=angle"], cwd=ROOT / "web", stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            tail = ""
            assert proc.stdout is not None
            for line in proc.stdout:
                tail = (tail + line)[-3000:]
                match = re.search(r"Rendered\s+(\d+)/(\d+)", line)
                if match and int(match.group(2)):
                    job["progress"] = min(99, round(100 * int(match.group(1)) / int(match.group(2))))
            if proc.wait() != 0:
                raise RuntimeError(tail.strip() or "Remotion render failed")
            job.update(status="done", progress=100, url=f"/renders/{target.name}")
        except Exception as e:
            job.update(status="error", error=str(e), progress=0)
        finally:
            props.unlink(missing_ok=True)
    import threading
    threading.Thread(target=run, daemon=True).start()
    return {"id": rid, **RENDER_JOBS[rid]}


ROUTES = {"/api/plan": create, "/api/edit": edit, "/api/voice": voice, "/api/assets/upload": upload,
          "/api/assets/scrape": scrape, "/api/assets/find": find, "/api/assets/delete": delete_asset,
          "/api/footage/upload": upload_footage, "/api/footage/transcribe": transcribe_footage,
          "/api/footage/storyboard": storyboard_footage, "/api/render": render}
ROUTES["/api/styles/from-url"] = create_style_from_url


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/assets":
            return self.reply(list_assets(), 200)
        if self.path == "/api/styles":
            return self.reply(cstyles.list_styles(), 200)
        if self.path.startswith("/api/styles/jobs/"):
            jid = self.path.rsplit("/", 1)[-1]
            return self.reply(STYLE_JOBS.get(jid, {"status": "not_found", "progress": 0}), 200 if jid in STYLE_JOBS else 404)
        if self.path == "/api/music":
            return self.reply(MUSIC, 200)
        if self.path.startswith("/api/render/"):
            rid = self.path.rsplit("/", 1)[-1]
            return self.reply(RENDER_JOBS.get(rid, {"status": "not_found", "progress": 0}), 200 if rid in RENDER_JOBS else 404)
        # Serve the bucket and voiceovers too, so any front end (e.g. a worktree's dev server) can proxy them here.
        for prefix, folder in (("/assets/", ASSETS), ("/media/", MEDIA), ("/music/", music.OUT), ("/footage/", FOOTAGE), ("/renders/", RENDERS)):
            if self.path.startswith(prefix):
                p = folder / Path(unquote(urlparse(self.path).path)).name  # .name keeps us inside the folder
                if not p.is_file():
                    return self.send_error(404)
                size = p.stat().st_size
                start, end, code = 0, size - 1, 200
                requested = self.headers.get("Range", "")
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if match:
                    if not match.group(1):
                        suffix = int(match.group(2) or 0)
                        start = max(0, size - suffix)
                    else:
                        start = int(match.group(1))
                        if match.group(2):
                            end = min(size - 1, int(match.group(2)))
                    if start >= size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    code = 206
                count = end - start + 1
                self.send_response(code)
                self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(count))
                self.send_header("Accept-Ranges", "bytes")
                if code == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                with p.open("rb") as source:
                    source.seek(start)
                    remaining = count
                    while remaining:
                        chunk = source.read(min(64_000, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return
        self.send_error(404)

    def do_POST(self):
        fn = ROUTES.get(self.path)
        if not fn:
            return self.send_error(404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            max_request = MAX_FOOTAGE_BYTES * 4 // 3 + 2_000_000 if self.path == "/api/footage/upload" else 30_000_000
            if length > max_request:
                raise ValueError("Request body is too large")
            out, code = fn(json.loads(self.rfile.read(length))), 200
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
    port = int(os.environ.get("BLOCKCUT_PORT", "8787"))  # parallel agents test on their own port
    print(f"Blockcut API on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
