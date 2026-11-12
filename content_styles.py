"""Content styles: what kind of video this is, how the script is written, and how it's cut.

A content style is independent of the visual style (editorial / 2d / pixel / 3d). Presets live here; custom styles
(e.g. extracted from a reference YouTube video by `style_ref.py`) are JSON files in styles/<id>.json with the same shape:

  {id, label, description, video_type, structure, writing, editing: {pace, cuts, transitions, captions, effects},
   visual: {style?, palette?, music?}, segments: [min, max], source?: {url, title}}

`style_brief(id)` turns one into prompt text; `list_styles()` feeds GET /api/styles and the editor's selector.
"""
import json
import re
from pathlib import Path

STYLES_DIR = Path(__file__).parent / "styles"

PRESETS: list[dict] = [
    {"id": "explainer", "label": "Explainer", "description": "Teaches one idea clearly, fact by fact.",
     "video_type": "explainer", "structure": "hook question → 3-5 facts or stats that build on each other → one clear takeaway",
     "writing": "curious and clear, second person, one idea per line, concrete numbers",
     "editing": {"pace": "punchy", "cuts": "steady, 2-4 s per beat", "transitions": "whip and slide, zoom on the big stat",
                 "captions": "on", "effects": "highlight key words, shake only on the biggest number"}, "segments": [6, 8]},
    {"id": "documentary", "label": "Documentary", "description": "Calm narrator, context and history, room to breathe.",
     "video_type": "documentary", "structure": "cold open image → context → turning point → consequences → reflective close",
     "writing": "measured, warm narrator voice, past tense for history, quotes from real people",
     "editing": {"pace": "documentary", "cuts": "long holds, 4-7 s", "transitions": "mostly cuts and slow slides",
                 "captions": "on, plain", "effects": "slow push-in, vignette on emotional beats"}, "segments": [6, 8],
     "visual": {"style": "editorial"}},
    {"id": "story", "label": "Story", "description": "A narrative with a character, a problem and a turn.",
     "video_type": "short story", "structure": "meet the character → what they want → the obstacle → the turn → resolution or twist",
     "writing": "present tense storytelling, a named character, sensory details, dialogue-like lines; facts serve the story",
     "editing": {"pace": "punchy", "cuts": "follow the story beats, faster at the obstacle, a held beat before the twist",
                 "transitions": "cuts within a scene, flash or whip between scenes", "captions": "on",
                 "effects": "typewriter for inner thoughts, punch-in on the turn"}, "segments": [6, 9]},
    {"id": "listicle", "label": "Top-N list", "description": "Countdown of ranked items, one per segment.",
     "video_type": "listicle", "structure": "hook promising the list → items counting down (#5 … #1), each with a stat or fact → #1 payoff",
     "writing": "punchy, numbered headlines ('#3 · …'), one surprising detail per item",
     "editing": {"pace": "punchy", "cuts": "fast, 2-3 s per item", "transitions": "whip between items, zoom on #1",
                 "captions": "on, bold", "effects": "big number per item"}, "segments": [6, 8]},
    {"id": "clip", "label": "Quick clip", "description": "15-25 s viral-style short with one punchline.",
     "video_type": "short clip", "structure": "scroll-stopping hook in the first second → 2-4 rapid beats → punchline or loop back to the hook",
     "writing": "very short lines (≤ 10 words), internet-native tone, one joke or surprise",
     "editing": {"pace": "punchy", "cuts": "very fast, 1-2 s", "transitions": "hard cuts and flash", "captions": "on, large",
                 "effects": "shake and zoom punches"}, "segments": [4, 6]},
    {"id": "tutorial", "label": "How-to", "description": "Step-by-step instructions anyone can follow.",
     "video_type": "tutorial", "structure": "what you'll make or learn → Step 1 … Step N (one action each) → result and one pro tip",
     "writing": "imperative and friendly ('Grate the ube.'), exact quantities and times, no fluff",
     "editing": {"pace": "punchy", "cuts": "one step per segment, hold long enough to read", "transitions": "slide between steps",
                 "captions": "on", "effects": "highlight quantities"}, "segments": [5, 8], "visual": {"style": "2d"}},
    {"id": "showcase", "label": "Showcase", "description": "Hero shots of a product, place or creation; few words, big visuals.",
     "video_type": "showcase", "structure": "dramatic reveal → 3-4 features as benefits → hero shot with name and call to action",
     "writing": "minimal, confident, short benefit lines, no lists of specs",
     "editing": {"pace": "punchy", "cuts": "cinematic holds on the reveal, quicker on features", "transitions": "zoom and flash",
                 "captions": "off or minimal", "effects": "slow push-in on hero shots"}, "segments": [5, 7], "visual": {"style": "3d"}},
    {"id": "news", "label": "News recap", "description": "What happened, why it matters, what's next.",
     "video_type": "news recap", "structure": "headline → what happened (who, what, when) → key numbers → reactions → what's next",
     "writing": "neutral and precise, attributed claims ('according to …'), no speculation",
     "editing": {"pace": "punchy", "cuts": "steady", "transitions": "slides and cuts", "captions": "on",
                 "effects": "highlight names and dates"}, "segments": [5, 7], "visual": {"style": "editorial", "palette": "mono"}},
    {"id": "comedy", "label": "Comedy skit", "description": "Lighthearted take with jokes, still accurate.",
     "video_type": "comedy explainer", "structure": "relatable setup → escalating jokes, each carrying a real fact → callback punchline",
     "writing": "playful, self-aware, Taglish welcome for PH topics, punchlines at the end of lines",
     "editing": {"pace": "punchy", "cuts": "comic timing: a beat of silence before punchlines", "transitions": "hard cuts and zoom punches",
                 "captions": "on, bold", "effects": "shake on punchlines"}, "segments": [5, 8], "visual": {"style": "2d", "palette": "pop"}},
]
PRESET_IDS = [p["id"] for p in PRESETS]


