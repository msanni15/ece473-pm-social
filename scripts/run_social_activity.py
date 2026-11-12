"""Development-only volume/magnitude experiments on already-inspected games."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from pmsocial import ingame, social_activity as activity
from pmsocial.config import DATA_PROCESSED as P
from pmsocial.enhanced_evaluation import game_uncertainty, holm


def main():
    panel = ingame.build_panel(pd.read_parquet(P / 'ingame_market_minute.parquet'),
                              pd.read_parquet(P / 'ingame_bluesky_minute.parquet'))
    folds, comparisons, predictions = [], [], []
    for horizon in (5, 15):
        frame = activity.build_frame(panel, horizon)
        for target in ('future_log_volume', 'future_abs_move'):
            for estimator in ('ridge', 'ols'):
                pr = activity.evaluate(frame, target, estimator)
                pr['horizon_min'], pr['target'], pr['estimator'] = horizon, target, estimator
                predictions.append(pr)
                names = ['persistence', 'train_mean', 'market', 'market_social']
                if target == 'future_abs_move':
                    names += ['zero_move']
                for (slug), g in pr.groupby('slug'):
                    for name in names:
                        error = g[name] - g.y
                        folds.append({'horizon_min': horizon, 'target': target, 'estimator': estimator,
                                      'slug': slug, 'model': name, 'n': len(g), 'sse': float((error**2).sum()),
                                      'rmse': float(np.sqrt(np.mean(error**2))), 'mae': float(error.abs().mean())})
                for name, baseline in [('market_social', 'market'), ('market', 'persistence')]:
                    loss = pr.assign(a=(pr[name]-pr.y)**2, b=(pr[baseline]-pr.y)**2)
                    games = loss.groupby('slug').agg(n=('a','size'), sse_model=('a','sum'), sse_base=('b','sum'))
                    comparisons.append({'horizon_min': horizon, 'target': target, 'estimator': estimator,
                                        'model': name, 'vs': baseline, 'n': len(pr),
                                        'rmse_change_pct': float(100*(np.sqrt(loss.a.sum()/loss.b.sum())-1)),
                                        'games_improved': int((games.sse_model<games.sse_base).sum()),
                                        **game_uncertainty(games)})
    folds, comparisons = pd.DataFrame(folds), pd.DataFrame(comparisons)
    comparisons['holm_p_social_family'] = np.nan
    for _, g in comparisons[comparisons.vs=='market'].groupby('estimator'):
        comparisons.loc[g.index, 'holm_p_social_family'] = holm(g.game_signflip_p)
    folds.to_csv(P / 'social_activity_development_folds.csv', index=False)
    comparisons.to_csv(P / 'social_activity_development_comparisons.csv', index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(P / 'social_activity_development_predictions.parquet', index=False)
    (P / 'social_activity_development_design.json').write_text(json.dumps({
        'status': 'exploratory development; all eight games previously inspected',
        'proposed_primary': 'next-five-minute log(1 + total USDC volume)',
        'secondary': 'absolute log-odds endpoint movement', 'horizons_minutes': [5,15],
        'estimators': ['ridge alpha=1','OLS'], 'evaluation': 'leave-one-game-out',
        'features': 'original baseline plus trailing horizon volume/magnitude; enhanced adds original social features',
        'prediction_clipping': 'nonnegative predictions for nonnegative targets',
        'future_window': 't+1 through t+h, all required inside actual game-time minutes',
        'fresh_holdout': 'not yet collected or evaluated',
        'inference': 'exploratory whole-game checks; Holm across four social target/horizon comparisons per estimator'
    }, indent=2))
    print(comparisons[comparisons.estimator=='ridge'].to_string(index=False))


if __name__ == '__main__':
    main()
