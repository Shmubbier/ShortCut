# Shot specification

Each JSON spec is a self-contained, portable Blender shot. Paths to GLB assets are relative to the repository root.

- `duration`, `fps`, `resolution`: exact output timing and pixel dimensions.
- `camera.keyframes`: `{t, position:[x,y,z], look_at:[x,y,z], fov, easing}`. Times are seconds; supported easing names are `linear`, `easeInOutCubic`, `easeOutBack`, and `easeInExpo`.
- `objects`: either `{name, glb, position, scale, rotation}` or `{name, primitive, position, scale, color, keyframes}`. Primitives are `cube`, `sphere`, `icosphere`, and `cylinder`. Object keyframes animate `position`, `rotation`, and/or `scale`.
- `lights`: `{position, energy, size}` area lights.
- `background`: paper hex color. `text`: `{body, in, out, position:[x,y], size, color}` where position is in normalized frame coordinates and visibility is in seconds.

All keyframe easing is deterministic between keys. Proof mode renders six evenly spaced frames at one-quarter resolution and writes a contact sheet; final mode renders all full-size PNG frames and encodes an H.264 MP4.