def list_styles() -> list[dict]:
    """Presets first, then custom styles from styles/*.json (newest last). Broken files are skipped, not fatal."""
    out = [dict(p, custom=False) for p in PRESETS]
    if STYLES_DIR.exists():
        for f in sorted(STYLES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
                if s.get("id") and s.get("label"):
                    out.append(dict(s, custom=True))
            except (OSError, ValueError) as e:
                print("skipping style", f.name, e)
    return out


def get_style(style_id: str | None) -> dict | None:
    return next((s for s in list_styles() if s["id"] == style_id), None) if style_id else None


def style_brief(style_id: str | None) -> str:
    """Prompt text for the content style; for 'auto' (or unknown), the list to choose from."""
    s = get_style(style_id)
    if not s:
        rows = "\n".join(f"- {p['id']}: {p['label']}, {p['description']}" for p in PRESETS)
        return ("CONTENT STYLE: choose the one that fits the topic and the user's wording best, and set direction.content_style to its id. "
                "Then follow its structure, writing and editing rules.\n" + rows + "\n" + "\n".join(_rules(p) for p in PRESETS))
    return f"CONTENT STYLE (the user chose it; set direction.content_style to \"{s['id']}\"):\n{_rules(s)}"


def plan_settings(s: dict | None) -> dict:
    """What a content style fixes on the plan itself: pacing and whether word captions show."""
    if not s:
        return {}
    e = s.get("editing", {})
    out = {"pace": e["pace"]} if e.get("pace") in ("punchy", "documentary") else {}
    cap = str(e.get("captions", "")).lower()
    if cap:
        out["captions"] = not re.search(r"^\s*(none|off|minimal|no\b)|\bno (full )?(burned.in )?(subtitles|captions)", cap)
    return out


def delete_style(style_id: str) -> None:
    """Remove a custom style (presets can't be deleted); the id must name a file in styles/."""
    path = STYLES_DIR / f"{style_id}.json"
    if not re.fullmatch(r"[a-z0-9-]+", style_id or "") or not path.is_file():
        raise ValueError("Only your own saved styles can be deleted")
    path.unlink()


def _rules(s: dict) -> str:
    e = s.get("editing", {})
    seg = s.get("segments", [6, 8])
    v = s.get("visual", {})
    return (f"[{s['id']}] {s['label']} ({s.get('video_type', '')}). Structure: {s.get('structure', '')}. Writing: {s.get('writing', '')}. "
            f"Editing pace {e.get('pace', '')}; cuts {e.get('cuts', '')}; transitions {e.get('transitions', '')}; effects {e.get('effects', '')}; captions {e.get('captions', 'on')}. "
            f"Visual look {v.get('style', 'choose to suit the content')}; palette {v.get('palette', 'choose to suit the content')}. "
            f"Use {seg[0]}-{seg[1]} segments." + _measured(s))


def _measured(s: dict) -> str:
    """Measured rhythm of a YouTube reference, so the script's beats match how fast the original cuts."""
    m = s.get("measured") or {}
    if not m.get("median_shot_seconds"):
        return ""
    return (f" Reference rhythm: {m.get('cuts_per_minute', 0)} cuts per minute, median shot {m['median_shot_seconds']} s: "
            + ("keep every segment's on-screen text very short and let visuals carry it." if m["median_shot_seconds"] < 2.5
               else "let segments breathe, fewer words per segment, calm holds."))
