"""SMOKE TEST ONLY. Creates FAKE delivery data (with deliberate errors) to check the code runs.
NEVER report results from it. Use the real Kaggle dataset."""
import numpy as np, pandas as pd
rng = np.random.default_rng(7); n = 20_000
centers = np.array([[12.97, 77.59], [19.07, 72.87], [28.61, 77.21], [17.38, 78.48]])
c = centers[rng.integers(0, 4, n)]
slat, slon = c[:, 0] + rng.normal(0, .04, n), c[:, 1] + rng.normal(0, .04, n)
dlat, dlon = slat + rng.normal(0, .05, n), slon + rng.normal(0, .05, n)
dist = 111 * np.sqrt((dlat - slat) ** 2 + (np.cos(np.radians(slat)) * (dlon - slon)) ** 2)
day = rng.integers(0, 55, n)
traffic = rng.choice(["Low ", "Medium ", "High ", "Jam "], n, p=[.25, .35, .3, .1])
weather = rng.choice(["Sunny", "Cloudy", "Fog", "Stormy", "Sandstorms", None], n, p=[.3, .2, .15, .15, .15, .05])
tadd = {"Low ": 0, "Medium ": 6, "High ": 14, "Jam ": 24}
wadd = {"Sunny": 0, "Cloudy": 3, "Fog": 6, "Stormy": 8, "Sandstorms": 10, None: 2}
tat = (12 + 4.5 * dist + np.array([tadd[t] for t in traffic]) + np.array([wadd[w] for w in weather])
       + rng.normal(0, 6, n) + np.where(day >= 48, 10, 0))
tat = np.clip(tat, 10, 270).round()
hour = rng.choice(np.arange(7, 23), n); minute = rng.integers(0, 60, n)
order_min = hour * 60 + minute; pick_min = (order_min + rng.integers(5, 16, n)) % 1440
fmt = lambda m: [f"{int(x)//60:02d}:{int(x)%60:02d}:00" for x in m]
slat = np.where(rng.random(n) < .01, 0.0, slat)           # deliberate data error
ot = np.array(fmt(order_min), dtype=object); ot[rng.random(n) < .01] = None
df = pd.DataFrame({
    "Order_ID": [f"ID{i:06d}" for i in range(n)], "Agent_Age": rng.integers(20, 40, n),
    "Agent_Rating": np.where(rng.random(n) < .01, np.nan, np.clip(rng.normal(4.6, .3, n), 2.5, 5).round(1)),
    "Store_Latitude": slat, "Store_Longitude": slon, "Drop_Latitude": dlat, "Drop_Longitude": dlon,
    "Order_Date": (pd.Timestamp("2022-02-11") + pd.to_timedelta(day, unit="D")).strftime("%Y-%m-%d"),
    "Order_Time": ot, "Pickup_Time": fmt(pick_min), "Weather": weather, "Traffic": traffic,
    "Vehicle": rng.choice(["motorcycle ", "scooter ", "van"], n, p=[.6, .3, .1]),
    "Area": rng.choice(["Urban ", "Metropolitan ", "Semi-Urban ", "Other"], n, p=[.3, .5, .1, .1]),
    "Delivery_Time": tat,
    "Category": rng.choice(["Electronics", "Grocery", "Clothing", "Snacks", "Books", "Toys"], n)})
df.to_csv("data/amazon_delivery_DUMMY.csv", index=False)
print("Wrote data/amazon_delivery_DUMMY.csv (FAKE DATA, smoke test only)")
