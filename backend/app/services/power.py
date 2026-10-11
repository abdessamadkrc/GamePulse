"""Sample-size and power maths for proportion KPIs, shared by the Investigation page and the Experiment Hub.

One implementation on purpose: if two pages quote different sample sizes for the same test, nobody trusts either.
All functions use statsmodels' NormalIndPower with Cohen's h (arcsine effect size), two-sided.
"""
from __future__ import annotations

import numpy as np
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize


def sample_size_control(baseline: float, lift_pp: float, power: float = 0.8, alpha: float = 0.05,
                        ratio: float = 1.0) -> int:
    """Players needed in the CONTROL arm to detect `lift_pp` percentage points over `baseline`.
    `ratio` = n_test / n_control. The test arm needs ceil(n_control * ratio)."""
    target = min(baseline + lift_pp / 100.0, 0.999)
    es = abs(proportion_effectsize(target, baseline))
    n = NormalIndPower().solve_power(effect_size=es, alpha=alpha, power=power, ratio=ratio, alternative="two-sided")
    return int(np.ceil(n))


def mde_pp(baseline: float, n_control: int, n_test: int, power: float = 0.8, alpha: float = 0.05) -> float | None:
    """Smallest absolute lift (percentage points) detectable with the given sample."""
    if n_control < 2 or n_test < 2 or not 0 < baseline < 1:
        return None
    es = NormalIndPower().solve_power(nobs1=n_control, alpha=alpha, power=power, ratio=n_test / n_control,
                                      alternative="two-sided")
    p1 = np.sin(np.arcsin(np.sqrt(baseline)) + es / 2) ** 2
    return float((p1 - baseline) * 100)
