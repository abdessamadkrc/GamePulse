"""Rule-based lifecycle segments (executed in SQL, see db/02_derived.sql) plus an optional
K-Means behavioural clustering for comparison."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from ..cache import cached
from ..db import query_df
from ..filters import Filters
from ..segment_rules import SEGMENT_DEFINITIONS, SEGMENT_ORDER

FEATURES = ["sessions_30d", "minutes_30d", "matches_30d", "revenue_total", "days_since_last_session",
            "days_since_install"]
FEATURE_LABELS = {
    "sessions_30d": "Sessions (30d)", "minutes_30d": "Play minutes (30d)", "matches_30d": "Matches (30d)",
    "revenue_total": "Lifetime spend ($)", "days_since_last_session": "Days since last session",
    "days_since_install": "Tenure (days)",
}


@cached
def distribution(f: Filters) -> list[dict[str, Any]]:
    """Segment sizes and behaviour. Segments are a snapshot at the last day of data, so only the
    population filters (country/platform/source/game mode) apply, not the date window."""
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT b.segment, COUNT(*) AS players,
               AVG(b.sessions_30d)::float8 AS sessions_30d,
               AVG(b.minutes_30d)::float8 AS minutes_30d,
               AVG(b.matches_30d)::float8 AS matches_30d,
               AVG(b.revenue_total)::float8 AS avg_spend,
               SUM(b.revenue_total)::float8 AS revenue,
               AVG(b.days_since_last_session)::float8 AS days_since_last,
               AVG(b.d7)::float8 AS d7
        FROM scope b GROUP BY 1
    """, f.params())
    total = df.players.sum()
    rev_total = df.revenue.sum()
    df["share"] = df.players / total if total else 0
    df["revenue_share"] = df.revenue / rev_total if rev_total else 0
    df["_o"] = df.segment.map({s: i for i, s in enumerate(SEGMENT_ORDER)})
    df = df.sort_values("_o").drop(columns="_o")
    return df.to_dict("records")


def definitions() -> list[dict[str, Any]]:
    return SEGMENT_DEFINITIONS


@cached
def segment_by_dimension(f: Filters, dim_sql: str, dim_name: str) -> list[dict[str, Any]]:
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT {dim_sql} AS dim, b.segment, COUNT(*) AS players
        FROM scope b GROUP BY 1, 2
    """, f.params())
    out = []
    for dim, g in df.groupby("dim"):
        tot = g.players.sum()
        row: dict[str, Any] = {dim_name: dim, "players": int(tot)}
        for seg in SEGMENT_ORDER:
            row[seg] = float(g.loc[g.segment == seg, "players"].sum() / tot)
        out.append(row)
    return out


# ------------------------------------------------------------------ K-Means
def _label_clusters(centroids: pd.DataFrame) -> dict[int, str]:
    """Give each cluster a business-readable name from its centroid (real units)."""
    names: dict[int, str] = {}
    left = set(centroids.index)

    def pick(score: pd.Series, label: str) -> None:
        if not left:
            return
        idx = score[list(left)].idxmax()
        names[int(idx)] = label
        left.discard(idx)

    pick(centroids.revenue_total, "Spenders")
    pick(centroids.sessions_30d, "Most active")
    pick(centroids.days_since_last_session, "Lapsed")
    pick(-centroids.days_since_install, "Newcomers")
    for n, i in enumerate(sorted(left), start=1):
        names[int(i)] = "Low activity" if len(left) == 1 else f"Low activity {n}"
    return names


@cached
def kmeans(k: int = 5, seed: int = 42) -> dict[str, Any]:
    """K-Means on log-scaled behavioural features of ALL players (snapshot at last data day)."""
    df = query_df(f"SELECT player_id, {', '.join(FEATURES)}, segment FROM player_base")
    X = np.log1p(df[FEATURES].clip(lower=0).to_numpy(dtype=float))
    Xs = StandardScaler().fit_transform(X)

    inertia = []
    for kk in range(2, 9):
        inertia.append({"k": kk, "inertia": float(KMeans(kk, n_init=3, random_state=seed).fit(Xs).inertia_)})

    model = KMeans(k, n_init=10, random_state=seed).fit(Xs)
    df["cluster"] = model.labels_
    rng = np.random.default_rng(seed)
    sample_idx = rng.choice(len(df), size=min(6000, len(df)), replace=False)
    sil = float(silhouette_score(Xs[sample_idx], model.labels_[sample_idx]))

    centroids = df.groupby("cluster")[FEATURES].mean()
    names = _label_clusters(centroids)
    sizes = df.cluster.value_counts().sort_index()
    clusters = []
    for c in centroids.index:
        g = df[df.cluster == c]
        clusters.append({
            "cluster": int(c),
            "name": names[int(c)],
            "players": int(len(g)),
            "share": float(len(g) / len(df)),
            "profile": {FEATURE_LABELS[f]: float(centroids.loc[c, f]) for f in FEATURES},
            "top_rule_segment": g.segment.value_counts().idxmax(),
        })
    clusters.sort(key=lambda r: -r["players"])

    pts = PCA(2, random_state=seed).fit_transform(Xs[sample_idx[:1500]])
    scatter = [{"x": float(x), "y": float(y), "cluster": names[int(c)]}
               for (x, y), c in zip(pts, model.labels_[sample_idx[:1500]])]

    cross = pd.crosstab(df.segment, df.cluster.map(names), normalize="index")
    overlap = [{"segment": s, **{c: float(cross.loc[s, c]) for c in cross.columns}}
               for s in SEGMENT_ORDER if s in cross.index]
    return {
        "k": k, "silhouette": sil, "features": list(FEATURE_LABELS.values()),
        "clusters": clusters, "elbow": inertia, "scatter": scatter, "overlap_with_rules": overlap,
        "note": "K-Means is an exploratory cross-check on the rule-based segments: it finds groups from "
                "behaviour alone, without our business rules. Cluster names are auto-assigned from centroids.",
    }
