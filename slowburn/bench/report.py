"""Render result CSVs as markdown tables, so reports quote generated numbers verbatim."""

from __future__ import annotations

import pandas as pd


def md_table(df: pd.DataFrame, floatfmt: str = "{:.4f}", index: bool = True) -> str:
    if index:
        df = df.reset_index()
    cols = [str(c) if not isinstance(c, tuple) else " ".join(map(str, c)) for c in df.columns]

    def fmt(v) -> str:
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        return str(v)

    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def detector_tables(auroc: pd.DataFrame) -> dict[str, str]:
    """Markdown tables for the detector write-up (chunk + file level)."""
    out = {}
    chunk = auroc[auroc.level == "chunk"]
    for model in sorted(chunk.damage_model.unique()):
        sub = chunk[chunk.damage_model == model]
        piv = sub.pivot_table(index="file_type", columns="fraction", values="auroc")
        piv = piv[sorted(piv.columns, reverse=True)]
        piv.columns = [f"{int(round(c * 100))}%" for c in piv.columns]
        out[f"chunk_{model}"] = md_table(piv)
    head = chunk[chunk.file_type.isin(["ALL", "HIGH_ENTROPY", "LOW_ENTROPY"])]
    alpha_cols = [c for c in head.columns if c.startswith(("tpr_at", "fpr_at"))]
    cols = ["damage_model", "fraction", "file_type", "auroc", "ci_low", "ci_high", *alpha_cols]
    out["chunk_groups_ci"] = md_table(
        head[cols].sort_values(["damage_model", "file_type", "fraction"]), index=False
    )
    f = auroc[(auroc.level == "file") & auroc.file_type.isin(["ALL", "HIGH_ENTROPY"])]
    piv = f.pivot_table(index=["damage_model", "file_type"], columns="fraction", values="auroc")
    piv = piv[sorted(piv.columns, reverse=True)]
    piv.columns = [f"{int(round(c * 100))}%" for c in piv.columns]
    out["file_level"] = md_table(piv)
    return out
