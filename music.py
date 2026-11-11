"""Original, royalty-free background music, synthesised locally (no downloads, no licences to check).

Each track is a 16-bar loop from a small recipe: tempo, key, chord progression, instruments, drum pattern.
`ensure_library()` renders any missing tracks to web/public/music/<id>.wav; LIBRARY is what Claude picks from.
Run directly to (re)render everything:  .venv/Scripts/python music.py
"""
import wave
from pathlib import Path

import numpy as np

SR = 22050
OUT = Path(__file__).parent / "web" / "public" / "music"

LIBRARY = [
    {"id": "sunny-pop", "title": "Sunny Pop", "mood": "upbeat, bright, playful, lifestyle, food, how-to",
     "bpm": 118, "key": 60, "mode": "major", "prog": [0, 4, 5, 3], "pad": "saw", "bass": "sine", "lead": "pluck", "drums": "four"},
    {"id": "lofi-merienda", "title": "Lo-fi Merienda", "mood": "chill, cozy, warm, food, study, slice of life",
     "bpm": 82, "key": 65, "mode": "major", "prog": [1, 4, 0, 5], "sevenths": True, "pad": "keys", "bass": "sine", "lead": None, "drums": "boombap", "swing": 0.18, "vinyl": True},
    {"id": "epic-rise", "title": "Epic Rise", "mood": "cinematic, dramatic, history, sports, records, triumph",
     "bpm": 90, "key": 50, "mode": "minor", "prog": [0, 5, 2, 6], "pad": "strings", "bass": "saw", "lead": None, "drums": "taiko", "build": True},
    {"id": "pixel-quest", "title": "Pixel Quest", "mood": "retro, gaming, chiptune, arcade, fun, nerdy",
     "bpm": 140, "key": 57, "mode": "minor", "prog": [0, 5, 6, 0], "pad": None, "bass": "triangle", "lead": "square", "drums": "chip"},
    {"id": "newsroom", "title": "Newsroom Pulse", "mood": "news, explainer, tech, business, serious, data",
     "bpm": 105, "key": 52, "mode": "minor", "prog": [0, 5, 3, 4], "pad": "soft", "bass": "sine", "lead": "pluck", "drums": "pulse"},
    {"id": "tropical-ride", "title": "Tropical Ride", "mood": "Filipino street life, travel, summer, island, festive, transport",
     "bpm": 100, "key": 55, "mode": "major", "prog": [0, 3, 4, 0], "pad": None, "bass": "sine", "lead": "marimba", "drums": "dembow"},
    {"id": "tension", "title": "Ticking Tension", "mood": "suspense, mystery, problem, crisis, traffic, warning",
     "bpm": 95, "key": 45, "mode": "minor", "prog": [0, 0, 1, 0], "pad": "drone", "bass": "saw", "lead": None, "drums": "tick"},
    {"id": "gentle-doc", "title": "Gentle Documentary", "mood": "calm, documentary, nature, culture, reflective, heritage",
     "bpm": 70, "key": 62, "mode": "major", "prog": [0, 5, 3, 4], "pad": "soft", "bass": None, "lead": "piano", "drums": None},
]

