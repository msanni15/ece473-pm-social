"""Build editable presentation, paper draft, PDFs and workbook from saved evidence.

Optional authoring dependencies (not model/runtime dependencies): python-pptx,
python-docx, reportlab, markdown, XlsxWriter. Does not run or alter research models.
"""
import csv
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image as PILImage
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from docx import Document
from docx.shared import Inches as DocInches
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables';F=ROOT/'data/processed/final_replication'
INK='14253D';TEAL='087F8C';BG='F5F7FA';MUTED='53647B'


def primary(path):
    data=pd.read_csv(path)
    return data[data.estimator=='ridge']


def text_plain(text):
    text=re.sub(r'\[([^]]+)\]\(([^)]+)\)',r'\1 (\2)',text)
    return text.replace('**','').replace('`','')


class Deck:
    def __init__(self):
        self.prs=Presentation();self.prs.slide_width=Inches(13.333);self.prs.slide_height=Inches(7.5)
        self.pdf=canvas.Canvas(str(OUT/'presentation.pdf'),pagesize=(13.333*72,7.5*72))
        self.slides=[]

    def text(self,slide,text,x,y,w,h,size=23,color=INK,bold=False):
        box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf=box.text_frame;tf.word_wrap=True
        tf.margin_left=tf.margin_right=0
        for i,line in enumerate(text.split('\n')):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line
            p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color)
            p.space_after=Pt(8)
        self.pdf.setFillColor(HexColor('#'+color));self.pdf.setFont('ReviewSans',size)
        top=(7.5-y)*72-size
        for line in text.split('\n'):
            words=line.split();current=''
            for word in words:
                candidate=(current+' '+word).strip()
                if pdfmetrics.stringWidth(candidate,'ReviewSans',size)>w*72 and current:
                    self.pdf.drawString(x*72,top,current);top-=size*1.25;current=word
                else:current=candidate
            self.pdf.drawString(x*72,top,current);top-=size*1.25+8
        return box

    def add(self,title,bullets=None,image=None,notes='',source='',tiles=None):
        slide=self.prs.slides.add_slide(self.prs.slide_layouts[6])
        slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string(BG)
        self.pdf.setFillColor(HexColor('#'+BG));self.pdf.rect(0,0,13.333*72,7.5*72,stroke=0,fill=1)
        number=len(self.slides)+1
        self.text(slide,'ECE 473  /  SOCIAL ATTENTION & PREDICTION MARKETS',.6,.22,12,.3,10,TEAL,True)
        self.text(slide,title,.6,.75,12.1,1.0,29,INK,True)
        if tiles:
            width=11.8/len(tiles)
            for i,(value,label) in enumerate(tiles):
                x=.65+i*width
                self.text(slide,value,x,2.15,width-.25,.8,38,TEAL,True)
                self.text(slide,label,x,3.1,width-.3,1.7,19,MUTED)
        if bullets:
            y=4.9 if tiles else 2.0
            self.text(slide,'\n'.join('• '+line for line in bullets),.7,y,11.8,6.7-y,22)
        if image:
            path=ROOT/image
            iw,ih=PILImage.open(path).size
            scale=min(12/iw,4.75/ih);w,h=iw*scale,ih*scale;x=(13.333-w)/2;y=1.8
            slide.shapes.add_picture(str(path),Inches(x),Inches(y),width=Inches(w),height=Inches(h))
            self.pdf.drawImage(str(path),x*72,(7.5-y-h)*72,width=w*72,height=h*72)
        self.text(slide,source,.6,6.85,11.6,.3,9,MUTED)
        self.text(slide,str(number),12.25,6.85,.4,.3,10,MUTED)
        slide.notes_slide.notes_text_frame.text=notes+'\n\nEvidence: '+source
        self.slides.append({'number':number,'title':title,'notes':notes,'source':source})
        self.pdf.showPage()

    def save(self):
        self.prs.save(OUT/'presentation.pptx');self.pdf.save()
        (OUT/'slide_outline.json').write_text(json.dumps(self.slides,indent=2))


