"""Exploratory reverse-direction analysis; original 8 train, later 24 test.

Declared after inspecting forward results. This is not another untouched test.
"""
import json
import argparse
import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge,LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from pmsocial import ingame,reverse_attention as reverse
from pmsocial.config import DATA_PROCESSED as P,FIGURES
from evaluate_final_social import exact_game_minutes,paired_interval


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir',type=Path,default=P/'final_social')
    parser.add_argument('--include-later-training',action='store_true')
    parser.add_argument('--figure-name',default='fig_final_reverse_attention.png')
    parser.add_argument('--design',type=Path)
    args=parser.parse_args()
    f=args.test_dir
    if args.design:
        manifest=json.loads((f/'manifest.json').read_text())
        if manifest['design_sha256']!=hashlib.sha256(args.design.read_bytes()).hexdigest():
            raise ValueError('Replication design differs from collection manifest')
    tr_market=pd.read_parquet(P/'ingame_market_minute.parquet')
    tr_checks=pd.read_csv(P/'ingame_market_checks.csv')
    tr_social=pd.read_parquet(P/'ingame_bluesky_minute.parquet')
    if args.include_later_training:
        tr_market=pd.concat([tr_market,pd.read_parquet(P/'final_social/market_minute.parquet')],ignore_index=True)
        tr_checks=pd.concat([tr_checks,pd.read_csv(P/'final_social/collection_checks.csv')],ignore_index=True)
        tr_social=pd.concat([tr_social,pd.read_parquet(P/'final_social/bluesky_minute.parquet')],ignore_index=True)
    tr=exact_game_minutes(tr_market,tr_checks)
    te=exact_game_minutes(pd.read_parquet(f/'market_minute.parquet'),pd.read_csv(f/'collection_checks.csv'))
    if set(tr.slug)&set(te.slug) or tr.minute.max()>=te.minute.min():raise ValueError('Chronology or game separation failed')
    train=ingame.build_panel(tr,tr_social)
    test=ingame.build_panel(te,pd.read_parquet(f/'bluesky_minute.parquet'))
    dates=pd.read_csv(f/'selected_games.csv').set_index('slug').game_date_local
    predictions=[]
    for horizon in (5,15):
        a,b=reverse.frame(train,horizon),reverse.frame(test,horizon)
        specs={'social_game':reverse.SOCIAL_GAME,
               'social_game_price':reverse.SOCIAL_GAME+reverse.PRICE,
               'social_game_market':reverse.SOCIAL_GAME+reverse.PRICE+reverse.TRADING}
        for estimator in ('ridge','ols'):
            preds={'persistence':b.persistence.to_numpy(),'train_mean':np.full(len(b),a.future_log_posts.mean())}
            for name,features in specs.items():
                fit=make_pipeline(StandardScaler(),Ridge(alpha=1.) if estimator=='ridge' else LinearRegression())
                preds[name]=np.maximum(fit.fit(a[features],a.future_log_posts).predict(b[features]),0.)
            for name,pred in preds.items():
                out=b[['slug','minute','future_log_posts']].rename(columns={'future_log_posts':'y'}).copy()
                out['prediction']=pred
                out['model'],out['estimator'],out['horizon_min']=name,estimator,horizon
                out['date']=out.slug.map(dates)
                predictions.append(out)
    pr=pd.concat(predictions,ignore_index=True)
    rows,folds=[],[]
    for (estimator,horizon),g in pr.groupby(['estimator','horizon_min']):
        for (slug,name),data in g.groupby(['slug','model']):
            e=data.prediction-data.y
            folds.append({'estimator':estimator,'horizon_min':horizon,'slug':slug,'model':name,
                          'n':len(data),'sse':float((e**2).sum()),'rmse':float(np.sqrt(np.mean(e**2))),'mae':float(e.abs().mean())})
        for name,base in [('social_game','persistence'),('social_game_price','social_game'),('social_game_market','social_game')]:
            a=g[g.model==name].set_index(['slug','minute']);b=g[g.model==base].set_index(['slug','minute'])
            if not a.index.equals(b.index):raise ValueError('Prediction keys differ')
            loss=pd.DataFrame({'a':(a.prediction-a.y)**2,'b':(b.prediction-b.y)**2,'date':a.date}).reset_index()
            low,high,n=paired_interval(loss,'slug');dl,dh,nd=paired_interval(loss,'date')
            games=loss.groupby('slug')[['a','b']].sum()
            rows.append({'estimator':estimator,'horizon_min':horizon,'model':name,'vs':base,
                         'n':len(loss),'games':n,'dates':nd,'rmse_model':float(np.sqrt(loss.a.mean())),
                         'rmse_reference':float(np.sqrt(loss.b.mean())),
                         'rmse_change_pct':float(100*(np.sqrt(loss.a.sum()/loss.b.sum())-1)),
                         'games_improved':int((games.a<games.b).sum()),'game_low_pct':low,'game_high_pct':high,
                         'date_low_pct':dl,'date_high_pct':dh})
    comparisons=pd.DataFrame(rows)
    comparisons.to_csv(f/'reverse_attention_comparisons.csv',index=False)
    pd.DataFrame(folds).to_csv(f/'reverse_attention_folds.csv',index=False)
    pr.to_parquet(f/'reverse_attention_predictions.parquet',index=False)
    (f/'reverse_attention_design.json').write_text(json.dumps({
        'status':('frozen replication of an exploratory reverse-direction hypothesis' if args.design
                  else 'exploratory reverse-direction analysis after forward outcomes were inspected'),
        'target':'log(1 + sum of home/away query matches in next 5 or 15 minutes)',
        'training_games':tr.slug.nunique(),'test_games':te.slug.nunique(),
        'training':'designated earlier games only; scaling/fitting never uses test games',
        'baseline':'own social history plus score and recent scoring/time remaining',
        'price_increment':'absolute current and past-five-minute log-odds moves',
        'market_increment':'price increments plus recent trading activity',
        'estimators':'ridge alpha=1, OLS sensitivity; nonnegative predictions',
        'claim_limit':'predictive association, not proof market prices cause posting; only three test dates and repeated teams',
        'fresh_replication':'interpret multiple endpoints and shared teams/dates cautiously',
        'design_sha256':hashlib.sha256(args.design.read_bytes()).hexdigest() if args.design else None
    },indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,3.8),sharey=True)
    for ax,horizon in zip(axes,(5,15)):
        g=comparisons[(comparisons.estimator=='ridge')&(comparisons.horizon_min==horizon)&(comparisons.vs=='social_game')]
        for i,r in enumerate(g.itertuples()):
            ax.plot([r.game_low_pct,r.game_high_pct],[i,i],color='tab:purple');ax.scatter(r.rmse_change_pct,i,color='tab:purple')
        ax.set_yticks(range(len(g)),g.model.map({'social_game_price':'Add price movements','social_game_market':'Add price + trading'}))
        ax.axvline(0,color='gray',linestyle='--');ax.set_title(f'Next {horizon} minutes of posting')
        ax.set_xlabel('RMSE change vs posting history + game state (%)\nNegative = improvement');ax.grid(alpha=.15)
    axes[0].invert_yaxis()
    fig.suptitle(f'Reverse direction: does market activity predict later Bluesky attention?\nTrain {tr.slug.nunique()} / test {te.slug.nunique()}; game-bootstrap sensitivity intervals')
    fig.tight_layout();fig.savefig(FIGURES/args.figure_name,dpi=170);plt.close(fig)
    print(comparisons[comparisons.estimator=='ridge'].to_string(index=False))


if __name__=='__main__':main()
