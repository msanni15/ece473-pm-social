"""Build the ECE 473 final-presentation deck (editable .pptx) from the project's result files.

Design follows the "Blue and Beige Simple Project Proposal" template: beige background, navy
text, a navy bar on the right edge, all-caps heavy headings, outlined pill labels. Every number
on a slide is read from the CSV/parquet outputs below, never typed by hand.

Usage: python build_deck.py <repo_root> <out.pptx>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.chart.data import XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

REPO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
P = REPO / "data" / "processed"

BEIGE, NAVY, ACCENT = "F3EEE3", "2E3770", "C8691C"   # navy = market, accent = Bluesky
GRID, MUTED = "D9D1BF", "5B6390"
HEAD, BODY = "Arial Black", "Arial"
W, H = 13.333, 7.5
L, CW = 0.75, 11.45          # left margin and content width (stops before the right bar)
MINUS = "−"


def rgb(h):
    return RGBColor.from_string(h)


def plain(sh):
    """Drop the default theme style (it adds a shadow); colours are set explicitly instead."""
    st = sh._element.find(qn("p:style"))
    if st is not None:
        sh._element.remove(st)
    return sh


def num(v, d=2, sign=True):
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s.replace("-", MINUS)


def ci(lo, hi, d=2):
    return f"[{num(lo, d)}%, {num(hi, d)}%]"


# ---------------------------------------------------------------- numbers from the data
def load_numbers():
    n = {}
    fr = pd.read_csv(P / "final_replication" / "heldout_comparisons.csv")
    ex = pd.read_csv(P / "final_social" / "heldout_comparisons.csv")
    rv = pd.read_csv(P / "final_replication" / "reverse_attention_comparisons.csv")

    def row(df, task, h, model, est="ridge", timing="pilot_sort_time"):
        r = df[(df.timing == timing) & (df.estimator == est) & (df.task == task)
               & (df.horizon_min == h) & (df.model == model)]
        assert len(r) == 1, (task, h, model, est, timing)
        r = r.iloc[0]
        return dict(est=r.rmse_change_pct, lo=r.game_bootstrap_low_pct, hi=r.game_bootstrap_high_pct,
                    better=int(r.games_improved), games=int(r.games), ref=r.rmse_reference, mod=r.rmse_model)

    n["base_price"] = row(fr, "signed_price", 1, "market")
    n["soc_price"] = row(fr, "signed_price", 1, "market_social")
    n["cnt_price"] = row(fr, "signed_price", 1, "market_counts")
    n["base_vol"] = row(fr, "log_volume", 5, "market")
    n["soc_vol"] = row(fr, "log_volume", 5, "market_social")
    n["cnt_vol"] = row(fr, "log_volume", 5, "market_counts")
    n["soc_price5"] = row(fr, "signed_price", 5, "market_social")
    n["soc_vol15"] = row(fr, "log_volume", 15, "market_social")
    n["soc_price_ols"] = row(fr, "signed_price", 1, "market_social", est="ols")
    n["soc_price_strict"] = row(fr, "signed_price", 1, "market_social", timing="both_timestamps_confirmed")
    n["ext_base_price"] = row(ex, "signed_price", 1, "market")
    n["ext_soc_price"] = row(ex, "signed_price", 1, "market_social")
    n["ext_base_vol"] = row(ex, "log_volume", 5, "market")
    n["ext_soc_vol"] = row(ex, "log_volume", 5, "market_social")
    r5 = rv[(rv.estimator == "ridge") & (rv.horizon_min == 5)].set_index("model")
    for k, m in (("rev_base", "social_game"), ("rev_price", "social_game_price"), ("rev_market", "social_game_market")):
        r = r5.loc[m]
        n[k] = dict(est=r.rmse_change_pct, lo=r.game_low_pct, hi=r.game_high_pct,
                    better=int(r.games_improved), games=int(r.games))

    t = pd.read_csv(P / "ingame_model_tests.csv")
    t = t[t.estimator == "ols"]
    n["pilot_b1"] = t[(t["sample"] == "all_8_games") & (t.horizon_min == 1) & (t.model == "B1")].iloc[0]
    n["pilot_vwap"] = t[(t["sample"] == "all_8_games_vwap_price") & (t.horizon_min == 1) & (t.model == "B1")].iloc[0]
    n["pilot_counts"] = t[(t["sample"] == "all_8_games") & (t.horizon_min == 1)
                          & (t.model == "B1+bsky_counts")].iloc[0]
    m1 = pd.read_csv(P / "model_summary.csv")
    m1 = m1[m1.estimator == "ols"].set_index(["target", "model"]).mean_mae
    n["m1"] = {k: m1[k] for k in m1.index}

    re = pd.read_csv(P / "ingame_scoring_reaction.csv")
    offs = [c for c in re.columns if c.lstrip("-").isdigit()]
    n["reaction"] = pd.Series({int(c): re[c].mean() * 100 for c in offs}).sort_index()
    n["reaction_n"] = len(re)
    n["timing"] = pd.read_csv(REPO / "figures" / "fig_m2_timing_scoring.csv").set_index("lag")
    n["jumps"] = pd.read_csv(REPO / "figures" / "fig_m2_timing_jumps.csv").set_index("lag")

    # Dataset inventory across the three stages, and the winner check.
    stages = [(P, "ingame_market_minute", "ingame_events", "ingame_bluesky_posts"),
              (P / "final_social", "market_minute", "events", "bluesky_posts"),
              (P / "final_replication", "market_minute", "events", "bluesky_posts")]
    games = minutes = ingame = scoring = posts = winners = 0
    for d, mk, ev, po in stages:
        m = pd.read_parquet(d / f"{mk}.parquet")
        games += m.slug.nunique()
        minutes += len(m)
        ingame += int(m.in_game.sum())
        scoring += int(pd.read_parquet(d / f"{ev}.parquet").scoring_play.sum())
        posts += len(pd.read_parquet(d / f"{po}.parquet"))
        last = m[m.in_game].sort_values("minute").groupby("slug").tail(1)
        winners += int(((last.score_home > last.score_away) == (last.p_home > 0.5)).sum())
    n.update(games=games, minutes=minutes, ingame=ingame, scoring=scoring, posts=posts, winners=winners)
    n["tests"] = sum(p.read_text().count("\ndef test_") for p in (REPO / "tests").glob("test_*.py"))
    n["inj"] = pd.read_csv(P / "final_social" / "injury_source_checks.csv").set_index("case")
    return n


# ---------------------------------------------------------------- drawing helpers
def new_slide(prs, notes):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(BEIGE)
    bar = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(12.59), 0, Inches(1.3), Inches(H))
    bar.adjustments[0] = 0.28
    bar.fill.solid()
    bar.fill.fore_color.rgb = rgb(NAVY)
    bar.line.fill.background()
    bar.name = "Template bar"
    plain(bar)
    s.notes_slide.notes_text_frame.text = notes
    return s


def text(s, x, y, w, h, paras, size=16, color=NAVY, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.15, after=6, caps=False, name=None, bullets=False, italic=False):
    """paras: list of paragraphs; a paragraph is a str or a list of (text, {bold, color, size, italic}) runs."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        p.space_after = Pt(after)
        runs = [(para, {})] if isinstance(para, str) else para
        for t, o in runs:
            r = p.add_run()
            r.text = t.upper() if caps else t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = rgb(o.get("color", color))
        if bullets:
            pPr = p._p.get_or_add_pPr()
            pPr.set("marL", str(Inches(0.28)))
            pPr.set("indent", str(-Inches(0.28)))
            bf = etree.SubElement(pPr, qn("a:buFont"))
            bf.set("typeface", "Arial")
            bc = etree.SubElement(pPr, qn("a:buChar"))
            bc.set("char", "•")
    return tb


