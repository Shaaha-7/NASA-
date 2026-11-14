# Project Idea: Analog Fingerprint

> **Team: please read this whole page, then add your suggestions** (see "Questions for the team" at the bottom).
> Open a GitHub Issue or tell the team lead. Deadline for suggestions: **Saturday night**, so we can start building.

**Challenge:** NASA Space Apps 2026, *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars*
**Official page:** https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/
**Submission closes:** Sunday Nov 15, 2026, 11:59 PM local time. **Team target: submit by Sunday 10 PM.**

---

## 1. The problem, in plain English

NASA tests robots and trains astronauts on Earth before they fly. They use places that are **partly** like the Moon or Mars: the Atacama Desert, Haughton Crater, Death Valley.

But:
- **No place on Earth is identical** to the Moon or Mars. Gravity, the lunar vacuum, the thin Martian air and space radiation can never be copied.
- Only a **few** analog places are well known, and the challenge says even those are **"not entirely well characterized."**
- A place can be great for one test and useless for another. A rocky slope is good for testing rover wheels and useless for testing an ice drill.

**NASA asks us to:** use open NASA and other space-agency data to **find and describe new places on Earth** that match the Moon or Mars, and present the findings as a map, visualization or tool.

---

## 2. Our answer in one sentence

> **A website where a mission team says what they are testing (robot or human, and its limits), and we tell them the best places on Earth to practice for a specific Moon or Mars site, with proof from NASA data and an honest list of what does NOT match.**

Plus our own **discoveries**: 2 new Earth places we found with this method.

---

## 3. What the website looks like (3 screens)

### Screen 1: Discoveries (front page)
What judges see first. It holds our main finding.
- Our **2 best new Earth analog places**, each with:
  - Name, coordinates and a map
  - A **scorecard** (radar chart) of how well it matches the Moon or Mars target on each feature
  - **What matches** and **what does not match**
  - **Comparison with a famous site** (for example, "beats Atacama on frozen ground, loses on dryness")
  - A short written **site report**

### Screen 2: Mission finder (the main tool)
The user fills in a short form:

| Question | Choices | Matched against |
|---|---|---|
| Target | Moon south pole (Mons Mouton) / Mars Arcadia Planitia / Mars Jezero Crater | Fixed target scorecards |
| Who is testing | Robot (rover) / Human (astronaut team) | Changes which features matter |
| Steepest slope it can handle | Number, in degrees | Elevation maps → slope |
| Coldest and hottest working temperature | Numbers, in °C | Temperature maps |
| Power | Solar / not solar | Sunlight, shadows, dust |
| Needs to drill for ice? | Yes / No | Frozen-ground and ice maps |

**Result:**
- A **top-10 list** of Earth practice sites, each with a match score per feature
- A **map** showing where they are
- For each site: **"This site tests: …"** and **"This site does NOT test: gravity, air pressure, radiation, …"**
- Best months to go (January vs July), if time allows

**Example:**
> Input: rover, climbs up to 20°, works from −40 °C to +40 °C, solar powered, drills ice, target Mars Arcadia Planitia.
> Output: "Best Earth practice sites: 1. Place A, 2. Place B, 3. Place C. Place A matches Arcadia on slope 85%, frozen ground 70%, cold 60%. It does not test gravity (Mars is 0.38 g) or air pressure (Mars is under 1% of Earth's)."

### Screen 3: Proof
Why judges should believe us.
- **Blind test:** we run our method **without telling it** which places are famous analogs. If it ranks Atacama, Haughton Crater, the Dry Valleys and others highly by itself, the method works.
- How the scoring works, in simple words
- **All data sources**, with credits

---

## 4. Our targets (why these three)

| Target | Why |
|---|---|
| **Moon: Mons Mouton** (south pole) | One of NASA's 9 published Artemis III candidate landing regions. A wide, flat-topped mountain: safe ground, long sunlight, close to very cold dark craters that may hold ice. Well covered by NASA data. |
| **Mars: Arcadia Planitia** | A flat plain with ice just under the surface. The most-cited candidate for future human landings. Fits rover, astronaut and ice-drilling missions. |
| **Mars: Jezero Crater** | An ancient lake and river delta where NASA's Perseverance rover is driving now, which gives real ground measurements to check against. |