DRUMS = {  # 16 steps per bar: kick / snare / hat
    "four": ("x...x...x...x...", "....x.......x...", "..x...x...x...x."),
    "boombap": ("x.......x.x.....", "....x.......x...", "x.x.x.x.x.x.x.x."),
    "taiko": ("x.......x..x....", "............x...", "................"),
    "chip": ("x...x...x...x...", "....x.......x...", "x.x.x.x.x.x.x.x."),
    "pulse": ("x.......x.......", "........x.......", "..x...x...x...x."),
    "dembow": ("x...x...x...x...", "...x..x....x..x.", "................"),
    "tick": ("x...............", "................", "x.x.x.x.x.x.x.x."),
}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Soft FFT low-pass: tames raw saw/square edges so pads sound warm, not buzzy."""
    f = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(f / (1 + (freqs / cutoff) ** 4), len(x))


def tone(freq: float, dur: float, wave_: str, decay: float = 0.0, attack: float = 0.005) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    ph = freq * t
    w = {"sine": np.sin(2 * np.pi * ph),
         "triangle": 2 * np.abs(2 * (ph % 1) - 1) - 1,
         "square": np.sign(np.sin(2 * np.pi * ph)) * 0.6,
         "saw": 2 * (ph % 1) - 1}[wave_]
    env = np.minimum(1, t / attack) if attack else np.ones_like(t)
    if decay:
        env = env * np.exp(-t / decay)
    rel = min(len(t), int(0.02 * SR))  # tiny release so notes never click
    env[-rel:] *= np.linspace(1, 0, rel)
    return w * env


def voice(kind: str, freq: float, dur: float) -> np.ndarray:
    if kind == "pluck":
        return tone(freq, dur, "saw", decay=0.18) * 0.5 + tone(freq * 2, dur, "sine", decay=0.1) * 0.3
    if kind == "marimba":
        return tone(freq, dur, "sine", decay=0.25) + tone(freq * 4, dur, "sine", decay=0.05) * 0.3
    if kind == "piano":
        return tone(freq, dur, "sine", decay=0.9) * 0.7 + tone(freq * 2, dur, "sine", decay=0.5) * 0.25 + tone(freq * 3, dur, "triangle", decay=0.3) * 0.1
    if kind == "square":
        return tone(freq, dur, "square", decay=0.3)
    if kind == "keys":
        return tone(freq, dur, "sine", decay=1.2, attack=0.01) + tone(freq * 2, dur, "sine", decay=0.6) * 0.2
    return tone(freq, dur, kind)


def drum(kind: str) -> np.ndarray:
    t = np.arange(int(0.35 * SR)) / SR
    rng = np.random.default_rng(len(kind))
    if kind == "kick":
        f = 45 + 80 * np.exp(-t / 0.04)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)
    if kind == "snare":
        n = rng.uniform(-1, 1, len(t))
        return n * np.exp(-t / 0.09) * 0.6 + np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05) * 0.4
    n = rng.uniform(-1, 1, len(t))  # hat: bright noise blip
    return (n - lowpass(n, 6000)) * np.exp(-t / 0.03) * 0.5


def chord(spec: dict, degree: int) -> list[int]:
    scale = SCALES[spec["mode"]]
    notes = [0, 2, 4, 6] if spec.get("sevenths") else [0, 2, 4]
    return [spec["key"] + scale[(degree + n) % 7] + 12 * ((degree + n) // 7) for n in notes]


def render(spec: dict) -> np.ndarray:
    beat = 60 / spec["bpm"]
    bar, step = 4 * beat, beat / 4
    bars = 16
    out = np.zeros(int(bars * bar * SR) + SR)

    def add(sig: np.ndarray, at: float, gain: float):
        i = int(at * SR)
        n = min(len(sig), len(out) - i)
        out[i:i + n] += sig[:n] * gain

    swing = spec.get("swing", 0.0)
    for b in range(bars):
        notes = chord(spec, spec["prog"][b % len(spec["prog"])])
        t0 = b * bar
        lift = (0.55 + 0.45 * b / bars) if spec.get("build") else 1.0  # cinematic tracks swell
        if spec.get("pad"):
            kind = {"saw": "saw", "strings": "saw", "soft": "triangle", "keys": "keys", "drone": "saw"}[spec["pad"]]
            for m in (notes if spec["pad"] != "drone" else notes[:1]):
                for det in (-0.06, 0.06) if kind == "saw" else (0,):  # detuned pair = ensemble width
                    sig = voice(kind, hz(m + det), bar)
                    sig *= np.minimum(1, np.arange(len(sig)) / (0.25 * SR))  # slow pad attack
                    add(lowpass(sig, 1400 if kind == "saw" else 2500), t0, 0.07 * lift)
        if spec.get("bass"):
            root = notes[0] - 12 if notes[0] >= 48 else notes[0]
            for k in range(4 if spec["drums"] else 2):
                add(voice(spec["bass"], hz(root), beat * (1 if spec["drums"] else 2) * 0.95), t0 + k * beat * (1 if spec["drums"] else 2), 0.22 * lift)
        if spec.get("lead"):
            arp = [0, 1, 2, 1, 0, 2, 1, 2]
            for k, idx in enumerate(arp):
                off = (step if k % 2 and swing else 0) * swing
                add(voice(spec["lead"], hz(notes[idx % len(notes)] + 12), beat / 2 * 0.9), t0 + k * beat / 2 + off, 0.12)
        if spec.get("drums"):
            for part, pattern, gain in zip(("kick", "snare", "hat"), DRUMS[spec["drums"]], (0.55, 0.35, 0.18)):
                for s, c in enumerate(pattern):
                    if c == "x":
                        add(drum(part), t0 + s * step + (step * swing if s % 2 else 0), gain * lift)

    out = out[: int(bars * bar * SR)]
    if spec.get("vinyl"):
        rng = np.random.default_rng(7)
        out += lowpass(rng.uniform(-1, 1, len(out)), 3000) * 0.01 + (rng.random(len(out)) > 0.9997) * 0.08
    out = np.tanh(out * 1.4)  # gentle glue + safety limiter
    out /= max(1e-6, np.abs(out).max()) / 0.85
    fade = int(0.01 * SR)  # loop-friendly ends
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def write_wav(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def ensure_library(force: bool = False) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    for spec in LIBRARY:
        p = OUT / f"{spec['id']}.wav"
        if force or not p.exists():
            write_wav(p, render(spec))
    return [{"id": s["id"], "title": s["title"], "mood": s["mood"], "bpm": s["bpm"], "url": f"/music/{s['id']}.wav"} for s in LIBRARY]


if __name__ == "__main__":
    import time

    t = time.time()
    for track in ensure_library(force=True):
        print(track["id"], track["url"])
    print(f"rendered in {time.time() - t:.1f}s")
