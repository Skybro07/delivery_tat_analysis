"""Delivery TAT dashboard.  Run:  streamlit run app.py"""
from pathlib import Path
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from pipeline import load_raw, clean
from kpi_report import kpis, flag_alerts

st.set_page_config(page_title="Delivery TAT Dashboard", page_icon="🚚", layout="wide")
ACCENT = "#b4571e"
DATA = Path(__file__).parent / "data" / "amazon_delivery.csv"

if not DATA.exists():
    st.error(f"Put the dataset at {DATA} (see README), then refresh.")
    st.stop()


@st.cache_data
def get_data():
    return clean(load_raw(DATA))


df, log = get_data()

st.sidebar.header("Filters")
sla = st.sidebar.slider("Late if delivery takes longer than (min)", 30, 240, 150, 10)


def pick(label, col):
    opts = sorted(df[col].unique())
    return st.sidebar.multiselect(label, opts, default=opts)


areas, traffic = pick("Area", "Area"), pick("Traffic", "Traffic")
weather, cats = pick("Weather", "Weather"), pick("Category", "Category")
f = df[df["Area"].isin(areas) & df["Traffic"].isin(traffic) & df["Weather"].isin(weather) & df["Category"].isin(cats)]
if f.empty:
    st.warning("No orders match these filters.")
    st.stop()

st.title("🚚 Delivery TAT Dashboard")
st.caption(f"{len(f):,} orders · {f['Order_Date'].min():%d %b %Y} to {f['Order_Date'].max():%d %b %Y}")

c = st.columns(5)
c[0].metric("Orders", f"{len(f):,}")
c[1].metric("Avg TAT (min)", f"{f['Delivery_Time'].mean():.1f}")
c[2].metric("P90 TAT (min)", f"{np.percentile(f['Delivery_Time'], 90):.0f}")
c[3].metric(f"% over {sla} min", f"{(f['Delivery_Time'] > sla).mean():.1%}")
c[4].metric("Avg distance (km)", f"{f['distance_km'].mean():.1f}")

st.subheader("Daily average TAT with alerts")
daily = flag_alerts(kpis(f, "Order_Date", sla))
line = alt.Chart(daily).mark_line(color=ACCENT).encode(
    x=alt.X("Order_Date:T", title=None), y=alt.Y("avg_tat:Q", title="Avg TAT (min)"))
pts = alt.Chart(daily[daily["alert"]]).mark_point(color="red", filled=True, size=90).encode(
    x="Order_Date:T", y="avg_tat:Q",
    tooltip=["Order_Date:T", "avg_tat:Q", "z_score:Q", "orders:Q"])
st.altair_chart(line + pts, use_container_width=True)
st.caption("Red dots: days where avg TAT is more than 2.5 standard deviations above the previous 7 days.")

l, r = st.columns(2)
with l:
    st.subheader("Avg TAT by traffic")
    t = kpis(f, "Traffic", sla)
    st.altair_chart(alt.Chart(t).mark_bar(color=ACCENT).encode(
        x=alt.X("Traffic:N", sort=["Low", "Medium", "High", "Jam"], title=None),
        y=alt.Y("avg_tat:Q", title="Avg TAT (min)"), tooltip=["Traffic", "orders", "avg_tat", "pct_late"]),
        use_container_width=True)
with r:
    st.subheader("Orders and TAT by hour")
    h = kpis(f.dropna(subset=["hour"]).assign(hour=lambda d: d["hour"].astype(int)), "hour", sla)
    if h.empty:
        st.info("No valid order times are available for the selected filters.")
    else:
        hour_x = alt.X("hour:O", title="Hour", sort=list(range(24)))
        hour_tooltip = ["hour:O", "orders:Q", "avg_tat:Q", "pct_late:Q"]
        volume = alt.Chart(h).mark_bar(color="#e7c7ae").encode(
            x=hour_x, y=alt.Y("orders:Q", title="Orders"),
            tooltip=hour_tooltip)
        tat = alt.Chart(h).mark_line(color=ACCENT, point=True).encode(
            x=hour_x,
            y=alt.Y("avg_tat:Q", title="Avg TAT (min)", axis=alt.Axis(orient="right")),
            tooltip=hour_tooltip)
        st.altair_chart(
            alt.layer(volume, tat).resolve_scale(y="independent"),
            use_container_width=True)

st.subheader("Explore delivery patterns")
driver_col, heat_col = st.columns(2)
with driver_col:
    st.markdown("#### Late-order rate by factor")
    driver = st.selectbox("Compare by", ["Category", "Weather", "Vehicle"])
    driver_kpis = kpis(f, driver, sla).sort_values("pct_late", ascending=False)
    driver_chart = alt.Chart(driver_kpis).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("pct_late:Q", title=f"% over {sla} min", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y(f"{driver}:N", sort=alt.SortField(field="pct_late", order="descending"), title=None),
        color=alt.Color("pct_late:Q", scale=alt.Scale(scheme="orangered"), legend=None),
        tooltip=[
            alt.Tooltip(f"{driver}:N", title=driver),
            alt.Tooltip("orders:Q", format=","),
            alt.Tooltip("avg_tat:Q", title="Avg TAT (min)", format=".1f"),
            alt.Tooltip("pct_late:Q", title="% late", format=".1f"),
        ],
    ).properties(height=alt.Step(24))
    st.altair_chart(driver_chart, use_container_width=True)

