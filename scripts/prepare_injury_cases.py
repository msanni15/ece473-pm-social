"""Descriptive injury-post case contexts; no event-time or causal claim inferred."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];P=ROOT/'data/processed';OUT=P/'final_social'
CASES=[('Cam Johnson','nba-den-okc-2026-10-22','2026-10-23T03:10:07.420Z','away',
        'https://www.nba.com/nuggets/news/nuggets-host-warriors-for-third-game-of-2026-27',
        'Team preview corroborates ankle injury in opener; exact onset/first publication unresolved.'),
       ('Jordan Walsh','nba-nyk-bos-2026-10-23','2026-10-24T00:50:28.013Z','home','',
        'Post describes limping; independent injury/diagnosis corroboration not established.')]


def main():
    trades=pd.read_parquet(P/'ingame_trades.parquet').sort_values('ts')
    events=pd.read_parquet(P/'ingame_events.parquet')
    posts=pd.read_parquet(P/'ingame_bluesky_posts.parquet')
    fig,axes=plt.subplots(2,2,figsize=(11,6),sharex='col')
    curves,checks=[],[]
    for j,(name,slug,t,side,url,note) in enumerate(CASES):
        center=pd.Timestamp(t);grid=pd.DataFrame({'ts':pd.date_range(center-pd.Timedelta(minutes=5),center+pd.Timedelta(minutes=5),freq='s')})
        grid['ts']=grid.ts.astype('datetime64[ns, UTC]')
        tr=trades[trades.slug==slug][['ts','price_home']].copy()
        tr['trade_ts']=tr.ts.astype('datetime64[ns, UTC]');tr=tr.drop(columns='ts')
        curve=pd.merge_asof(grid,tr,left_on='ts',right_on='trade_ts',direction='backward')
        curve['lag_seconds']=(curve.ts-center).dt.total_seconds()
        curve['price_affected']=curve.price_home if side=='home' else 1-curve.price_home
        curve['trade_age_seconds']=(curve.ts-curve.trade_ts).dt.total_seconds()
        pl=events[(events.slug==slug)&events.ts.notna()].sort_values('ts')
        score=pl[['ts','score_home','score_away']].copy();score['ts']=score.ts.astype('datetime64[ns, UTC]')
        curve=pd.merge_asof(curve,score,on='ts',direction='backward')
        curve['score_margin_affected']=(curve.score_home-curve.score_away)*(1 if side=='home' else -1)
        curve['case'],curve['slug']=name,slug;curves.append(curve)
        ax=axes[0,j]
        # Avoid connecting stale trade prices as if fresh second-level observations.
        ax.plot(curve.lag_seconds,curve.price_affected.where(curve.trade_age_seconds<=30),color='tab:blue')
        ax.set_ylabel('Affected-team win probability');ax.set_title(name+' candidate post')
        axes[1,j].step(curve.lag_seconds,curve.score_margin_affected,where='post',color='tab:green')
        axes[1,j].set_ylabel('Affected-team score margin');axes[1,j].set_xlabel('Seconds relative to Bluesky post (not injury onset)')
        scoring=pl[pl.scoring_play & pl.ts.between(center-pd.Timedelta(minutes=5),center+pd.Timedelta(minutes=5))]
        for event in scoring.itertuples():
            lag=(event.ts-center).total_seconds()
            ax.axvline(lag,color='gray',alpha=.18,lw=.7)
        for a in axes[:,j]:a.axvline(0,color='red',linestyle='--');a.grid(alpha=.15)
        candidate=posts[(posts.slug==slug)&posts.sort_at.eq(center)].drop_duplicates('uri')
        nearest=scoring.assign(abs_lag=(scoring.ts-center).dt.total_seconds().abs()).sort_values('abs_lag').head(1)
        checks.append({'case':name,'slug':slug,'post_ts':center,'affected_side':side,
                       'post_uri':candidate.uri.iloc[0] if len(candidate) else '', 'corroborating_url':url,'status':note,
                       'nearest_scoring_ts':nearest.ts.iloc[0] if len(nearest) else pd.NaT,
                       'nearest_scoring_offset_seconds':(nearest.ts.iloc[0]-center).total_seconds() if len(nearest) else np.nan,
                       'review_status':'AI-assisted source/context check; independent student review pending'})
    fig.suptitle('Candidate injury-post contexts: scoring changes are competing explanations\nGray lines = scoring plays; red line = post; no claim of first publication or causal price effect')
    fig.tight_layout();fig.savefig(ROOT/'figures/fig_final_injury_case_contexts.png',dpi=160);plt.close(fig)
    pd.concat(curves,ignore_index=True).to_csv(OUT/'injury_case_contexts.csv',index=False)
    pd.DataFrame(checks).to_csv(OUT/'injury_source_checks.csv',index=False)


if __name__=='__main__':main()
