# MarsPath

**A terrain-aware Marswalk planner for the first crews on Mars, built on real NASA data for Jezero Crater.**

NASA Space Apps Challenge 2026 · *Interplanetary Survival Guide: Martian Map* · [Submission text](SUBMISSION.md) · [MIT License](LICENSE)

![MarsPath mission dashboard: Jezero route with science stops, layers, EVA summary and space weather](docs/screenshots/dashboard.png)

## What it does

| Feature | What the crew gets |
|---|---|
| **Layered map** | Seven kinds of NASA data for Jezero: topographic (HiRISE 1 m DTM, CTX DEM, MOLA), optical (CTX), geologic (USGS SIM 3464), thermal (THEMIS), spectral (CRISM), atmospheric (Perseverance MEDA) and radiation (DONKI, Curiosity RAD) |
| **Science-stop routes** | Routes through Perseverance sample sites tied to three science goals; fastest, gentlest and shortest profiles; best stop order; turn-by-turn directions |
| **EVA check** | Modelled walking time out and back against the suit's time budget, for a crew walking together with shared kit |
| **Rover + walk-back** | Drive between stops and walk only at them; at every point MarsPath checks Apollo's rule: could the crew walk home if the rover failed? |
| **Warnings** | Steep grade, rough ground, soft-sand or rim units, low-resolution terrain, EVA budget, recent solar particle events: each with its rule, value and data source |
| **Walking range** | Where the crew can go from the habitat and still get back in time |
| **Point of view** | The nearest real Perseverance photo for each stop, with MEDA weather from that sol |
| **Helmet HUD** | A visor-style view along the planned route: compass, EVA time left, next stop, grade ahead, walk-home time |
| **Science assistant** | Answers only from 21 cited NASA/USGS documents and papers; every generated sentence is checked against its source |
| **Offline** | Terrain, routes, images, space-weather cache and document search all work with no network |

**Tested against reality:** planned routes stay a median **61 m** from the tracks Perseverance actually drove, against 122 m for a straight line (closer in 4 of 5 stretches). Run `backend/scripts/validate_against_rover.py jezero`, or see `/api/v1/validation`.

![MarsPath point of view: Perseverance Navcam image at Rochette with MEDA weather and terrain cards](docs/screenshots/pov.png)

## Quick start (Windows)

```
git clone https://github.com/Shaaha-7/NASA-.git
cd NASA-
setup.bat
get_jezero_data.bat
run.bat
```

- **`setup.bat`** creates `.venv`, installs the packages, builds a small synthetic test region and runs the tests.
- **`get_jezero_data.bat`** downloads the Jezero data into `data/raw/jezero/` and prepares it. The HiRISE DTM is about 1.8 GB; `backend/scripts/fetch_data.py --small` skips it and uses the 20 m CTX DEM instead.
- **`run.bat`** starts the app at http://localhost:8000/app/. The 3D globe opens first; pick Jezero or press **Skip to map**.

Without the Jezero data the app runs on the synthetic region, marked **TEST FIXTURE**: invented terrain, not Mars.

On macOS or Linux: `python -m venv .venv`, activate it, `pip install -r requirements.txt`, then `python -m uvicorn app.main:app --app-dir backend --port 8000`.

### Pages

| Page | Address |
|---|---|
| 3D globe | http://localhost:8000/app/ |
| Mission dashboard | http://localhost:8000/app/dashboard.html |
| Point of view | http://localhost:8000/app/pov.html |
| Helmet HUD | http://localhost:8000/app/hud.html (move with the slider, play button or arrow keys; the position is simulated) |
| Earlier map page | http://localhost:8000/app/?classic=1 |
| API docs | http://localhost:8000/docs |

### Offline demo

1. While online, run **`build_offline.bat`**: it downloads the assistant documents, caches the map tiles, rover images and space weather, and writes `data/cache/marspath_offline_jezero.zip`.
2. **`run_offline.bat`** starts the app with all network calls refused, like Wi-Fi off.

Offline, the assistant quotes the best source passage with its citation instead of writing an answer.

### Keys (optional)

