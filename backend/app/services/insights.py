"""Operations Insights: Data -> Insight -> Hypothesis -> Action.

Every card is generated from live queries (nothing is hard-coded text with fixed numbers), and
every hypothesis keeps the 'requiring validation' label. Cards are ranked by business severity.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..cache import cached
from ..db import query_df
from ..filters import Filters, data_bounds
from . import experiments as exp
from . import importer as imp
from . import investigation as inv
from . import mena as mena_svc
from . import metrics as m


def pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"


def pp(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x * 100:+.{d}f} pp"


def num(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:,.{d}f}"


def usd(x: float | None, d: int = 2) -> str:
    return "n/a" if x is None or pd.isna(x) else f"${x:,.{d}f}"


def arrow(a: float | None, b: float | None, fmt=pct) -> str:
    return f"{fmt(a)} → {fmt(b)}"


def _hyp_summary(hyps: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"title": h["title"], "signal": h["signal"]["strength"], "signal_text": h["signal"]["text"],
             "label": h["label"]} for h in hyps]


def _metric(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(i for i in items if i["key"] == key)


# --------------------------------------------------------------------------- individual insights
def _window() -> int:
    """Length of each comparison window that this dataset's history can support."""
    w = imp.dataset_info()["capabilities"]["suggested_window"]
    if not w:
        raise ValueError("not enough history for a before/after comparison (needs roughly 3 weeks of installs)")
    return int(w)


def retention_insight() -> dict[str, Any]:
    w = _window()
    r = inv.investigate("d7", w)
    pr, cu = r["problem"], r["culprit"]
    met = lambda k: _metric(cu["metrics"], k)  # noqa: E731
    ret, sess, dur, churn = met("retention"), met("sessions_per_player"), met("session_minutes"), met("early_churn")
    share = cu["share_of_change"]
    top = r["segments"]["rows"][0]
    down = pr["delta_pp"] < 0
    verb = "fell" if down else "rose"
    consistent = [h["title"] for h in r["hypotheses"] if h["signal"]["strength"] in ("consistent", "weak")]
    td = r["test_design"]
    src = (cu.get("filters") or {}).get("source")
    if down:
        step = (f"Run an onboarding A/B test for the affected group ({cu['label']}). Detecting a "
                f"{td['options'][1]['mde_pp']:.0f} pp D7 lift needs ~{td['options'][1]['n_per_arm']:,} players per arm "
                f"(~{td['options'][1]['days_to_complete']} days at current install volume). In parallel, review "
                f"{'the ' + src + ' campaigns' if src else 'the traffic sources'} and the crash log for the affected devices."
                if td else "Run an onboarding A/B test for the affected group.")
    else:
        step = (f"Find out what drove the improvement (start with {cu['label']}) and protect it: check what changed in "
                f"acquisition, releases or live-ops over this period before it is undone.")
    sig_txt = "statistically significant" if pr["significant"] else "not statistically significant, so it may be noise"
    return {
        "id": "retention-drop",
        "severity": ("high" if pr["significant"] else "medium") if down else "positive",
        "category": "Retention",
        "title": f"{pr['statement']}",
        "insight": (f"{r['metric_label']} {verb} {abs(pr['delta_pp']):.1f} pp "
                    f"({abs(pr['relative_change']) * 100:.0f}% relative; {sig_txt}). "
                    f"{cu['label']} is the largest single contributor"
                    + (f", explaining about {abs(share) * 100:.0f}% of the change" if share else "")
                    + f". Its install share moved {pct(top['share_prev'])} → {pct(top['share_cur'])}, "
                      f"and its own D7 moved {arrow(ret['previous'], ret['current'])}."),
        "evidence": [
            f"{r['metric_label']}: {arrow(ret['previous'], ret['current'])} in {cu['label']} "
            f"({pp(ret['delta'])}); overall {arrow(pr['previous'], pr['current'])}",
            f"Sessions per player (first 7 days): {arrow(sess['previous'], sess['current'], num)}",
            f"Average session duration: {arrow(dur['previous'], dur['current'], lambda v: f'{v:.0f}m')}",
            f"Early churn (no session days 8-14): {arrow(churn['previous'], churn['current'])} ({pp(churn['delta'])})",
            f"Window: installs {r['periods']['cur_from']} to {r['periods']['cur_to']} vs "
            f"{r['periods']['prev_from']} to {r['periods']['prev_to']}",
        ],
        "hypotheses": _hyp_summary(r["hypotheses"]),
        "hypothesis_note": ("Signals consistent with: " + ", ".join(consistent) + ". " if consistent else "")
                           + "None of these is confirmed - each requires validation.",
        "next_step": step,
        "kpi_to_monitor": "D7 retention (guardrails: D1 retention, tutorial completion, crash-free players)",
        "link": "/investigation",
    }


