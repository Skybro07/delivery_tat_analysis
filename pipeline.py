"""Load, validate and clean the delivery data. Shared by the notebook, KPI report and dashboard."""
import numpy as np
import pandas as pd

EXPECTED = ["Order_ID", "Agent_Age", "Agent_Rating", "Store_Latitude", "Store_Longitude",
            "Drop_Latitude", "Drop_Longitude", "Order_Date", "Order_Time", "Pickup_Time",
            "Weather", "Traffic", "Vehicle", "Area", "Delivery_Time", "Category"]
CATEGORICAL = ["Weather", "Traffic", "Vehicle", "Area", "Category"]
INDIA_LAT, INDIA_LON = (6.0, 37.5), (68.0, 98.0)
MAX_KM = 50  # a store-to-customer distance above this is treated as a data error


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def load_raw(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    missing = [c for c in EXPECTED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}. Found: {list(df.columns)}. "
                         "Rename columns in your file or edit EXPECTED in pipeline.py.")
    return df


def _minutes(s):
    t = pd.to_datetime(s.astype(str), format="%H:%M:%S", errors="coerce")
    t = t.fillna(pd.to_datetime(s.astype(str), format="%H:%M", errors="coerce"))
    return t.dt.hour * 60 + t.dt.minute


def clean(raw):
    """Return (clean_df, data_quality_log). Every fix is counted so errors are caught, not hidden."""
    df, log = raw.copy(), {"raw_rows": len(raw)}
    log["duplicate_order_ids_removed"] = int(df["Order_ID"].duplicated().sum())
    df = df.drop_duplicates("Order_ID")

    for c in CATEGORICAL:
        df[c] = df[c].astype("string").str.strip().str.title()
        df[c] = df[c].replace({"Nan": pd.NA, "": pd.NA, "None": pd.NA})  # text "NaN " in the raw file
    df["Area"] = df["Area"].replace({"Metropolitian": "Metropolitan"})   # spelling error in the source data
    log["missing_traffic"] = int(df["Traffic"].isna().sum())
    log["missing_weather"] = int(df["Weather"].isna().sum())
    log["missing_agent_rating"] = int(pd.to_numeric(df["Agent_Rating"], errors="coerce").isna().sum())
    log["missing_order_time"] = int(df["Order_Time"].isna().sum())
    for c in CATEGORICAL:
        df[c] = df[c].fillna("Unknown").astype(object)

    for c in ["Delivery_Time", "Agent_Age", "Agent_Rating", "Store_Latitude", "Store_Longitude",
              "Drop_Latitude", "Drop_Longitude"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Order_Date"] = pd.to_datetime(df["Order_Date"], errors="coerce")

    bad_rating = df["Agent_Rating"] > 5            # ratings above 5 are impossible
    bad_age = df["Agent_Age"] < 18                 # agents under 18 cannot be right
    log["agent_rating_above_5_set_missing"], log["agent_age_under_18_set_missing"] = int(bad_rating.sum()), int(bad_age.sum())
    df.loc[bad_rating, "Agent_Rating"] = np.nan
    df.loc[bad_age, "Agent_Age"] = np.nan

    bad_date = df["Order_Date"].isna()
    bad_tat = df["Delivery_Time"].isna() | (df["Delivery_Time"] <= 0)
    log["invalid_date_removed"], log["invalid_delivery_time_removed"] = int(bad_date.sum()), int(bad_tat.sum())
    df = df[~(bad_date | bad_tat)]

    lat_ok = df["Store_Latitude"].between(*INDIA_LAT) & df["Drop_Latitude"].between(*INDIA_LAT)
    lon_ok = df["Store_Longitude"].between(*INDIA_LON) & df["Drop_Longitude"].between(*INDIA_LON)
    zero = (df[["Store_Latitude", "Store_Longitude", "Drop_Latitude", "Drop_Longitude"]].abs() < 1e-6).any(axis=1)
    bad_coord = ~(lat_ok & lon_ok) | zero
    log["invalid_coordinates_removed"] = int(bad_coord.sum())
    df = df[~bad_coord].copy()

    df["distance_km"] = haversine_km(df["Store_Latitude"], df["Store_Longitude"],
                                     df["Drop_Latitude"], df["Drop_Longitude"])
    far = df["distance_km"] > MAX_KM
    log[f"distance_over_{MAX_KM}km_removed"] = int(far.sum())
    df = df[~far].copy()

    df["hour"] = _minutes(df["Order_Time"]) // 60
    wait = (_minutes(df["Pickup_Time"]) - _minutes(df["Order_Time"])) % 1440
    df["pickup_wait_min"] = wait.where(wait <= 180)
    df["speed_kmph"] = df["distance_km"] / (df["Delivery_Time"] / 60)
    df["week"] = df["Order_Date"].dt.to_period("W").dt.start_time
    span = pd.date_range(df["Order_Date"].min(), df["Order_Date"].max())
    log["calendar_days_with_no_orders"] = int(len(span) - df["Order_Date"].nunique())
    log["clean_rows"] = len(df)
    return df.reset_index(drop=True), log
