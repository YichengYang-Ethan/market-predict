import pandas as pd

from market_predict.transforms.gex import gex_profile


def _chain(strikes, oi):
    return pd.DataFrame({
        "strike": strikes,
        "openInterest": oi,
        "impliedVolatility": [0.15] * len(strikes),
    })


STRIKES = list(range(700, 821, 10))


def test_profile_shape():
    prof = gex_profile(760, "2026-06-26", _chain(STRIKES, [1000] * len(STRIKES)),
                       _chain(STRIKES, [1000] * len(STRIKES)), atm_iv=0.13, n=41)
    assert prof is not None
    assert len(prof.spots) == 41 == len(prof.net_gex)
    assert prof.spots[0] < 760 < prof.spots[-1]


def test_call_heavy_is_positive_gamma():
    prof = gex_profile(760, "2026-06-26", _chain(STRIKES, [2000] * len(STRIKES)),
                       _chain(STRIKES, [500] * len(STRIKES)), atm_iv=0.13, n=41)
    assert prof.total_gex > 0


def test_put_heavy_is_negative_gamma():
    prof = gex_profile(760, "2026-06-26", _chain(STRIKES, [500] * len(STRIKES)),
                       _chain(STRIKES, [2000] * len(STRIKES)), atm_iv=0.13, n=41)
    assert prof.total_gex < 0


def test_zero_oi_returns_none():
    prof = gex_profile(760, "2026-06-26", _chain(STRIKES, [0] * len(STRIKES)),
                       _chain(STRIKES, [0] * len(STRIKES)), atm_iv=0.13)
    assert prof is None


def test_bad_spot_returns_none():
    assert gex_profile(0, "2026-06-26", _chain(STRIKES, [1] * len(STRIKES)),
                       _chain(STRIKES, [1] * len(STRIKES)), atm_iv=0.13) is None
