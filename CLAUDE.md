# CLAUDE.md: MarsPath guiding document

**Project:** MarsPath, NASA Space Apps Challenge 2026, *Interplanetary Survival Guide: Martian Map*
**Official page:** https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/
**Team plan:** "MarsPath — Project Outline" and "Challenge Analysis & Dataset Plan" PDFs. The user is a team member working on the **backend**; the frontend belongs to the frontend team (repo: github.com/umairai21/NASA---Space-Apps-Challenge). Our repo: github.com/Shaaha-7/NASA-.
**Goal:** a top 1% project. Every upgrade is judged by quality and by the five judging criteria (Impact, Creativity, Validity, Relevance, Presentation).

---

## 1. My role
Senior planetary scientist, geospatial/backend engineer and reviewer for the MarsPath backend: scientific correctness, data, algorithms, APIs, the AI assistant, tests, and honest critical review.

## 2. Rules (non-negotiable)
1. **Never guess.** Research first; mark anything unconfirmed as UNVERIFIED.
2. **Every scientific number has a source** (dataset, product, resolution, date).
3. **Never invent values.** Missing data is null or "not available", never 0 unless 0 was measured.
4. **Mars coordinates:** planetocentric latitude, east-positive longitude, Mars 2000 sphere. Confirm each raster's CRS; never assume Earth WGS84.
5. **Slope only from numerical elevation**, never from imagery or hillshade.
6. **Never call terrain "safe"**; say lower or higher modelled traversal cost under stated assumptions.
7. **Backend only.** Do not change visuals or the frontend unless the user asks; make the backend easy for the frontend to use.
8. **Keys stay private:** only in `local_keys.bat` (git-ignored). Check staged files for keys before every push.
9. **Raw data stays in `C:\NASA_DATA`** or `data/raw` (git-ignored); only code and small config go to GitHub.
10. **Do not talk about time or deadlines** when recommending upgrades; rank by quality and value.
11. **Official demo limit:** a video of 30 seconds or less, or 7 slides or fewer.
12. **Tests must pass before every push**; add a test with every new feature.

## 3. What is built (backend, all tested)
| Area | What it does | API |
|---|---|---|
| Terrain | HiRISE 1 m DTM (CTX 20 m gap fill), slope, 2 m roughness, USGS SIM 3464 geology, THEMIS, CTX imagery | `/layers`, `/terrain/sample` |
| Routing | A* on modelled walking time (Tobler, signed grade, roughness and sand multipliers, EVA limits), 3 profiles, stops, stop-order optimisation | `/routes/calculate`, `/routes/compare` |
| Directions | Turn-by-turn steps that add up to the route totals | in every route |
| Walking range | Where a crew can go and still get back within the usable EVA time | `/reachability` |
| What's here | Terrain, geology, walkability with reasons, nearest site/rover stop/hazard | `/point-info` |
| Search | IAU names, science sites, units, "sol N", coordinates | `/search` |
| Science stops | 10 verified Perseverance sample sites tied to goals G1-G3 | `/science-sites` |
| Ground view | Real Perseverance images from the nearest rover stop, cached offline | `/ground-view` |
| Proof | Planner vs Perseverance's real drives: median 61 m vs 122 m straight line, closer in 4 of 5 | `/validation` |
| Safety | DONKI space weather (per-list, key never shown), RAD reference dose, hazard zones | `/space-weather`, `/hazards` |
| AI assistant | Hybrid RAG (BM25 + local embeddings), 34 documents, page citations, off-topic refusal, Gemini with hallucination guard, quoted-source fallback | `/assistant/ask` |
| Offline | Region, tiles, space weather, rover images, assistant index packaged | `/offline/*` |

## 4. Upgrade roadmap (ranked by value)
| # | Upgrade | Value | Status |
|---|---|---|---|
| U1 | Shareable processed-data package so any teammate can run real Jezero data | Demo reliability | todo |
| U2 | Warm up the assistant's search model at server start | Smooth live demo | todo |
| U3 | Return the hallucination-guard result in a form the frontend can show ("3 of 3 sentences supported") | Visible proof for judges | backend done; frontend to display |
| U4 | Larger rover benchmark (more stretches, report spread not just median) | Validity | todo |
| U5 | Radiation exposure per route (EVA hours x RAD reference, shielding note) shown with route metrics | Crew-safety objective O5 | todo |
| U6 | Sun/lighting at route time (illumination and shadow from DEM) | Safety and power | research needed |
| U7 | More regions (Gale, other candidate human landing sites) via config + prepare | Scalability | todo |
| U8 | Concurrency for many users (numba nogil, more server workers) | Scalability | todo |
| U9 | Google Maps-style deep zoom: tile server (XYZ tiles, disk cache, offline) for CTX/HiRISE imagery and slope/roughness/geology layers, replacing single overlay images that blur when zoomed | Usable, polished map | todo (backend serves tiles; frontend switches layers to tile URLs) |
| U10 | Google Earth-style 3D terrain: terrain tiles/heightmaps from the HiRISE 1 m DTM for a 3D view of the walk | Visual impact | todo (backend serves terrain; needs a frontend 3D viewer) |

Google Maps-style features already built: directions, search, "what's here", rover ground view (street-view analogue), walking range.

## 5. Quality gates for every result
Source check · physics/units check · resolution check · honest limitations stated · tests pass · no keys staged.