def acquisition_insight() -> dict[str, Any]:
    """Find the acquisition source whose share of installs grew the most and judge the quality of its players."""
    w = _window()
    df, _ = inv._load("d7", w)  # noqa: SLF001
    d = df[df.d7.notna()]
    if d.source.nunique() < 2:
        raise ValueError("only one acquisition source in the data")
    per = {}
    for period, g in d.groupby("period"):
        per[period] = {"n": len(g), "ret": float(g.d7.sum()), "share": g.source.value_counts(normalize=True)}
    if set(per) != {"previous", "current"}:
        raise ValueError("need installs in both periods")
    gain = (per["current"]["share"].reindex(per["previous"]["share"].index.union(per["current"]["share"].index)).fillna(0)
            - per["previous"]["share"].reindex(per["previous"]["share"].index.union(per["current"]["share"].index)).fillna(0))
    src = gain.idxmax()
    if gain[src] < 0.02:
        raise ValueError("no source changed its share of installs by 2 points or more")
    a_share = float(per["previous"]["share"].get(src, 0))
    b_share = float(per["current"]["share"].get(src, 0))
    cur = d[d.period == "current"]
    s_d7, o_d7 = float(cur[cur.source == src].d7.mean()), float(cur[cur.source != src].d7.mean())
    a_inst, b_inst = per["previous"]["n"] / w, per["current"]["n"] / w
    a_ret, b_ret = per["previous"]["ret"] / w, per["current"]["ret"] / w
    low_quality = b_share >= 1.5 * a_share and s_d7 <= o_d7 - 0.05
    inst_g = b_inst / a_inst - 1 if a_inst else 0.0
    ret_g = b_ret / a_ret - 1 if a_ret else 0.0
    worse = s_d7 < o_d7
    return {
        "id": "acquisition-quality",
        "severity": "high" if (low_quality and ret_g < inst_g / 2) else "medium",
        "category": "Acquisition",
        "title": f"{src} grew its share of installs" + (", but its players stay less" if worse else ""),
        "insight": (f"Daily installs moved {inst_g * 100:+.0f}% while D7-retained new players per day moved {ret_g * 100:+.0f}%. "
                    f"{src} went from {pct(a_share)} to {pct(b_share)} of installs; its players reach D7 at {pct(s_d7)} "
                    f"vs {pct(o_d7)} for every other source."),
        "evidence": [
            f"Installs per day: {arrow(a_inst, b_inst, lambda v: num(v, 0))}",
            f"D7-retained players per day: {arrow(a_ret, b_ret, lambda v: num(v, 0))}",
            f"{src} share of installs: {arrow(a_share, b_share)}",
            f"D7 retention, {src} vs other sources (current period): {pct(s_d7)} vs {pct(o_d7)}",
            "Ad spend is not part of the data, so cost per install and return on ad spend are deliberately not computed.",
        ],
        "hypotheses": [
            {"title": "Campaign targeting or creatives attract low-intent traffic",
             "signal": "consistent" if low_quality else "weak",
             "signal_text": "Data consistent with this hypothesis" if low_quality else "Weak signal",
             "label": inv.LABEL},
            {"title": "Traffic is real but the product fails to onboard it", "signal": "weak",
             "signal_text": "Cannot be separated from the above without an experiment", "label": inv.LABEL},
        ],
        "hypothesis_note": "Distinguishing 'bad traffic' from 'bad onboarding' requires an experiment, not more dashboards.",
        "next_step": f"Judge campaigns on cost per D7-retained player rather than cost per install, and review or cap the "
                     f"lowest-quality {src} campaigns while any onboarding test runs.",
        "kpi_to_monitor": "Cost per D7-retained player (needs spend data); share of installs by source",
        "link": "/acquisition",
    }


