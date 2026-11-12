"""Deterministic geometric and pixel checks used by render_shot.py in Blender."""
import math
import json
import subprocess
from pathlib import Path
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def srgb_to_lab(rgb):
    def linear(v):
        return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    r, g, b = [linear(max(0., min(1., c))) for c in rgb]
    x = (r * .4124564 + g * .3575761 + b * .1804375) / .95047
    y = (r * .2126729 + g * .7151522 + b * .0721750)
    z = (r * .0193339 + g * .1191920 + b * .9503041) / 1.08883
    f = lambda t: t ** (1 / 3) if t > .008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(rgb_a, rgb_b):
    a, b = srgb_to_lab(rgb_a), srgb_to_lab(rgb_b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def projected_box(objects, camera, scene, depsgraph):
    coords = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.type != "MESH" and evaluated.type != "FONT":
            continue
        for corner in evaluated.bound_box:
            p = world_to_camera_view(scene, camera, evaluated.matrix_world @ Vector(corner))
            coords.append((p.x, 1 - p.y, p.z))
    if not coords:
        return None
    return [min(p[0] for p in coords), min(p[1] for p in coords),
            max(p[0] for p in coords), max(p[1] for p in coords)]


def intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def object_world_bounds(objects, depsgraph):
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.type != "MESH":
            continue
        points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not points:
        return None
    return [min(p.x for p in points), min(p.y for p in points), min(p.z for p in points),
            max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)]


def image_corner_rgb(path):
    # Sharp reads encoded PNG bytes, avoiding Blender's scene-linear image-buffer transform.
    js = "const sharp=require('sharp'); sharp(process.argv[1]).raw().toBuffer({resolveWithObject:true}).then(({data,info})=>{const y=Math.round(info.height*.04),xs=[Math.round(info.width*.05),Math.round(info.width*.5),Math.round(info.width*.95)];console.log(JSON.stringify(xs.map(x=>[...data.slice((y*info.width+x)*info.channels,(y*info.width+x)*info.channels+3)].map(v=>v/255))))})"
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "-e", js, str(path)], cwd=str(root / "web"), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("background pixel sampling failed: " + result.stderr)
    samples = json.loads(result.stdout.strip())
    return [sum(s[i] for s in samples) / len(samples) for i in range(3)]


def check_frame(spec, frame, t, objects, overlays, camera, scene, depsgraph, image_path, target_rgb):
    checks = []
    add = lambda name, ok, detail: checks.append({"name": name, "status": "PASS" if ok else "FAIL", "frame": frame, "time": round(t, 4), "detail": detail})
    for name, parts, cfg in objects:
        bounds = object_world_bounds(parts, depsgraph)
        if bounds is None:
            add("grounding", False, f"{name}: no mesh bounds")
            continue
        airborne = bool(cfg.get("airborne"))
        bottom = bounds[2]
        add("grounding", airborne or abs(bottom) <= .01,
            f"{name}: lowest z={bottom:.4f} m" + (" (airborne exempt)" if airborne else ""))
        box = projected_box(parts, camera, scene, depsgraph)
        allow = bool(cfg.get("allow_offscreen"))
        if frame == 0 and cfg.get("enters"): allow = True
        if frame == max(0, spec["_frame_count"] - 1) and cfg.get("exits"): allow = True
        inside = box is not None and box[0] >= 0 and box[1] >= 0 and box[2] <= 1 and box[3] <= 1
        add("in_frame", allow or inside, f"{name}: projected box={box}"
            + (" (offscreen allowed)" if allow else ""))
        subject_top = cfg.get("subject_top_min")
        if subject_top is not None:
            in_zone = box is not None and box[1] >= float(subject_top)
            add("subject_zone", in_zone, f"{name}: top={box[1] if box else None}; required >= {subject_top}")
        for title, title_parts, text_cfg in overlays:
            if not (text_cfg.get("in", 0) <= t < text_cfg.get("out", spec["duration"])):
                continue
            text_box = projected_box(title_parts, camera, scene, depsgraph)
            safe = (text_box is not None and text_box[0] >= .04 and text_box[2] <= .96
                    and text_box[1] >= .04 and text_box[3] <= .33)
            add("title_safe", safe, f"{title}: box={text_box}, required x=.04-.96 y=.04-.33")
            no_overlap = text_box is not None and box is not None and not intersects(text_box, box)
            add("text_object_overlap", no_overlap, f"{title} vs {name}: text={text_box}; object={box}")
    actual = image_corner_rgb(image_path)
    de = delta_e(actual, target_rgb)
    add("background_de", de <= 3, f"corner RGB={actual}; target RGB={target_rgb}; dE76={de:.3f} (limit 3)")
    return checks
