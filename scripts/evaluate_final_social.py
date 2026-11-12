"""Frozen-training evaluation on later games; preserves all pilot model outputs.

Only run after collection is complete. No tuning, row replacement, or fitting on
test outcomes. First use scores the frozen held-out sample; subsequent edits must
be disclosed as post-test exploratory work.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from pmsocial import ingame, ingame_models as base, social_activity as activity
from pmsocial.config import DATA_PROCESSED as P, ROOT, FIGURES

F = P / 'final_social'
DESIGN = ROOT / 'reports/final_social_design.json'


def conservative_social(social, posts, games):
    """Index-confirmed subset at original bins; not a new complete indexed-time feed."""
    result = social.copy()
    p = posts.copy()
    p['minute'] = p.sort_at.dt.floor('min')
    unavailable = ((p.indexed_at >= p.minute+pd.Timedelta(minutes=1))
                   | (p.created_at >= p.minute+pd.Timedelta(minutes=1)))
    for side in ('home','away'):
        removed = p[unavailable & (p.side==side)].groupby(['slug','minute']).agg(
            removed_posts=('uri','size'),removed_injury=('kw_injury','sum'))
        result = result.merge(removed,on=['slug','minute'],how='left',validate='one_to_one')
        result[f'posts_{side}'] -= result.removed_posts.fillna(0)
        result[f'injury_{side}'] -= result.removed_injury.fillna(0)
        result = result.drop(columns=['removed_posts','removed_injury'])
        for _, game in games.iterrows():
            mask = result.slug==game.slug
            pre = result[mask & (result.minute<game.game_start_utc)][f'posts_{side}']
            mean = np.log1p(pre).mean() if len(pre)==120 and pre.notna().all() else np.nan
            result.loc[mask,f'abn_{side}'] = np.log1p(result.loc[mask,f'posts_{side}'])-mean
    result['imbalance'] = np.log1p(result.posts_home)-np.log1p(result.posts_away)
    return result


def load_games(path):
    g = pd.read_csv(path)
    g['game_start_utc'] = pd.to_datetime(g.game_start_utc,utc=True)
    return g


def exact_game_minutes(market, checks):
    """A forecast cutoff must be after actual tip and no later than final play.

    The original inclusive minute flag admits the final partial minute. Exclude
    that minute because its last trade can occur after the final buzzer. This is
    a timing correction, not a change of features or estimator based on scores.
    """
    checks=checks.dropna(subset=['tip_utc','final_play_utc']).set_index('slug')
    tip=pd.to_datetime(market.slug.map(checks.tip_utc),utc=True)
    final=pd.to_datetime(market.slug.map(checks.final_play_utc),utc=True)
    if tip.isna().any() or final.isna().any():raise ValueError('Exact game boundaries missing')
    out=market.copy()
    cutoff=out.minute+pd.Timedelta(minutes=1)
    out['in_game']=(cutoff>tip)&(cutoff<=final)
    return out


def paired_interval(losses,cluster):
    group = losses.groupby(cluster)[['a','b']].sum()
    rng=np.random.default_rng(473)
    index=rng.integers(0,len(group),size=(10000,len(group)))
    a,b=group.a.to_numpy(),group.b.to_numpy()
    change=100*(np.sqrt(a[index].sum(axis=1)/b[index].sum(axis=1))-1)
    low,high=np.quantile(change,[.025,.975])
    return float(low),float(high),len(group)


def main():
    manifest=json.loads((F/'manifest.json').read_text())
    if manifest['design_sha256'] != hashlib.sha256(DESIGN.read_bytes()).hexdigest():
        raise ValueError('Design changed after collection; disclose and reconcile before scoring')
    train_market=pd.read_parquet(P/'ingame_market_minute.parquet')
    test_market=pd.read_parquet(F/'market_minute.parquet')
    train_market=exact_game_minutes(train_market,pd.read_csv(P/'ingame_market_checks.csv'))
    test_market=exact_game_minutes(test_market,pd.read_csv(F/'collection_checks.csv'))
    if set(train_market.slug)&set(test_market.slug):
        raise ValueError('Training/test games overlap')
    train_social=pd.read_parquet(P/'ingame_bluesky_minute.parquet')
    test_social=pd.read_parquet(F/'bluesky_minute.parquet')
    train_games=load_games(P/'markets.csv')
    test_games=load_games(F/'selected_games.csv')
    if train_market.minute.max()>=test_market.minute.min():
        raise ValueError('Test data are not strictly later than training')
    dates=test_games.set_index('slug').game_date_local.to_dict()
    all_predictions=[]
    for timing in ('pilot_sort_time','both_timestamps_confirmed'):
        a,b=train_social,test_social
        if timing=='both_timestamps_confirmed':
            a=conservative_social(a,pd.read_parquet(P/'ingame_bluesky_posts.parquet'),train_games)
            b=conservative_social(b,pd.read_parquet(F/'bluesky_posts.parquet'),test_games)
        train=ingame.build_panel(train_market,a)
        test=ingame.build_panel(test_market,b)
        for task,horizons in [('signed_price',(1,5)),('log_volume',(5,15))]:
            for h in horizons:
                if task=='signed_price':
                    tr,te=base.model_frame(train,True),base.model_frame(test,True)
                    target=f'dlogit_next{h}'
                    baseline=base.BASELINE
                else:
                    tr,te=activity.build_frame(train,h),activity.build_frame(test,h)
                    target='future_log_volume'
                    baseline=base.BASELINE+['past_log_volume','past_abs_move']
                specs={'market':baseline,'market_social':baseline+base.BLUESKY['all'],
                       'market_counts':baseline+base.BLUESKY['counts']}
                for estimator in ('ridge','ols'):
                    predictions={'zero_or_persistence':np.zeros(len(te)) if task=='signed_price' else te.past_log_volume.to_numpy()}
                    for name,features in specs.items():
                        reg=Ridge(alpha=1.) if estimator=='ridge' else LinearRegression()
                        fit=make_pipeline(StandardScaler(),reg).fit(tr[features],tr[target])
                        predictions[name]=fit.predict(te[features])
                        if task=='log_volume':
                            predictions[name]=np.maximum(predictions[name],0.)
                    for name,pred in predictions.items():
                        out=te[['slug','minute',target]].rename(columns={target:'y'}).copy()
                        out['prediction']=pred
                        out['model'],out['estimator'],out['timing'],out['task'],out['horizon_min']=name,estimator,timing,task,h
                        out['date']=out.slug.map(dates)
                        all_predictions.append(out)
    pr=pd.concat(all_predictions,ignore_index=True)
    if not np.isfinite(pr[['y','prediction']]).all().all():
        raise ValueError('Invalid held-out forecasts')
    pr.to_parquet(F/'heldout_predictions.parquet',index=False)
    fold_rows,comparisons=[],[]
    keys=['timing','task','horizon_min','estimator']
    for key,g in pr.groupby(keys):
        meta=dict(zip(keys,key))
        for (slug,name),rows in g.groupby(['slug','model']):
            error=rows.prediction-rows.y
            fold_rows.append({**meta,'slug':slug,'model':name,'n':len(rows),'sse':float((error**2).sum()),
                              'rmse':float(np.sqrt(np.mean(error**2))),'mae':float(error.abs().mean())})
        for name,reference in [('market','zero_or_persistence'),('market_social','market'),('market_counts','market')]:
            a=g[g.model==name].set_index(['slug','minute'])
            b=g[g.model==reference].set_index(['slug','minute'])
            if not a.index.equals(b.index):raise ValueError('Forecast rows differ')
            loss=pd.DataFrame({'a':(a.prediction-a.y)**2,'b':(b.prediction-b.y)**2,'date':a.date}).reset_index()
            gl,gh,ng=paired_interval(loss,'slug');dl,dh,nd=paired_interval(loss,'date')
            by_game=loss.groupby('slug')[['a','b']].sum()
            comparisons.append({**meta,'model':name,'vs':reference,'n':len(loss),'games':ng,'dates':nd,
                                'rmse_model':float(np.sqrt(loss.a.mean())),'rmse_reference':float(np.sqrt(loss.b.mean())),
                                'rmse_change_pct':float(100*(np.sqrt(loss.a.sum()/loss.b.sum())-1)),
                                'games_improved':int((by_game.a<by_game.b).sum()),
                                'game_bootstrap_low_pct':gl,'game_bootstrap_high_pct':gh,
                                'date_bootstrap_low_pct':dl,'date_bootstrap_high_pct':dh})
    folds=pd.DataFrame(fold_rows);comp=pd.DataFrame(comparisons)
    folds.to_csv(F/'heldout_folds.csv',index=False)
    comp.to_csv(F/'heldout_comparisons.csv',index=False)
    summary=folds.groupby(keys+['model']).agg(macro_rmse=('rmse','mean'),macro_mae=('mae','mean'),
                                             n=('n','sum'),sse=('sse','sum'),games=('slug','nunique')).reset_index()
    summary['pooled_rmse']=np.sqrt(summary.sse/summary.n)
    summary.to_csv(F/'heldout_summary.csv',index=False)
    (F/'evaluation_manifest.json').write_text(json.dumps({'design_sha256':manifest['design_sha256'],
        'training_games':train_market.slug.nunique(),'test_games':test_market.slug.nunique(),
        'training':'original eight only; no tuning or retraining on test',
        'boundary_correction':'exclude final partial minute using exact ESPN final timestamps; pre-correction artifacts retained separately',
        'bootstrap':'10000 draws seed473; game and date cluster sensitivity; repeated-team dependence unresolved',
        'status':'later-game outcomes now evaluated; further changes are post-test exploratory'},indent=2))
    print(comp[(comp.timing=='pilot_sort_time')&(comp.estimator=='ridge')].to_string(index=False))


if __name__=='__main__':main()