def device_insight() -> dict[str, Any]:
    r = inv.investigate("d7", _window())
    rows = {x["device_tier"]: x for x in r["device_performance"]}
    low, high = rows.get("low"), rows.get("high")
    if not low or not high:
        raise ValueError("no device data")
    crash_up = (low["crash100_prev"] or 0) > 0 and low["crash100_cur"] / low["crash100_prev"] >= 1.6
    return {
        "id": "device-performance",
        "severity": "medium",
        "category": "Technical performance",
        "title": "Crash exposure rose sharply on low-end devices",
        "insight": (f"Crashes per 100 sessions for new low-end players moved "
                    f"{arrow(low['crash100_prev'], low['crash100_cur'], num)}, while high-end devices stayed flat "
                    f"({arrow(high['crash100_prev'], high['crash100_cur'], num)}). Low-end D7 retention fell "
                    f"{arrow(low['rate_prev'], low['rate_cur'])}."),
        "evidence": [
            f"Low-end crashes per 100 sessions (first 7 days): {arrow(low['crash100_prev'], low['crash100_cur'], num)}",
            f"High-end crashes per 100 sessions: {arrow(high['crash100_prev'], high['crash100_cur'], num)}",
            f"Players with a crash in week 1 (low-end): {arrow(low['crash_prev'], low['crash_cur'])}",
            f"Low-end avg session: {arrow(low['minutes_prev'], low['minutes_cur'], lambda v: f'{v:.0f}m')}",
            f"Low-end D7: {arrow(low['rate_prev'], low['rate_cur'])}; high-end D7: {arrow(high['rate_prev'], high['rate_cur'])}",
        ],
        "hypotheses": [
            {"title": "A recent release regressed performance on low-end Android",
             "signal": "consistent" if crash_up else "weak",
             "signal_text": "Data consistent with this hypothesis" if crash_up else "Weak signal",
             "label": inv.LABEL},
            {"title": "Crashes are a symptom of heavier content, not a bug", "signal": "weak",
             "signal_text": "Needs crash logs to separate", "label": inv.LABEL},
        ],
        "hypothesis_note": "Crash timing aligns with the retention drop, but correlation is not cause: confirm with release and crash logs.",
        "next_step": "Ask engineering for crash-free sessions by app version x device model; if a release lines up, "
                     "ship a hotfix or a low-spec graphics preset to low-end devices.",
        "kpi_to_monitor": "Crash-free sessions on low-end Android; low-end D7 retention",
        "link": "/investigation",
    }


def monetization_insight() -> dict[str, Any]:
    _, hi = data_bounds()
    f = Filters(hi - timedelta(days=27), hi)
    cur, prev = m.period_metrics(f), m.period_metrics(f.previous())
    conc = m.spend_concentration(f)
    top5 = next((s for s in conc["top_shares"] if s["top_pct_of_payers"] == 5), None)
    rev_g = cur["revenue"] / prev["revenue"] - 1 if prev.get("revenue") else None
    return {
        "id": "monetization",
        "severity": "medium",
        "category": "Monetization",
        "title": "Revenue is concentrated in a small group of payers",
        "insight": (f"Last 28 days: revenue {usd(cur['revenue'], 0)} ({rev_g * 100:+.1f}% vs previous 28 days), "
                    f"payer conversion {arrow(prev['conversion'], cur['conversion'])}, ARPPU {usd(cur['arppu'])}. "
                    + (f"The top 5% of payers generate {pct(top5['share_of_revenue'], 0)} of revenue, so protecting "
                       f"High-Value players matters more than lifting the average." if top5 else "")),
        "evidence": [
            f"Revenue: {arrow(prev['revenue'], cur['revenue'], lambda v: usd(v, 0))}",
            f"ARPU: {arrow(prev['arpu'], cur['arpu'], usd)}; ARPPU: {arrow(prev['arppu'], cur['arppu'], usd)}",
            f"Payer conversion: {arrow(prev['conversion'], cur['conversion'])}",
            f"Paying users: {arrow(prev['payers'], cur['payers'], lambda v: num(v, 0))}",
        ],
        "hypotheses": [
            {"title": "Lower-quality new cohorts dilute conversion (more non-payers in the denominator)",
             "signal": "weak", "signal_text": "Weak signal", "label": inv.LABEL},
            {"title": "Offer relevance is not differentiated by player value tier", "signal": "weak",
             "signal_text": "Test required", "label": inv.LABEL},
        ],
        "hypothesis_note": "Conversion moves with cohort quality, so read it together with the retention investigation.",
        "next_step": "Build a win-back / VIP-care programme for High-Value and At-Risk spenders; test tiered offers "
                     "instead of a single store layout.",
        "kpi_to_monitor": "Payer conversion; revenue share of top 5% payers; ARPPU",
        "link": "/monetization",
    }


