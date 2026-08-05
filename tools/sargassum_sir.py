#!/usr/bin/env python3
"""
NOAA Sargassum Inundation Risk (SIR v1.5) reader.

Replaces the old calendar rule ("it is July, therefore sargassum") with an
actual daily observation of the water around this island.

Source
------
NOAA/AOML CoastWatch Caribbean node, in collaboration with NOAA/CoastWatch
OceanWatch and the University of South Florida.
    https://cwcgom.aoml.noaa.gov/SIR/

The product takes USF's AFAI (Alternative Floating Algae Index) satellite
fields, analyses them in a 50-100 km neighbourhood of every coastal pixel,
differences that against a multiday baseline, and classifies the result into
four risk levels:

    0 low   1 warning   2 medium   3 high

Licence: "The data may be used and redistributed for free but is not intended
for legal use, since it may contain inaccuracies." NOAA also labels SIR an
experimental product still subject to validation. Both facts are carried
through to today.json so the site can say so.

Why not raw AFAI
----------------
Thresholding raw AFAI near the coast does not work, and fails in a way that
looks plausible. Tested against the 2016-2026 archive for a box over this
island, raw AFAI peaks in November, December and January - the months with the
LEAST sargassum - because the index saturates on sun glint and whitecaps, which
are worst in the winter swell season. A naive detector would have shouted
loudest when the water was cleanest. The SIR baseline differencing removes
that, and the seasonal shape it produces is the correct one: high April to
September, near zero October to January.

Failure policy
--------------
Every failure path returns None. build_today.py then falls back to the calendar
rule and flags the day as unobserved. This module must never break the build.
"""
from __future__ import annotations

import datetime as dt
import io
import math
import re
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://cwcgom.aoml.noaa.gov/SIR/KMZ/sargassum_risk_{ymd}.kmz"
ATTRIBUTION = "NOAA/AOML CoastWatch & University of South Florida - Sargassum Inundation Risk v1.5 (experimental)"
SOURCE_URL = "https://cwcgom.aoml.noaa.gov/SIR/"

# Sint Maarten / Saint-Martin only. Deliberately tight: Anguilla sits just
# north at 18.2 and St Barths east at -62.83, and neither should colour our
# reading. Validated at 466 coastal vertices.
BBOX = {"lon_min": -63.20, "lon_max": -62.95, "lat_min": 17.99, "lat_max": 18.13}
CENTRE = (-63.06, 18.06)

# How many days back to walk. The product is daily but publishes in arrears -
# on 4 August the newest available was 3 August.
MAX_LOOKBACK_DAYS = 5
TIMEOUT_SECONDS = 45

LEVEL_NAMES = {0: "low", 1: "warning", 2: "medium", 3: "high"}

_PLACEMARK = re.compile(r"<Placemark", re.I)
_RISK = re.compile(r'name="risk">(-?\d+)<')
_COORDS = re.compile(r"<coordinates>([\s\S]*?)</coordinates>", re.I)


# ------------------------------------------------------------------ geometry

def sector_of(lon: float, lat: float) -> str:
    """Which coast a point sits on, as seen from the middle of the island.

    N and W are the Caribbean/leeward shores (Grand Case, Baie Rouge, Mullet).
    E and S are the Atlantic/windward shores (Orient, Dawn, Guana), which is
    where sargassum lands - it rides the North Equatorial Current in from the
    east. Confirmed in the data: on 3 August 2026 every one of the 51 high-risk
    vertices fell in E or S, and none in N or W.
    """
    ang = (math.degrees(math.atan2(lon - CENTRE[0], lat - CENTRE[1])) + 360) % 360
    if ang < 45 or ang >= 315:
        return "N"
    if ang < 135:
        return "E"
    if ang < 225:
        return "S"
    return "W"


