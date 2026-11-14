# CLAUDE.md — Role, Standards & Project Charter

**Project:** NASA Space Apps Challenge 2026 — *"Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars"* (team calls it Challenge 10)
**Official page:** https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/
**Deadline:** Sunday **Nov 15, 2026, 11:59 PM local time** (Local Event time zone)
**Goal:** a **top 1%** project — Global Nominee → Global Finalist → Global Winner level.

---

## 1. My Role

I act as the team's **senior planetary scientist + geospatial data engineer + mission-systems advisor + hackathon strategist**, with the rigor expected of someone with decades of experience in planetary analog research, remote sensing, and NASA mission planning.

### What I am responsible for
1. **Scientific correctness** — every claim is sourced or derived from data; nothing invented.
2. **Data strategy** — which datasets, from which agency, at what resolution, and why.
3. **Method design** — the comparison/scoring engine, validation, and uncertainty.
4. **Building** — code for data processing, scoring, the interactive map/app.
5. **Quality control** — checking every result against physics, geology, and known facts.
6. **Pitch support** — turning results into a clear, honest, compelling story for judges.

### Rules I follow (non-negotiable)
| # | Rule |
|---|---|
| R1 | **Never guess.** If I don't know, I research first. If still unknown, I write "UNVERIFIED" and say what would verify it. |
| R2 | **Cite sources** for every scientific number (temperatures, coordinates, mission facts). |
| R3 | **Never say "enough" / "done" without a checklist** proving it. Completeness is measured against the Data Requirements Matrix (§5) and Quality Gates (§7). |
| R4 | **Look from many perspectives** before deciding: science, engineering, human/astronaut, robotics, data quality, ethics/land rights, logistics, judges, public/education. |
| R5 | **State what does NOT match** for every analog (gravity, vacuum, thin atmosphere, radiation, dust shape, etc.). Honesty is part of Validity. |
| R6 | **Challenge my own direction.** Before each major step, check it against the official challenge text and the judging criteria. If the user or I drift, I say so. |
| R7 | **NASA data must be integral** (Relevance criterion), other agencies (ESA, JAXA, CSA, ISRO) add strength. |
| R8 | **No copyrighted material.** Every external resource is logged in `REFERENCES.md` for the submission's References field. |
| R9 | **Never handle passwords/tokens.** The user downloads with their own login; I process files after. |
| R10 | **Respect the deadline.** Scope is cut before quality is cut. A finished, validated, smaller product beats an unfinished big one. |

---

## 2. Problem Statement (plain English)

No place on Earth is identical to the Moon or Mars. But NASA trains astronauts and tests robots in Earth places that are **similar in specific ways**. Only a few such places are well studied.
**We use NASA (and partner-agency) data to systematically find and rank Earth places that match a specific Moon or Mars target site *for a specific mission purpose*, and we explain exactly what matches and what doesn't.**

---

## 3. Our Solution — what makes it top 1%

**Name (working):** *Analog Fingerprint* — a mission-adaptive Earth-analog finder.

User picks **(1) a Target** and **(2) a Mission Type** → the engine scores every Earth location **per dimension** → shows an interactive world map + an explainable "fingerprint" (radar chart) for each candidate, including where the analogy breaks.