def make_deck():
    d=Deck()
    d.add('Social attention and NBA prediction markets',tiles=[('66','games across three stages'),('32 → 34','chronological training → final test'),('2 directions','social → market; market → social')],
          bullets=['Draft for author review. Add team names before submission.'],source='Source: reports/final_project_status.md',
          notes='Introduce the project in your own words. We study short-horizon activity, not simply which team wins. The original pilot and the later final test are distinct stages.')
    d.add('Two questions, with separate forecasting baselines',bullets=[
        'Does Bluesky attention add to market/game-state forecasts of price changes or volume?',
        'Does market activity add to posting-history/game-state forecasts of later attention?',
        'Evaluate extra predictive information; do not infer causation or trading profit.'],
        notes='The reverse task must control for posting persistence. A correlation or post-event rise alone cannot answer either incremental-prediction question.',source='Designs: reports/final_social_design.json; final_replication_design.json')
    d.add('Separate development, extension and replication',tiles=[('8','original development games'),('24','October 28–30 extension games'),('34','November 1–10 replication games, 9 dates')],
          bullets=['Final models fit only the 32 earlier games. Scaling and fitting never use November targets.'],
          notes='Do not call all 66 games held out. Only the final 34 form the last replication test. Earlier stages informed the final design; no test-based hyperparameter search was used.',source='Registries: data/processed/final_social/ and final_replication/selected_games.csv')
    d.add('One minute: known features first, future target second',bullets=[
        'At minute end: last-trade price, trades, game score and observed posting.',
        'Price target: next-minute change in clipped home-win log-odds.',
        'Volume/posting targets: totals over the next 5 minutes; 15-minute sensitivity.',
        'Exclude the final partial minute using exact ESPN final-play timestamps.'],
        notes='The first extension used an inclusive final-minute flag. That was corrected transparently, with old outputs retained. The correction preceded the November replication. Creation/indexing timestamps have a separate sensitivity check.',source='scripts/evaluate_final_social.py; src/pmsocial/social_activity.py')
    d.add('Attention is measured; news content needs validation',bullets=[
        'Bluesky: counts, pre-tip abnormal attention, home/away imbalance, injury keywords.',
        'Market controls: price history, trades, flow; game controls: scoring and time left.',
        'A query match is not verified news, sentiment, or the injured player’s team.',
        'Both sides can match one post. Human content-review sample: 100 posts.'],
        notes='Search coverage succeeded for all collected minutes but is not proof of exhaustive indexing or relevance. AI review suggestions are separate from the blank human-label file. Injury keywords include figurative uses and repeated availability reports.',source='reports/social_annotation_guide.md; data/processed/social_validation_sample.csv')
    d.add('Score the comparison, not just one fitted model',bullets=[
        'Price benchmark: predict no change. Volume benchmark: trailing-window persistence.',
        'Ridge α=1 primary; OLS and counts-only sensitivities. Training-only scaling.',
        'Primary score: pooled RMSE. Also retain equal-game RMSE, MAE and per-game losses.',
        'Game/date bootstrap intervals are sensitivity checks; repeated teams remain.'],
        notes='RMSE is not percentage accuracy. Relative RMSE changes are percentages of error, not probability percentage points. Multiple endpoints are reported rather than selecting a favorable specification.',source='data/processed/final_replication/*comparisons.csv; *folds.csv')
    c=primary(F/'heldout_comparisons.csv')
    def value(task,h,model):return c[(c.timing=='pilot_sort_time')&(c.task==task)&(c.horizon_min==h)&(c.model==model)].iloc[0]
    price=value('signed_price',1,'market');volume=value('log_volume',5,'market')
    d.add('The final baseline comparisons have measured gains',tiles=[(f'{-price.rmse_change_pct:.2f}%','lower next-minute price RMSE vs no change'),(f'{-volume.rmse_change_pct:.2f}%','lower 5-minute log-volume RMSE vs persistence')],
          bullets=['These are forecasting error reductions, not returns from an executable strategy.'],
          notes=f'Price pooled RMSE: {price.rmse_reference:.6f} to {price.rmse_model:.6f}. Volume pooled RMSE: {volume.rmse_reference:.6f} to {volume.rmse_model:.6f}. The old eight-game no-change comparison must not be generalized to this larger final test.',source='34-game test; ridge; heldout_comparisons.csv; model=market')
    d.add('Increment from Bluesky: small point estimates, uncertainty',image='figures/fig_final_social_replication.png',
          notes='Left: next-minute signed price; right: next-five-minute log volume. Negative is lower error versus the market baseline. The complete social bundle gives −0.073% for price and +0.348% for volume; both game intervals span zero. Counts-only estimates and other horizons remain visible in the workbook. Do not state that no information can ever exist.',source='data/processed/final_replication/heldout_comparisons.csv; 32 train / 34 test')
    d.add('Reverse direction: market features predicting posting',image='figures/fig_final_reverse_replication.png',
          notes='Reference is posting history plus game state, not a constant forecast. Adding price/trading gives about 0.405% lower five-minute error, but both game/date intervals include zero. Post-event timing is descriptive and does not show that prices caused fans to post.',source='data/processed/final_replication/reverse_attention_comparisons.csv')
    d.add('Injury candidates need event-time and source checks',image='figures/fig_final_injury_case_contexts.png',
          notes='Red marks posting time, not injury onset. Cam Johnson’s ankle injury has team follow-up corroboration, but first publication is unresolved. A scoring play is logged 4.58 seconds after the post. The Walsh limping post lacks independent diagnosis corroboration. Neither demonstrates a news trading edge.',source='data/processed/final_social/injury_source_checks.csv; source/context checks remain provisional')
    d.add('Robustness and limitations are part of the evidence',bullets=[
        'Ridge/OLS, longer horizons, counts-only/full bundles, timestamp-confirmed subset.',
        'Exact game-end cutoffs; keep early timing corrections and unfavorable runs.',
        'Repeated teams, search omissions, sparse/noisy posts and imperfect timestamps.',
        'No historical order-book execution, costs or causal identification.'],
        notes='Use the workbook to inspect sensitivity rather than claim a universal result. The final sample spans nine dates. Results can reflect last-trade spread effects and cannot be converted into profit claims.',source='reports/final_replication_methods.md; results_workbook.xlsx')
    d.add('Finish with author-reviewed interpretation',bullets=[
        'Review the 100-post sample and adjudicate ambiguous/context-dependent labels.',
        'Keep verified events distinct from keyword matches and repeated reports.',
        'State the scope of the forecasting evidence in your own words.',
        'Add names/contributions; rehearse the difference between prediction and causation.'],
        notes='This is a draft presentation package. Formulate your own closing statement. The final-paper introduction, findings and conclusion remain for unaided author writing. Do not say the paper or human validation is completed.',source='reports/final_paper_scaffold.md; deliverables/presenter_guide.md')
    d.save()


