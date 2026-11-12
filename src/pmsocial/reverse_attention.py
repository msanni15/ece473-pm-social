"""Reverse-direction exploratory forecasts: market activity -> future attention.

Condition on posting history and observable game state; do not treat forecast
improvement as a causal effect. Current features end at t+1 minute; targets start
at t+1. Game-time flags must be corrected to exact final-play cutoffs first.
"""
import numpy as np
import pandas as pd

from .social_activity import future_sum

SOCIAL_GAME = ['log_posts_now', 'log_posts_past5', 'log_posts_past15',
               'score_diff', 'score_scaled', 'time_left', 'points_now', 'points_past5']
PRICE = ['abs_move_now', 'abs_move_past5']
TRADING = ['log_volume_now', 'log_volume_past5', 'log_trades_now', 'abs_flow_now']


def frame(panel, horizon=5):
    p=panel.sort_values(['slug','minute']).reset_index(drop=True).copy()
    p['posts_total']=p.posts_home+p.posts_away
    p['points_now']=p.pts_home+p.pts_away
    p['future_log_posts']=np.log1p(future_sum(p,'posts_total',horizon))
    rolling={c:[] for c in ('log_posts_past5','log_posts_past15','log_volume_past5','points_past5','persistence')}
    for _,g in p.groupby('slug',sort=False):
        if not g.minute.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            raise ValueError('Reverse analysis requires a complete minute grid')
        for h in (5,15):
            rolling[f'log_posts_past{h}'].append(np.log1p(g.posts_total.rolling(h,min_periods=h).sum()))
        rolling['log_volume_past5'].append(np.log1p(g.volume_usd.rolling(5,min_periods=5).sum()))
        rolling['points_past5'].append(g.points_now.rolling(5,min_periods=5).sum())
        rolling['persistence'].append(np.log1p(g.posts_total.rolling(horizon,min_periods=horizon).sum()))
    for c,values in rolling.items():p[c]=pd.concat(values).sort_index()
    group=p.groupby('slug',sort=False)
    p['abs_move_now']=group.logit_p.diff().abs()
    p['abs_move_past5']=(p.logit_p-group.logit_p.shift(5)).abs()
    p['log_posts_now']=np.log1p(p.posts_total)
    p['log_volume_now']=np.log1p(p.volume_usd)
    p['log_trades_now']=np.log1p(p.n_trades)
    p['abs_flow_now']=np.log1p(p.flow_home.abs())
    p['score_scaled']=p.score_diff/np.sqrt(p.sec_remaining+60)
    p['time_left']=p.sec_remaining/2880
    # Invalid prices cannot be disguised as zero-sized moves by differencing.
    cols=SOCIAL_GAME+PRICE+TRADING+['future_log_posts','persistence']
    return p[p.in_game].dropna(subset=cols).reset_index(drop=True)
