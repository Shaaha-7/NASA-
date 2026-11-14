# TEAM TASKS — Analog Fingerprint (Space Apps 2026)

**Hard deadline:** Sunday Nov 15, 11:59 PM local. **Team target: submit by Sun 10:00 PM** (2-hour safety buffer).
**Rule:** every person updates their status in this file (⬜ todo · 🟨 doing · 🟩 done) and logs every dataset/image/code they use in `REFERENCES.md`.
**Plan & standards:** `CLAUDE.md` · **Data links:** `DATA_SOURCES.md`

---

## Roles (6 people — see bottom for 3/4/5-person versions)

### 👤 P1 — Team Lead & Science Lead
**Skills:** organized, good communicator, interest in space science
**Owns:** direction, final decisions, story, judge-facing quality
| # | Task | When | Status |
|---|---|---|---|
| 1 | Check everyone is registered for the **same Local Event** and listed on the team page | Now | ⬜ |
| 2 | With Claude: finalize the 3 targets (Phase 1, `TARGETS.md`) and approve them | Sat night | ⬜ |
| 3 | Run 30-min check-ins: Sat night, Sun noon, Sun 6 PM | Sat–Sun | ⬜ |
| 4 | Pick the 2–3 "surprise" Earth sites with the team (Phase 6) | Sun noon | ⬜ |
| 5 | Write project page text (problem, solution, impact) | Sun 6 PM | ⬜ |
| 6 | Press **Submit** (not just save) + tick both checkboxes | Sun 10 PM | ⬜ |

### 👤 P2 — Moon & Mars Data Specialist
**Skills:** patient with data portals; basic GIS (QGIS) helpful
**Owns:** all target-side data (Moon + Mars)
| # | Task | When | Status |
|---|---|---|---|
| 1 | Moon: download LOLA south-pole elevation + Diviner temperature for the chosen Artemis region (PDS / PGDA) | Sat night | ⬜ |
| 2 | Mars: download SWIM ice maps (Arcadia) + MOLA elevation; Jezero geology/minerals | Sat night | ⬜ |
| 3 | Mars Climate Database: temperature, pressure, dust for Arcadia & Jezero | Sun morning | ⬜ |
| 4 | Optional partner data: JAXA Kaguya, ISRO Chandrayaan-2, ESA Mars Express HRSC | Sun morning | ⬜ |
| 5 | Hand files to P4 in `data/moon` and `data/mars` with a short note (what, units, resolution) | Sun morning | ⬜ |

### 👤 P3 — Earth Data Specialist
**Skills:** comfortable with NASA Earthdata (account already created ✅), Google Earth Engine a plus
**Owns:** all Earth-side data
| # | Task | When | Status |
|---|---|---|---|
| 1 | Download MODIS LST **MOD11C3** (Jan + Jul 2025) and GPM **GPM_3IMERGM** (Jan + Jul 2025) | Sat night | ⬜ |
| 2 | Elevation: NASADEM / Copernicus DEM / JAXA AW3D30 (global coarse via Earth Engine, detailed only for shortlisted sites) | Sat night | ⬜ |
| 3 | Permafrost (ESA CCI), dust (MERRA-2), volcanic fields (Smithsonian GVP), impact craters (Earth Impact Database), rock types (Macrostrat) | Sun morning | ⬜ |
| 4 | EMIT minerals — **only** for shortlisted sites via AppEEARS | Sun noon | ⬜ |
| 5 | Validation set: USGS known analog sites + ESA analog catalogue → `data/validation` | Sat night | ⬜ |

