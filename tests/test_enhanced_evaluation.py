"""Synthetic checks of additional evaluation and uncertainty calculations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
import pandas as pd
from pmsocial import enhanced_evaluation as e


def test_identical_forecasts_have_zero_interval_and_unit_p():
    losses = pd.DataFrame({'n': [10, 20, 30], 'sse_model': [2., 3., 4.], 'sse_base': [2., 3., 4.]})
    result = e.game_uncertainty(losses)
    assert result == {'bootstrap_low_pct': 0., 'bootstrap_high_pct': 0., 'game_signflip_p': 1.}


def test_uniform_improvement_is_negative_and_signflip_uses_games():
    losses = pd.DataFrame({'n': [10]*8, 'sse_model': [1.]*8, 'sse_base': [4.]*8})
    r = e.game_uncertainty(losses)
    assert r['bootstrap_low_pct'] == -50
    assert r['bootstrap_high_pct'] == -50
    assert r['game_signflip_p'] == 2 / 256


def test_holm_restores_original_order_and_is_monotone():
    np.testing.assert_allclose(e.holm([.04, .001, .03]), [.06, .003, .06])


def test_observed_mask_requires_real_minute_history_and_future():
    t = pd.date_range('2026-10-23', periods=25, freq='min', tz='UTC')
    p = pd.DataFrame({'slug': 'a', 'minute': t, 'price_observed': True})
    valid = e.observed_history_mask(p)
    assert valid.sum() == 15
    p.loc[12, 'price_observed'] = False
    assert not e.observed_history_mask(p).iloc[7:18].any()
    p = p.drop(index=12)
    assert not e.observed_history_mask(p).loc[7:17].any()