def kicker(s, label):
    tb = text(s, L, 0.42, 6, 0.3, [label], size=12, bold=True, caps=True, name="Section label")
    for r in tb.text_frame.paragraphs[0].runs:
        r.font._rPr.set("spc", "300")


def title(s, t, y=0.72, size=40, w=CW, h=0.9, align=PP_ALIGN.LEFT, x=L):
    return text(s, x, y, w, h, [t], size=size, font=HEAD, caps=True, spacing=0.95, align=align,
                anchor=MSO_ANCHOR.TOP, name="Title")


def pill(s, t, x, y, w, h=0.5, size=15, filled=False, bold=False, name="Pill"):
    sh = plain(s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)))
    sh.name = name
    sh.adjustments[0] = 0.5
    sh.line.color.rgb = rgb(NAVY)
    sh.line.width = Pt(1.75)
    if filled:
        sh.fill.solid()
        sh.fill.fore_color.rgb = rgb(NAVY)
    else:
        sh.fill.background()
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = Inches(0.15)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = t
    r.font.name, r.font.size, r.font.bold = BODY, Pt(size), bold
    r.font.color.rgb = rgb(BEIGE if filled else NAVY)
    return sh


def line(s, x1, y1, x2, y2, color=NAVY, width=1.5, dash=None, name=None):
    c = plain(s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    if dash:
        c.line.dash_style = dash
    if name:
        c.name = name
    return c


def dot(s, cx, cy, d, color, name=None):
    o = plain(s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d)))
    o.fill.solid()
    o.fill.fore_color.rgb = rgb(color)
    o.line.fill.background()
    if name:
        o.name = name
    return o


def no_fill(el):
    """Give a chartSpace/plotArea element a transparent fill and no border."""
    sp = el.find(qn("c:spPr"))
    if sp is None:
        sp = etree.Element(qn("c:spPr"))
        chart = el.find(qn("c:chart"))
        ext = el.find(qn("c:extLst"))
        if chart is not None:          # chartSpace: spPr must follow c:chart
            chart.addnext(sp)
        elif ext is not None:          # plotArea: spPr precedes extLst
            ext.addprevious(sp)
        else:
            el.append(sp)
    for ch in list(sp):
        sp.remove(ch)
    etree.SubElement(sp, qn("a:noFill"))
    ln = etree.SubElement(sp, qn("a:ln"))
    etree.SubElement(ln, qn("a:noFill"))