### 👤 P4 — Data Scientist / Scoring Engine
**Skills:** Python (numpy, pandas, rasterio/xarray), basic statistics
**Owns:** the "brain" — comparing and scoring (works closely with Claude)
| # | Task | When | Status |
|---|---|---|---|
| 1 | Build per-dimension feature layers (slope, roughness, thermal, dryness, ice, minerals) at matched resolution | Sun morning | ⬜ |
| 2 | Mission-adaptive scoring (5 mission types, documented weights) + uncertainty | Sun noon | ⬜ |
| 3 | **Blind rediscovery test** — do known analogs rank high? Report recall@k honestly | Sun 2 PM | ⬜ |
| 4 | Export results (GeoJSON/CSV) for the web app | Sun 3 PM | ⬜ |
| 5 | Analog calendar (Jan vs Jul) + reverse search data | Sun 5 PM | ⬜ |

### 👤 P5 — Web App / Visualization Developer
**Skills:** HTML/JS, Leaflet or Kepler.gl, charts (Chart.js/D3)
**Owns:** the interactive tool judges will click
| # | Task | When | Status |
|---|---|---|---|
| 1 | Build app skeleton NOW with fake data: world map + target picker + mission picker | Sat night | ⬜ |
| 2 | Radar "fingerprint" chart per site + "analogy breaks here" panel | Sun noon | ⬜ |
| 3 | Plug in real results from P4 | Sun 3 PM | ⬜ |
| 4 | Calendar toggle + reverse search view | Sun 6 PM | ⬜ |
| 5 | Deploy (GitHub Pages) + test on phone and laptop | Sun 8 PM | ⬜ |

### 👤 P6 — Storyteller / Designer / Submission Manager
**Skills:** design, video editing, clear English writing
**Owns:** everything judges see first (Presentation score)
| # | Task | When | Status |
|---|---|---|---|
| 1 | Create `REFERENCES.md`; collect every source from teammates all weekend | Ongoing | ⬜ |
| 2 | Draft the story: problem → method → proof → discoveries → impact | Sun noon | ⬜ |
| 3 | Make **≤7 slides** OR **≤30-second video** (English subtitles if needed) using screenshots of the real app | Sun 8 PM | ⬜ |
| 4 | Only use own images or NASA public-domain images (no copyrighted music/images) | Ongoing | ⬜ |
| 5 | Run the official submission checklist (`CLAUDE.md` §8) with P1 | Sun 9:30 PM | ⬜ |

### 🤖 Claude (AI assistant)
| # | Task | When |
|---|---|---|
| 1 | Phase 1: research exact target coordinates + fingerprints → `TARGETS.md` | Sat night |
| 2 | Write processing & scoring code with P4; explain every step | Sat–Sun |
| 3 | Fact-check every number and claim (quality gates) | Ongoing |
| 4 | Research and write the "surprise site" deep dives with sources | Sun |
| 5 | Review app, slides, project page against judging criteria | Sun evening |

---

## Timeline (all times local)
| Time | Milestone |
|---|---|
| **Sat night** | Targets approved · first data downloaded · app skeleton running |
| **Sun 12 PM** | ✅ Check-in 1: features + first scores · story draft |
| **Sun 3 PM** | Validation test done · real data in app |
| **Sun 6 PM** | ✅ Check-in 2: surprise sites chosen · project page text drafted |
| **Sun 8 PM** | **Feature freeze** — no new features after this · video/slides final |
| **Sun 10 PM** | **SUBMIT** |
| Sun 11:59 PM | Official close (buffer only) |

## Handoffs (who needs what from whom)
- P2 + P3 → **data files** → P4
- P4 → **results (GeoJSON/CSV)** → P5
- P5 → **app screenshots / link** → P6
- Everyone → **sources** → P6 (`REFERENCES.md`)
- Claude → **targets + facts** → everyone

---

## If your team is smaller
| Team size | Merge |
|---|---|
| **5** | P2 + P3 → one "Data Specialist" (Claude helps with downloads guidance) |
| **4** | P2 + P3 → Data · P1 + P6 → Lead & Storyteller |
| **3** | P1 + P6 (Lead/Story) · P2 + P3 (Data) · P4 + P5 (Code — Claude writes most code) |
| **2** | Person A: Lead + Data + Story · Person B: Code + App (Claude heavily supports both) |
