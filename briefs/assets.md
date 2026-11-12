# Codex task 2: robust asset discovery (images, video clips, 3D models)

Branch `codex/assets`. Read `briefs/COMMON.md` first.

## Problem
Most prompts fail to get usable assets, so the video can't show the intended idea. Today's `find_images()` in `server.py`
(ScrapeGraphAI `search_on_web` → page images, with DuckDuckGo image top-up, prompt-to-topic via `topic_query`) finds images only.
There is **no video-clip search and no 3D-model search**.

## Build
1. **New module `asset_search.py`** with one entry point: `search(query, kinds=("image","video","model"), limit)` returns
   normalized candidates `{kind, url, preview_url, title, source_page, license, author, width, height, duration?, format}`, plus
   `fetch(candidate) -> saved asset` that downloads, validates (type sniffing, size caps, dimensions) and stores with attribution.
   Prefer sources with clear licences and **no API key**:
   - **Images:** keep ScrapeGraphAI + DuckDuckGo; add **Wikimedia Commons** (MediaWiki API, `generator=search` +
     `prop=imageinfo`, `iiprop=url|size|extmetadata` for licence/author) and **Openverse** (`api.openverse.org/v1/images`).
   - **Video clips:** Wikimedia Commons (filetype webm/ogv; mp4 if available), Openverse audio/video if usable, and NASA's image and
     video library (`images-api.nasa.gov`, public domain) where topical. Only keep clips the browser can play (mp4/webm); clip
     length ≤ 60 s or trim later. **Pexels/Pixabay** only if `PEXELS_API_KEY` / `PIXABAY_API_KEY` exist in `.env` (optional).
   - **3D models (GLB):** polyfork (`https://polyfork.dev/cdn/<asset-id>.glb`; see `bench3d/REPORT.md` for its licence terms),
     **Poly Pizza** (CC0/CC-BY low-poly; check whether its API needs a key), **Smithsonian 3D** or **Khronos glTF sample models** as
     fallbacks. Validate GLBs by parsing the header and checking size.
2. **Query planning:** a failed search usually means a bad query. Generate 2-3 query variants per kind (topic, topic + concrete
   nouns, the single main noun) with `topic_query()` and simple rules (no AI call needed). Run sources **in parallel** with
   timeouts; one source failing must never sink the result. Log per-source counts and errors.
3. **Endpoints:** `POST /api/assets/search {query, kinds}` → candidates (no download); `POST /api/assets/import {candidate}` → saved
   asset (images go to the existing bucket; videos go to the `footage/` store Codex built in phase 4 so they work as clips; GLBs go to
   a new `web/public/models3d/`, served by the static handler). Keep `/api/assets/find` working (call the new module underneath).
4. **UI (small, Assets panel in `web/src/App.tsx`):** a "Search" box with kind chips (Images · Video · 3D). Results show a preview grid
   with the licence; click to import. Imported videos appear with the clips; GLBs appear in a new "3D models" list. If you have time,
   a GLB on a segment (`media: {type: 'model', url}`) renders via `Stage3D` with `useGLTF` (the bench3d `Model` component shows how).
   Only add the 3D-on-segment UI if it actually renders.
5. **Test with the user's real failure cases:** "the epstein files", "Manila traffic", "jeepney", "tower defense game", "ube halaya",
   "Mobile Legends", "Philippine eagle", "how coffee is made". Report hit counts per kind and source, and time per query.

## Done
For at least 6 of the 8 test topics: ≥4 usable images, and ≥1 usable video clip or 3D model where one plausibly exists. Each
asset is importable from the UI and usable in a segment, with licence and source recorded.