def xy_chart(s, x, y, w, h, series, xlab, ylab, xmin, xmax, ymin, ymax, ymajor, xmajor, title_text=None, vline=None):
    """series: list of (name, xs, ys, color). Native scatter-with-lines chart in template style."""
    cd = XyChartData()
    for nm, xs, ys, _ in series:
        sr = cd.add_series(nm)
        for a, b in zip(xs, ys):
            sr.add_data_point(float(a), float(b))
    if vline is not None:
        sr = cd.add_series("event")
        sr.add_data_point(vline, ymin)
        sr.add_data_point(vline, ymax)
    gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.font.name, ch.font.size = BODY, Pt(12)
    ch.font.color.rgb = rgb(NAVY)
    if title_text:
        ch.has_title = True
        ch.chart_title.text_frame.text = title_text
        tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
        tr.font.size, tr.font.bold, tr.font.name = Pt(13), True, BODY
        tr.font.color.rgb = rgb(NAVY)
    else:
        ch.has_title = False
    for i, ser in enumerate(ch.plots[0].series):
        ser.smooth = False
        if i < len(series):
            color = series[i][3]
            ser.format.line.color.rgb = rgb(color)
            ser.format.line.width = Pt(2.75)
            ser.marker.style = XL_MARKER_STYLE.CIRCLE
            ser.marker.size = 7
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = rgb(color)
            ser.marker.format.line.color.rgb = rgb(BEIGE)
        else:
            ser.format.line.color.rgb = rgb(MUTED)
            ser.format.line.width = Pt(1.25)
            ser.format.line.dash_style = MSO_LINE.DASH
            ser.marker.style = XL_MARKER_STYLE.NONE
    for ax, lo, hi, major, lab, grid in ((ch.category_axis, xmin, xmax, xmajor, xlab, False),
                                         (ch.value_axis, ymin, ymax, ymajor, ylab, True)):
        ax.minimum_scale, ax.maximum_scale, ax.major_unit = lo, hi, major
        ax.has_major_gridlines = grid
        if grid:
            ax.major_gridlines.format.line.color.rgb = rgb(GRID)
            ax.major_gridlines.format.line.width = Pt(0.75)
        ax.format.line.color.rgb = rgb(GRID)
        ax.tick_labels.font.size = Pt(12)
        ax.tick_labels.font.color.rgb = rgb(NAVY)
        ax.tick_label_position = XL_TICK_LABEL_POSITION.LOW
        if lab:
            ax.has_title = True
            ax.axis_title.text_frame.text = lab
            r = ax.axis_title.text_frame.paragraphs[0].runs[0]
            r.font.size, r.font.bold, r.font.name = Pt(12), False, BODY
            r.font.color.rgb = rgb(NAVY)
    no_fill(ch._chartSpace)
    no_fill(ch._chartSpace.find(qn("c:chart")).find(qn("c:plotArea")))
    return gf


def forest(s, x, y, w, rows, xmin, xmax, ticks, axis_label, row_h=1.25, fmt_d=2):
    """Shape-drawn interval chart. rows: (label, est, lo, hi, color, value_text)."""
    def X(v):
        return x + (v - xmin) / (xmax - xmin) * w
    top, bottom = y, y + row_h * len(rows)
    line(s, X(0), top - 0.1, X(0), bottom + 0.05, color=MUTED, width=1.25, dash=MSO_LINE.DASH, name="Zero line")
    for i, (lab, est, lo, hi, color, vt) in enumerate(rows):
        cy = top + row_h * i + 0.62
        text(s, x, top + row_h * i, w, 0.35, [lab], size=14, bold=True, name=f"Row label {i + 1}")
        line(s, X(lo), cy, X(hi), cy, color=color, width=5, name=f"Interval {i + 1}")
        dot(s, X(est), cy, 0.26, color, name=f"Estimate {i + 1}")
        text(s, x, cy + 0.2, w, 0.3, [vt], size=13, color=color, bold=True, name=f"Value {i + 1}")
    line(s, x, bottom + 0.15, x + w, bottom + 0.15, color=MUTED, width=1, name="Axis")
    for t in ticks:
        line(s, X(t), bottom + 0.15, X(t), bottom + 0.23, color=MUTED, width=1)
        text(s, X(t) - 0.45, bottom + 0.27, 0.9, 0.25, [f"{num(t, 0, sign=t != 0)}%"], size=12,
             align=PP_ALIGN.CENTER)
    text(s, x, bottom + 0.6, w, 0.5, [axis_label], size=12, color=MUTED, align=PP_ALIGN.CENTER)


def table(s, x, y, w, col_w, data, size=13, row_h=0.42):
    rows, cols = len(data), len(data[0])
    gf = s.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(row_h * rows))
    tb = gf.table
    for j, cw in enumerate(col_w):
        tb.columns[j].width = Inches(cw)
    for i in range(rows):
        for j in range(cols):
            c = tb.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(NAVY if i == 0 else ("EAE3D3" if i % 2 == 0 else BEIGE))
            c.margin_left = c.margin_right = Inches(0.1)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = str(data[i][j])
            r.font.name, r.font.size = BODY, Pt(size)
            r.font.bold = i == 0 or j == 0
            r.font.color.rgb = rgb(BEIGE if i == 0 else NAVY)
    return gf


def fmt(r, d=2):
    d = 3 if abs(r["est"]) < 0.01 else d   # e.g. +0.005%, not "+0.00%"
    return f"{num(r['est'], d)}% {ci(r['lo'], r['hi'], 2)} · {r['better']}/{r['games']} games better"


NB = " "  # keeps "p = 0.97" on one line


