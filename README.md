# MarsPath

**NASA Space Apps Challenge 2026:** *Interplanetary Survival Guide: Martian Map*
Official challenge: https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/

MarsPath is a browser-based, terrain-aware route planner for a human Marswalk. It combines data from several NASA Mars missions into one layered map of a study region, suggests a route from a start point to a destination, and shows the distance, elevation profile, slope and caution flags for that route, with the source of every number. The core works offline once a region is packaged.

## First study region: Jezero Crater
| Item | Value | Source |
|---|---|---|
| Center | 18.41° N, 77.69° E (planetocentric, east-positive, 0–360°) | [IAU/USGS Gazetteer, Jezero](https://planetarynames.wr.usgs.gov/Feature/14300) |
| Diameter | 47.52 km | same |
| Why | Ancient lake and river delta; NASA's Perseverance rover has explored it since February 2021 | [Stack et al. 2020](https://link.springer.com/article/10.1007/s11214-020-00739-x) |

## Data
| Dataset | Use | Resolution | Source |
|---|---|---|---|
| Mars 2020 Science Investigation CTX DEM mosaic | Main elevation, slope and route cost | 20 m/pixel | [USGS Astrogeology](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic) |
| Mars 2020 TRN HiRISE DTM mosaic | Detailed zoom area (stretch) | 1 m/pixel | [USGS Astrogeology](https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic) |
| MGS MOLA MEGDR | Regional overview | ~463 m/pixel | [NASA PDS Geosciences](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) |
| NASA Mars Trek | Imagery and layer browsing | varies | [trek.nasa.gov/mars](https://trek.nasa.gov/mars/) |
| USGS-NASA geologic maps of Mars | Geology layer and science stops | varies | [USGS Astrogeology](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars) |
| Perseverance raw images | Science-stop images | n/a | [NASA Mars 2020](https://mars.nasa.gov/mars2020/multimedia/raw-images/) |

Raw downloads are kept outside the repository (`C:\NASA_DATA`). Only small processed files go in `data/processed/`.

## Limitations
MarsPath is a prototype planning aid, not a certified navigation or safety system. Route costs are relative and depend on a stated slope-cost model. Packaged data has a date and shows no live conditions.