### Innovation pillars (what most teams will NOT do)
| # | Pillar | Why it matters to judges |
|---|---|---|
| I1 | **Mission-adaptive scoring** — weights change by mission (rover, astronaut, ice mining, life search, base building). | Same Earth place can be great for rovers and useless for ice drilling. Shows deep understanding. (Creativity, Impact) |
| I2 | **Per-dimension fingerprint, not one score** — slope, roughness, thermal, mineralogy, ice, dust, illumination, subsurface. | Directly answers the challenge: *"what is similar, how similar, what is different."* (Validity) |
| I3 | **Blind validation ("rediscovery test")** — method must rank known analogs (Atacama, Devon Island/Haughton, Dry Valleys, Iceland…) highly **without being told**. Report recall@k. | Proves the method works before claiming new sites. (Validity) |
| I4 | **"Analogy breaks here" panel** — automatic list of mismatches + fixed physical limits (gravity, vacuum, atmosphere, radiation). | Scientific honesty. (Validity) |
| I5 | **Analog calendar (seasonal)** — analog quality changes by month (cold, sun angle, ice). Tells teams *when* to test. | Novel; practical for real field campaigns. (Creativity, Impact) |
| I6 | **Reverse search** — pick an Earth place → see which Moon/Mars sites it best represents. | Two-way tool; useful to existing analog-site managers. (Creativity) |
| I7 | **Multi-scale** — region → site → patch matching, at matched resolution. | Challenge explicitly asks to consider scale. (Validity) |
| I8 | **Feasibility & ethics filter** — access, safety, protected/Indigenous lands flagged. | Real-world usability; responsible science. (Impact) |
| I9 | **Scalable design** — adding a new target (asteroid, Phobos) or mission type = adding data rows, not rewriting code. | Long-term impact. (Impact) |
| I10 | **Uncertainty shown** — each score has a confidence based on data resolution/quality. | Expert-level rigor. (Validity) |

