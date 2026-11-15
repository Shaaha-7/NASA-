# MarsPath: Space Apps 2026 submission text

Ready-to-paste text for the Space Apps project form (all in English). Every number here comes from this repository; see the README for how each one is produced. Lines marked **TEAM TO FILL** need a teammate.

- **Challenge:** Interplanetary Survival Guide: Martian Map
- **Final project link:** https://github.com/Shaaha-7/NASA- (MIT License)
- **Demo link:** **TEAM TO FILL** (Google Drive or YouTube, "anyone with the link", tested in an incognito window)
- **Team name and members:** **TEAM TO FILL**

---

## Project name

MarsPath: terrain-aware Marswalk planner for Jezero Crater

## High-level summary

MarsPath is a Google Maps-style planner for astronauts walking on Mars. For Jezero Crater, Perseverance's landing site, it builds walking routes from real NASA elevation data at 1 m resolution. It plans around steep and rough ground, visits science stops, checks the route against the suit's EVA time budget, and gives turn-by-turn directions. It also shows how far a crew can walk and still get back, real Perseverance photos at each stop, Martian weather measured by the rover, space-weather alerts, and an AI assistant that answers only from cited NASA and USGS documents. Everything runs offline from a packaged region, as it would have to on Mars. We checked the planner against Perseverance's real drives: its routes stay a median 61 m from the rover's track, against 122 m for a straight line.

## Detailed description

