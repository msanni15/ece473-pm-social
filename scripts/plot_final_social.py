"""Plot held-out social comparisons without rerunning or selecting models."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]


def main():
    c=pd.read_csv(ROOT/'data/processed/final_social/heldout_comparisons.csv')
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
    fig.suptitle('Train on 8 games; test on 24 later games\nGame-bootstrap 95% sensitivity intervals; repeated teams and only 3 test dates')
    fig.tight_layout()
    fig.savefig(ROOT/'figures/fig_final_social_holdout.png',dpi=170)
    plt.close(fig)


if __name__=='__main__':main()