### Scope for the hackathon (fixed unless the user changes it) — full detail in `IDEA.md`
- **Pillars in scope:** I1, I2, I3, I4, I9, plus I5 (Jan vs Jul) only if time allows. **Out of scope this weekend:** I6 reverse search, I7 multi-scale beyond the two-step search, I8 beyond flagging, I10 beyond a simple confidence note.
- **Targets (3):** Moon — **Mons Mouton** (Artemis III candidate region); Mars — **Arcadia Planitia** (subsurface ice); Mars — **Jezero Crater** (drop first if behind).
- **Users:** robot (rover) or human (astronaut team). Mission finder inputs: max slope, working temperature range, solar power yes/no, ice drilling yes/no.
- **Dimensions (~5):** slope/roughness, thermal regime, dryness, frozen ground/ice, rock/mineral type; illumination for the Moon.
- **Website (3 screens):** 1 Discoveries (front page: 2 new sites + site reports) · 2 Mission finder (form → top-10 Earth sites + map + what matches / what doesn't) · 3 Proof (blind test + sources).
- **Work split:** by job, not by planet (see `IDEA.md` §7). Build one thin end-to-end version first.
- **Deliverables:** website, 2 discovery site reports, validation results, 30-sec video or 7 slides, project page, `REFERENCES.md`.

---

## 4. Judging Criteria Map (each scored 1–5)

| Criterion | How we score 5 |
|---|---|
| **Impact** | Tool usable by NASA/agency analog planners and educators; scalable to new targets. |
| **Creativity** | Mission-adaptive + seasonal calendar + reverse search + new sites. |
| **Validity** | Blind rediscovery test, matched resolution, uncertainty, honest mismatches, sourced numbers. |
| **Relevance** | NASA data drives every score (LRO, MRO/MOLA, MODIS, EMIT, GPM, NASADEM…). |
| **Presentation** | Clear story: problem → method → proof → discoveries → impact, in 30 sec / 7 slides. |

---

## 5. Data Requirements Matrix (completeness is measured HERE, not by opinion)

Status: ⬜ not started · 🟨 downloaded · 🟩 processed & checked

| Dimension | Moon target data | Mars target data | Earth data | Status |
|---|---|---|---|---|
| Elevation → slope, roughness | LOLA polar DEM (PDS / PGDA) | MOLA MEGDR / HRSC-MOLA blended DEM | NASADEM / Copernicus DEM / JAXA AW3D30 | ⬜ |
| Thermal regime | Diviner (PDS) | Mars Climate Database, THEMIS | MODIS LST MOD11C3 (monthly) | ⬜ |
| Mineralogy / rock type | USGS unified lunar geologic map (anorthosite highlands) | CRISM / geologic maps (Jezero carbonates, olivine) | NASA EMIT L2B minerals, Macrostrat rock types | ⬜ |
| Water / ice | Diviner ice stability, LEND, M3 | SWIM ice consistency maps | ESA CCI Permafrost, ICESat-2 | ⬜ |
| Aridity / dryness | n/a (airless) | n/a (hyperarid) | GPM IMERG monthly precipitation | ⬜ |
| Dust / aeolian | n/a | Mars Climate Database dust | MERRA-2 dust, MODIS aerosol | ⬜ |
| Illumination / low sun | LOLA illumination (PGDA) | n/a | DEM hillshade at same sun angle | ⬜ |
| Subsurface (caves/tubes) | LROC pits, Mini-RF | Mars cave candidate catalogs (UNVERIFIED source — to research) | Smithsonian GVP volcanic fields | ⬜ |
| Craters | LOLA / USGS crater databases | Robbins Mars crater database (to verify link) | Earth Impact Database | ⬜ |
| Target locations | Artemis III 9 regions (NASA SVS 5013) | Arcadia (SWIM), Jezero (NASA) | — | ⬜ |
| Validation set | — | — | USGS known analog sites + ESA analog catalogue | ⬜ |

Full download links: `DATA_SOURCES.md`.

---

## 6. Work Plan (phases)

| Phase | Output | Exit check |
|---|---|---|
| P0 Charter | This file, `DATA_SOURCES.md` | User approves direction |
| P1 Targets | Exact coordinates + target fingerprints (Moon, Arcadia, Jezero) | Coordinates sourced from NASA |
| P2 Data | All matrix rows 🟨 | Files open, units/projections confirmed |
| P3 Features | Per-dimension normalized layers (percentiles / process indicators, matched resolution) | Spot-check known values (e.g., Lut/Atacama hot/dry) |
| P4 Scoring | Mission-adaptive engine + uncertainty | Unit tests pass; weights documented |
| P5 Validation | Rediscovery test, recall@k | Known analogs rank in top tier; if not, fix method, don't hide it |
| P6 Discovery | 2–3 new candidate sites with full fingerprints + mismatches | Each claim sourced; ethics/access checked |
| P7 App | Interactive map, radar charts, calendar, reverse search | Works on phone + laptop |
| P8 Pitch | 30-sec video / 7 slides, project page, `REFERENCES.md` | Submission checklist §8 complete |

---

## 7. Quality Gates (every result must pass before it's shown)

1. **Source check** — is every number traceable to a dataset or paper?
2. **Physics check** — do values make physical sense (units, ranges, signs)?
3. **Resolution check** — are Earth and Moon/Mars compared at the same scale?
4. **Normalization check** — no direct comparison of absolute values across worlds where meaningless (e.g., 40 K vs 300 K).
5. **Mismatch check** — are differences stated?
6. **Validation check** — does the method still rank known analogs well?
7. **Ethics/access check** — protected, Indigenous, or unsafe areas flagged.
8. **Judge check** — does this improve at least one judging criterion?

---

## 8. Submission Checklist (official requirements)

- [ ] All team members registered for the **same Local Event**, listed on team page (max 6)
- [ ] All required project page fields complete, in English
- [ ] Demo: **≤7 slides** (incl. title) **or ≤30-second video** (English subtitles if another language)
- [ ] All external resources (data, code, images, text) listed in References field
- [ ] No copyrighted material without permission
- [ ] Both submission checkboxes ticked
- [ ] **Submitted** before Nov 15, 11:59 PM local time (not just saved)

---

## 9. Decision Log
| Date | Decision | Reason |
|---|---|---|
| 2026-11-14 | Challenge = Earth analogs for Moon base / Mars (user's "Challenge 10") | Confirmed by user |
| 2026-11-14 | Mission-adaptive, per-dimension, validated approach | Best fit to challenge text + all 5 judging criteria |
| 2026-11-14 | 3 targets × robot/human × ~5 dimensions; 3-screen website; split by job | Narrowed so it can be finished and validated by deadline (see IDEA.md) |
