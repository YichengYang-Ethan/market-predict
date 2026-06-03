from datetime import date
from types import SimpleNamespace

from market_predict.models import OptionsWall
from market_predict.transforms.setup import build_setup


def _wall(gamma_flip):
    return OptionsWall(
        expiry=date(2026, 6, 26),
        call_wall_strike=800, call_wall_oi=9963,
        put_wall_strike=720, put_wall_oi=10188,
        max_pain=750, gamma_flip=gamma_flip,
        total_call_oi=100_000, total_put_oi=258_000, atm_iv=0.127,
    )


def _view(spot, gf, p_up=0.495):
    return SimpleNamespace(
        spot=spot,
        options_wall=_wall(gf),
        vix=SimpleNamespace(current=15.8, mean_30d=17.1),
        polymarket_daily_updown=SimpleNamespace(p_up=p_up),
    )


def test_positive_gamma_above_flip():
    s = build_setup(_view(760, 751))
    assert s is not None
    assert "positive-gamma" in s.tag.lower()
    assert any("above" in ln for ln in s.lines)
    assert "long" in s.verdict.lower()


def test_negative_gamma_below_flip():
    s = build_setup(_view(745, 751))
    assert "negative-gamma" in s.tag.lower()
    assert any("below" in ln for ln in s.lines)


def test_pin_tag_when_spot_at_max_pain():
    s = build_setup(_view(750, 751))  # spot == max_pain 750
    assert "pinned to max-pain" in s.tag.lower()


def test_pc_oi_defensive():
    s = build_setup(_view(760, 751))  # P/C = 258k/100k = 2.58 > 1.1
    assert any("put-heavy" in ln for ln in s.lines)


def test_no_spot_returns_none():
    assert build_setup(SimpleNamespace(spot=0, options_wall=None, vix=None)) is None


def test_handles_missing_wall_and_vix():
    v = SimpleNamespace(spot=760, options_wall=None, vix=None)
    s = build_setup(v)
    assert s is not None  # still returns a (thin) setup
    assert s.tag.lower() == "neutral"