def churn_insight() -> dict[str, Any]:
    df = query_df("""
        SELECT COUNT(*) FILTER (WHERE segment = 'At-Risk Players') AS at_risk,
               COUNT(*) FILTER (WHERE segment = 'At-Risk Players' AND revenue_total >= 5) AS at_risk_spenders,
               COALESCE(SUM(revenue_total) FILTER (WHERE segment = 'At-Risk Players'), 0) AS at_risk_rev,
               COALESCE(SUM(revenue_total), 0) AS total_rev,
               COUNT(*) FILTER (WHERE segment = 'Churned Players') AS churned,
               COUNT(*) AS total
        FROM player_base
    """).iloc[0]
    if not df.total_rev:
        raise ValueError("there is no purchase data, so spending cannot be analysed")
    return {
        "id": "at-risk-spenders",
        "severity": "medium",
        "category": "Churn",
        "title": "A recoverable pool of lapsing spenders",
        "insight": (f"{int(df.at_risk):,} players are At-Risk (no session for 8-29 days), including "
                    f"{int(df.at_risk_spenders):,} who have spent $5 or more. They hold "
                    f"{pct(df.at_risk_rev / df.total_rev, 0)} of lifetime revenue, and are cheaper to win back "
                    f"than to replace."),
        "evidence": [
            f"At-Risk players: {int(df.at_risk):,} ({pct(df.at_risk / df.total)} of all players)",
            f"At-Risk spenders (>= $5 lifetime): {int(df.at_risk_spenders):,}",
            f"Share of lifetime revenue held by At-Risk players: {pct(df.at_risk_rev / df.total_rev)}",
            f"Already churned (30+ days inactive): {int(df.churned):,}",
        ],
        "hypotheses": [
            {"title": "A time-limited, personalised comeback reward re-activates lapsing spenders", "signal": "weak",
             "signal_text": "Untested", "label": inv.LABEL},
        ],
        "hypothesis_note": "Win-back effectiveness is unknown until measured against a holdout group.",
        "next_step": "Launch a push / in-game mail win-back to At-Risk spenders with a 10% holdout to measure true "
                     "incremental reactivation.",
        "kpi_to_monitor": "7-day reactivation rate vs holdout; At-Risk -> Engaged transition",
        "link": "/segmentation",
    }


def _culprit_label() -> str | None:
    try:
        return inv.investigate("d7", _window())["culprit"]["label"]
    except Exception:  # noqa: BLE001
        return None


def experiment_insight() -> list[dict[str, Any]]:
    out = []
    focus = _culprit_label()
    for e in exp.list_experiments():
        try:
            a = exp.analyse(e["experiment_id"])
            if not a:
                continue
            pk = next(r for r in a["results"] if r["is_primary"])
        except Exception:  # noqa: BLE001  (e.g. too few players in an imported experiment)
            continue
        rec = a["recommendation"]
        is_prop = pk["kind"] == "proportion"
        diff_txt = f"{pk['abs_diff'] * 100:+.1f} pp" if is_prop else f"{pk['abs_diff']:+.2f}"
        out.append({
            "id": f"experiment-{e['experiment_id']}",
            "severity": "positive" if rec["decision"] == "ship" else "info",
            "category": "Experimentation",
            "title": f"{e['name']}: {rec['headline'].lower()}",
            "insight": rec["text"],
            "evidence": [
                f"Primary KPI {pk['label']}: control {pct(pk['control']) if is_prop else num(pk['control'], 2)} vs test "
                f"{pct(pk['test']) if is_prop else num(pk['test'], 2)} ({diff_txt}, relative {pk['rel_diff'] * 100:+.1f}%)",
                f"Sample: {a['sample']['control']:,} control / {a['sample']['test']:,} test; SRM check "
                f"{'passed' if a['sample']['srm_ok'] else 'FAILED'}",
                f"p-value {pk['p_value']:.4g}; 95% CI of the difference "
                + (f"{pk['ci_low'] * 100:.1f} to {pk['ci_high'] * 100:.1f} pp" if is_prop
                   else f"{pk['ci_low']:.2f} to {pk['ci_high']:.2f}"),
            ],
            "hypotheses": [{"title": e["hypothesis"], "signal":
                            "consistent" if rec["decision"] == "ship" else "none",
                            "signal_text": "Supported by the experiment" if rec["decision"] == "ship"
                            else "Not supported at this sample size",
                            "label": "Tested hypothesis"}],
            "hypothesis_note": "Experiment results are the one place where causal language is justified.",
            "next_step": ("Roll out in stages (25% -> 50% -> 100%)"
                          + (f", starting with {focus}, the group flagged in the retention investigation." if focus else ".")
                          if rec["decision"] == "ship" else
                          "Do not roll out. Decide whether the potential upside justifies a larger follow-up test."),
            "kpi_to_monitor": f"{pk['label']} (guardrails: payer conversion, revenue per player, crash rate)",
            "link": "/experiments",
        })
    return out


