"""Local Qwen3-TTS (speech.cpp) and Edge TTS adapter for Blockcut."""
from __future__ import annotations

import asyncio
import json
import hashlib
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

_proc: subprocess.Popen | None = None
_proc_model = ""
_BASE = os.environ.get("BLOCKCUT_SPEECH_URL", "http://127.0.0.1:8792").rstrip("/")
_MODEL = os.environ.get("BLOCKCUT_QWEN_MODEL", "qwen3-tts-0.6b")
_WORKTREE_ROOT = Path(__file__).resolve().parent.parent
_SHARED_ROOT = _WORKTREE_ROOT.parent / "ManilaHack"
_EXE = Path(os.environ.get("BLOCKCUT_SPEECH_EXE", _SHARED_ROOT / "tools" / "speechcpp" / "speech.exe"))


def engine_status() -> dict:
    """Report engines the UI can actually use; starts no model as a side effect."""
    exe = str(_EXE) if _EXE.is_file() else shutil.which("speech")
    size = "1.7B" if _MODEL.endswith("1.7b") else "0.6B"
    cache = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "speech.cpp" / "models"
    cached = any(cache.rglob(f"Qwen3-TTS-12Hz-{size}-CustomVoice*.gguf")) if cache.exists() else False
    try:
        req = urllib.request.Request(f"{_BASE}/v1/models")
        data = json.load(urllib.request.urlopen(req, timeout=3))
        models = data.get("data", [])
        qwen_models = [m.get("id", "") for m in models if "qwen3-tts" in m.get("id", "").lower()]
        ready = bool(qwen_models)
        matching = any(_MODEL.rsplit("-", 1)[-1].lower() in model.lower() for model in qwen_models)
        return {"edge": True, "qwen": (bool(exe) and cached) or ready, "qwenReady": ready,
                "qwenModel": _MODEL if matching else (qwen_models[0] if qwen_models else None)}
    except Exception:
        return {"edge": True, "qwen": bool(exe) and cached, "qwenReady": False, "qwenModel": None}


def _ensure_server() -> None:
    global _proc, _proc_model
    status = engine_status()
    if status["qwenReady"] and status["qwenModel"] == _MODEL:
        return
    if _proc is not None and _proc.poll() is None:
        if _proc_model == _MODEL:
            for _ in range(180):
                if engine_status()["qwenReady"]:
                    return
                if _proc.poll() is not None:
                    break
                time.sleep(1)
            raise RuntimeError("speech.cpp did not become ready; check its server log")
        _proc.terminate()
        _proc.wait(timeout=10)
    exe = str(_EXE) if _EXE.is_file() else shutil.which("speech")
    if not exe:
        raise RuntimeError(f"speech.cpp executable not found: {_EXE}")
    device = os.environ.get("BLOCKCUT_QWEN_DEVICE", "")
    if not device:
        try:
            devices = subprocess.run([exe, "devices"], capture_output=True, text=True, timeout=8).stdout
            device = next((line.split()[0] for line in devices.splitlines()
                           if line.startswith("Vulkan") and "NVIDIA" in line), "")
        except Exception:
            pass
    _proc_model = _MODEL
    command = [exe, "serve", _MODEL, "--host", "127.0.0.1", "--port", _BASE.rsplit(":", 1)[-1]]
    if device:
        command.extend(["--device", device])
    _proc = subprocess.Popen(command,
                             cwd=str(_EXE.parent if _EXE.is_file() else Path(exe).parent),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(180):
        if _proc.poll() is not None:
            raise RuntimeError("speech.cpp exited while loading the Qwen model")
        if engine_status()["qwenReady"]:
            return
        time.sleep(1)
    raise RuntimeError("speech.cpp model startup timed out")


async def _edge(text: str, voice: str, path: Path, rate: int) -> list:
    import edge_tts
    words, audio = [], bytearray()
    async for ch in edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary="WordBoundary").stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            start = ch["offset"] / 1e7
            words.append({"text": ch["text"], "start": round(start, 2), "end": round(start + ch["duration"] / 1e7, 2)})
    path.write_bytes(audio)
    return words


def synthesize(text: str, voice: str, style_hint: str = "", rate: int = 0) -> tuple[Path, list]:
    """Synthesize to a cache-compatible media path and return native timings when available."""
    qwen = voice.startswith("qwen:")
    key = hashlib.sha1(f"{voice}|{rate}|{style_hint}|{text}".encode()).hexdigest()[:12]
    if not qwen:
        path = Path(__file__).parent / "web" / "public" / "media" / f"vo-{key}.mp3"
        timing = path.with_suffix(".json")
        if not (path.exists() and timing.exists()):
            for attempt in (1, 2):
                try:
                    timing.write_text(json.dumps(asyncio.run(_edge(text, voice, path, rate))), encoding="utf-8")
                    break
                except Exception:
                    if attempt == 2:
                        raise
        return path, json.loads(timing.read_text(encoding="utf-8"))

    path = Path(__file__).parent / "web" / "public" / "media" / f"vo-{key}.wav"
    if not path.exists():
        _ensure_server()
        payload = {"input": text, "voice": voice.split(":", 1)[1].lower(), "response_format": "wav"}
        if _MODEL.endswith("1.7b") and style_hint:
            payload["instructions"] = style_hint[:200]
        if rate:
            payload["speed"] = max(0.5, min(2.0, 1 + rate / 100))
        req = urllib.request.Request(f"{_BASE}/v1/audio/speech", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            path.write_bytes(urllib.request.urlopen(req, timeout=180).read())
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return path, []


def scribe_words(path: Path) -> list | None:
    """Optional Scribe v2 word alignment; return None on absent key or service failure."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    boundary = "----Blockcut" + hashlib.sha1(os.urandom(16)).hexdigest()
    mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\nscribe_v2\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"timestamps_granularity\"\r\n\r\nword\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=body,
                                 headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        result = json.load(urllib.request.urlopen(req, timeout=60))
        return [{"text": w.get("text", "").strip(), "start": round(w["start"], 2), "end": round(w["end"], 2)}
                for w in result.get("words", []) if w.get("type", "word") == "word" and "start" in w and "end" in w]
    except Exception as e:
        print("Scribe v2 unavailable, using Whisper:", repr(e)[:180])
        return None