def markdown_blocks(text):
    lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',x or ' ') for x in cells):rows.append(cells)
                i+=1
            yield 'table',rows;continue
        if line.startswith('#'):
            level=len(line)-len(line.lstrip('#'));yield 'heading',(min(level,3),line.lstrip('#').strip());i+=1;continue
        if line.startswith('!['):yield 'image',re.search(r'\]\(([^)]+)\)',line).group(1);i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','![','|')):
            paragraph.append(lines[i].strip());i+=1
        yield 'paragraph',' '.join(paragraph)


def make_paper():
    text=(ROOT/'reports/final_paper_scaffold.md').read_text()
    text=text.replace('## 6. Limitations and robustness — authors develop','## 6. Limitations and robustness')
    text=text.replace('Document search coverage and semantic ambiguity, game/date/team dependence,\ntimestamp uncertainty, price-definition sensitivity, lack of historical order-book\nexecution, multiple comparisons, retrospective sampling, and the distinction\nbetween prediction and causation. Report what changes under the timestamp subset,\nOLS, longer horizons, and the earlier sample rather than choosing a single winner.',
        'The data are retrospective. Last-trade prices contain spread effects, and historical trade and ESPN records do not establish exactly what each trader saw in real time. No historical order-book execution, transaction-cost, or profitability backtest is implemented. Forecast improvements must not be described as attainable trading returns.\n\n'
        'Social search is a keyword-based sample rather than a complete feed of game information. Counts can include unrelated discussion, link cards, duplicated topic coverage, and old availability reports. The AI-assisted text judgments are provisional; independent content validity and news novelty have not been established. Neither creation nor indexing time proves when someone learned information.\n\n'
        'Games share teams and calendar dates. Bootstrap intervals are dependence sensitivities rather than exact independent-sample guarantees. Multiple targets and feature sets were examined, and the internal design freezes were not external preregistration. The initial extension boundary correction followed inspection of an earlier run; that history and the prior outputs are retained.\n\n'
        'Chronological testing reduces one form of leakage but does not identify causal effects. Both market activity and posting may respond to scoring, broadcasts, or other shared events. The timestamp subset, OLS, longer horizons, and previous samples are reported to expose sensitivity rather than to select a favorable specification.')
    text+='\n\n## Appendix A. Numerical evidence tables for author review\n\n'
    for filename,title,filters in [('heldout_comparisons.csv','Forward replication',True),('reverse_attention_comparisons.csv','Reverse replication',False)]:
        c=primary(F/filename)
        if filters:c=c[c.timing=='pilot_sort_time']
        text+=f'\n### {title}\n\nNegative changes indicate lower error than the named baseline. These tables are data artifacts; authors supply their own findings prose.\n\n'
        text+='| Target / horizon | Model | Reference | RMSE change (%) | Game interval (%) |\n|---|---|---|---:|---|\n'
        for r in c.itertuples():
            target=(r.task if filters else 'future posting')+f' / {r.horizon_min} min'
            lo=r.game_bootstrap_low_pct if filters else r.game_low_pct
            hi=r.game_bootstrap_high_pct if filters else r.game_high_pct
            text+=f'| {target} | {r.model} | {r.vs} | {r.rmse_change_pct:+.3f} | [{lo:+.3f}, {hi:+.3f}] |\n'
    text+='''\n\n## Bibliography records for author verification\n\nWolfers, J., & Zitzewitz, E. (2004). Prediction Markets. NBER Working Paper 10504. https://doi.org/10.3386/w10504\n\nBrown, A., Rambaccussing, D., Reade, J. J., & Rossi, G. (2017, May 20). Forecasting with Social Media: Evidence from Tweets on Soccer Matches. Author manuscript, University of East Anglia repository. https://ueaeprints.uea.ac.uk/64244/1/BetfairTwitterEI_revisedv2.pdf\n\nSultan, O., & Morstatter, F. (2026). The Conversation Turns First: Crowd Discussion and Price Reversals in Prediction Markets. arXiv preprint 2609.28965. https://doi.org/10.48550/arXiv.2609.28965\n'''
    (ROOT/'reports/final_paper_draft.md').write_text(text)
    doc=Document();doc.sections[0].header.paragraphs[0].text='DRAFT — author sections and validation pending'
    styles=getSampleStyleSheet()
    for name in ['Normal','BodyText','Heading1','Heading2','Heading3','Title']:
        styles[name].fontName='ReviewSans'
    styles['BodyText'].fontSize=10;styles['BodyText'].leading=14
    story=[]
    for kind,value in markdown_blocks(text):
        if kind=='heading':
            level,title=value;doc.add_heading(text_plain(title),level=level)
            story.append(Paragraph(escape(text_plain(title)),styles[f'Heading{level}']))
        elif kind=='paragraph':
            plain=text_plain(value);doc.add_paragraph(plain)
            story.extend([Paragraph(escape(plain),styles['BodyText']),Spacer(1,7)])
        elif kind=='image':
            path=(ROOT/'reports'/value).resolve()
            if path.exists():
                doc.add_picture(str(path),width=DocInches(6.1))
                w,h=PILImage.open(path).size;scale=min(450/w,290/h)
                story.extend([Image(str(path),width=w*scale,height=h*scale),Spacer(1,10)])
        elif kind=='table':
            n=max(map(len,value));table=doc.add_table(rows=0,cols=n);table.style='Light Shading Accent 1'
            for row in value:
                cells=table.add_row().cells
                for cell,v in zip(cells,row):cell.text=text_plain(v)
            pdfrows=[[Paragraph(escape(text_plain(v)),styles['BodyText']) for v in row+['']*(n-len(row))] for row in value]
            tbl=Table(pdfrows,colWidths=[450/n]*n,repeatRows=1)
            tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#E6EEF4')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,HexColor('#CBD5E1')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]))
            story.extend([tbl,Spacer(1,12)])
    doc.save(OUT/'final_paper_draft.docx')
    def page_header(c,d):
        c.setFont('ReviewSans',8);c.setFillColor(HexColor('#53647B'))
        c.drawString(72,760,'DRAFT — author sections and independent validation pending')
        c.drawRightString(540,28,str(d.page))
    SimpleDocTemplate(str(OUT/'final_paper_draft.pdf'),pagesize=(612,792),leftMargin=72,rightMargin=72,topMargin=55,bottomMargin=45).build(story,onFirstPage=page_header,onLaterPages=page_header)


def make_workbook():
    files={'Forward':F/'heldout_comparisons.csv','Reverse':F/'reverse_attention_comparisons.csv',
           'Forward_by_game':F/'heldout_folds.csv','Reverse_by_game':F/'reverse_attention_folds.csv',
           'Sample_registry':F/'selected_games.csv','Collection_checks':F/'collection_checks.csv',
           'Human_review':ROOT/'data/processed/social_validation_sample.csv',
           'AI_suggestions':ROOT/'data/processed/social_validation_ai_suggestions.csv'}
    with pd.ExcelWriter(OUT/'results_workbook.xlsx',engine='xlsxwriter') as writer:
        for sheet,path in files.items():
            frame=pd.read_csv(path,keep_default_na=False);frame.to_excel(writer,sheet_name=sheet,index=False)
            ws=writer.sheets[sheet];ws.freeze_panes(1,2);ws.autofilter(0,0,len(frame),len(frame.columns)-1)
            ws.set_row(0,30);ws.set_column(0,len(frame.columns)-1,19)
            for i,col in enumerate(frame.columns):
                if col in ['text','ai_note','review_note','notes']:ws.set_column(i,i,65)
                if sheet=='Human_review' and col in ['game_relevant','information_type','new_information']:
                    choices={'game_relevant':['yes','no','unclear'],'information_type':['play_reaction','availability_report','opinion','promotion','other','unclear'],'new_information':['candidate_new','already_reported','unknown']}[col]
                    ws.data_validation(1,i,len(frame),i,{'validate':'list','source':choices})


def main():
    OUT.mkdir(exist_ok=True)
    import matplotlib
    font=Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'
    pdfmetrics.registerFont(TTFont('ReviewSans',str(font)))
    make_deck();make_paper();make_workbook()
    outline=json.loads((OUT/'slide_outline.json').read_text())
    guide=['# Presenter guide','', 'Suggested rehearsal: about nine minutes plus transitions; adapt to the actual assigned duration. Do not assume the course slot is nine minutes.','',
           'The deck is AI-assisted. Review the evidence and formulate your own opening and closing explanations. The final-paper reserved sections remain for your unaided writing.','']
    times=[30,40,40,50,50,50,45,70,55,45,40,25]
    for row,seconds in zip(outline,times):
        guide += [f'## Slide {row["number"]}: {row["title"]}', '',f'Suggested time: {seconds} seconds.', '', row['notes'],'', 'Evidence: '+row['source'],'']
    guide += ['## Questions to rehearse','',
        '- **Are you predicting the winner?** The main price task forecasts the next-minute log-odds increment. It is distinct from evaluating winner probabilities at settlement.',
        '- **What is the strongest benchmark?** No change for signed price; trailing-window persistence for volume/posting, then feature-appropriate market or posting-history/game-state regressions.',
        '- **Does 2.58% mean 2.58 probability points?** No. It is the relative reduction in pooled forecast RMSE compared with the named baseline.',
        '- **What happens when Bluesky is added?** On the final ridge test, the full bundle changes next-minute price RMSE by −0.073%; the game interval crosses zero. For five-minute log volume it changes error by +0.348%, also with an interval crossing zero.',
        '- **Does that prove social media has no information?** No. These feature definitions and this dataset do not establish a reliable incremental forecasting gain. Content measures, other samples and other horizons can differ.',
        '- **Does the reverse result establish causation?** No. Market/price features give small uncertain increments after controls; shared events can explain associations.',
        '- **How many games train and test?** The final replication uses 32 earlier training games and 34 later test games. The total inventory is 66; all 66 are not held out.',
        '- **Was the human relevance review completed?** No. There are 100 explicit AI text-review suggestions in a separate sheet; they are not independent human validation.',
        '- **Are injury cases verified breaking news?** No. One injury has follow-up corroboration but not an established release time; the other symptom post is uncorroborated. Nearby scoring is a competing explanation.',
        '- **Is the paper ready to submit?** No. Authors must finish the reserved sections, names/contributions, content review or provisional-label disclosure, and formatting checks.',
        '', '## Optional contribution statement structure','',
        'List the responsibilities each student actually owned, including decisions, data validation, model evaluation, interpretation and presentation. Disclose AI-generated code/materials. Do not claim independently implemented or manually validated work when that is not what occurred.','']
    (OUT/'presenter_guide.md').write_text('\n'.join(guide))
    print('Built PowerPoint, presentation PDF, Word/PDF paper drafts, results workbook and slide outline.')


if __name__=='__main__':main()