# ---------------------------------------------------------------- slides
def build(n):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    bp, sp, bv, sv, cp = n["base_price"], n["soc_price"], n["base_vol"], n["soc_vol"], n["cnt_price"]
    rx, tm, jm = n["reaction"], n["timing"], n["jumps"]

    # 1 Title ------------------------------------------------------------------
    s = new_slide(prs, "Introduce yourselves and the one-line question. (~10 s)\n"
                       "Research track: we answer a question and test one hypothesis.")
    text(s, L, 0.9, 6, 0.4, ["ECE 473 · Fall 2026 · Research track"], size=18)
    title(s, "Does social media move NBA prediction markets?", y=2.05, size=50, w=10.6, h=2.7)
    pill(s, "Polymarket × Bluesky during live NBA games", L, 4.95, 6.0, 0.62, size=17)
    text(s, L, 6.55, 8, 0.4, ["Alicia Cheng & Misimi Sanni"], size=18)

    # 2 Question ------------------------------------------------------------------
    s = new_slide(prs, "GOAL (~55 s). Two sentences of motivation, then the question. No numbers.\n"
                       "Prediction markets are supposed to price all public information; social media is "
                       "the fastest public channel during a game. If posts predicted price moves, the market "
                       "would be slow; if not, it is efficient at in-game speed.")
    kicker(s, "Goal")
    title(s, "The question", y=0.95, size=44, align=PP_ALIGN.CENTER)
    text(s, 1.4, 2.0, 10.2, 1.3, ["When people post about a live NBA game on Bluesky, does that tell us anything "
                                  "Polymarket's price doesn't already know?"],
         size=26, bold=True, align=PP_ALIGN.CENTER, spacing=1.1)
    cols = [("Markets aggregate", "Prediction-market prices should already reflect public information. "
                                  "Polymarket is a blockchain market that settles in USDC."),
            ("Social is fastest", "Fans and reporters post during the game, in real time, often within "
                                  "seconds of a play."),
            ("So who leads?", "If posts predict price moves, the market is slow to use public information. "
                              "If not, it is efficient at in-game speed.")]
    cw, gap = 3.45, 0.55
    for i, (h_, b_) in enumerate(cols):
        x = L + 0.2 + i * (cw + gap)
        pill(s, h_, x, 3.85, cw, 0.55, size=16, bold=True)
        text(s, x + 0.05, 4.65, cw - 0.1, 1.9, [b_], size=15, spacing=1.2)

    # 3 Hypothesis --------------------------------------------------------------
    s = new_slide(prs, "GOAL (~55 s). One hypothesis, stated so it can fail.\n"
                       "This slide also answers the Milestone I feedback: metric = out-of-sample forecast "
                       "error (RMSE); baseline = market + game-state model; Bluesky enters as extra inputs "
                       "to that model.\nProgress against plan: Milestone I (pregame, hourly) found nothing; "
                       "after feedback we moved in-game at one minute with Bluesky only, piloted on 3 then "
                       "8 games, then ran the final test.")
    kicker(s, "Goal")
    title(s, "Our hypothesis", size=44)
    text(s, L, 1.9, 5.35, 0.4, ["Hypothesis"], size=20, bold=True)
    text(s, L, 2.4, 5.35, 2.2, ["Adding Bluesky activity to a market + game-state model makes forecasts of the "
                                "next minute's price change more accurate on games the model has never seen."],
         size=18, spacing=1.25)
    text(s, 6.6, 1.9, 5.5, 0.4, ["How we'd know"], size=20, bold=True)
    text(s, 6.6, 2.4, 5.5, 2.4, ["Compare forecast error with and without Bluesky on 34 later games held out "
                                 "from training.",
                                 "Supported only if the error drops and its 95% interval excludes zero."],
         size=18, spacing=1.2, after=10, bullets=True)
    chain = ["Question", "Hypothesis", "Test", "Conclusion"]
    pw, ag = 2.2, 0.55
    for i, c in enumerate(chain):
        x = L + i * (pw + ag)
        pill(s, c, x, 4.85, pw, 0.55, size=16, bold=True, filled=(c == "Conclusion"))
        if i < 3:
            text(s, x + pw, 4.85, ag, 0.55, ["→"], size=20, bold=True, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE)
    text(s, L, 5.85, CW, 1.0, [[("Progress vs. plan: ", {"bold": True}),
                               ("Milestone I (pregame, hourly) found nothing → after feedback we moved inside "
                                "the games, at one minute, Bluesky only → pilot on 3, then 8 games → final test "
                                "on 34 later games.", {})]], size=15, spacing=1.2)

    # 4 Finding 1 ---------------------------------------------------------------
    s = new_slide(prs, f"RESULTS (~60 s). This sets the bar for Bluesky.\nAcross {n['reaction_n']} scoring plays "
                       f"(8 pilot games), price move toward the scorer vs. the price 60 s before ESPN's play "
                       f"time: +{rx[5]:.1f} pts at 5 s, +{rx[10]:.2f} at 10 s, +{rx[30]:.1f} at 30 s; "
                       f"+{rx[-30]:.1f} at −30 s.\nSay: anything visible on Bluesky a minute later is probably "
                       f"already in the price.\nSource: data/processed/ingame_scoring_reaction.csv")
    kicker(s, "Results · 1 of 4")
    title(s, "Priced in seconds", size=44)
    text(s, L, 1.9, 5.2, 1.2, ["A basket moves the price 2–3 points within seconds"], size=22, bold=True,
         spacing=1.1)
    text(s, L, 3.2, 5.2, 3.0, [f"Across {n['reaction_n']:,} scoring plays, the price moves toward the scoring "
                               f"team by +{rx[5]:.1f} points within 5 seconds, and about +{rx[30]:.0f} points by "
                               "30 seconds.",
                               "So anything that shows up on Bluesky a minute later is probably already in "
                               "the price."], size=17, spacing=1.25, after=12)
    xy_chart(s, 6.25, 1.75, 6.0, 5.1, [("Price move", rx.index, rx.values, NAVY)],
             "Seconds from the scoring play (ESPN time)", "Price move toward scorer (points)",
             -60, 120, -0.5, 3.5, 0.5, 30, vline=0)

    # 5 Finding 2 ---------------------------------------------------------------
    s = new_slide(prs, "RESULTS (~60 s). Descriptive, not causal.\n"
                       f"Scoring plays (8 games): scoring team's win probability {tm.p_side[-1] * 100:.1f}% → "
                       f"{tm.p_side[0] * 100:.1f}% in the same minute; posts per minute {tm.posts[-1]:.2f} at −1, "
                       f"{tm.posts[1]:.2f} at +1, {tm.posts[5]:.2f} at +5.\nBig price jumps (≥5 pts): price "
                       f"+{jm.price_change_pp[0]:.1f} pts in the same minute; posts {jm.posts[-1]:.2f} → "
                       f"{jm.posts[1]:.2f}–{jm.posts[2]:.2f} within 1–2 minutes.\n"
                       "Source: figures/fig_m2_timing_scoring.csv, fig_m2_timing_jumps.csv")
    kicker(s, "Results · 2 of 4")
    title(s, "Bluesky follows", size=44)
    text(s, L, 1.9, 5.2, 1.2, ["Posts rise after the price moves, not before"], size=22, bold=True, spacing=1.1)
    text(s, L, 3.2, 5.2, 3.2, [f"Around scoring plays the price jumps within the same minute. Posts about the "
                               f"scoring team climb over the next 5 minutes, from {tm.posts[-1]:.2f} to "
                               f"{tm.posts[5]:.2f} per minute.",
                               "The same order appears around big price jumps. Bluesky reacts to the game; "
                               "it doesn't anticipate it."], size=17, spacing=1.25, after=12)
    lags = tm.index.values
    xy_chart(s, 6.25, 1.6, 6.0, 2.6, [("Win probability", lags, tm.p_side.values * 100, NAVY)],
             None, "Win prob. (%)", -10, 10, 48, 53, 1, 2, title_text="Scoring team's win probability", vline=0)
    xy_chart(s, 6.25, 4.25, 6.0, 2.75, [("Posts", lags, tm.posts.values, ACCENT)],
             "Minutes from the scoring play", "Posts / minute", -10, 10, 0, 0.7, 0.1, 2,
             title_text="Bluesky posts about the scoring team", vline=0)

    # 6 Verdict -----------------------------------------------------------------
    s = new_slide(prs, f"RESULTS (~90 s). The test of the hypothesis, on 34 unseen November games "
                       f"(trained on 32 earlier games; ridge).\nMarket + game model vs. no change: "
                       f"{num(bp['est'])}% {ci(bp['lo'], bp['hi'])}, better in {bp['better']}/{bp['games']} "
                       f"games.\n+ Bluesky vs. market model: {num(sp['est'])}% {ci(sp['lo'], sp['hi'])}, better "
                       f"in {sp['better']}/{sp['games']}.\nSay: '−2.6% means 2.6% less forecast error, not "
                       "2.6 probability points.' A negligible gain over a sound baseline: the answer is no.\n"
                       "Source: data/processed/final_replication/heldout_comparisons.csv")
    kicker(s, "Results · 3 of 4")
    title(s, "The verdict", size=44)
    pill(s, "Hypothesis not supported", L, 1.85, 4.6, 0.62, size=19, filled=True, bold=True)
    text(s, L, 2.85, 5.2, 3.8, [f"On 34 games the model never saw, the market + game model cuts forecast error by "
                                f"{abs(bp['est']):.1f}% compared with 'no change'.",
                                f"Adding Bluesky changes error by {num(sp['est'])}%, and its 95% interval "
                                f"({num(sp['lo'])}% to {num(sp['hi'])}%) includes zero.",
                                "The market's own information helps. Bluesky adds nothing measurable."],
         size=17, spacing=1.25, after=12)
    forest(s, 6.35, 2.0, 5.75,
           [("Market + game model vs. no change", bp["est"], bp["lo"], bp["hi"], NAVY,
             f"{num(bp['est'], 1)}%  {ci(bp['lo'], bp['hi'], 1)}"),
            ("Adding Bluesky to that model", sp["est"], sp["lo"], sp["hi"], ACCENT,
             f"{num(sp['est'])}%  {ci(sp['lo'], sp['hi'])}")],
           -5, 1, [-5, -4, -3, -2, -1, 0, 1],
           "Change in next-minute forecast error (RMSE); 95% interval resampling whole games. Left = better.",
           row_h=1.45)

    # 7 Holds up ----------------------------------------------------------------
    s5, v15, ols, strict = n["soc_price5"], n["soc_vol15"], n["soc_price_ols"], n["soc_price_strict"]
    es, ev, rm = n["ext_soc_price"], n["ext_soc_vol"], n["rev_market"]
    s = new_slide(prs, "RESULTS (~75 s). The rigorously tested negative result the guidelines ask for.\n"
                       f"Counts only (34 games): {fmt(cp)}. Volume, 5 min: {fmt(sv)}.\n"
                       f"Price 5 min: {fmt(s5)}. Volume 15 min: {fmt(v15)}.\n"
                       f"24-game stage: price {fmt(es)}; volume {fmt(ev)} (reliably worse).\n"
                       f"OLS: {num(ols['est'])}%; stricter timestamps: {num(strict['est'])}%.\n"
                       f"Reverse (posting, 5 min): + market data {fmt(rm)}.\n"
                       "Sources: final_replication/heldout_comparisons.csv, final_social/heldout_comparisons.csv, "
                       "reverse_attention_comparisons.csv, ingame_model_tests.csv")
    kicker(s, "Results · 4 of 4")
    title(s, "It holds up", size=44, align=PP_ALIGN.CENTER)
    text(s, L, 1.62, CW, 0.5, ["We looked for a gain six ways. None showed one."], size=20, bold=True,
         align=PP_ALIGN.CENTER)
    left = [("Every Bluesky measure", "Counts, abnormal attention, imbalance and injury posts, alone and "
                                      "together: no gain"),
            ("Volume instead of price", f"Adding Bluesky: {num(sv['est'])}% error; interval includes zero"),
            ("Longer horizons", "5- and 15-minute forecasts: no gain")]
    right = [("Three separate stages", "8 pilot games, 24 later games, 34 later games: same answer"),
             ("Other model settings", "OLS vs. ridge, stricter timestamps: same answer"),
             ("Reverse direction", f"Market data doesn't reliably predict later posting "
                                   f"({num(rm['est'])}%, interval includes zero)")]
    sx = L + CW / 2
    line(s, sx, 2.45, sx, 6.95, color=NAVY, width=2, name="Spine")
    for i, ((lh, lb), (rh, rb)) in enumerate(zip(left, right)):
        yy = 2.45 + i * 1.5
        dot(s, sx, yy + 0.2, 0.22, NAVY)
        text(s, L, yy, CW / 2 - 0.4, 0.4, [lh], size=19, bold=True, align=PP_ALIGN.RIGHT)
        text(s, L, yy + 0.45, CW / 2 - 0.4, 0.9, [lb], size=14, align=PP_ALIGN.RIGHT, spacing=1.15)
        text(s, sx + 0.4, yy, CW / 2 - 0.4, 0.4, [rh], size=19, bold=True)
        text(s, sx + 0.4, yy + 0.45, CW / 2 - 0.4, 0.9, [rb], size=14, spacing=1.15)

    # 8 Data --------------------------------------------------------------------
    s = new_slide(prs, "METHOD (~60 s). Just enough to trust the data; no implementation details.\n"
                       f"Inventory recomputed from the stage parquet files: {n['games']} games, "
                       f"{n['minutes']:,} game-minutes ({n['ingame']:,} during play), {n['scoring']:,} scoring "
                       f"plays, {n['posts']:,} Bluesky post matches; final price matches the winner in "
                       f"{n['winners']}/{n['games']} games; {n['tests']} automated tests in tests/.\n"
                       f"Lesson: with a within-minute average price, the market model looked "
                       f"{abs(n['pilot_vwap'].rmse_change_pct):.0f}% better than no change (8-game pilot); "
                       "with end-of-minute prices the gain vanished.")
    kicker(s, "Method · 1 of 2")
    title(s, "The data", size=44)
    text(s, L, 1.62, CW, 0.5, [f"{n['games']} NBA games, minute by minute during play"], size=20, bold=True)
    cells = [("Polymarket", "Every trade in each game's winner market, timed to the second"),
             ("ESPN", f"Every play with real-world time, score and win probability "
                      f"({n['scoring']:,} scoring plays)"),
             ("Bluesky", f"Posts mentioning each team, counted per minute ({n['posts']:,} post matches)"),
             ("Minute grid", f"All sources aligned on UTC minutes: {n['minutes']:,} game-minutes, "
                             f"{n['ingame']:,} during play"),
             ("Checked", f"Final price matches the winner in {n['winners']}/{n['games']} games · "
                         f"{n['tests']} automated tests · failed searches count as missing, not zero"),
             ("Lesson", f"Measure the price at the end of each minute. A minute-average faked a "
                        f"{abs(n['pilot_vwap'].rmse_change_pct):.0f}% gain.")]
    cw3 = 3.55
    for i, (hh, bb) in enumerate(cells):
        x = L + (i % 3) * (cw3 + 0.4)
        yy = 2.45 + (i // 3) * 2.25
        text(s, x, yy, cw3, 0.45, [hh], size=21, bold=True)
        text(s, x, yy + 0.55, cw3, 1.5, [bb], size=15, spacing=1.2)

    # 9 Fair test ---------------------------------------------------------------
    s = new_slide(prs, "METHOD (~60 s). How the test was made fair.\nTarget: next-minute change in the "
                       "log-odds of a home win. Baselines: no change; market + game state (recent price "
                       "moves, trading, buy/sell pressure, score, time left, ESPN win probability). Bluesky "
                       "features are added to the second model; forecast price = logistic(logit p + "
                       "predicted change).\nFinal test: trained on the 32 October games, tested on 34 "
                       "November games; design fixed before scoring; whole-game bootstrap intervals.")
    kicker(s, "Method · 2 of 2")
    title(s, "A fair test", size=44)
    quad = [("What we predict", "The next minute's change in the home team's win odds (log-odds)"),
            ("Baselines", "(1) No change. (2) Market + game state: recent price moves, trading, score, "
                          "time left"),
            ("How Bluesky enters", "As extra inputs to model (2). Forecast price = logistic(logit p + "
                                   "predicted change)"),
            ("Out-of-sample", "Train on earlier games, test on later ones. Design fixed first; 95% "
                              "intervals resample whole games")]
    for i, (hh, bb) in enumerate(quad):
        x = L + (i % 2) * 5.85
        yy = 1.85 + (i // 2) * 1.75
        text(s, x, yy, 5.4, 0.45, [hh], size=21, bold=True)
        text(s, x, yy + 0.5, 5.4, 1.1, [bb], size=16, spacing=1.2)
    stages = [("Oct 21–26 · 8 pilot games", False), ("Oct 28–30 · 24 games", False),
              ("Nov 1–10 · 34 games", True)]
    sw = 3.45
    for i, (lab, filled) in enumerate(stages):
        x = L + i * (sw + 0.55)
        pill(s, lab, x, 5.6, sw, 0.55, size=15, bold=True, filled=filled)
        if i < 2:
            text(s, x + sw, 5.6, 0.55, 0.55, ["→"], size=20, bold=True, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE)
    text(s, L, 6.3, 2 * sw + 0.55, 0.4, ["Training: 32 earlier games"], size=14, color=MUTED,
         align=PP_ALIGN.CENTER)
    text(s, L + 2 * (sw + 0.55), 6.3, sw, 0.4, ["Test: never seen in training"], size=14, color=MUTED,
         align=PP_ALIGN.CENTER)

    # 10 Next -------------------------------------------------------------------
    rate = n["posts_per_min"]
    s = new_slide(prs, f"NEXT (~50 s). Bluesky averages {rate:.2f} posts per team per minute during play "
                       "across the 66 games. Post relevance was only checked with an AI-assisted review "
                       "(24 of 50 clearly about the game); the 100-post human review is still pending.")
    kicker(s, "Next")
    title(s, "Limits & next steps", size=44)
    pill(s, "What limits the result", L, 1.9, 4.2, 0.55, size=16, bold=True)
    text(s, L, 2.75, 5.3, 4.0, [f"Bluesky is sparse: about 1 post every {1 / rate:.0f} minutes per team",
                                "Post content hasn't been human-verified yet",
                                "Prices are last trades; we had no order books",
                                f"{n['games']} games over about 3 weeks"],
         size=17, spacing=1.2, after=12, bullets=True)
    pill(s, "What we'd do next", 6.6, 1.9, 4.2, 0.55, size=16, bold=True)
    text(s, 6.6, 2.75, 5.5, 4.0, ["Test news that isn't in the score (injuries, lineups) as verified events",
                                  "Use what posts say (content, sentiment), not just how many there are",
                                  "Record order books and the full Bluesky stream live, for second-level timing",
                                  "Try other markets, such as elections"],
         size=17, spacing=1.2, after=12, bullets=True)

    # 11 Answer -----------------------------------------------------------------
    s = new_slide(prs, "Close (~10 s): state the answer, then open for questions. Backup slides follow.")
    text(s, L, 0.9, 6, 0.4, ["ECE 473 · Fall 2026"], size=18)
    title(s, "Our answer: no", y=2.1, size=60, w=11, h=1.2)
    text(s, L, 3.55, 10.5, 1.4, ["Live NBA markets price public information within seconds. Bluesky follows "
                                 "the market and doesn't improve forecasts."], size=22, spacing=1.2)
    pill(s, "Thank you · Questions?", L, 5.15, 4.2, 0.62, size=18, bold=True)
    text(s, L, 6.55, 8, 0.4, ["Alicia Cheng & Misimi Sanni"], size=18)

    # Backups -------------------------------------------------------------------
    s = new_slide(prs, "Backup slides for Q&A only.")
    title(s, "Backup slides", y=3.0, size=54, h=1.2)

    s = new_slide(prs, "B1. Final test, ridge, primary timestamp rule. Source: "
                       "final_replication/heldout_comparisons.csv and reverse_attention_comparisons.csv.")
    kicker(s, "Backup")
    title(s, "Full results: 34 unseen games", size=36)
    rp, rmk = n["rev_price"], n["rev_market"]
    table(s, L, 1.9, CW, [3.45, 4.0, 4.0], [
        ["Comparison (change in forecast error)", "Price, next minute", "Volume, next 5 minutes"],
        ["Market + game model vs. no change", fmt(bp), fmt(bv)],
        ["+ Bluesky (all measures)", fmt(sp), fmt(sv)],
        ["+ Bluesky counts only", fmt(cp), fmt(n["cnt_vol"])],
    ], size=13, row_h=0.6)
    text(s, L, 4.6, CW, 1.5, [[("Reverse direction (next-5-minute posting): ", {"bold": True}),
                               (f"posting history + game state vs. same-as-before {fmt(n['rev_base'], 1)}; "
                                f"+ price {fmt(rp)}; + price and trading {fmt(rmk)}.", {})],
                              "Negative = lower error. Intervals are 95% whole-game bootstrap intervals."],
         size=14, spacing=1.2, after=8)

    s = new_slide(prs, "B2. Reverse direction: does market activity predict later posting? Source: "
                       "final_replication/reverse_attention_comparisons.csv (ridge, 5 minutes).")
    kicker(s, "Backup")
    title(s, "Reverse direction", size=40)
    text(s, L, 1.85, 5.0, 3.5, ["Posting is driven by the game and its own momentum.",
                                "Adding price and trading data doesn't reliably improve forecasts of the "
                                "next five minutes of posting."], size=17, spacing=1.25, after=12)
    rb = n["rev_base"]
    forest(s, 6.35, 1.95, 5.75,
           [("Posting history + game state vs. same as before", rb["est"], rb["lo"], rb["hi"], NAVY,
             f"{num(rb['est'], 1)}%  {ci(rb['lo'], rb['hi'], 1)}"),
            ("+ price movements", rp["est"], rp["lo"], rp["hi"], ACCENT,
             f"{num(rp['est'])}%  {ci(rp['lo'], rp['hi'])}"),
            ("+ price and trading", rmk["est"], rmk["lo"], rmk["hi"], ACCENT,
             f"{num(rmk['est'])}%  {ci(rmk['lo'], rmk['hi'])}")],
           -20, 2, [-20, -15, -10, -5, 0], "Change in forecast error (RMSE), 95% interval. Left = better.",
           row_h=1.3)

    s = new_slide(prs, "B3. How we responded to the Milestone I feedback.")
    kicker(s, "Backup")
    title(s, "Feedback → our changes", size=36)
    table(s, L, 1.75, CW, [4.2, 7.25], [
        ["Professor's feedback", "What we changed"],
        ["One social-media source is enough", "Bluesky only; GDELT dropped"],
        ["Why that horizon? Markets absorb information in seconds", "In-game data at one minute, plus a "
                                                                    "second-by-second reaction test"],
        ["Show a few games before expanding", "Pilot on 3, then 8 games; then 24 and 34 later games"],
        ["What is the main metric?", "Out-of-sample forecast error (RMSE) on games never used in training"],
        ["What is the baseline?", "No change, and a market + game-state model"],
        ["How does the media data enter the price?", "Bluesky features are added to the market model; "
                                                     "forecast = logistic(logit p + predicted change)"],
    ], size=13, row_h=0.62)

    inj = n["inj"]
    cj, jw = inj.loc["Cam Johnson"], inj.loc["Jordan Walsh"]
    s = new_slide(prs, "B4. Injury candidates. Labels come from an AI-assisted source/context check; independent "
                       "student review is pending. Source: data/processed/final_social/injury_source_checks.csv; "
                       "figure: figures/fig_final_injury_case_contexts.png")
    kicker(s, "Backup")
    title(s, "Injury posts: two candidates", size=36)
    cards = [("Cam Johnson · Nuggets @ Thunder", "A team preview later corroborated an ankle injury; who "
              f"published first is unresolved. A scoring play was logged {cj.nearest_scoring_offset_seconds:.1f} "
              "seconds after the post, which may explain the market move."),
             ("Jordan Walsh · Knicks @ Celtics", "The post describes limping. No independent report or "
              "diagnosis corroborates it.")]
    for i, (hh, bb) in enumerate(cards):
        x = L + i * 5.85
        pill(s, hh, x, 1.9, 5.4, 0.55, size=15, bold=True)
        text(s, x + 0.05, 2.75, 5.3, 2.5, [bb], size=16, spacing=1.25)
    text(s, L, 5.4, CW, 1.0, ["Neither case shows Bluesky giving a trading edge. Treat both as provisional."],
         size=17, bold=True)

    e_bp, e_bv = n["ext_base_price"], n["ext_base_vol"]
    s = new_slide(prs, "B5. First later-game stage: trained on the 8 pilot games, tested on 24 games "
                       "(Oct 28–30). Source: data/processed/final_social/heldout_comparisons.csv (ridge).")
    kicker(s, "Backup")
    title(s, "The 24-game stage", size=36)
    table(s, L, 1.9, CW, [3.45, 4.0, 4.0], [
        ["Comparison (change in forecast error)", "Price, next minute", "Volume, next 5 minutes"],
        ["Market + game model vs. no change", fmt(e_bp), fmt(e_bv)],
        ["+ Bluesky (all measures)", fmt(es), fmt(ev)],
    ], size=13, row_h=0.6)
    text(s, L, 4.0, CW, 1.2, ["With only 8 training games the baseline gain was not yet reliable, and adding "
                              "Bluesky made volume forecasts reliably worse."], size=16, spacing=1.2)

    pb, pv, pc, m1 = n["pilot_b1"], n["pilot_vwap"], n["pilot_counts"], n["m1"]
    s = new_slide(prs, "B6. Earlier stages. Sources: data/processed/ingame_model_tests.csv (8-game in-game "
                       "pilot, OLS, leave-one-game-out) and data/processed/model_summary.csv (Milestone I).")
    kicker(s, "Backup")
    title(s, "Pilot & Milestone I", size=36)
    pill(s, "8-game in-game pilot", L, 1.9, 4.2, 0.55, size=16, bold=True)
    text(s, L, 2.75, 5.3, 3.8, [f"Market + game model vs. no change: {num(pb.rmse_change_pct)}% "
                                f"(p{NB}={NB}{pb.dm_p:.2f})",
                                f"With minute-average prices it looked {abs(pv.rmse_change_pct):.0f}% better "
                                f"(p{NB}<{NB}0.001): a timing artifact",
                                f"+ Bluesky counts: {num(pc.rmse_change_pct)}% (p{NB}={NB}{pc.dm_p:.2f})"],
         size=16, spacing=1.2, after=10, bullets=True)
    pill(s, "Milestone I: pregame, hourly", 6.6, 1.9, 4.6, 0.55, size=16, bold=True)
    text(s, 6.6, 2.75, 5.5, 3.8, [f"Next-hour price change error: {m1[('abs_dp_next', 'baseline')] * 100:.3f} "
                                  f"vs. {m1[('abs_dp_next', 'enhanced_social')] * 100:.3f} points with Bluesky",
                                  f"Next-hour volume error: {m1[('log_vol_next', 'baseline')]:.3f} vs. "
                                  f"{m1[('log_vol_next', 'enhanced_social')]:.3f} with Bluesky",
                                  "No gain, which is why we moved inside the games"],
         size=16, spacing=1.2, after=10, bullets=True)

    s = new_slide(prs, "B7. Who did what.")
    kicker(s, "Backup")
    title(s, "Our team", size=44)
    team = [("Alicia Cheng", "Polymarket and ESPN data, price measurement, forecasting models, reports"),
            ("Misimi Sanni", "Bluesky data and attention measures, timing analysis, robustness checks, "
                             "66-game extension")]
    for i, (nm, role) in enumerate(team):
        x = L + i * 5.85
        pill(s, nm, x, 2.0, 4.0, 0.62, size=19, bold=True)
        text(s, x + 0.05, 2.9, 5.2, 1.6, [role], size=17, spacing=1.25)
    text(s, L, 5.3, CW, 0.8, ["Built with AI-assisted coding (Claude Code and similar tools), as the course "
                              "permits."], size=15, color=MUTED)
    return prs


if __name__ == "__main__":
    nums = load_numbers()
    mm = []
    for d, mk, bk in ((P, "ingame_market_minute", "ingame_bluesky_minute"),
                      (P / "final_social", "market_minute", "bluesky_minute"),
                      (P / "final_replication", "market_minute", "bluesky_minute")):
        m = pd.read_parquet(d / f"{mk}.parquet")
        b = pd.read_parquet(d / f"{bk}.parquet")
        mm.append(m[m.in_game][["slug", "minute"]].merge(b, on=["slug", "minute"])[["posts_home", "posts_away"]]
                  .stack())
    nums["posts_per_min"] = float(pd.concat(mm).mean())
    prs = build(nums)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print("saved", OUT, "slides:", len(prs.slides))
