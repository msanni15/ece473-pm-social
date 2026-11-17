"""Verify published comparison numbers directly from saved test predictions."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];F=ROOT/'data/processed/final_replication'


def audit(pred_name,table_name,keys):
    p=pd.read_parquet(F/pred_name);c=pd.read_csv(F/table_name)
    assert not p.duplicated(keys+['model','slug','minute']).any()
    assert np.isfinite(p[['y','prediction']]).all().all()
    for row in c.to_dict('records'):
        g=p.copy()
        for key in keys:g=g[g[key]==row[key]]
        a=g[g.model==row['model']].set_index(['slug','minute']).sort_index()
        b=g[g.model==row['vs']].set_index(['slug','minute']).sort_index()
        assert a.index.equals(b.index) and np.allclose(a.y,b.y)
        ra=float(np.sqrt(np.mean((a.prediction-a.y)**2)));rb=float(np.sqrt(np.mean((b.prediction-b.y)**2)))
        np.testing.assert_allclose([ra,rb,100*(ra/rb-1)],
                                   [row['rmse_model'],row['rmse_reference'],row['rmse_change_pct']],rtol=1e-9,atol=1e-10)
    return {'prediction_records':len(p),'comparisons_verified':len(c),'test_games':p.slug.nunique(),
            'prediction_sha256':hashlib.sha256((F/pred_name).read_bytes()).hexdigest()}


def main():
    report={'forward':audit('heldout_predictions.parquet','heldout_comparisons.csv',['timing','task','horizon_min','estimator']),
            'reverse':audit('reverse_attention_predictions.parquet','reverse_attention_comparisons.csv',['horizon_min','estimator'])}
    report['status']='Every comparison RMSE/change reproduced from saved finite, uniquely keyed held-out predictions.'
    (ROOT/'deliverables/evidence_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
