"""Collect the frozen later-game sample; deliberately does not fit/evaluate models.

Raw caches and processed artifacts are isolated from the Milestone II dataset.
Run python scripts/collect_final_social.py; reruns resume successful caches.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pandas as pd
from pmsocial import apilog, polymarket, espn, ingame, bluesky_ingame as social
from pmsocial.config import ROOT, GAMMA_API

RAW = ROOT / 'data/raw/final_social'
OUT = ROOT / 'data/processed/final_social'
DESIGN = ROOT / 'reports/final_social_design.json'


def discover(design):
    path = RAW / 'gamma_later_events.json'
    if path.exists():
        return json.loads(path.read_text())
    lo, hi = design['test_dates_inclusive']
    result = []
    for offset in range(0, 10000, 100):
        page = apilog.get(f'{GAMMA_API}/events', {'tag_slug':'nba', 'closed':'true', 'limit':100,
                                               'offset':offset, 'order':'endDate', 'ascending':'false'},
                          source='final_gamma', min_interval=.3, count_fn=len)
        if page is None:
            raise RuntimeError('Market discovery request failed')
        for event in page:
            match = polymarket.SLUG_RE.match(event.get('slug',''))
            if match and lo <= match.group(3) <= hi:
                result.append(event)
        if not page or len(page)<100 or min((e.get('endDate') or '9999') for e in page)[:10] < lo:
            break
    else:
        raise RuntimeError('Discovery pagination safety limit reached')
    path.write_text(json.dumps(result))
    return result


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text())
    apilog.LOGS = RAW / 'request_logs'
    polymarket.RAW, espn.RAW = RAW / 'polymarket', RAW / 'espn'
    candidates = polymarket.candidate_table(discover(design))
    candidates = candidates.drop_duplicates('slug').sort_values(['game_start_utc','slug'])
    valid = candidates.exclusion.isna()
    chosen = candidates[valid].head(design['n_test_games_requested']).copy()
    chosen['selected'] = True
    candidates.to_csv(OUT / 'candidate_games.csv', index=False)
    chosen.to_csv(OUT / 'selected_games.csv', index=False)
    if len(chosen) != design['n_test_games_requested']:
        raise RuntimeError(f'Only {len(chosen)} valid games; no silent selection changes')
    markets, events, trades, windows, statuses = [], [], [], [], []
    completed = []
    for _, game in chosen.iterrows():
        print('COLLECT',game.slug, flush=True)
        try:
            plays = espn.plays_table(game)
            start, end = social.game_window(game)
            if plays.ts.dropna().min()<start or plays.ts.dropna().max()>=end:
                raise ValueError('ESPN game extends outside fixed collection window')
            tr = ingame.game_trades(game)
            market, checks = ingame.market_minutes(game, plays, tr)
            if checks['trades_wrong_market'] or checks['trades_unknown_asset']:
                raise ValueError('Trade identity check failed')
            w = social.collect_game(game, raw_dir=RAW / 'bluesky')
            markets.append(market);events.append(plays);trades.append(tr);windows.extend(w)
            completed.append(game)
            statuses.append({'slug':game.slug,'status':'collected', 'reason':'', **checks})
        except (RuntimeError, ValueError, KeyError, LookupError) as exc:
            print('INCOMPLETE',game.slug,str(exc),flush=True)
            statuses.append({'slug':game.slug,'status':'excluded_or_failed','reason':str(exc)})
        pd.DataFrame(statuses).to_csv(OUT / 'collection_checks.csv',index=False)
    if not completed:
        raise RuntimeError('No complete games collected')
    games = pd.DataFrame(completed)
    posts = social.build_posts(windows,games)
    minutes = social.build_minutes(games,windows,posts)
    pd.concat(markets,ignore_index=True).to_parquet(OUT / 'market_minute.parquet',index=False)
    pd.concat(events,ignore_index=True).to_parquet(OUT / 'events.parquet',index=False)
    pd.concat(trades,ignore_index=True).to_parquet(OUT / 'trades.parquet',index=False)
    posts.to_parquet(OUT / 'bluesky_posts.parquet',index=False)
    minutes.to_parquet(OUT / 'bluesky_minute.parquet',index=False)
    manifest={'design_sha256':hashlib.sha256(DESIGN.read_bytes()).hexdigest(),
              'selected_games':len(chosen),'collected_games':len(games),
              'minute_rows':len(minutes),'post_side_rows':len(posts),
              'both_sides_covered_minutes':int(minutes.bsky_ok.sum()),
              'status':'collection only; no holdout model outcomes evaluated'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':
    main()