# S is deliberately in neither. The south coast is two coasts: Guana and Dawn
# at its eastern end face the open Atlantic, while Mullet, Maho and Great Bay
# at its western end are sheltered Caribbean water. Counting the whole of it as
# windward inflates the reading; counting it as leeward hides a real one. It
# still contributes to island_max, it just does not decide the split.
WINDWARD = ("E",)
LEEWARD = ("N", "W")


def _in_bbox(lon: float, lat: float) -> bool:
    return (BBOX["lon_min"] <= lon <= BBOX["lon_max"]
            and BBOX["lat_min"] <= lat <= BBOX["lat_max"])


# -------------------------------------------------------------------- parse

def parse_kml(kml: str) -> list[tuple[float, float, int]]:
    """Pull (lon, lat, risk) for every coastal vertex inside the bbox.

    Pure function - no network - so the tests can run against a fixture.
    """
    out: list[tuple[float, float, int]] = []
    for chunk in _PLACEMARK.split(kml)[1:]:
        rm = _RISK.search(chunk)
        cm = _COORDS.search(chunk)
        if not rm or not cm:
            continue
        blob = cm.group(1)
        # Cheap reject before the expensive split. Everything we care about is
        # in the -63.x / -62.9x longitudes.
        if "-63." not in blob and "-62.9" not in blob:
            continue
        risk = int(rm.group(1))
        for token in blob.split():
            parts = token.split(",")
            if len(parts) < 2:
                continue
            try:
                lon, lat = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            if _in_bbox(lon, lat):
                out.append((lon, lat, risk))
    return out


def summarise(points: list[tuple[float, float, int]]) -> dict | None:
    """Collapse vertices into per-sector and island-wide risk."""
    if not points:
        return None
    by_sector: dict[str, list[int]] = {}
    for lon, lat, risk in points:
        by_sector.setdefault(sector_of(lon, lat), []).append(risk)

    sectors = {s: {"max": max(v), "n": len(v)} for s, v in by_sector.items()}
    all_risk = [r for _, _, r in points]

    wind = [sectors[s]["max"] for s in WINDWARD if s in sectors]
    lee = [sectors[s]["max"] for s in LEEWARD if s in sectors]

    return {
        "island_max": max(all_risk),
        "island_mean": round(sum(all_risk) / len(all_risk), 2),
        "windward_max": max(wind) if wind else None,
        "leeward_max": max(lee) if lee else None,
        "sectors": sectors,
        "vertices": len(points),
    }


# ------------------------------------------------------------------- fetch

def _download(ymd: str) -> str | None:
    """Return the KML text for one date, or None."""
    req = Request(BASE.format(ymd=ymd), headers={"User-Agent": "RR-Guide-To-SXM/1.0"})
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not name:
                return None
            return z.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, UnicodeError):
        return None


def observe(day: dt.date | None = None, lookback: int = MAX_LOOKBACK_DAYS) -> dict | None:
    """Newest SIR reading on or before `day`, or None if nothing is reachable.

    Walks backwards because the product publishes a day or two in arrears. The
    date actually used is returned so the banner can admit its age.
    """
    day = day or dt.date.today()
    for back in range(lookback + 1):
        d = day - dt.timedelta(days=back)
        kml = _download(d.strftime("%Y%m%d"))
        if kml is None:
            continue
        summary = summarise(parse_kml(kml))
        if summary is None:
            continue
        summary.update({
            "observed_date": d.isoformat(),
            "days_old": back,
            "source": SOURCE_URL,
            "attribution": ATTRIBUTION,
            "experimental": True,
        })
        return summary
    return None


if __name__ == "__main__":
    import json
    import sys

    target = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    result = observe(target)
    if result is None:
        print("SIR unavailable - the build will fall back to the calendar rule.")
        raise SystemExit(1)
    print(json.dumps(result, indent=1))
    print(f"\n{result['observed_date']} ({result['days_old']}d old)  "
          f"island max={LEVEL_NAMES[result['island_max']]}  "
          f"windward={result['windward_max']}  leeward={result['leeward_max']}")
