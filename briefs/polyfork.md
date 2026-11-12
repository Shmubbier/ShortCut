# Task: Polyfork-first 3D models (Codex)

Goal: 3D segments use real low-poly models from Polyfork (https://polyfork.dev) instead of AI-written prop recipes.
AI-built recipes become the LAST resort, used only when BOTH (a) Polyfork has nothing usable, even after remixing a near
match, AND (b) the user explicitly asked to create a 3D model (prompt wording such as "create/build/make a 3D model", or an
explicit UI toggle you add on the hero: "Build custom 3D models"). Otherwise a segment with no model falls back to the
existing 2D/image visuals; it never silently falls back to a recipe.

Polyfork facts (verified by the director, read https://polyfork.dev/llms.txt first, it is the API doc):
- No key needed: `GET https://polyfork.dev/api/assets?q=<word>&free=1` (WORD match, not concept: "jeepney" → 0, "basket" → 29;
  try plainer words and `class=building|vehicle|character|prop`), `GET /api/assets/{id}`, `/api/assets/{id}/matching`,
  `/api/assets/{id}/variant?want=<words>` (remix: recolour/reshape; anonymous budget 40/hour, 100/month, so cache results),
  GLB at `/cdn/{id}.glb`, parametric ES module at `/cdn/{id}.mjs` (knobs at runtime, no bake budget used).
- Every low-poly model is free; check the `free` field anyway. Keep the licence/attribution with each cached model.

Build:
1. `polyfork.py`: search with query fallbacks (the AI gives 2-3 plain nouns per subject, then the class), pick the best
   match (title/description word overlap, triangle budget ≤ ~5k), optional remix via `variant?want=` (palette words such
   as "purple", "night") with a disk cache, download GLB to `web/public/models3d/` (same store as `/api/models3d`) with a JSON sidecar
   (id, title, source URL, licence). Timeouts ≤ 8 s per call, total ≤ 20 s per plan, run lookups in parallel.
2. Generation (`server.py` `generate`/edits): for 3D segments ask the AI for a short `model_query` (2-3 plain nouns + optional
   remix words) INSTEAD of a full recipe, unless the user explicitly asked for custom models. Resolve queries via polyfork.py
   after the plan returns. Missing → 2D image fallback (existing `find_images`), or, only with explicit consent, the existing
   recipe + `ensure_props` path. Keep everything optional/backward compatible (old plans with recipes still render).
   This should also make 3D generation much faster (no long recipe output); measure before/after.
3. Rendering: a GLB on a segment renders in the existing 3D stage (`web/src/video/Stage3D.tsx`, `@remotion/three`) with
   GLTFLoader from the local `/models3d/` URL (no network at render time), auto-fit to the frame, grounded, with the
   palette's lighting. Also make imported models from the Assets panel assignable to a segment.
4. Exercise for real: plans for 3 topics (a fruit basket, a jeepney/bus, a windmill) on your API port. Report which
   Polyfork model each got, remixes used, fallbacks taken, and times. Render one 3D segment still to PNG and look at it.

Your ports: API 8796, UI 5186. Follow briefs/COMMON.md (Done means: tsc, recipe.check, real exercise, briefs/polyfork.report.md, commits).
Generations draw on the user's Claude plan: at most 3 full plan generations in total.
