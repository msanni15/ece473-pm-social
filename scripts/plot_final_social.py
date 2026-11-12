"""Plot held-out social comparisons without rerunning or selecting models."""
from pathlib import Path
import argparse
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir',type=Path,default=ROOT/'data/processed/final_social')
    parser.add_argument('--figure-name',default='fig_final_social_holdout.png')
    args=parser.parse_args()
    c=pd.read_csv(args.test_dir/'heldout_comparisons.csv')
    manifest=json.loads((args.test_dir/'evaluation_manifest.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(10,4),sharey=True)
    for ax,task,h,title in zip(axes,['signed_price','log_volume'],[1,5],
                               ['Next-minute signed price change','Next-five-minute log volume']):
        rows=c[(c.timing=='pilot_sort_time')&(c.estimator=='ridge')&(c.task==task)&(c.horizon_min==h)&(c.vs=='market')]
        for i,r in enumerate(rows.itertuples()):
            ax.plot([r.game_bootstrap_low_pct,r.game_bootstrap_high_pct],[i,i],color='tab:blue')
            ax.scatter(r.rmse_change_pct,i,color='tab:blue')
        ax.set_yticks(range(len(rows)),rows.model.map({'market_social':'All original social features','market_counts':'Counts only'}))
        ax.axvline(0,color='gray',linestyle='--')
        ax.set_title(title)
        ax.set_xlabel('Pooled RMSE change versus market baseline (%)\nNegative = improvement')
        ax.grid(alpha=.15)
    axes[0].invert_yaxis()
    n_dates=int(c.dates.iloc[0])
    fig.suptitle(f'Train on {manifest["training_games"]} games; test on {manifest["test_games"]} later games\nGame-bootstrap 95% sensitivity intervals; {n_dates} test dates; repeated-team dependence remains')
    fig.tight_layout()
    fig.savefig(ROOT/'figures'/args.figure_name,dpi=170)
    plt.close(fig)


if __name__=='__main__':main()
