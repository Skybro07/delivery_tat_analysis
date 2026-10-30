"""Automated KPI report with trend alerts.
Usage: python kpi_report.py --data data/amazon_delivery.csv --sla 150
Writes outputs/weekly_kpi_report.xlsx (or CSV files if openpyxl is missing)."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline import load_raw, clean


def _round(d, n=2):
    num = d.select_dtypes("number").columns
    d[num] = d[num].round(n)
    return d


def kpis(df, by, sla):
    g = df.groupby(by).agg(
        orders=("Order_ID", "count"), avg_tat=("Delivery_Time", "mean"),
        p90_tat=("Delivery_Time", lambda s: np.percentile(s, 90)),
        pct_late=("Delivery_Time", lambda s: (s > sla).mean() * 100),
        avg_distance_km=("distance_km", "mean")).reset_index()
    return _round(g)


def flag_alerts(daily, window=7, z=2.5):
    """Flag days whose avg TAT is more than z std-devs above the previous `window` days."""
    d = daily.sort_values("Order_Date").copy()
    prior = d["avg_tat"].shift(1).rolling(window)
    d["prior_mean"], d["z_score"] = prior.mean(), (d["avg_tat"] - prior.mean()) / prior.std()
    d["alert"] = d["z_score"] > z
    return _round(d)


def build_report(df, log, sla=45):
    daily = flag_alerts(kpis(df, "Order_Date", sla))
    weekly = kpis(df, "week", sla)
    weekly["days_in_data"] = df.groupby("week")["Order_Date"].nunique().values
    weekly["avg_tat_wow_pct"] = (weekly["avg_tat"].pct_change() * 100).round(1)
    seg = kpis(df, ["Traffic", "Area"], sla)
    seg = seg[seg["orders"] >= 100].sort_values("pct_late", ascending=False)
    alerts = daily[daily["alert"]][["Order_Date", "orders", "avg_tat", "prior_mean", "z_score", "pct_late"]]
    dq = pd.Series(log, name="count").rename_axis("check").reset_index()
    return {"Weekly": weekly, "Daily": daily, "Alerts": alerts, "Worst segments": seg, "Data quality": dq}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/amazon_delivery.csv")
    ap.add_argument("--sla", type=int, default=150, help="late if delivery takes longer than this (minutes)")
    ap.add_argument("--out", default="outputs")
    a = ap.parse_args()
    df, log = clean(load_raw(a.data))
    sheets = build_report(df, log, a.sla)
    out = Path(a.out); out.mkdir(exist_ok=True)

    print(f"Orders: {len(df):,} | avg TAT {df['Delivery_Time'].mean():.1f} min | "
          f"{(df['Delivery_Time'] > a.sla).mean():.1%} over {a.sla} min")
    alerts = sheets["Alerts"]
    print(f"\n{len(alerts)} alert day(s):" if len(alerts) else "\nNo alert days.")
    if len(alerts):
        print(alerts.to_string(index=False))
    print("\nWorst segments by % late:\n", sheets["Worst segments"].head(5).to_string(index=False))
    try:
        with pd.ExcelWriter(out / "weekly_kpi_report.xlsx", engine="openpyxl") as w:
            for name, frame in sheets.items():
                frame.to_excel(w, sheet_name=name, index=False)
        print(f"\nSaved {out / 'weekly_kpi_report.xlsx'}")
    except ImportError:
        for name, frame in sheets.items():
            frame.to_csv(out / f"{name.replace(' ', '_').lower()}.csv", index=False)
        print("\nopenpyxl missing, saved CSV files instead")


if __name__ == "__main__":
    main()