**What it does**
- **Routes:** plans a Marswalk between a start, any number of science stops and a destination, with three profiles (fastest, gentlest, shortest). It can reorder stops for the shortest total time.
- **Route details:** each route shows distance, modelled walking time, maximum slope, roughness and an EVA-feasibility check (time out + time back + reserve against the suit's time budget). Turn-by-turn directions add up to the route totals.
- **Warnings:** each states its rule, value, threshold and data basis: steep grade, rough ground, flagged geologic unit, low-resolution terrain, EVA budget, point moved to walkable ground, recent solar particle activity.
- **Walking range:** shows where a crew can go and still return within the usable EVA time.
- **Rover-assisted plan with walk-back check:** the crew drives between stops and walks only at them. Speed (about 10 km/h), crew of two and suit-up time (under 10 min) come from NASA's Space Exploration Vehicle concept fact sheet. At every point of the drive MarsPath checks Apollo's walk-back rule: could the crew walk home within their suit time if the rover failed? Example, landing site to Rochette and Wildcat Ridge: walking alone exceeds the suit budget; the rover plan keeps each suit period to 40 min, and flags Rochette as 13 min beyond walk-back range.
- **Crew pairs:** set the crew size; shared kit is split between them, and times apply to the whole crew.
- **Helmet HUD:** a visor-style view over the nearest real Perseverance photo, with compass, EVA time left, next stop and ETA, grade ahead, walk-home time and warnings. You move along the planned route with a slider (labelled as a simulation; nothing is live).
- **"What's here":** at any point, gives elevation, slope, roughness, geologic unit, walkability with reasons, and the nearest science site, rover stop and hazard.
- **Science stops:** 10 Perseverance sample sites tied to three science goals (carbonates as biosignature targets, the olivine-rich Séítah unit, delta stratigraphy). Positions come from the rover's own localizations on the sampling sol.
- **Point of view:** real Perseverance raw images from the nearest rover stop, with MEDA weather from the sol of that stop.
- **Space weather:** NASA DONKI solar flares, solar energetic particles and CMEs from the last 30 days. Curiosity RAD's measured surface dose is shown as a labelled reference scale.
- **AI science assistant:** answers mission and science questions only from 21 public NASA/USGS documents and open-access papers plus MarsPath's own data notes. It cites page numbers, refuses off-topic questions, and checks every generated sentence against its sources before showing it.
- **Offline:** terrain, layers, routing, rover images, space-weather cache and document search are packaged per region, so the app works with no network.

**How it works**
- **Terrain:** USGS's Mars 2020 HiRISE digital terrain model (1 m) is the main surface; the Mars 2020 CTX DEM (20 m) fills its gaps. Slope and roughness come only from these numerical elevation models, never from images. Roughness is detrended RMS height on about 2 m cells, which picks up boulder fields and scarp edges.
- **Route cost:** modelled walking time. Speed follows Tobler's hiking function on the signed grade (uphill and downhill differ), scaled to a suited walking speed and reduced for carried load. Time is multiplied by roughness and geologic-unit factors from the USGS SIM 3464 geologic map. Ground over the slope or roughness limits is excluded.
- **Search:** A* search compiled with numba, about 0.1-0.4 s per route on the Jezero grid.
- **Coordinates:** Mars 2000 sphere (R = 3,396,190 m), planetocentric latitude, east-positive longitude throughout.
- **Software:** FastAPI backend; Leaflet map, Three.js globe and plain HTML/JS dashboard on the frontend.
- **Assistant search:** hybrid of BM25 keywords and a local embedding model, merged by reciprocal-rank fusion. Retrieval test: the right document is first for 14 of 15 questions and in the top 3 for 15 of 15.

**How MarsPath meets the challenge**

| Challenge asks for | MarsPath |
|---|---|
| A map or tool a Mars astronaut could use on a surface mission | Mission dashboard for planning in the habitat; point-of-view screen for what the crew will see at each stop |
| Science goals and a chosen location | Jezero Crater; three goals (carbonates as biosignature targets, olivine-rich Séítah, delta stratigraphy) tied to 10 Perseverance sample sites |
| At least three kinds of data, layered | Seven: topographic (HiRISE and CTX DEMs, MOLA), optical (CTX orthomosaic, rover images), thermal (THEMIS), spectral (CRISM), geologic (USGS SIM 3464), atmospheric (MEDA), radiation (DONKI, RAD reference) |
| Astronaut safety and space weather | Slope and roughness limits, hazard zones, EVA time check with return reserve, DONKI solar-particle warning, radiation reference |
| Spacesuit mobility and carried equipment | Suited walking speed reduced for load; signed-grade (uphill vs downhill) walking model; editable EVA settings |
| A route that reaches the science objectives and avoids obstacles | Multi-stop routes with three profiles, stop reordering, turn-by-turn directions, walking range |
| Point-of-view imagery | Real Perseverance raw images from the nearest rover stop, cached offline |
| Display formats the challenge suggests (habitat screen, tablet, helmet HUD) | Mission dashboard for planning; helmet HUD view along the route |
| Rovers helping the crew; astronauts working in pairs | Rover-assisted plan with the Apollo walk-back check; crew size with shared kit |
| Current conditions | Live DONKI space weather when online; MEDA weather for the sol of each stop (historical, labelled as such) |

**Why it matters**

Crews on Mars will walk to science targets on foot, with limited suit time and no rescue nearby. MarsPath turns orbital and rover data into a plan a crew can act on: where to walk, how long it takes, what makes a stretch harder, and whether they can get back in time. It is built so its claims can be checked: every number has a source, missing data is shown as missing, and the planner is benchmarked against a real rover's drives.

**Limitations (stated in the app and README)**
- MarsPath is a prototype planning aid, not a certified navigation or safety system. Route scores are relative and never mean "safe".
- Rocks smaller than about 1-2 m are below the terrain resolution.
- The data is historical. Weather is MEDA's record for a past sol, not a forecast.
- The radiation figure is a reference from Gale crater (2012-13), not a Jezero measurement.
- Walking speed and load effects are team assumptions based on an Earth hiking model.
- The rover drives only where walkers can (conservative), and power and communication range are not modelled.
- The HUD position is simulated along the planned route; there is no live tracking.

## NASA data used

| Dataset | Source | How MarsPath uses it |
|---|---|---|
| Mars 2020 TRN HiRISE DTM mosaic, 1 m (MRO HiRISE) | USGS Astrogeology / NASA | Main elevation surface: slope, roughness, routing, walking range |
| Mars 2020 Science Investigation CTX DEM mosaic, 20 m (MRO CTX) | USGS Astrogeology / NASA | Fills gaps in the HiRISE DTM |
| Mars 2020 TRN CTX orthomosaic, 6 m (MRO CTX) | USGS Astrogeology / NASA | Base imagery on the map |
| MGS MOLA colour hillshade, 463 m | NASA JPL Mars Trek | Context map tiles around the study area (the HiRISE DTM is also tied to MOLA heights) |
| Mars Odyssey THEMIS day and night infrared | In USGS SIM 3464 database | Thermal layer (night IR relates to rock vs loose material) |
| MRO CRISM MTRDR browse products CAR and MAF, observation HRL000040FF | NASA PDS Geosciences Node | Carbonate and mafic mineral layers |
| Perseverance waypoints and traverse (MMGIS) | NASA/JPL | Rover stops, science-site positions, benchmark against real drives |
| Perseverance raw images | NASA/JPL-Caltech raw-images feed | Ground-level photos at each stop (point of view) |
| Perseverance MEDA weather (calibrated and derived) | NASA PDS Atmospheres Node | Air and ground temperature, pressure, wind on the sol of each science stop |
| DONKI space weather (FLR, SEP, CME) | NASA CCMC via api.nasa.gov | Space-weather advisory and route warning |
| Curiosity RAD surface dose, 0.67 mSv/day (Hassler et al. 2014) | MSL RAD, published | Labelled radiation reference scale |
| Viking colorized global mosaic 232 m (NASA Ames / USGS) | USGS Astrogeology | 3D globe texture, orientation only |
| Space Exploration Vehicle concept fact sheet (FS-2011-08-045-JSC) | NASA | Rover speed, crew of two, suitport time, Apollo walk-back rule |

## Other data and tools

- **Geology:** USGS SIM 3464, *Geologic Map of Jezero Crater and the Nili Planum Region, Mars* (Sun and Stack, 2020), US public domain. Geologic units and walking-cost factors.
- **Assistant documents:** 21 public NASA/USGS documents and open-access papers, each with its licence in `data/docs/docs_sources.json`. They are downloaded on each machine, not stored in the repository.
- **Logo:** NASA Space Apps Challenge 2026 logo, from the Space Apps brand page, used unchanged. No NASA insignia is used.
- **Libraries:**
  - Frontend: Leaflet (BSD-2-Clause) and Three.js r170 (MIT); details in `frontend/vendor/SOURCES.md`.
  - Python: FastAPI, Uvicorn, NumPy, SciPy, rasterio, pyproj, pyshp, pyogrio, numba, fastembed, httpx, pytest.
- **Embedding model:** BAAI bge-small-en-v1.5 (run locally via fastembed).

## Use of AI

- **Writing the code:** much of the code, tests and documentation in this repository was written and reviewed with **Claude Code** (Anthropic; models Claude Fable 5.2 and Claude Opus 5.5). That includes the backend, the mission dashboard and point-of-view pages, and the MarsPath logo (hand-coded SVG). The team chose the design, checked the outputs and ran the tests. **TEAM TO FILL:** add any other AI tools teammates used (for example for slides or the video).
- **Inside the app:**
  - The assistant writes answers with **Google Gemini**, or optionally Anthropic Claude, but only from passages retrieved from the cited documents. Each sentence is checked against those sources before it is shown, and without a key or network the assistant quotes the source passage instead.
  - Search uses a local embedding model (BAAI bge-small-en-v1.5).
- **No AI-generated images or data:** all terrain, imagery, weather and rover data are real NASA/USGS products as listed above.

## Screenshots (optional upload)

`docs/screenshots/dashboard.png` (mission dashboard), `docs/screenshots/pov.png` (point of view), `docs/screenshots/route.jpg`, `docs/screenshots/globe.jpg`.
