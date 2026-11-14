# Data Sources — Earth Analogs for Moon & Mars (Space Apps 2026)

> Most NASA Earth downloads need a free **Earthdata Login**: https://urs.earthdata.nasa.gov/users/new
> Do NOT download whole global datasets (many are terabytes). Clip to your area with AppEEARS or Google Earth Engine.
> Log every dataset you use — it must go in the project's **References** field.

## A. MOON (target side)
| What | Source | Link |
|---|---|---|
| Browse everything visually (start here) | NASA Moon Trek | https://trek.nasa.gov/moon/ |
| Browse + measure LRO layers | LROC QuickMap | https://quickmap.lroc.asu.edu |
| Elevation / slope (LOLA) | PDS Geosciences | https://pds-geosciences.wustl.edu/missions/lro/lola.htm |
| High-res polar DEMs, illumination | NASA PGDA | https://pgda.gsfc.nasa.gov/ |
| Temperature, cold traps (Diviner) | PDS Geosciences | https://pds-geosciences.wustl.edu/missions/lro/diviner.htm |
| All LRO instruments | PDS Geosciences | https://pds-geosciences.wustl.edu/missions/lro/ |
| Geologic map of the Moon | USGS Astrogeology | https://astrogeology.usgs.gov/search |
| Artemis III 9 candidate regions | NASA SVS | https://svs.gsfc.nasa.gov/5013 |
| Kaguya / SELENE (JAXA) | JAXA DARTS | https://darts.isas.jaxa.jp/planet/pdap/selene/ |
| Chandrayaan-2 (ISRO) | ISSDC PRADAN | https://pradan.issdc.gov.in |

## B. MARS (target side)
| What | Source | Link |
|---|---|---|
| Browse everything visually (start here) | NASA Mars Trek | https://trek.nasa.gov/mars/ |
| GIS tool with all Mars layers | JMARS (ASU) | https://jmars.asu.edu |
| Subsurface ice maps | SWIM project (PSI) | https://swim.psi.edu |
| Temperature, pressure, dust, wind (model) | Mars Climate Database (LMD/ESA/CNES) | https://www-mars.lmd.jussieu.fr/ |
| Global 5 m image mosaic | CTX Mosaic (Caltech Murray Lab) | https://murray-lab.caltech.edu/CTX/ |
| Very high-res images | HiRISE | https://www.uahirise.org/ |
| MOLA, THEMIS, CRISM, etc. | PDS Geosciences | https://pds-geosciences.wustl.edu/ |
| Mars Express HRSC, ExoMars TGO (ESA) | ESA Planetary Science Archive | https://psa.esa.int |
| Geologic maps | USGS Astrogeology | https://astrogeology.usgs.gov/search |

## C. EARTH (candidate side)
| What | Source | Link |
|---|---|---|
| Search all NASA Earth data | NASA Earthdata Search | https://search.earthdata.nasa.gov |
| Clip & download only your area (MODIS, EMIT, NASADEM…) | NASA AppEEARS | https://appeears.earthdatacloud.nasa.gov |
| Quick visual browsing | NASA Worldview | https://worldview.earthdata.nasa.gov |
| Minerals (clays, sulfates, carbonates, iron oxides) | NASA EMIT | https://earth.jpl.nasa.gov/emit/ |
| Elevation 30 m | NASADEM (in AppEEARS / Earthdata) | https://search.earthdata.nasa.gov |
| Dust / wind / climate reanalysis (MERRA-2) | NASA GES DISC | https://disc.gsfc.nasa.gov |
| Global processing in the cloud (fastest) | Google Earth Engine catalog | https://developers.google.com/earth-engine/datasets |
| Sentinel-1/2/3, Copernicus DEM (ESA) | Copernicus Data Space | https://dataspace.copernicus.eu |
| ESA geoscience datasets | ESA Open Science Catalog | https://opensciencedata.esa.int |
| Permafrost (ESA CCI) | ESA Climate Change Initiative | https://climate.esa.int/en/projects/permafrost/ |
| JAXA Earth data | JAXA G-Portal | https://gportal.jaxa.jp/gpr/ |
| 30 m DEM (JAXA ALOS AW3D30) | JAXA EORC | https://www.eorc.jaxa.jp/ALOS/en/aw3d30/ |
| Radar, day/night, all weather (CSA) | RADARSAT Constellation Mission | https://donnees-data.asc-csa.gc.ca/en/dataset/rcm |
| RADARSAT-1 open archive (CSA) | CSA Open Data | https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1 |
| SAR Python tutorial (CSA) | GitHub | https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial |
| Rock types worldwide | Macrostrat | https://macrostrat.org/map |
| Volcanoes worldwide | Smithsonian GVP | https://volcano.si.edu |
| Impact craters on Earth | Earth Impact Database | http://www.passc.net/EarthImpactDatabase/ |
| Known analog sites (for validation test) | USGS via data.gov | https://catalog.data.gov/dataset/known-terrestrial-analog-sites-for-planetary-science |
| Known analog sites catalogue | ESA | https://www.esa.int/Our_Activities/Preparing_for_the_Future/Discovery_and_Preparation/Cataloguing_otherworldly_landscapes_on_Earth |

## Download order (don't download everything)
1. Moon Trek + Mars Trek: look at your 2 targets, note coordinates.
2. Target-side numbers: LOLA slope + Diviner temps (Moon); MOLA + SWIM + MCD (Mars).
3. Earth: run global layers in Google Earth Engine (DEM slope, MODIS LST, aridity), only download EMIT for shortlisted places via AppEEARS.
4. Validation: USGS known analog sites list.
