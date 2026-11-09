"""D70 Pareto summary (descriptive): recovery vs work lost per world x K, verify_snap and oracle
restore; Pareto flags among policies on the SAME machines; D66 products as reference points."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "C:/PROJECTS/ISM")
from slowburn.bench import plotstyle as ps  # noqa: E402

plt = ps.plt
ps.apply_style()
OUT = Path("paper/generated")
OUT.mkdir(parents=True, exist_ok=True)
WORLDS, KS = ["uniform", "early", "late", "bursty"], [4, 6, 8, 12]
STYLE = {  # policy -> (slot, marker, filled, label)
    "slowburn": (0, "o", True, "SlowBurn"), "prior_only": (1, "o", True, "prior-only"),
    "tower_of_hanoi": (2, "s", True, "Tower of Hanoi"), "gfs": (3, "s", True, "GFS"),
    "shamir_exact": (4, "^", True, "Bar-On exact"), "shamir_rr": (5, "^", True, "Bar-On round-robin"),
    "shamir_recursive": (6, "^", True, "Bar-On recursive"), "toh_eqh": (7, "D", True, "ToH equal horizon"),
    "gfs_eqh": (3, "D", False, "GFS equal horizon")}
REST = {"verify_snap": ("clean_recovery", "work_lost_whole_system_hours"),
        "oracle": ("oracle_clean_recovery", "oracle_work_lost_whole_system_hours")}
DELAYS = [7, 14, 30, 45, 60]


def load(run):
    d = pd.read_csv(f"results/{run}/tuning_sweep.csv", low_memory=False)
    d = d[d.budget_kind == "count"].copy()
    d["q"] = d.detect_prob.astype(float)
    return d


d69, d68 = load("dev_d69_full"), load("dev_d68_equal_horizon")
d68 = d68[d68.policy.isin(["toh_eqh", "gfs_eqh"])]
prod = pd.read_csv("results/dev_d66_retention_audit/audit_rows.csv.gz")
prod = prod[prod.discovery_delay.isin(DELAYS) & ~prod["product"].str.contains(r"_r\d+$")]


def pareto(df):
    flag = []
    for _, r in df.iterrows():
        dom = ((df.recovery >= r.recovery) & (df.work_lost_h <= r.work_lost_h)
               & ((df.recovery > r.recovery) | (df.work_lost_h < r.work_lost_h))).any()
        flag.append(not dom)
    return flag


pts = []
for qsel, qname in ((None, "all_q"), (0.0, "q0"), (1.0, "q1")):
    for rest, (rc, wc) in REST.items():
        srcs = [d69] + ([d68] if rest == "verify_snap" else [])
        for src in srcs:
            x = src if qsel is None else src[src.q == qsel]
            g = x.groupby(["world", "budget", "policy"]).agg(recovery=(rc, "mean"), work_lost_h=(wc, "mean"), rows=(rc, "size")).reset_index()
            pts.append(g.assign(restore=rest, q=qname, source="d69" if src is d69 else "d68"))
P = pd.concat(pts, ignore_index=True)
P["pareto"] = False
for key, g in P.groupby(["q", "restore", "world", "budget"]):
    P.loc[g.index, "pareto"] = pareto(g)
# D66 reference points (own machines, no K)
ref = []
for qsel, qname in ((None, "all_q"), (0.0, "q0"), (1.0, "q1")):
    x = prod if qsel is None else prod[prod.detect_prob == qsel]
    g = x.groupby(["world", "product"]).agg(recovery=("clean_recovery", "mean"), held=("clean_point_held", "mean"), work_lost_h=("work_lost_whole_system_hours", "mean")).reset_index()
    ref.append(g.assign(q=qname))
REF = pd.concat(ref, ignore_index=True)
P.to_csv(OUT / "pareto_points.csv", index=False)
REF.to_csv(OUT / "pareto_reference_products_d66.csv", index=False)

for qname in ("all_q", "q0", "q1"):
    for rest in REST:
        fig, axes = plt.subplots(4, 4, figsize=(13, 11), sharey=True)
        for i, w in enumerate(WORLDS):
            for j, K in enumerate(KS):
                ax = axes[i, j]
                rf = REF[(REF.q == qname) & (REF.world == w)]
                ax.scatter(rf.work_lost_h, rf.recovery, s=14, color=ps.MUTED, alpha=0.6, marker="x", linewidths=0.8, zorder=1)
                g = P[(P.q == qname) & (P.restore == rest) & (P.world == w) & (P.budget == K)]
                for _, r in g.iterrows():
                    slot, mk, filled, _ = STYLE[r.policy]
                    c = ps.CATEGORICAL[slot]
                    ax.scatter(r.work_lost_h, r.recovery, s=46, marker=mk, facecolors=c if filled else ps.SURFACE,
                               edgecolors=ps.INK if r.pareto else c, linewidths=1.6 if r.pareto else 1.2, zorder=3)
                ax.set_title(f"{w}, K = {K}", fontsize=9)
                if j == 0:
                    ax.set_ylabel("clean recovery")
                if i == 3:
                    ax.set_xlabel("work lost (h)")
                ax.set_ylim(-0.03, 1.03)
        handles = [plt.Line2D([], [], marker=m, linestyle="", markersize=7, markerfacecolor=ps.CATEGORICAL[s] if f else ps.SURFACE,
                              markeredgecolor=ps.CATEGORICAL[s], label=l) for s, m, f, l in STYLE.values()]
        handles += [plt.Line2D([], [], marker="o", linestyle="", markersize=7, markerfacecolor="none", markeredgecolor=ps.INK, markeredgewidth=1.6, label="Pareto optimal (ink ring)"),
                    plt.Line2D([], [], marker="x", linestyle="", markersize=6, color=ps.MUTED, label="D66 product defaults (other machines; reference only)")]
        fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=8)
        fig.suptitle(f"Recovery vs work lost, {rest} restore, {'all q' if qname == 'all_q' else qname.replace('q', 'q = ')} (DEV, D70)", x=0.01, ha="left", fontsize=11, fontweight="bold")
        fig.tight_layout(rect=(0, 0.07, 1, 0.97))
        f = OUT / f"fig_pareto_{rest}{'' if qname == 'all_q' else '_' + qname}.png"
        fig.savefig(f, dpi=150); plt.close(fig); print("wrote", f)
print(P[(P.q == "all_q") & P.pareto].groupby(["restore", "policy"]).size().unstack(fill_value=0).to_string())
