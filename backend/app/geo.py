"""Mars coordinate conventions used everywhere in MarsPath.

* Body: Mars 2000 sphere, radius 3,396,190 m (IAU 2000, used by USGS products).
* Latitude: planetocentric degrees, north positive.
* Longitude: degrees, EAST positive. Jezero is ~77.5 E, identical in 0..360 and -180..180.
* API geometry: GeoJSON order [lon, lat].
* Analysis grid: a regular lon/lat grid (row 0 = north edge). Cell sizes in metres are
  derived from the sphere radius, so slope and distance are computed in metres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

MARS_RADIUS_M = 3_396_190.0
# PROJ definition of the Mars 2000 geographic CRS (sphere). Avoids Earth WGS84 defaults.
MARS_GEOGRAPHIC_PROJ = "+proj=longlat +R=3396190 +no_defs +type=crs"
COORDINATE_CONVENTION = {
    "body": "Mars",
    "datum": "Mars 2000 sphere, R = 3396190 m",
    "latitude": "planetocentric, degrees, north positive",
    "longitude": "degrees, east positive",
    "geometry_order": "GeoJSON [lon, lat]",
    "elevation": "metres relative to the source DEM's vertical datum (see layer metadata)",
}


def norm_lon(lon: float) -> float:
    """Return longitude in -180..180 (east positive)."""
    lon = ((lon + 180.0) % 360.0) - 180.0
    return lon


@dataclass
class Grid:
    west: float
    east: float
    south: float
    north: float
    width: int
    height: int

    @property
    def dlon(self) -> float:
        return (self.east - self.west) / self.width

    @property
    def dlat(self) -> float:
        return (self.north - self.south) / self.height

    @property
    def dy_m(self) -> float:
        return MARS_RADIUS_M * math.radians(self.dlat)

    def dx_m_rows(self) -> np.ndarray:
        """East-west cell size (m) for every row (shrinks with cos(lat))."""
        lats = self.north - (np.arange(self.height) + 0.5) * self.dlat
        return MARS_RADIUS_M * np.cos(np.radians(lats)) * math.radians(self.dlon)

    @property
    def mean_res_m(self) -> float:
        return float((self.dy_m + self.dx_m_rows().mean()) / 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(dlon=self.dlon, dlat=self.dlat, dy_m=self.dy_m, mean_res_m=self.mean_res_m,
                 crs=MARS_GEOGRAPHIC_PROJ, row0="north")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Grid":
        return cls(d["west"], d["east"], d["south"], d["north"], int(d["width"]), int(d["height"]))

    @classmethod
    def from_bbox(cls, west, south, east, north, res_m: float) -> "Grid":
        lat_c = (south + north) / 2
        dlat = math.degrees(res_m / MARS_RADIUS_M)
        dlon = math.degrees(res_m / (MARS_RADIUS_M * math.cos(math.radians(lat_c))))
        width = max(2, int(round((east - west) / dlon)))
        height = max(2, int(round((north - south) / dlat)))
        return cls(west, west + width * dlon, north - height * dlat, north, width, height)

    def contains(self, lon: float, lat: float) -> bool:
        lon = norm_lon(lon)
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def cell_of(self, lon: float, lat: float) -> tuple[int, int]:
        lon = norm_lon(lon)
        c = int((lon - self.west) / self.dlon)
        r = int((self.north - lat) / self.dlat)
        return min(max(r, 0), self.height - 1), min(max(c, 0), self.width - 1)

    def center_of(self, r: int, c: int) -> tuple[float, float]:
        return (self.west + (c + 0.5) * self.dlon, self.north - (r + 0.5) * self.dlat)

    def affine(self):
        from rasterio.transform import from_bounds
        return from_bounds(self.west, self.south, self.east, self.north, self.width, self.height)

    def leaflet_bounds(self) -> list:
        return [[self.south, self.west], [self.north, self.east]]


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def validate_lonlat(lon: float, lat: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude {lat} out of range -90..90")
    if not (-180.0 <= lon <= 360.0):
        raise ValueError(f"longitude {lon} out of range -180..360")
