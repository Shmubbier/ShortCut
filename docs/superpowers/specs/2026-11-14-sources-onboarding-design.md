# Image relevance, Sources tab, onboarding (2026-11-14)

## Why
Panelists review the hosted build on their own. Images drifted off-topic ("Sean Kenny" for Kenny Rogers, a "Mount & Blade" game
shot for Everest), nothing showed where facts and pictures came from, and a first-time visitor had no guide to the editor.

## A. Image relevance (asset_search.py)
- Root cause: `search()` also searched the first word alone (`"kenny"`) and `"<topic> objects places"`, and kept any result.
- Fix: search the topic only. Then keep a candidate only if its title/page URL contains every *core* word of the topic. Core words =
  topic keywords (stopwords dropped) that show up in at least half as many candidate titles as the most common keyword, so
  "kenny rogers" needs both words, "mount everest" needs both, and "why filipinos love ube" needs just "ube".
- The same filter guards the DuckDuckGo fallback in `server.find_images`. 3D models keep Polyfork's own strict matcher.

## B. Sources
- The AI returns `sources: [{title, url}]` with the plan: pages it actually opened, never invented, may be empty. Server keeps https URLs only, max 8.
  Whole-video edits merge new sources into the old ones.
- New rail tab **Sources**: "Research" (the links) and "Images & 3D" (per segment: thumbnail, title, author, license, link). Image credits come
  from `plan.credits` (demo plans) or the asset sidecars (`/api/assets`); 3D credits from `scene.model`.
- Demo plans: ube gets its Commons credits (already in index.json) and Wikipedia background links, marked as such.

## C. Onboarding
- First visit (no saved code, never toured): a small window, "Got a reviewer code?". Yes → the existing code dialog → tour. No → tour in demo mode.
- The tour loads the ready-made ube video and spotlights, one short line each: the preview, a segment card, its module tags, Asset Library,
  the ✦ AI button, Project Settings (export), Sources. Back/Next/Skip, Esc skips.
- Ending: live/admin → "Ready to make your own?" Start creating → prompt page. Demo → "That's the end of the demo" → prompt page to try the
  jeepney or tower-defense demos. "Take the tour" on the start screen replays it.

## Approaches considered
- Image relevance: (1) core-word title filter (picked: no new services, explains itself), (2) AI vision check of each image (slow, costs
  Codex quota per image), (3) paid Google image API (keys, cost). 
- Tour: (1) hand-built spotlight overlay (picked: ~150 lines, matches the app's look), (2) a tour library (new dependency for a few steps).

## Non-goals
No change to Polyfork matching, no new image providers, no per-fact citation markers in the video.
