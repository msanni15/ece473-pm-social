"""Preserve explicit AI text-review suggestions separately from human labels.

All 100 texts were read in the assistant session. The index sets below record
those judgments against the fixed seed-473 review sample; they are not a trained
classifier, independent annotation, source verification, or a model input.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
YES={0,2,3,7,8,14,18,20,22,23,29,30,32,34,35,38,42,44,46,50,51,55,56,57,58,59,60,61,63,64,65,66,70,71,75,77,79,84,87,88,90,95,97}
NO={16,36,41,48,49,68,69,73,74,99}
REACTIONS={2,3,7,8,14,19,22,23,29,30,34,44,46,51,55,56,58,59,60,63,65,66,70,71,75,77,80,81,83,84,87,90,95,97,98}
PROMOTIONS={0,16,20,36,39,41,50,57,64,69}
AVAILABILITY={13,45,76,88}
EMPTY={1,9,11,12,17,28,40,82,96}
LINK_ONLY={5,21,37,72,86,89,93}
NOTES={
 16:'Player recreation story, not the sampled game.',36:'Discusses Spurs-Thunder rather than sampled Rockets-Spurs.',
 39:'Teams match, but title reverses home/away; wrong-game/context risk.',41:'76ers-Knicks recap, not Cavaliers-76ers.',
 45:'Speculation about a wrist issue and prior game; diagnosis and novelty unverified.',
 48:'Anthem/political topic; sampled game not established.',49:'Personal physical-therapy story; no game evidence.',
 68:'Team ownership discussion.',69:'Anthem/political controversy rather than game action.',
 73:'Baseball/rhyme reference; no sampled-game information.',74:'Bird photograph uses raptors in a non-basketball sense.',
 76:'Injury-like headline; game identity, event chronology, and source require checking.',
 88:'Availability topic appears in pregame collection; knee-side inconsistency noted in earlier audit. Not verified new news.',
 94:'Generic LeBron comment; Celtic-fan identity alone does not establish game relevance.',
 99:'Eastern Washington/bye-week language indicates a different Grizzlies team/sport.'}


def main():
    source=ROOT/'data/processed/social_validation_sample.csv'
    rows=list(csv.DictReader(source.open()))
    identity=json.dumps([[r['slug'],r['uri'],r['text']] for r in rows],ensure_ascii=False).encode()
    if len(rows)!=100 or hashlib.sha256(identity).hexdigest()!='3bce4aed783a40db4c00d778b0c2c383ec6899517ce08dd297216d82de646226':
        raise ValueError('Review sample changed; do not apply old index-based suggestions')
    for i,row in enumerate(rows):
        row['ai_game_relevant']='yes' if i in YES else 'no' if i in NO else 'unclear'
        row['ai_information_type']='availability_report' if i in AVAILABILITY else 'play_reaction' if i in REACTIONS else 'promotion' if i in PROMOTIONS else 'unclear' if i in EMPTY|LINK_ONLY else 'opinion' if i not in NO else 'other'
        row['ai_new_information']='already_reported' if i==88 else 'unknown'
        row['ai_note']=NOTES.get(i,'No standalone text; image/link/reply context not reviewed.' if i in EMPTY else 'URL alone does not establish sampled-game relevance.' if i in LINK_ONLY else 'Standalone text suggests game context.' if i in YES else 'Team-related/context-dependent; this specific game is not established by standalone text.')
        row['annotation_status']='AI text-only suggestion; human/source review pending'
    dest=ROOT/'data/processed/social_validation_ai_suggestions.csv'
    with dest.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('Created separate suggestions for',len(rows),'posts; human-label CSV unchanged.')


if __name__=='__main__':main()
