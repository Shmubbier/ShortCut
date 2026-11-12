Director follow-up (Claude Code). You now have FULL ACCESS: no sandbox. The shared venv works
(`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python`), and `git commit` works in your worktree.
I committed your first pass (3c4530a) and merged the latest `main` into your branch (0d2a374): content styles, prop validation,
and a format selector. Re-read `git log -5` and keep everything that's there.

Finish the task:
1. **Verify for real now.** Start your API on port 8792 (`BLOCKCUT_PORT=8792`) and run `/api/assets/search` on all 8 test topics
   (the epstein files, Manila traffic, jeepney, tower defense game, ube halaya, Mobile Legends, Philippine eagle, how coffee is made).
   Record per-topic, per-kind and per-source hit counts and times in the report. Fix whatever fails. Import at least one image, one
   video clip and one model end to end.
2. **A keyless 3D-model source.** polyfork.dev hosts ~3,250 free low-poly GLBs: asset pages are `https://polyfork.dev/asset/<slug>-<id>`
   and files are `https://polyfork.dev/cdn/<id>.glb` (licence: CC BY 4.0 with credit "<Name> by Polyfork (<asset URL>)"; see
   `bench3d/REPORT.md`). Build a small **local index** (`models/polyfork_index.json`: name, slug, id, category, tags) by fetching their
   asset listing page(s) once (cache it; refresh at most daily; be polite: one request at a time, User-Agent with no personal data).
   Search it by keyword overlap, and return GLB candidates with the credit line as the licence/author.
   Keep the Khronos glTF sample models as a fallback if useful.
3. **Models on segments.** Support `media: {type: 'model', url, name}` on a segment. In `web/src/video/Stage3D.tsx` (or a small new
   component next to it), render the GLB with drei `useGLTF` on the same paper stage and auto-framed orbit camera used for recipe
   props (the bench3d `Model` component shows how; set `castShadow` at clone time). Show it in **any** visual style (not only 3d) when
   a segment has a model. Allow dragging a model tile onto a card or the inspector's Media box (mirror the clip path in `App.tsx`
   `assignClip` / Inspector `clipFor`). Add imported models to `bucket_text()` in `server.py` so the AI can place them in segments
   (it sets `asset` today; add a way to set a model, e.g. a `model` url field on `Scene`, optional).
4. Render one still with a polyfork model on a 9:16 segment (`npx remotion still … --gl=angle`) and look at it. Fix the framing if needed.
5. Commit in small steps; update `briefs/assets.report.md` with real numbers; final message as before.
