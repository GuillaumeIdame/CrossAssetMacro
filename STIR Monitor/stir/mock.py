"""Clearly-labelled MOCK data for curves with no free futures feed
(Euribor, SONIA, CORRA, SARON, Aussie Bills) and for BoC meeting pricing.

Only used when the sidebar switch "Show mock rows" is on; every row it feeds is tagged MOCK.
Deterministic (seeded on curve + timeframe) so numbers do not jump around on rerun.
"""

import random
from datetime import date

# (front, peak at ~Z27, back) day profile in bp, same ranges as the original mockup
PROFILES = {"Euribor": (1, 4, 2.5), "SONIA": (2, 6, 4), "CORRA": (-3, -8, -5), "SARON": (-1, 1.5, 2)}
SCALE = {"15m": .15, "30m": .28, "1h": .42, "Day": 1, "Week": 1.55, "Since": 2.1, "Since EU Open": .72,
         "1W": 1.9, "1M": 3.1, "3M": 4.4, "6M": 5.2}
SENTIMENT_BASE = {"Aussie Bills": -4.5, "SARON": -1.0, "Euribor": 3.0, "SONIA": 5.25, "CORRA": -6.5}


def _q(x):
    return round(x * 4) / 4


def strip(curve, contracts, timeframe):
    a, p, b = PROFILES[curve]
    rnd = random.Random(f"{curve}-{timeframe}")
    out = {}
    for i, c in enumerate(contracts):
        base = a + (p - a) * i / 5 if i <= 5 else p + (b - p) * (i - 5) / 7
        out[c] = _q(base * SCALE[timeframe] * (1 + rnd.uniform(-.12, .12)))
    return out


def dec_spreads(curve, timeframe):
    s = strip(curve, ["Z26", "Z27", "Z28", "Z29"], timeframe)
    vals = [round(s["Z27"] - s["Z26"], 2), round(s["Z28"] - s["Z27"], 2), round(s["Z29"] - s["Z28"], 2)]
    return vals[:2] + [None] if curve == "CORRA" else vals


def sentiment(curve, timeframe):
    rnd = random.Random(f"sent-{curve}-{timeframe}")
    return _q(SENTIMENT_BASE[curve] * SCALE[timeframe] * (1 + rnd.uniform(-.25, .25)))


BOC_MEETINGS = [date(2026, 12, 9), date(2027, 1, 27), date(2027, 3, 10), date(2027, 4, 14),
                date(2027, 6, 2), date(2027, 7, 14), date(2027, 9, 8), date(2027, 10, 27)]
BOC_START = 2.25
BOC_MOVES = [-3.4, -4.6, -2.1, -1.5, -0.8, 0.0, 0.6, 1.1]


def boc_moves(days_ago):
    rnd = random.Random(f"boc-{days_ago}")
    return [round(m * (1 - 0.1 * days_ago) + rnd.uniform(-.6, .6), 1) if m else 0.0 for m in BOC_MOVES]
