import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stir import calc  # noqa: E402


def test_contract_ticker():
    assert calc.contract_ticker("Z26", "SR3", "CME", "{root}{month}{yy}.{exchange}") == "SR3Z26.CME"
    assert calc.fed_funds_code(2027, 1) == "F27"


def test_rate_change_sign():
    # price down 10bp = rates up 10bp
    assert calc.rate_change_bp(96.00, 96.10) == pytest.approx(10.0)
    assert calc.rate_change_bp(None, 96.0) is None


def test_spread_change():
    # front unchanged, back down 5bp in price -> spread +5bp
    assert calc.spread_change_bp(96.0, 95.95, 96.0, 96.0) == pytest.approx(5.0)
    assert calc.spread_change_bp(96.0, None, 96.0, 96.0) is None


def _daily():
    idx = pd.to_datetime(["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"])
    return pd.Series([96.30, 96.28, 96.25, 96.22, 96.20, 96.10], index=idx)


def _intraday():
    idx = pd.date_range("2026-11-13 06:00", "2026-11-13 14:30", freq="5min", tz="UTC")
    return pd.Series([96.20 - 0.0005 * i for i in range(len(idx))], index=idx)


def test_reference_points():
    d, i = _daily(), _intraday()
    assert calc.reference_price("Day", i, d) == 96.20                      # prior settle (12 Nov)
    assert calc.reference_price("Week", i, d) == 96.30                     # Fri 6 Nov
    assert calc.reference_price("Since", i, d, date(2026, 11, 10)) == 96.25
    assert calc.reference_price("15m", i, d) == pytest.approx(i.iloc[-4])
    assert calc.reference_price("1h", i, d) == pytest.approx(i.iloc[-13])
    assert calc.reference_price("Since EU Open", i, d) == pytest.approx(i.loc["2026-11-13 07:00"])  # 07:00 London = UTC in Nov
    assert calc.reference_price("1W", i, d) == 96.30


def test_fomc_path_hike_then_hold():
    # Nov avg 3.63 (no meeting), Dec meeting on 9th lifts to 3.88 -> Dec avg = (3.63*9 + 3.88*22)/31
    dec_avg = (3.63 * 9 + 3.88 * 22) / 31
    monthly = {(2026, 11): 3.63, (2026, 12): dec_avg, (2027, 1): 3.88, (2027, 2): 3.88}
    rows = calc.fomc_path([date(2026, 12, 9), date(2027, 1, 27)], monthly)
    assert rows[0].move == pytest.approx(25.0, abs=0.05)
    assert rows[1].move == pytest.approx(0.0, abs=0.05)
    assert rows[1].cumulative == pytest.approx(25.0, abs=0.05)
    assert rows[1].implied == pytest.approx(3.88, abs=1e-3)


def test_fomc_path_cumulative_is_running_sum():
    monthly = {(2026, 11): 3.63, (2026, 12): 3.75, (2027, 1): 3.86, (2027, 2): 3.90, (2027, 3): 3.92, (2027, 4): 3.93}
    rows = calc.fomc_path([date(2026, 12, 9), date(2027, 1, 27), date(2027, 3, 17)], monthly)
    assert rows[-1].cumulative == pytest.approx(sum(r.move for r in rows), abs=0.15)


def test_priced_history_delta():
    idx = pd.to_datetime(["2026-11-11", "2026-11-12", "2026-11-13"])
    zq = {(2026, 11): pd.Series([96.37] * 3, index=idx),
          (2026, 12): pd.Series([96.30, 96.28, 96.25], index=idx),
          (2027, 1): pd.Series([96.20, 96.18, 96.15], index=idx),
          (2027, 2): pd.Series([96.18, 96.16, 96.12], index=idx)}
    hist = calc.priced_history([date(2026, 12, 9), date(2027, 1, 27)], zq, days=1)
    assert len(hist) == 2
    d, rows, delta = hist[0]
    assert d == date(2026, 11, 13)
    prev = {r.meeting: r.cumulative for r in hist[1][1]}
    assert delta[0] == pytest.approx(rows[0].cumulative - prev[rows[0].meeting], abs=0.05)


def test_imm_period():
    assert calc.imm_period("Z26") == (date(2026, 12, 16), date(2027, 3, 17))
    assert calc.imm_period("U26") == (date(2026, 9, 16), date(2026, 12, 16))


def test_strip_meeting_path_recovers_flat_and_cut():
    meetings = [date(2026, 12, 9), date(2027, 1, 27), date(2027, 3, 3), date(2027, 4, 28), date(2027, 6, 2)]
    asof, cur = date(2026, 11, 13), 2.25
    true = {m: (2.00 if m >= date(2027, 1, 27) else 2.25) for m in meetings}  # one 25bp cut in Jan

    def rate_on(d):
        r = cur
        for m in meetings:
            if d > m:
                r = true[m]
        return r

    strip = {}
    for code in ["U26", "Z26", "H27", "M27"]:
        s, e = calc.imm_period(code)
        days = [s + timedelta(days=i) for i in range((e - s).days)]
        strip[code] = sum(cur if d < asof else rate_on(d) for d in days) / len(days)
    rows = calc.strip_meeting_path(meetings, strip, cur, asof)
    cum = {r.meeting: r.cumulative for r in rows}
    assert cum[date(2027, 3, 3)] == pytest.approx(-25, abs=4)
    assert rows[-1].implied == pytest.approx(2.00, abs=0.04)
