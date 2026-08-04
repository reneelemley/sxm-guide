"""
TODAY IN SXM — decision engine.

Pure functions plus small lookup tables. No I/O here; build_today.py does that.
Every function is independently testable.

Design note: this module emits STATE KEYS only, never sentences. All wording
lives in copy.json, which Renee owns. A state with no copy renders nothing.
"""

from __future__ import annotations
import json, datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


T = load("tables.json")
BEACHES = load("beaches.json")["beaches"]


# ---------------------------------------------------------------- season

def season_band(d: dt.date) -> str:
    m, day = d.month, d.day
    if (m == 12 and day >= 20) or (m == 1 and day <= 5):
        return "PEAK_HOLIDAY"
    if m == 12 and 15 <= day <= 19:
        return "HIGH"
    if (m == 1 and day >= 6) or m in (2, 3) or (m == 4 and day <= 15):
        return "HIGH"
    if m == 11 or (m == 12 and day <= 14):
        return "SHOULDER_FALL"
    if (m == 4 and day >= 16) or m == 5:
        return "SHOULDER_SPRING"
    if m in (6, 7, 8):
        return "LOW"
    if m in (9, 10):
        return "DEAD"
    raise ValueError(f"unreachable date {d}")


# ---------------------------------------------------------------- traffic

def pax_band_index(pax: int) -> int:
    for i, b in enumerate(T["pax_bands"]):
        if b["max"] is None or pax <= b["max"]:
            return i
    return len(T["pax_bands"]) - 1


def severity(band: str, pax: int) -> str:
    return T["traffic_matrix"][band][pax_band_index(pax)]


def anomaly(pax: int, month: int) -> tuple[str, float]:
    expected = T["expected_pax"][str(month)]
    ratio = pax / expected if expected else 0.0
    for b in T["anomaly_bands"]:
        if b["max"] is None or ratio < b["max"]:
            return b["key"], round(ratio, 2)
    return T["anomaly_bands"][-1]["key"], round(ratio, 2)


# ---------------------------------------------------------------- events

def easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    day = (h + l - 7 * m + 33 * month + 19) % 32
    return dt.date(year, month, day)


def french_carnival(year: int) -> tuple[dt.date, dt.date]:
    """Runs into Ash Wednesday, when Vaval burns. Mardi Gras = Easter - 47."""
    mardi_gras = easter(year) - dt.timedelta(days=47)
    return mardi_gras - dt.timedelta(days=11), mardi_gras + dt.timedelta(days=1)


def _range_contains(d: dt.date, pair) -> bool:
    if not pair:
        return False
    a = dt.date.fromisoformat(pair[0])
    b = dt.date.fromisoformat(pair[1])
    return a <= d <= b


def events(d: dt.date) -> list[str]:
    out, y, m, day = [], d.year, d.month, d.day

    fc_start, fc_end = french_carnival(y)
    if fc_start <= d <= fc_end:
        out.append("EVENT_FRENCH_CARNIVAL")

    if _range_contains(d, T["dutch_carnival"].get(str(y))):
        out.append("EVENT_DUTCH_CARNIVAL")

    if _range_contains(d, T["regatta"].get(str(y))):
        out.append("EVENT_REGATTA")

    e = easter(y)
    dutch_fixed = {(1, 1), (4, 27), (4, 30), (5, 1), (7, 1), (10, 10), (11, 11), (12, 25), (12, 26)}
    dutch_movable = {
        e - dt.timedelta(days=2), e, e + dt.timedelta(days=1),
        e + dt.timedelta(days=39), e + dt.timedelta(days=49),
    }
    if (m, day) in dutch_fixed or d in dutch_movable:
        out.append("EVENT_PUBLIC_HOLIDAY_DUTCH")

    # 28 May is Saint-Martin's own abolition day, distinct from Guadeloupe/Martinique
    french_fixed = {(1, 1), (5, 1), (5, 8), (5, 28), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)}
    french_movable = {e + dt.timedelta(days=1), e + dt.timedelta(days=39), e + dt.timedelta(days=50)}
    if (m, day) in french_fixed or d in french_movable:
        out.append("EVENT_PUBLIC_HOLIDAY_FRENCH")

    return out


