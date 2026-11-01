"""Paper figures (IEEE Access draft), from the TEST analysis outputs (results/analysis_test,
frozen_v2; neither figure compares DEV and TEST, so no DEV series):
- fig_d74_recovery_vs_delay.pdf: best-response recovery (evaluation half, recovery-minimising
  attacker, restore A, NapierOne v2) vs discovery delay, one line per policy, K 4 / 8 panels;
  at K = 8 Tower of Hanoi is its own equal-horizon configuration.
- fig_c2_d79_forest.pdf: SlowBurn's relative work lost vs each baseline (C2) and the age-capped
  SlowBurn vs the equal-horizon schedules (D79), NapierOne v2, paired bootstrap 95% CIs.
Palette: the dataviz reference categorical slots in fixed order (validated, light mode); every
line also carries a distinct marker and a legend entry. Run from the repo root:

    uv run python paper/scripts/fig_paper.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

OUT = Path("paper/ieee_access/figures")
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
POLICIES = [("slowburn", "SlowBurn", "o"), ("prior_only", "Prior-only", "s"),
            ("shamir_recursive", "Bar-On recursive", "^"), ("gfs", "GFS", "D"),
            ("tower_of_hanoi", "Tower of Hanoi", "v"),
            ("toh_eqh", "ToH equal horizon", "P")]  # fmt: skip
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False})  # fmt: skip


def recovery_vs_delay():
    br = pd.read_csv("results/analysis_test/d74_report/best_response.csv")
    br = br[(br.arm == "napierone_bytes") & (br.restore == "A") & (br.objective == "rec")
            & (br.analysis == "primary_feasible")]  # fmt: skip
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.4), sharey=True)
    for ax, K in zip(axes, (4, 8), strict=True):
        for i, (pol, label, mk) in enumerate(POLICIES):
            g = br[(br.policy == pol) & (br.budget == K)].sort_values("discovery_delay")
            if g.empty:
                continue
            ax.plot(g.discovery_delay, g.eval_rec, color=SERIES[i], lw=1.5, marker=mk, ms=4,
                    mec="white", mew=0.8, label=label, solid_capstyle="round")  # fmt: skip
        ax.axvline(60, color=MUTED, lw=0.8, ls=(0, (3, 3)))
        ax.text(61, 0.97, "assumed bound M = 60", color=MUTED, fontsize=6.5, va="top")
        ax.set_title(f"K = {K}", color=INK, fontsize=8)
        ax.set_xlabel("discovery delay (days)")
        ax.set_xticks([7, 14, 30, 45, 60, 90, 120])
        ax.set_ylim(-0.03, 1.03)
        ax.grid(axis="y", color=GRID, lw=0.6)
    axes[0].set_ylabel("clean recovery\n(best-response attacker)")
    h, lab = axes[1].get_legend_handles_labels()
    if not h:
        h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=len(lab), frameon=False, fontsize=7,
               bbox_to_anchor=(0.5, 1.06))  # fmt: skip
    fig.savefig(OUT / "fig_d74_recovery_vs_delay.pdf", bbox_inches="tight")


def forest():
    c2 = pd.read_csv("results/analysis_test/d72_c2r_holm/c2_holm.csv")
    c2 = c2[c2.arm == "napierone_bytes"]
    d79 = pd.read_csv("results/analysis_test/d79_report/primary.csv")
    d79 = d79[d79.arm == "napierone_bytes"]
    names = {"gfs": "GFS (default)", "tower_of_hanoi": "Tower of Hanoi (default)",
             "shamir_recursive": "Bar-On recursive", "shamir_rr": "Bar-On round robin",
             "gfs_eqh": "GFS equal horizon", "toh_eqh": "ToH equal horizon"}  # fmt: skip
    rows = [(f"SlowBurn vs {names[r.vs]}", r) for r in c2.itertuples()]
    rows += [(f"Age-capped SlowBurn vs {names[r.vs]}", r) for r in d79.itertuples()]
    fig, ax = plt.subplots(figsize=(3.45, 2.6))
    for y, (label, r) in enumerate(reversed(rows)):
        lo, hi, pt = 100 * r.work_lost_rel_lo, 100 * r.work_lost_rel_hi, 100 * r.work_lost_rel
        ax.plot([lo, hi], [y, y], color=SERIES[0], lw=1.5, solid_capstyle="round")
        ax.plot(pt, y, "o", color=SERIES[0], ms=4, mec="white", mew=0.8)
        ax.text(-40, y, label, ha="right", va="center", fontsize=6.5, color=INK)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.axhline(len(d79) - 0.5, color=GRID, lw=0.8)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlim(-40, 40)
    ax.set_xlabel("relative work lost (%)\n< 0: SlowBurn loses less", fontsize=7)
    ax.grid(axis="x", color=GRID, lw=0.6)
    fig.savefig(OUT / "fig_c2_d79_forest.pdf", bbox_inches="tight")


def overhead():
    """Exploratory E1: median wall time per daily decision vs K (results/exploratory/overhead)."""
    o = pd.read_csv("results/exploratory/overhead/overhead.csv")
    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    lines = [(o[(o.policy == "slowburn") & (o.M == M)], f"SlowBurn, M = {M}", mk, SERIES[i])
             for i, (M, mk) in enumerate(((30, "o"), (60, "s"), (120, "^"), (365, "D")))]
    lines += [(o[o.policy == "gfs"], "GFS", "v", SERIES[4]),
              (o[o.policy == "tower_of_hanoi"], "Tower of Hanoi", "P", SERIES[5])]  # fmt: skip
    for g, label, mk, col in lines:
        g = g.sort_values("K")
        ax.plot(g.K, g.ms_median, color=col, lw=1.5, marker=mk, ms=4, mec="white", mew=0.8,
                label=label)  # fmt: skip
    ax.set_yscale("log")
    ax.set_xticks([4, 6, 8, 12, 16, 24])
    ax.set_xlabel("budget K (snapshots)")
    ax.set_ylabel("median ms per daily decision")
    ax.grid(axis="y", color=GRID, lw=0.6, which="both")
    ax.legend(frameon=False, fontsize=6.5, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.3))
    fig.savefig(OUT / "fig_overhead.pdf", bbox_inches="tight")


def architecture():
    """System overview: data flow from file versions to the restore (no data)."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    w, h, top, bot = 0.2, 0.3, 0.62, 0.17
    boxes = {  # name: (x, y, text); top row = decision path, bottom row = data and restore
        "files": (0.02, top, "Machine files\n(benign edits;\nsimulated damage)"),
        "det": (0.27, top, "Write-time detector\nflag per changed\nversion (p <= 0.01)"),
        "post": (0.52, top, "Start posterior\npi_t(s), conditioned\non not discovered"),
        "dp": (0.77, top, "Retention DP\nkeep K snapshots\n(+ ToH backbone)"),
        "snap": (0.02, bot, "Daily snapshot\n(all file versions)"),
        "alarm": (0.27, bot, "Daily count alarm\nfires if k_t >= c"),
        "rest": (0.52, bot, "Restore at discovery\nA verify_snap\n(B-E alternatives)"),
        "store": (0.77, bot, "Held snapshots\n(K per machine)"),
    }
    fig, ax = plt.subplots(figsize=(7.0, 2.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.04, 1)
    ax.axis("off")
    for x, y, text in boxes.values():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                                    fc="white", ec=MUTED, lw=0.9))  # fmt: skip
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.5, color=INK)

    def right(n):
        return boxes[n][0] + w, boxes[n][1] + h / 2

    def left(n):
        return boxes[n][0], boxes[n][1] + h / 2

    def below(n):
        return boxes[n][0] + w / 2, boxes[n][1]

    def above(n):
        return boxes[n][0] + w / 2, boxes[n][1] + h

    arrows = [(right("files"), left("det")), (right("det"), left("post")),
              (right("post"), left("dp")), (below("files"), above("snap")),
              (below("det"), above("alarm")), (below("post"), above("rest")),
              (below("dp"), above("store")), (right("alarm"), left("rest")),
              (left("store"), right("rest"))]  # fmt: skip
    for p, q in arrows:
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=7, color=SERIES[0],
                                     lw=0.9, shrinkA=1, shrinkB=1))  # fmt: skip
    # snapshots enter the held set under the DP's decision: routed below the bottom row
    (sx, sy), (tx, ty) = below("snap"), below("store")
    ax.plot([sx, sx, tx], [sy, -0.02, -0.02], color=SERIES[0], lw=0.9)
    ax.add_patch(FancyArrowPatch((tx, -0.02), (tx, ty), arrowstyle="-|>", mutation_scale=7,
                                 color=SERIES[0], lw=0.9, shrinkA=0, shrinkB=1))  # fmt: skip
    fig.savefig(OUT / "fig_architecture.pdf", bbox_inches="tight")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    recovery_vs_delay()
    forest()
    overhead()
    architecture()