Put them in `local_keys.bat` next to `run.bat`. It is git-ignored; never commit keys.

```
@echo off
set NASA_API_KEY=your_key_here
set GEMINI_API_KEY=your_key_here
REM set ANTHROPIC_API_KEY=your_key_here
```

- `NASA_API_KEY` (free at https://api.nasa.gov): DONKI space weather. `DEMO_KEY` works but is rate-limited.
- `GEMINI_API_KEY` (preferred) or `ANTHROPIC_API_KEY`: written assistant answers. Without one, answers are quoted passages, still cited.
- `MARSPATH_OFFLINE=1`: forces offline behaviour.

Error messages from NASA calls are cleaned so a key never appears in the API or the UI.

## How it works

```
NASA/USGS files --prepare_data.py--> data/processed/<region>/ (terrain.npz, layers, pins, hazards, manifest)
                                          |
browser <--> FastAPI (backend/app/main.py) +-- routing.py       A* on modelled walking time
                                          +-- eva.py           suited walking model (team assumptions)
                                          +-- rover.py         rover plan + walk-back check
                                          +-- reachability.py  walking range (Dijkstra out and back)
                                          +-- weather.py       Perseverance MEDA summaries
                                          +-- spaceweather.py  DONKI + RAD reference
                                          +-- assistant.py     hybrid search + checked LLM answers
                                          +-- offline.py       tile cache, offline package
```

- **Coordinates:** Mars 2000 sphere (R = 3,396,190 m), planetocentric latitude, east-positive longitude, GeoJSON `[lon, lat]`. Never Earth WGS84 or Web Mercator.
- **Elevation:** the HiRISE 1 m DTM is primary; the CTX 20 m DEM fills its gaps. Slope and roughness come only from these elevation models, never from images.
- **Roughness:** detrended RMS height in a 5×5 window on the ~2 m DEM, the maximum for each 10 m routing cell. It picks up boulder fields and scarp edges.
- **Route cost = modelled walking time:** Tobler's hiking function on the signed grade of each step (uphill and downhill differ), scaled to a suited walking speed and slowed for each person's load; multiplied by roughness and geologic-unit factors (`config/geo_penalties.json`). Ground over the slope or roughness limits is excluded. A* compiled with numba: about 0.1-0.4 s per route.
- **Rover plan:** drive at about 10 km/h with a crew of two and under 10 min to suit up at each stop (NASA Space Exploration Vehicle concept fact sheet, FS-2011-08-045-JSC). The walk home from every point of the drive is computed on the walking model and compared with the suit time available (Apollo walk-back rule).
- **Radiation:** DONKI flares, solar particle events and CMEs are an advisory (near-Earth catalogue). Curiosity RAD's Gale crater average (0.67 mSv/day, Hassler et al. 2014) is a labelled reference, not a Jezero or live value.
- **Assistant:** BM25 keywords plus a local embedding model (BAAI bge-small-en-v1.5), merged by reciprocal-rank fusion; right source first for 14 of 15 test questions. PDF citations keep page numbers; off-topic questions get "not found".

All EVA numbers are **team assumptions**, listed in `config/eva_defaults.json` and returned with every route.

## API (all under `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/status`, `/health` | Online/offline, regions ready, engine |
| GET | `/regions` | Region list, bbox, layers, data date, science goals |
| GET | `/layers?region_id=` | Layer metadata: mission, instrument, units, resolution, limitations |
| GET | `/tiles/{layer}/{z}/{y}/{x}` | Mars Trek tiles with a disk cache |
| GET | `/terrain/sample`, `/terrain/patch` | Terrain at a point, or a small 3D terrain patch |
| GET | `/point-info?region_id=&lon=&lat=` | "What's here?": terrain, geology, walkability with reasons, nearest site, rover stop and hazard |
| GET | `/search?region_id=&q=` | Place names, science sites, geologic units, `sol 509`, coordinates |
| GET | `/science-sites`, `/hazards`, `/validation` | Science stops, hazard zones, rover benchmark |
| POST | `/routes/calculate`, `/routes/compare` | Walking routes with directions, warnings and EVA check |
| POST | `/routes/rover` | Rover-assisted plan with the walk-back check |
| POST | `/reachability` | Walking range from a habitat as map bands |
| GET | `/ground-view`, `/ground-view/image/{id}` | Real Perseverance images near a point, cached for offline use |
| GET | `/weather?region_id=` | MEDA weather on the sol of each science stop |
| GET | `/space-weather?eva_hours=` | DONKI advisory and RAD reference |
| GET | `/eva/defaults` | EVA parameters with their basis |
| POST/GET | `/missions`, `/missions/{id}/export` | Save and export plans (GeoJSON, CSV, JSON) |
| GET/POST | `/offline/package`, `/offline/prefetch` | Offline package and cache |
| POST | `/assistant/ask` | Cited answers from the loaded documents |

Errors are JSON `{"detail": {"code", "message"}}`: 404 `unsupported_region`, 422 `outside_region` or invalid input, 409 `no_route` or `enclosed`.

## Repository

```
backend/app/       API and engines
backend/scripts/   data download, preparation, documents, benchmark, packaging
backend/tests/     tests: python -m pytest backend/tests -q
config/            region, EVA defaults, terrain penalties, science sites, weather summary
frontend/          globe, dashboard, point of view, HUD (plain HTML/JS, Leaflet, Three.js)
data/              raw/, processed/, cache/, docs/ (downloaded data is not stored in Git)
```

## Limitations

- A prototype planning aid, not a certified navigation or safety system. Route scores are relative; no ground is called "safe".
- Terrain is resolved at the DEM scale: rocks smaller than about 1-2 m are not seen.
- Data is historical. Weather is MEDA's record for a past sol, not a forecast; the radiation figure is a Gale crater reference.
- Walking speed and load effects are team assumptions based on an Earth hiking model. The rover drives only where walkers can.
- The HUD position is simulated along the planned route; nothing is tracked live.

## Troubleshooting

- **`pip install` fails on rasterio:** use 64-bit Python 3.11-3.13 and upgrade pip, or `conda install -c conda-forge rasterio`.
- **Black map background:** Mars Trek tiles need the internet or the offline cache; the region layers work regardless.
- **"enclosed" route error:** the point is ringed by slopes over the limit. Move it or raise the maximum slope.
- **First route takes a few seconds:** numba compiles once; later routes are fast.

## Data and credits

All terrain, imagery, weather and rover data are NASA and USGS products. The full list, with what each is used for, is in [SUBMISSION.md](SUBMISSION.md#nasa-data-used). Third-party frontend files and their licences are in [frontend/vendor/SOURCES.md](frontend/vendor/SOURCES.md); each assistant document's licence is in `data/docs/docs_sources.json`. The header shows the NASA Space Apps Challenge 2026 logo, unchanged, from the Space Apps brand page; no NASA insignia is used.

## Declaration of AI use

In line with the NASA Space Apps rules, we declare how AI was used in this project.

**In building MarsPath**
- The team used **Claude Code** (Anthropic), an AI coding assistant, to help write and review code, tests and documentation, and to help find and check data sources.
- The team defined the project and the science goals, chose the datasets and the design, directed the work, reviewed the results and ran the tests.
- The MarsPath logo is SVG code written with the same assistant.

**Inside the app**
- The science assistant uses **Google Gemini** (or optionally Anthropic Claude) to write answers, but only from passages retrieved from cited NASA and USGS documents. Each sentence is checked against those passages before it is shown; without a key or network it quotes the passage instead.
- Document search uses a local embedding model, **BAAI bge-small-en-v1.5**.

**Not generated by AI**
- All terrain, imagery, weather, radiation and rover data are real NASA and USGS products, listed with their sources.
- Every scientific number comes from a cited source; values that are team assumptions are labelled as such.

## License

MarsPath's own code and documentation are under the [MIT License](LICENSE). Leaflet (BSD-2-Clause), Three.js (MIT), NASA/USGS data and the assistant's documents keep their own terms. The Space Apps logo follows the Space Apps brand guidelines and is not covered by the MIT License.
