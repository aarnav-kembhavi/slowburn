"""D66 retention audit report (read only after D68 has results, team rule)."""
import pandas as pd

pd.set_option("display.width", 240, "display.max_columns", 40)
R = "results/dev_d66_retention_audit"
c = pd.read_csv(f"{R}/audit_curves.csv")
t = pd.read_csv(f"{R}/audit_thresholds.csv")
rows = pd.read_csv(f"{R}/audit_rows.csv.gz")
print("machines", rows.groupby(["world", "rep"]).ngroups, "rows", len(rows), "products", rows["product"].nunique())
main = [p for p in c["product"].unique() if "_r" not in p.rpartition("_")[1] or not p.rpartition("_r")[2].isdigit()]
for q in (0.0, 1.0):
    x = c[c.detect_prob == q]
    print(f"== recovery vs true delay, q = {q}")
    print(x.pivot_table(index="product", columns="discovery_delay", values="recovery").round(3).to_string())
    print(f"== clean point held vs true delay, q = {q}")
    print(x.pivot_table(index="product", columns="discovery_delay", values="held").round(3).to_string())
print("== first grid delay with recovery / held below 0.5 and 0.1")
print(t.round(1).to_string(index=False))
print("== work lost (h) at delay 30, q 0 / 1")
print(c[c.discovery_delay == 30].pivot_table(index="product", columns="detect_prob", values="work_lost_h").round(1).to_string())
