"""Result tables -> LaTeX (booktabs). Numbers are formatted from the data, never typed."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
            "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}"}  # fmt: skip


def escape(text: str) -> str:
    return "".join(_ESCAPES.get(ch, ch) for ch in str(text))


def _fmt(v, floatfmt: str) -> str:
    if isinstance(v, float):
        return "--" if pd.isna(v) else floatfmt.format(v)
    if v is None:
        return "--"
    return escape(v)


def to_latex_table(df: pd.DataFrame, caption: str, label: str, floatfmt: str = "{:.3f}",
                   colfmt: str | None = None, index: bool = False) -> str:  # fmt: skip
    """A self-contained ``table`` environment with booktabs rules."""
    if index:
        df = df.reset_index()
    cols = [escape(" ".join(map(str, c)) if isinstance(c, tuple) else c) for c in df.columns]
    colfmt = colfmt or "l" * len(cols)
    lines = [r"\begin{table}[t]", r"\centering", rf"\caption{{{escape(caption)}}}",
             rf"\label{{{label}}}", r"\small", rf"\begin{{tabular}}{{{colfmt}}}", r"\toprule",
             " & ".join(cols) + r" \\", r"\midrule"]  # fmt: skip
    for row in df.itertuples(index=False):
        lines.append(" & ".join(_fmt(v, floatfmt) for v in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def write_latex_table(df: pd.DataFrame, path: str | Path, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("% generated from result CSVs; do not edit by hand\n"
                    + to_latex_table(df, **kwargs), encoding="utf-8")  # fmt: skip
    return path
