
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
from zoneinfo import ZoneInfo

# Konfiguration
PRICE_AREA = "SE4"
TZ = ZoneInfo("Europe/Stockholm")
VAT_RATE = 0.25
DISPLAY_ORE = True
INCLUDE_VAT = False

COLOR_TOP16_PURPLE = "#8E44AD"
COLOR_NEXT8_RED = "#E74C3C"
COLOR_OTHER_GREEN = "#2ECC71"

def build_api_url(date):
    return f"https://www.elprisetjustnu.se/api/v1/prices/{date.year}/{date:%m}-{date:%d}_{PRICE_AREA}.json"

def fetch_day_prices(date):
    try:
        resp = requests.get(build_api_url(date), timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, list) else None
    except:
        return None

def apply_unit_and_vat(sek_per_kwh):
    price = sek_per_kwh * (1 + VAT_RATE) if INCLUDE_VAT else sek_per_kwh
    return price * 100 if DISPLAY_ORE else price

def rank_sets(rows):
    sorted_rows = sorted(rows, key=lambda r: r.get("SEK_per_kWh", 0.0), reverse=True)
    top16 = {r["time_start"] for r in sorted_rows[:16]}
    next8 = {r["time_start"] for r in sorted_rows[16:24]}
    return top16, next8

def plot_day(rows, date):
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["time_start"]).dt.tz_convert(TZ)
    df["price_display"] = df["SEK_per_kWh"].apply(apply_unit_and_vat)
    df = df.sort_values("start").reset_index(drop=True)
    top16, next8 = rank_sets(rows)
    colors = []
    for _, r in df.iterrows():
        orig = r["time_start"]
        if orig in top16:
            colors.append(COLOR_TOP16_PURPLE)
        elif orig in next8:
            colors.append(COLOR_NEXT8_RED)
        else:
            colors.append(COLOR_OTHER_GREEN)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(range(len(df)), df["price_display"], color=colors)
    ax.set_title(f"SE4 – {date:%Y-%m-%d}")
    ax.set_xlabel("Tid")
    unit = "öre/kWh" if DISPLAY_ORE else "SEK/kWh"
    ax.set_ylabel(f"Pris ({unit})")
    tick_step = 8
    x_labels = [ts.strftime("%H:%M") for ts in df["start"]]
    ax.set_xticks(range(0, len(df), tick_step))
    ax.set_xticklabels([x_labels[i] for i in range(0, len(df), tick_step)], rotation=0)
    ax.grid(axis="y", linestyle=":", alpha=0.3)
    st.pyplot(fig)

# Streamlit UI
st.title("SE4 Kvartspriser")
choice = st.radio("Välj dag:", ["Idag", "Imorgon"])
date = dt.datetime.now(TZ).date() if choice == "Idag" else (dt.datetime.now(TZ) + dt.timedelta(days=1)).date()
rows = fetch_day_prices(date)
if rows:
    plot_day(rows, date)
else:
    st.warning("Data saknas eller ej publicerad ännu.")
