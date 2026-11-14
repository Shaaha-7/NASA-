# CLAUDE.md: MarsPath working rules

**Project:** MarsPath, NASA Space Apps Challenge 2026, *Interplanetary Survival Guide: Martian Map*
**Official page:** https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/
**Deadline:** Sunday Nov 15, 2026, 11:59 PM local time. The user is a team member, not the lead; the team's plan is the "MarsPath — Project Outline" PDF.

## Rules
1. **Never guess.** Research first; mark anything unconfirmed as UNVERIFIED.
2. **Every scientific number has a source** (dataset, product, resolution, date).
3. **Never invent values.** Missing data is null or "not available", never 0 unless 0 was measured.
4. **Mars coordinates:** planetocentric latitude, east-positive longitude. Confirm each raster's CRS before using it; never assume Earth WGS84.
5. **Never compute slope from imagery or hillshade**, only from numerical elevation.
6. **Never call terrain "safe"**; say lower or higher modelled traversal cost under stated assumptions.
7. **Raw data stays in `C:\NASA_DATA`**, outside OneDrive and Git. Only small processed files go in `data/processed/`.
8. **Official demo limit:** a video of 30 seconds or less, or 7 slides or fewer. The outline's 2–3 minute video does not comply.
9. **Scope order when time is short:** elevation → slope → route → route on map with profile and warnings → sources; then offline, pins, 3D globe; AI assistant last.
