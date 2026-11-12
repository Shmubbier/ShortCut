# Shot specification

Each JSON spec is a self-contained, portable Blender shot. Paths to GLB assets are relative to the repository root.

- `duration`, `fps`, `resolution`: exact output timing and pixel dimensions.
- `camera.keyframes`: `{t, position:[x,y,z], look_at:[x,y,z], fov, easing}`. Times are seconds; supported easing names are `linear`, `easeInOutCubic`, `easeOutBack`, and `easeInExpo`.
- `objects`: either `{name, glb, position, scale, rotation}` or `{name, primitive, position, scale, color, keyframes}`. Primitives are `cube`, `sphere`, `icosphere`, and `cylinder`. Object keyframes animate `position`, `rotation`, and/or `scale`.
- `lights`: `{position, energy, size}` area lights.
- `background`: paper hex color. `text`: `{body, in, out, position:[x,y], size, color}` where position is in normalized frame coordinates and visibility is in seconds.

All keyframe easing is deterministic between keys. Proof mode renders six evenly spaced frames at one-quarter resolution and writes a contact sheet, machine-readable `proof.json`, and per-check PASS/FAIL output. Checks cover text boxes vs projected object bounds, the title-safe region (normalized x=.04-.96, y=.04-.33), floor contact (z=0 within 1 cm unless `airborne`), background ΔE76≤3, and in-frame object bounds unless `allow_offscreen`, `enters`, or `exits` is set. Optional `subject_top_min` requires the projected subject to begin below a normalized y coordinate.

Final mode requires a passing proof for the same spec hash, aspect, and full output contract dimensions. `--force` bypasses that guard. `--aspect 9:16|16:9|1:1|4:5` selects app output dimensions (1080×1920, 1920×1080, 1080×1080, 1080×1350); `--draft` renders final output at 50% resolution while retaining that same proof contract. If a draft dimension is odd, H.264 encoding trims the last row/column to remain yuv420p compatible. The spec's `fps` controls proof and final output (the library uses the app's 30 fps).
