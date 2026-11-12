"""Synthetic tests of the activity extension's forecast timing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pandas as pd
from pmsocial.social_activity import future_sum


def fixture():
    return pd.DataFrame({'slug':['a']*6+['b']*6,
                         'minute':list(pd.date_range('2026-10-23',periods=6,freq='min',tz='UTC'))*2,
                         'volume':[1.,2.,3.,4.,5.,6.]*2,'in_game':True})


def test_future_volume_excludes_current_and_never_borrows_next_game():
    p=fixture(); s=future_sum(p,'volume',3)
    assert s.iloc[0]==9 and s.iloc[6]==9
    assert s.iloc[3:6].isna().all()


def test_missing_minute_and_outside_game_make_target_missing():
    p=fixture();p.loc[2,'in_game']=False
    assert pd.isna(future_sum(p,'volume',3).iloc[0])
    p=fixture().drop(index=2)
    assert pd.isna(future_sum(p,'volume',3).iloc[0])
