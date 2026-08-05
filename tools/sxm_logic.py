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

def sargassum_calendar(month: int) -> str:
    """Fallback only. A rule about the month, not a look at the water.

    Kept because the satellite read can fail, but every state it returns is
    suffixed so the copy can admit it is a guess.
    """
    if 4 <= month <= 9:
        return "SARGASSUM_LIKELY_UNOBSERVED"
    if month in (3, 10):
        return "SARGASSUM_POSSIBLE_UNOBSERVED"
    return "SARGASSUM_UNLIKELY_UNOBSERVED"


# The gap that makes a split worth mentioning. SIR levels are 0-3, and one
# whole level between the Atlantic and Caribbean shores is the difference
# between "go to Grand Case instead" and noise.
SPLIT_THRESHOLD = 1


def sargassum_state(obs: dict | None, month: int) -> str:
    """Observed risk if we have it, calendar if we do not.

    `obs` is the summary from sargassum_sir.observe(). The split states are the
    genuinely useful ones: they say the windward side is fouled and the
    Caribbean side is not, which is an actual instruction to a visitor.
    """
    if not obs:
        return sargassum_calendar(month)

    if obs.get("days_old", 0) > 3:
        return "SARGASSUM_OBSERVED_STALE"

    wind, lee = obs.get("windward_max"), obs.get("leeward_max")
    level = obs.get("island_max", 0)

    if wind is not None and lee is not None and wind - lee >= SPLIT_THRESHOLD:
        return "SARGASSUM_WINDWARD_ONLY_HIGH" if wind >= 3 else "SARGASSUM_WINDWARD_ONLY"

    return {
        0: "SARGASSUM_NONE",
        1: "SARGASSUM_TRACE",
        2: "SARGASSUM_MODERATE",
        3: "SARGASSUM_HIGH",
    }.get(level, "SARGASSUM_OBSERVED_STALE")


def sargassum_beach_risk(obs: dict | None) -> dict:
    """Per-beach observed level, mapped through each beach's coast sector.

    Honest limitation: SIR analyses a 50-100 km neighbourhood around each
    coastal pixel, so neighbouring beaches share nearly all their input. This
    resolves Atlantic-side from Caribbean-side. It does not resolve Orient from
    Le Galion, and the copy must not pretend otherwise.
    """
    if not obs:
        return {}
    sectors = obs.get("sectors", {})
    out = {}
    for b in BEACHES:
        sec = _face_sector(b.get("faces", ""))
        if sec and sec in sectors:
            out[b["n"]] = sectors[sec]["max"]
    return out


def _face_sector(faces: str) -> str | None:
    """Primary compass sector from a beach's aspect string, e.g. 'E/NE' -> 'E'."""
    first = faces.split("/")[0].strip().upper()
    if not first:
        return None
    if first.startswith("N"):
        return "N"
    if first.startswith("S"):
        return "S"
    if first.startswith("E"):
        return "E"
    if first.startswith("W"):
        return "W"
    return None


# ---------------------------------------------------------------- beaches

def _in_arc(deg: float, arc) -> bool:
    lo, hi = arc
    deg %= 360
    return (lo <= deg <= 360 or 0 <= deg <= hi) if lo > hi else (lo <= deg <= hi)


def swell_state(height, direction, period, wind_kt=None):
    """Graded, and routed on direction first.

    Calibrated against the eastern Caribbean swell climatology: the ordinary
    east trade state is ~1.5-1.7m at ~8s, so the old 1.5m/9s trigger fired on
    roughly half of all days. North swell is 2.0-2.5m at 10.2-10.6s.

    Period is a trigger in its own right, not just a discriminator - 1.5m at
    13s dumps harder on a steep beach than 2.5m at 7s.
    """
    s = T["swell"]
    if height is None or direction is None:
        return "SWELL_DATA_STALE"

    if _in_arc(direction, s["nw_arc"]):
        sev, al, wa = s["severe"], s["alert"], s["watch"]
        if height >= sev["height"] or (period or 0) >= sev["period"]:
            return "SWELL_NORTH_WEST_DANGEROUS"
        if height >= al["height"] and (period or 0) >= al["period"]:
            return "SWELL_NORTH_WEST_ROUGH"
        if height >= wa["height"] and (period or 0) >= wa["period"]:
            return "SWELL_NORTH_WEST_ROUGH"

    if wind_kt is not None and wind_kt >= s["wind_kt_unpleasant"]:
        return "SWELL_EAST_WINDY"
    if _in_arc(direction, s["e_arc"]) and height >= s["east_choppy_wave"]:
        return "SWELL_EAST_CHOPPY"

    c = s["calm"]
    if height < c["wave"] and (period or 0) < c["period"] \
            and (wind_kt is None or wind_kt < c["wind_kt"]):
        return "SWELL_CALM"
    return "SWELL_CALM"


def beaches_for(state: str, month: int) -> dict:
    rough, calm, weed = [], [], []
    for b in BEACHES:
        if state.startswith("SWELL_NORTH_WEST"):
            (rough if b["nw_swell"] == "high" else calm).append(b["n"])
        elif state in ("SWELL_EAST_CHOPPY", "SWELL_EAST_WINDY"):
            (rough if b.get("wind") == "exposed" else calm).append(b["n"])
        if 3 <= month <= 10 and b["sargassum"] == "high":
            weed.append(b["n"])
    return {"rough": rough, "calm": calm, "sargassum_risk": weed,
            "high_rip": [b["n"] for b in BEACHES if b.get("rip") in ("high", "severe")],
            "wind_spots": [b["n"] for b in BEACHES if b.get("wind") == "better"]}


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