with heat_col:
    st.markdown("#### Late-order rate: traffic × area")
    traffic_area = f.groupby(["Traffic", "Area"]).agg(
        orders=("Order_ID", "count"),
        pct_late=("Delivery_Time", lambda values: (values > sla).mean() * 100),
    ).reset_index()
    heat = alt.Chart(traffic_area).mark_rect(cornerRadius=3).encode(
        x=alt.X("Area:N", title=None, sort=["Metropolitan", "Urban", "Other", "Semi-Urban"]),
        y=alt.Y("Traffic:N", title=None, sort=["Low", "Medium", "High", "Jam", "Unknown"]),
        color=alt.Color(
            "pct_late:Q", title="% late", scale=alt.Scale(domain=[0, 100], scheme="orangered")),
        tooltip=[
            alt.Tooltip("Area:N"),
            alt.Tooltip("Traffic:N"),
            alt.Tooltip("orders:Q", format=","),
            alt.Tooltip("pct_late:Q", title="% late", format=".1f"),
        ],
    )
    labels = alt.Chart(traffic_area).mark_text(fontSize=11, color="#33251d").encode(
        x=alt.X("Area:N", sort=["Metropolitan", "Urban", "Other", "Semi-Urban"]),
        y=alt.Y("Traffic:N", sort=["Low", "Medium", "High", "Jam", "Unknown"]),
        text=alt.Text("pct_late:Q", format=".0f"),
    )
    st.altair_chart((heat + labels).properties(height=220), use_container_width=True)
    st.caption("Hover over a cell to see its order count; low-volume segments can be less reliable.")

distribution_col, weekday_col = st.columns(2)
with distribution_col:
    st.markdown("#### Delivery-time distribution")
    bin_width = 10
    max_edge = max(bin_width, (int(f["Delivery_Time"].max() // bin_width) + 1) * bin_width)
    edges = np.arange(0, max_edge + bin_width + 1, bin_width)
    counts, edges = np.histogram(f["Delivery_Time"], bins=edges)
    distribution = pd.DataFrame({
        "tat_min": edges[:-1],
        "orders": counts,
        "sla_band": np.where(edges[:-1] >= sla, "Over SLA", "Within SLA"),
    })
    bars = alt.Chart(distribution).mark_bar(size=14).encode(
        x=alt.X("tat_min:Q", title="Delivery time (min)", scale=alt.Scale(domain=[0, edges[-1]])),
        y=alt.Y("orders:Q", title="Orders"),
        color=alt.Color(
            "sla_band:N",
            scale=alt.Scale(domain=["Within SLA", "Over SLA"], range=["#e7c7ae", ACCENT]),
            legend=alt.Legend(title=None),
        ),
        tooltip=[
            alt.Tooltip("tat_min:Q", title="Bin starts at (min)", format=".0f"),
            alt.Tooltip("orders:Q", format=","),
            alt.Tooltip("sla_band:N", title="SLA band"),
        ],
    )
    sla_rule = alt.Chart(pd.DataFrame({"sla": [sla]})).mark_rule(
        color="#9b2c2c", strokeDash=[5, 4], strokeWidth=2
    ).encode(x="sla:Q", tooltip=alt.Tooltip("sla:Q", title="SLA threshold (min)"))
    st.altair_chart((bars + sla_rule).properties(height=260), use_container_width=True)

with weekday_col:
    st.markdown("#### Average TAT by weekday and hour")
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    timed = f.dropna(subset=["hour"]).assign(
        hour=lambda data: data["hour"].astype(int),
        weekday=lambda data: data["Order_Date"].dt.day_name(),
    )
    weekday_hour = timed.groupby(["weekday", "hour"]).agg(
        orders=("Order_ID", "count"),
        avg_tat=("Delivery_Time", "mean"),
    ).reset_index()
    if weekday_hour.empty:
        st.info("No valid order times are available for the selected filters.")
    else:
        weekday_heatmap = alt.Chart(weekday_hour).mark_rect(cornerRadius=2).encode(
            x=alt.X("hour:O", title="Hour", sort=list(range(24))),
            y=alt.Y("weekday:N", title=None, sort=weekdays),
            color=alt.Color(
                "avg_tat:Q", title="Avg TAT (min)", scale=alt.Scale(scheme="oranges")),
            tooltip=[
                alt.Tooltip("weekday:N"),
                alt.Tooltip("hour:O"),
                alt.Tooltip("orders:Q", format=","),
                alt.Tooltip("avg_tat:Q", title="Avg TAT (min)", format=".1f"),
            ],
        ).properties(height=220)
        st.altair_chart(weekday_heatmap, use_container_width=True)

st.subheader("Worst segments (traffic × area)")
seg = kpis(f, ["Traffic", "Area"], sla)
st.dataframe(seg[seg["orders"] >= 30].sort_values("pct_late", ascending=False).head(10),
             use_container_width=True, hide_index=True)

with st.expander("Data quality log (what the cleaning step fixed)"):
    st.dataframe(pd.Series(log, name="count").rename_axis("check").reset_index(), hide_index=True)