**Not included:** asteroids (the challenge only asks for the Moon and Mars, and asteroids have almost no gravity, which Earth cannot imitate).

Exact coordinates and measured conditions for each target are **Phase 1** and will be written in `TARGETS.md` with NASA sources.

---

## 5. How the method works

1. **Describe the target** in numbers: slope, temperature, rock type, ice, dust, sunlight.
2. **Describe every place on Earth** the same way, on one shared grid (graph paper over the whole Earth, about 5 km squares).
3. **Compare feature by feature.** We never compare raw values that cannot match (the Moon's coldest craters are about −235 °C; nowhere on Earth is). Instead we compare **patterns and rankings**: "one of the coldest and driest places on its planet," "slopes in the same range."
4. **Weight the features by mission.** A rover cares most about slope and ground; an ice drill cares most about frozen ground.
5. **Two-step search** so we don't download all of Earth:
   - Rough scan of the whole Earth with small global layers
   - Detailed data only for the best ~20 places
6. **Blind test** on famous sites to prove it works.

### What Earth can and cannot match
| Can match (we score these) | Cannot match (we always state these) |
|---|---|
| Slope and roughness of the ground | Gravity (Moon 0.17 g, Mars 0.38 g) |
| Rock and mineral type | The Moon's vacuum |
| Extreme cold, dryness | Mars's very thin air |
| Frozen ground and ice | Space radiation |
| Very low sun and long shadows (high latitudes) | The sharp, jagged shape of Moon dust |
| Dust and wind | |

---

## 6. Data we use

**NASA (main):** LRO for the Moon (elevation, temperature), Mars orbiter data (elevation, ice maps), MODIS (Earth temperature), GPM (rainfall), NASADEM (Earth elevation), EMIT (minerals).
**Other agencies:** ESA (Copernicus, Mars Express), JAXA (Kaguya, ALOS elevation), CSA (RADARSAT radar), ISRO (Chandrayaan-2).

Full list with links: `DATA_SOURCES.md`.

---

## 7. How we split the work (by job, not by planet)

Everyone works on **all three targets** for their job, so there is one method and one set of code.

| Person | Job | Coder? |
|---|---|---|
| 1 | **Earth data:** downloads Earth layers once and prepares clean shared files | Yes |
| 2 | **Moon and Mars data:** data and scorecards for Mons Mouton, Arcadia and Jezero | Yes |
| 3 | **Scoring and proof:** comparison code and the blind test | Yes |
| 4 | **Website:** the 3 screens, online, works on phone and laptop | Yes |
| 5 | **Team lead and discoveries:** keeps time, picks the 2 discoveries, writes site reports | No |
| 6 | **Story and submission:** 30-second video or 7 slides, references, submission checklist | No |

With 5 people, jobs 5 and 6 merge. Claude (AI) writes code alongside persons 1–4 and fact-checks every number.

**First build rule:** tonight we build one thin version of the whole thing (one target, one feature, one score, shown on the website) so we know all the pieces connect. Then everyone widens their own part.

---

## 8. Why this can be a top project

The 5 judging criteria (each scored 1 to 5) and our answer:

| Criterion | Our answer |
|---|---|
| **Impact** | Real mission teams could use it to choose where to test before they fly. |
| **Creativity** | Matches places to a specific robot's limits, not just "looks like Mars." Few tools do this. |
| **Validity** | Blind test, every number sourced, honest list of what doesn't match. |
| **Relevance** | NASA data drives every score. |
| **Presentation** | A discovery up front, a tool to click, and proof. |

**Honest risks:**
- We may find that no new place beats the famous ones. If so, we report that honestly and present "the best site per mission," which is still a finding.
- Time is short. If we fall behind, we drop Jezero and the January/July months first, not the proof.

---

## 9. Questions for the team

Please answer these (GitHub Issue, or tell the team lead):

1. Which job (1–6) do you want?
2. Is anything in the idea unclear?
3. Do you know any lesser-known place on Earth (deserts, volcanoes, caves, frozen ground, salt flats) that might be a good Moon or Mars analog? Local knowledge can be the discovery.
4. Is there anything in the mission finder form you would add or remove?
5. Any skills we haven't used (video, design, GIS, machine learning)?
