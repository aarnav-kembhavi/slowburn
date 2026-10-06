import pandas as pd

from slowburn.bench.report import md_table


def test_md_table_formats_and_keeps_values():
    df = pd.DataFrame({"a": ["x", "y"], "b": [0.123456, float("nan")]})
    t = md_table(df, index=False)
    lines = t.splitlines()
    assert lines[0] == "| a | b |"
    assert lines[2] == "| x | 0.1235 |"
    assert lines[3] == "| y |  |"
