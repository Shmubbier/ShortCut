"""Background proof/final jobs for the Blender shot library."""
import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "shots" / "library"
JOBS_DIR = ROOT / "web" / "out" / "shot-jobs"
FOOTAGE = ROOT / "web" / "public" / "footage"
RENDERS = ROOT / "web" / "public" / "renders"
ASPECTS = {"9:16", "16:9", "1:1", "4:5"}
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def blender_executable() -> Path:
    configured = os.environ.get("BLOCKCUT_BLENDER")
    candidates = [Path(configured)] if configured else []
    candidates.extend([
        ROOT / "bench3d" / "tools" / "blender-5.3.0-windows-x64" / "blender.exe",
        ROOT.parent.parent / "ManilaHack" / "bench3d" / "tools" / "blender-5.3.0-windows-x64" / "blender.exe",
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Blender 5.3 was not found; set BLOCKCUT_BLENDER to blender.exe")


def _resolve_spec(value, job_dir: Path) -> tuple[Path, dict, str]:
    if isinstance(value, str):
        # A library id or a JSON filename, never a caller-controlled arbitrary path.
        name = Path(value).name
        if not name.endswith(".json"):
            name += ".json"
        if Path(value).name != value or name != value and value.endswith(".json"):
            raise ValueError("spec must be a library shot name or JSON object")
        path = (LIBRARY / name).resolve()
        if not path.is_relative_to(LIBRARY.resolve()) or not path.is_file():
            raise ValueError("shot spec was not found in the scene library")
        data = json.loads(path.read_text(encoding="utf-8"))
        return path, data, path.stem
    if not isinstance(value, dict):
        raise ValueError("spec must be a library shot name or JSON object")
    data = value
    slug = "custom-shot"
    path = job_dir / "spec.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path, data, slug


def _validate_spec(spec: dict, aspect: str):
    if aspect not in ASPECTS:
        raise ValueError("aspect must be 9:16, 16:9, 1:1, or 4:5")
    duration = float(spec.get("duration", 0))
    fps = int(spec.get("fps", 30))
    if duration <= 0 or duration > 60:
        raise ValueError("shot duration must be between 0 and 60 seconds")
    if fps != 30:
        raise ValueError("API shot jobs currently require 30 fps")
    if not spec.get("camera", {}).get("keyframes") or not spec.get("objects"):
        raise ValueError("shot spec needs camera keyframes and at least one object")


def _set_job(job_id: str, **values):
    with LOCK:
        JOBS[job_id].update(values)


def create_shot_job(body: dict) -> dict:
    mode = body.get("mode")
    if mode not in ("proof", "final"):
        raise ValueError("mode must be proof or final")
    aspect = body.get("aspect", "9:16")
    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    spec_path, spec, spec_name = _resolve_spec(body.get("spec"), job_dir)
    _validate_spec(spec, aspect)
    blender = blender_executable()
    public_proof = RENDERS / f"shot-{job_id}-proof.png"
    render_dir = job_dir / "render"
    with LOCK:
        JOBS[job_id] = {"id": job_id, "status": "queued", "stage": "queued", "proof_url": None,
                        "checks": None, "video_url": None, "error": None}

    def run():
        try:
            _set_job(job_id, status="running", stage="proof")
            cmd = [str(blender), "-b", "--factory-startup", "-P", str(ROOT / "shots" / "render_shot.py"),
                   "--", str(spec_path), str(render_dir), "--proof", "--aspect", aspect]
            proof_run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            proof_json = render_dir / "proof.json"
            if proof_run.returncode or not proof_json.is_file():
                raise RuntimeError((proof_run.stderr or proof_run.stdout)[-4000:] or "proof render failed")
            proof = json.loads(proof_json.read_text(encoding="utf-8"))
            checks = {"passed": bool(proof.get("passed")),
                      "pass_count": sum(x.get("status") == "PASS" for x in proof.get("checks", [])),
                      "fail_count": sum(x.get("status") == "FAIL" for x in proof.get("checks", [])),
                      "items": proof.get("checks", [])}
            shutil.copy2(render_dir / "proof.png", public_proof)
            proof_url = f"/renders/{public_proof.name}"
            _set_job(job_id, proof_url=proof_url, checks=checks)
            if not proof.get("passed"):
                _set_job(job_id, status="failed", stage="proof_failed", error="Automatic proof checks failed")
                return
            if mode == "proof":
                _set_job(job_id, status="completed", stage="proof_complete")
                return

            _set_job(job_id, stage="rendering")
            cmd = [str(blender), "-b", "--factory-startup", "-P", str(ROOT / "shots" / "render_shot.py"),
                   "--", str(spec_path), str(render_dir), "--final", "--aspect", aspect]
            final_run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            movie = render_dir / f"{spec_name}.mp4"
            if final_run.returncode or not movie.is_file():
                raise RuntimeError((final_run.stderr or final_run.stdout)[-4000:] or "final render failed")

            _set_job(job_id, stage="saving")
            FOOTAGE.mkdir(parents=True, exist_ok=True)
            target = FOOTAGE / f"shot-{job_id}.mp4"
            shutil.copy2(movie, target)
            _set_job(job_id, status="completed", stage="complete", video_url=f"/footage/{target.name}")
        except Exception as exc:
            _set_job(job_id, status="failed", stage="failed", error=str(exc)[-4000:])

    threading.Thread(target=run, name=f"shot-{job_id}", daemon=True).start()
    with LOCK:
        return dict(JOBS[job_id])


def get_shot_job(job_id: str) -> dict | None:
    with LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job is not None else None