# ---------------------------------------------------------------- closures

def closures(band: str) -> list[str]:
    return ["CLOSURE_SEPTEMBER"] if band == "DEAD" else []


# ---------------------------------------------------------------- sargassum

def sargassum(month: int) -> str:
    if 4 <= month <= 9:
        return "SARGASSUM_LIKELY"
    if month in (3, 10):
        return "SARGASSUM_POSSIBLE"
    return "SARGASSUM_UNLIKELY"


# ---------------------------------------------------------------- beaches

def _in_arc(deg: float, arc) -> bool:
    lo, hi = arc
    deg %= 360
    return (lo <= deg <= 360 or 0 <= deg <= hi) if lo > hi else (lo <= deg <= hi)


def swell_state(height: float, direction: float, period: float) -> str:
    """Period is the discriminator: groundswell wraps into leeward bays, chop does not."""
    s = T["swell"]
    if height is None or direction is None:
        return "SWELL_DATA_STALE"
    if period is not None and period >= s["groundswell_min_period"] \
            and _in_arc(direction, s["nw_arc"]) and height >= s["min_height"]:
        return "SWELL_NORTH_WEST_ROUGH"
    if _in_arc(direction, s["e_arc"]) and height >= s["min_height"]:
        return "SWELL_EAST_CHOPPY"
    return "SWELL_CALM"


def beaches_for(state: str, month: int) -> dict:
    rough, calm, weed = [], [], []
    for b in BEACHES:
        if state == "SWELL_NORTH_WEST_ROUGH":
            (rough if b["nw_swell"] == "high" else calm).append(b["n"])
        elif state == "SWELL_EAST_CHOPPY":
            (rough if b["chop"] == "high" else calm).append(b["n"])
        if 3 <= month <= 10 and b["sargassum"] == "high":
            weed.append(b["n"])
    return {"rough": rough, "calm": calm, "sargassum_risk": weed}


def crowd_lists() -> dict:
    return {
        "avoid":  [b["n"] for b in BEACHES if b["crowd"] == "exposed"],
        "escape": [b["n"] for b in BEACHES if b["crowd"] == "absorbs"],
    }


# ---------------------------------------------------------------- resolver

PRIORITY = [
    "bridge", "traffic", "anomaly", "swell", "sargassum",
    "crowd", "event", "closure", "specials",
]

# The bug in the old build: two blocks could both fire and contradict.
MUTUALLY_EXCLUSIVE = [
    {"TRAFFIC_EMPTY", "TRAFFIC_QUIET", "TRAFFIC_NORMAL",
     "TRAFFIC_BUSY", "TRAFFIC_CONGESTED", "TRAFFIC_GRIDLOCK",
     "TRAFFIC_ZERO_SHIPS_STILL_BUSY"},
    {"SWELL_NORTH_WEST_ROUGH", "SWELL_EAST_CHOPPY", "SWELL_CALM", "SWELL_DATA_STALE"},
    {"SARGASSUM_LIKELY", "SARGASSUM_POSSIBLE", "SARGASSUM_UNLIKELY"},
]


def resolve(slots: list[str], limit: int = 3) -> list[str]:
    """Pick at most `limit` slots, honouring priority and never emitting a contradiction."""
    order = {k: i for i, k in enumerate(PRIORITY)}

    def rank(s: str) -> int:
        for k, i in order.items():
            if s.lower().startswith(k) or s.lower().startswith(k.rstrip("s")):
                return i
        return len(PRIORITY)

    chosen: list[str] = []
    for s in sorted(dict.fromkeys(slots), key=rank):
        if any(s in group and any(c in group for c in chosen) for group in MUTUALLY_EXCLUSIVE):
            continue
        chosen.append(s)
        if len(chosen) >= limit:
            break
    return chosen