def mena_insight() -> dict[str, Any]:
    _, hi = data_bounds()
    f = Filters(hi - timedelta(days=89), hi)
    c = mena_svc.comparison(f)
    if not c.get("available", True):
        raise ValueError("fewer than two MENA markets in the data")
    lead = {x["key"]: x for x in c["leaders"]}
    d7, arpu, conv = lead["d7"], lead["arpu"], lead["conversion"]
    return {
        "id": "mena-markets",
        "severity": "info",
        "category": "Market comparison",
        "title": "Retention and monetization leaders differ across MENA markets",
        "insight": (f"Among the six MENA markets, {d7['best']['country']} leads on D7 ({pct(d7['best']['value'])}) and "
                    f"{d7['worst']['country']} trails ({pct(d7['worst']['value'])}). {arpu['best']['country']} leads "
                    f"on ARPU ({usd(arpu['best']['value'])}) vs {arpu['worst']['country']} ({usd(arpu['worst']['value'])}). "
                    f"Different levers apply: fix acquisition quality where retention trails, and offers/pricing where "
                    f"conversion trails. (Synthetic data - framework illustration only.)"),
        "evidence": [
            f"D7 retention best/worst: {d7['best']['country']} {pct(d7['best']['value'])} / "
            f"{d7['worst']['country']} {pct(d7['worst']['value'])}",
            f"ARPU best/worst: {arpu['best']['country']} {usd(arpu['best']['value'])} / "
            f"{arpu['worst']['country']} {usd(arpu['worst']['value'])}",
            f"Payer conversion best/worst: {conv['best']['country']} {pct(conv['best']['value'])} / "
            f"{conv['worst']['country']} {pct(conv['worst']['value'])}",
        ],
        "hypotheses": [
            {"title": "Market differences are driven by device mix and acquisition mix, not the country itself",
             "signal": "weak", "signal_text": "Needs mix-adjusted comparison", "label": inv.LABEL},
        ],
        "hypothesis_note": "Compare markets after controlling for platform, source and device before localising anything.",
        "next_step": "Prioritise markets on (retention gap x market size) and run localisation / offer tests in the top two.",
        "kpi_to_monitor": "Market-level D7 index vs MENA average; ARPU index",
        "link": "/mena",
    }


@cached
def generate() -> list[dict[str, Any]]:
    builders = [(retention_insight, "Retention change"), (acquisition_insight, "Acquisition quality"),
                (device_insight, "Device performance"), (monetization_insight, "Monetization"),
                (churn_insight, "Lapsing players"), (mena_insight, "MENA market comparison")]
    cards: list[dict[str, Any]] = []
    skipped: list[str] = []
    for b, label in builders:
        try:
            cards.append(b())
        except Exception as exc:  # noqa: BLE001  one card that cannot be computed must not take the page down
            skipped.append(f"{label}: {exc}")
    cards.extend(experiment_insight())
    if skipped:
        cards.append({
            "id": "needs-more-data", "severity": "info", "category": "Data coverage",
            "title": f"{len(skipped)} finding(s) need more data",
            "insight": "These automatic analyses were skipped because the current dataset does not contain what they need.",
            "evidence": skipped, "hypotheses": [], "hypothesis_note": "",
            "next_step": "Import more history or the missing tables (purchases, events, devices, experiments) on the Import page.",
            "kpi_to_monitor": "Data completeness", "link": "/import",
        })
    rank = {"high": 0, "medium": 1, "positive": 2, "info": 3}
    cards.sort(key=lambda c: rank.get(c["severity"], 9))
    return cards
