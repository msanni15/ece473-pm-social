"""Synthetic checks of conservative timestamp sensitivity and paired intervals."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

path=Path(__file__).resolve().parents[1]/'scripts/evaluate_final_social.py'
spec=importlib.util.spec_from_file_location('final_evaluation',path)
evaluation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_timestamp_subset_recalculates_counts_injuries_and_baseline():
    tip=pd.Timestamp('2026-10-23T23:00:00Z')
    times=pd.date_range(tip-pd.Timedelta(hours=2),periods=330,freq='min')
    s=pd.DataFrame({'slug':'test','minute':times,'posts_home':0.,'posts_away':0.,
                    'injury_home':0.,'injury_away':0.,'abn_home':0.,'abn_away':0.,'imbalance':0.,'bsky_ok':True})
    s.loc[120,['posts_home','injury_home']]=1.
    p=pd.DataFrame({'slug':['test'],'side':['home'],'sort_at':[tip+pd.Timedelta(seconds=10)],
                    'created_at':[tip+pd.Timedelta(seconds=10)],'indexed_at':[tip+pd.Timedelta(minutes=2)],
                    'kw_injury':[True],'uri':['u1']})
    games=pd.DataFrame({'slug':['test'],'game_start_utc':[tip]})
    result=evaluation.conservative_social(s,p,games)
    assert result.posts_home.sum()==0 and result.injury_home.sum()==0
    assert result.abn_home.eq(0).all() and result.imbalance.eq(0).all()
    assert s.posts_home.sum()==1  # sensitivity never mutates original features


def test_cluster_intervals_preserve_paired_equal_forecasts():
    loss=pd.DataFrame({'slug':['a','a','b'],'a':[1.,2.,4.],'b':[1.,2.,4.]})
    low,high,n=evaluation.paired_interval(loss,'slug')
    assert low==0 and high==0 and n==2


def test_espn_clippers_name_alias_preserves_home_away(monkeypatch):
    from pmsocial import espn
    game=pd.Series({'slug':'nba-lal-lac-2026-10-28','game_date_local':'2026-10-28','home':'lac','away':'lal'})
    event={'id':'test','competitions':[{'competitors':[
        {'homeAway':'home','team':{'displayName':'LA Clippers'}},
        {'homeAway':'away','team':{'displayName':'Los Angeles Lakers'}}]}]}
    monkeypatch.setattr(espn,'_cached',lambda *a,**kw:{'events':[event]})
    assert espn.find_event(game)['id']=='test'


def test_exact_boundaries_exclude_after_buzzer_partial_minute():
    t=pd.date_range('2026-10-23T23:00:00Z',periods=4,freq='min')
    market=pd.DataFrame({'slug':'test','minute':t,'in_game':True})
    checks=pd.DataFrame({'slug':['test'],'tip_utc':['2026-10-23T23:00:20Z'],
                         'final_play_utc':['2026-10-23T23:02:10Z']})
    corrected=evaluation.exact_game_minutes(market,checks)
    assert corrected.in_game.tolist()==[True,True,False,False]
