"""EVA (Marswalk) model: suited walking speed vs grade, load and terrain.

All parameters are TEAM ASSUMPTIONS (config/eva_defaults.json) and are returned with every
route so the judge sees exactly what the numbers rest on.

Speed model: Tobler's hiking function (Tobler 1993),
    v(g) = v_flat * exp(-3.5 * |g + 0.05|) / exp(-3.5 * 0.05)
where g = dz/dx is the signed grade along the step. It is rescaled so v(0) = v_flat.
It is an Earth hiking model; using it for a suited astronaut on Mars is an assumption.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

from . import config

TOBLER_K = 3.5
TOBLER_OPT = 0.05


@dataclass
class EvaParams:
    max_slope_deg: float = 25.0
    caution_slope_deg: float = 15.0
    flat_speed_kmh: float = 3.0
    eva_hours: float = 4.0
    reserve_fraction: float = 0.25
    load_kg: float = 20.0
    load_speed_penalty_per_10kg: float = 0.05
    roughness_ref_m: float = 0.5
    roughness_max_m: float = 1.5
    roughness_caution_m: float = 0.75
    round_trip: bool = True
    crew_size: int = 2
    shared_load_kg: float = 0.0

    @classmethod
    def defaults(cls) -> "EvaParams":
        d = config.eva_defaults()
        kw = {k: d[k]["value"] for k in cls.__dataclass_fields__ if k in d}
        return cls(**kw)

    def merged(self, overrides: dict | None) -> "EvaParams":
        if not overrides:
            return self
        kw = asdict(self)
        for k, v in overrides.items():
            if k in kw and v is not None:
                kw[k] = type(kw[k])(v) if not isinstance(kw[k], bool) else bool(v)
        p = EvaParams(**kw)
        p.validate()
        return p

    def validate(self) -> None:
        if not (1 <= self.max_slope_deg <= 60):
            raise ValueError("max_slope_deg must be 1..60")
        if not (0.2 <= self.flat_speed_kmh <= 10):
            raise ValueError("flat_speed_kmh must be 0.2..10")
        if not (0.25 <= self.eva_hours <= 12):
            raise ValueError("eva_hours must be 0.25..12")
        if not (0 <= self.reserve_fraction < 0.9):
            raise ValueError("reserve_fraction must be 0..0.9")
        if not (0 <= self.load_kg <= 200):
            raise ValueError("load_kg must be 0..200")
        if not (1 <= self.crew_size <= 4):
            raise ValueError("crew_size must be 1..4")
        if not (0 <= self.shared_load_kg <= 400):
            raise ValueError("shared_load_kg must be 0..400")
        if self.roughness_max_m <= 0 or self.roughness_ref_m <= 0:
            raise ValueError("roughness thresholds must be > 0")

    # ---- derived quantities
    @property
    def load_per_person_kg(self) -> float:
        """Own load plus an equal share of the crew's shared kit (the pair walks together at one pace)."""
        return self.load_kg + self.shared_load_kg / self.crew_size

    @property
    def load_factor(self) -> float:
        return max(0.3, 1.0 - self.load_speed_penalty_per_10kg * self.load_per_person_kg / 10.0)

    @property
    def flat_speed_ms(self) -> float:
        return self.flat_speed_kmh / 3.6 * self.load_factor

    @property
    def max_grade(self) -> float:
        return math.tan(math.radians(self.max_slope_deg))

    @property
    def usable_minutes(self) -> float:
        return self.eva_hours * 60 * (1 - self.reserve_fraction)

    def speed_ms(self, grade: float) -> float:
        return self.flat_speed_ms * math.exp(-TOBLER_K * abs(grade + TOBLER_OPT)) / math.exp(-TOBLER_K * TOBLER_OPT)

    def assumptions(self) -> list[str]:
        return [
            f"Suited walking speed on flat ground {self.flat_speed_kmh} km/h, reduced {100*(1-self.load_factor):.0f}% "
            f"for a {self.load_per_person_kg:g} kg load per person ({self.load_speed_penalty_per_10kg*100:.0f}% per 10 kg) - team assumption.",
            f"Crew of {self.crew_size} walking together at one pace" + (f"; {self.shared_load_kg:g} kg of shared kit split equally "
            f"({self.shared_load_kg / self.crew_size:g} kg each) on top of {self.load_kg:g} kg personal load." if self.shared_load_kg else
            f"; {self.load_kg:g} kg carried by each.") + " Times apply to the whole crew.",
            "Speed varies with grade by Tobler's hiking function (Tobler 1993), rescaled to the flat speed - an Earth model used as an assumption.",
            f"Grades steeper than {self.max_slope_deg:g} deg (up or down) are not walked; cells whose slope exceeds it are avoided.",
            f"Roughness slows walking (speed halves at {self.roughness_ref_m:g} m); cells rougher than {self.roughness_max_m:g} m are avoided.",
            "Geologic units mapped as sand/bedforms or rim carry a time multiplier (config/geo_penalties.json).",
            f"EVA budget {self.eva_hours:g} h with {self.reserve_fraction*100:.0f}% reserve"
            + (" and the walk back to the start included." if self.round_trip else "."),
            "Distances are horizontal on the Mars 2000 sphere (R = 3396.19 km).",
        ]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["derived"] = {"load_factor": round(self.load_factor, 3), "load_per_person_kg": round(self.load_per_person_kg, 1), "effective_flat_speed_kmh": round(self.flat_speed_ms * 3.6, 3),
                        "usable_minutes": round(self.usable_minutes, 1)}
        return d
