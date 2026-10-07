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


def _fraction_pivot(sub: pd.DataFrame, index, value: str = "auroc") -> pd.DataFrame:
    piv = sub.pivot_table(index=index, columns="fraction", values=value)
    piv = piv[sorted(piv.columns, reverse=True)]
    piv.columns = [f"{int(round(c * 100))}%" for c in piv.columns]
    return piv


def detector_tables(auroc: pd.DataFrame) -> dict[str, str]:
    """Markdown tables for the detector write-up: per detector x damage model, per type and
    weighted-average rows (chunk level), plus file-level weighted averages."""
    out = {}
    chunk = auroc[auroc.level == "chunk"]
    for det in sorted(chunk.detector.unique()):
        for model in sorted(chunk.damage_model.unique()):
            sub = chunk[(chunk.detector == det) & (chunk.damage_model == model)]
            out[f"chunk_{det}_{model}"] = md_table(_fraction_pivot(sub, "file_type"))
    f = auroc[(auroc.level == "file") & auroc.file_type.str.startswith("WAVG_")]
    out["file_level_wavg"] = md_table(_fraction_pivot(f, ["detector", "damage_model", "file_type"]))
    return out
