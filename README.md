# Analog Fingerprint

**NASA Space Apps Challenge 2026:** *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars*
Official challenge: https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/

## What it does
No place on Earth is identical to the Moon or Mars. This project uses open NASA and partner-agency data (ESA, JAXA, CSA, ISRO) to find the best places on Earth to practice for a specific mission.

1. **Discoveries:** new Earth analog sites we identified, each with a scorecard showing what matches and what does not.
2. **Mission finder:** enter what you are testing (robot or human, maximum slope, temperature range, power source, ice drilling) and get a ranked list of Earth practice sites for a chosen Moon or Mars target.
3. **Proof:** a blind test showing the method finds well-known analog sites (Atacama, Haughton Crater, Death Valley, and others) on its own, plus all data sources.

## Targets
- **Moon:** Mons Mouton, a NASA Artemis III candidate landing region near the south pole
- **Mars:** Arcadia Planitia (shallow subsurface ice)
- **Mars:** Jezero Crater (ancient lake delta, Perseverance rover site)

## What Earth cannot reproduce
Gravity (Moon 0.17 g, Mars 0.38 g), the lunar vacuum, the thin Martian atmosphere, and the radiation environment. Every result states these limits.

## Repository layout
| Path | Contents |
|---|---|
| `IDEA.md` | **Start here:** the detailed project idea and questions for the team |
| `CLAUDE.md` | Project charter, standards, and quality gates |
| `DATA_SOURCES.md` | Download links for all datasets |
| `TEAM_TASKS.md` | Who does what, and when |
| `data/` | Data folders. Raw downloads stay local (git-ignored); only small processed files are committed. |

## Team
NASA Space Apps Challenge 2026 team. All data sources are credited in `REFERENCES.md` (in progress).
