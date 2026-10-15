"""K = 12 diagnostic (D37): with an attack-free prior-like posterior, how many slots does
PosteriorDP use, and does it delete yesterday's snapshot because it has zero marginal value
under the gated loss?

Run: ``uv run python -m slowburn.bench.diag_k12``. Before the D37 fix (commit 7cb91da) it
printed kept size 2/2.00/2 at K = 8 and 12 without a backbone, 3 at K = 8 and 4 at K = 12 with
backbone 0.25 (day-199 set [193, 197, 198, 199]: no snapshot older than 6 days), and "yesterday
deleted with zero marginal value on 98/99 days". After the fix the kept size equals K.
"""

import numpy as np

from slowburn.retention.base import PosteriorDP, replay
from slowburn.retention.dp import (
    discovery_survival,
    expected_loss,
    gate_day,
    retention_posterior,
)

S = discovery_survival("uniform", 60)
h = 1 - 0.95 ** (1 / 60)


def pi_for(day):
    s = np.arange(day + 1)
    post = np.r_[h * (1 - h) ** (day - s), 0.0]  # constant hazard, recent starts
    post[-1] = 1 - post[:-1].sum()
    return retention_posterior(post, day, S)


def extra(day):
    p = pi_for(day)
    return {"retention_pi": p, "prior_retention_pi": p}


for K, bb in [(8, 0.0), (12, 0.0), (8, 0.25), (12, 0.25), (12, 0.5)]:
    hist = replay(PosteriorDP(90.0, gate=0.8, backbone=bb), 200, K, extra)
    sizes = [len(x) for x in hist[100:]]
    print(
        f"K={K} backbone={bb}: kept size min/mean/max over days 100-199 = "
        f"{min(sizes)}/{np.mean(sizes):.2f}/{max(sizes)}; day-199 set {sorted(hist[-1])}"
    )

# zero-marginal-value check, no backbone, K=12
hist = replay(PosteriorDP(90.0, gate=0.8), 200, 12, extra)
zero = 0
for t in range(101, 200):
    held = sorted(hist[t - 1] | {t})
    kept = sorted(hist[t])
    p = pi_for(t)
    g = gate_day(p, 0.8)
    if t - 1 not in kept:
        with_y = sorted(set(kept) | {t - 1})
        d = expected_loss(kept, p, 90.0, 0.8) - expected_loss(with_y, p, 90.0, 0.8)
        zero += abs(d) < 1e-12
print(
    f"days 101-199: yesterday deleted with zero marginal value on {zero}/99 days; "
    f"gate day g = t - {200 - 1 - gate_day(pi_for(199), 0.8):.0f} at t=199"
)
