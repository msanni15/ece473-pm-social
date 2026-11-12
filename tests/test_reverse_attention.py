import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from pmsocial import reverse_attention as r


def fixture():
    n=40
    p=pd.DataFrame({'slug':'test','minute':pd.date_range('2026-10-23',periods=n,freq='min',tz='UTC'),
                    'posts_home':np.arange(n,dtype=float),'posts_away':0.,'pts_home':1.,'pts_away':0.,
                    'volume_usd':10.,'logit_p':np.arange(n)/100,'n_trades':2.,'flow_home':1.,
                    'score_diff':1.,'sec_remaining':1000.,'in_game':True})
    return p


def test_posting_target_excludes_current_minute_and_ends_inside_game():
    p=fixture();f=r.frame(p,5)
    row=f[f.minute==p.minute.iloc[20]].iloc[0]
    assert row.future_log_posts==np.log1p(sum(range(21,26)))
    assert row.persistence==np.log1p(sum(range(16,21)))
    assert f.minute.max()==p.minute.iloc[34]


def test_future_posts_do_not_change_past_predictors():
    p=fixture();a=r.frame(p,5)
    p.loc[25:,'posts_home']=1e6;b=r.frame(p,5)
    cols=['minute']+r.SOCIAL_GAME+r.PRICE+r.TRADING
    pd.testing.assert_frame_equal(a[a.minute<p.minute.iloc[25]][cols].reset_index(drop=True),
                                  b[b.minute<p.minute.iloc[25]][cols].reset_index(drop=True))
