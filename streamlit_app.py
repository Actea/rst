
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# (valfritt) komponenter för click-events & auto-refresh
try:
    from streamlit_plotly_events import plotly_events  # click/tap fångas
except Exception:
    plotly_events = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

# ------------- Konfiguration -------------
TZ = ZoneInfo("Europe/Stockholm")

DEFAULT_AREA = "SE4"
AREAS = ["SE1", "SE2", "SE3", "SE4"]

VAT_RATE = 0.25  # 25 %
COLOR_TOP16_PURPLE = "#8E44AD"   # lila
COLOR_NEXT8_RED    = "#E74C3C"   # röd
COLOR_OTHER_GREEN  = "#2ECC71"   # grön

# ------------- Hjälpfunktioner -------------

def build_api_url(date: dt.date, area: str) -> str:
    # Elpriset just nu JSON API
    return f"https://www.elprisetjustnu.se/api/v1/prices/{date.year}/{date:%m}-{date:%d}_{area}.json"
# Källa: öppet API, pris per dag/område; kvartspriser från 2025-10-01. [4](https://www.elprisetjustnu.se/elpris-api)

@st.cache_data(ttl="15m", show_spinner="Hämtar elpriser…")  # cachea i 15 min
def fetch_day_rows(date: dt.date, area: str) -> list[dict] | None:
    """Hämta listan av prisrader för ett datum och område. Cacheas i 15 min."""
    try:
        url = build_api_url(date, area)
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, list) and len(data) > 0 else None
    except Exception:
        return None
# Streamlit caching med ttl dokumenteras i st.cache_data. [1](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)[2](https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/cache-data.md)

def apply_unit_and_vat(sek_per_kwh: float, display_ore: bool, include_vat: bool) -> float:
    price = sek_per_kwh * (1 + VAT_RATE) if include_vat else sek_per_kwh
    return price * 100 if display_ore else price

def rank_sets(rows: list[dict]) -> tuple[set[str], set[str]]:
    """Returnera (top16, next8) via 'time_start' baserat på SEK_per_kWh (fallande)."""
    sorted_rows = sorted(rows, key=lambda r: r.get("SEK_per_kWh", 0.0), reverse=True)
    top16 = {r["time_start"] for r in sorted_rows[:16]}
    next8 = {r["time_start"] for r in sorted_rows[16:24]}
    return top16, next8

def to_dataframe(rows: list[dict], display_ore: bool, include_vat: bool) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["time_start"], utc=True).dt.tz_convert(TZ)
    df["price_display"] = df["SEK_per_kWh"].astype(float).apply(
        lambda x: apply_unit_and_vat(x, display_ore, include_vat)
    )
    df = df.sort_values("start").reset_index(drop=True)
    return df

def build_plotly_figure(df: pd.DataFrame, top16: set[str], next8: set[str],
                        selected_idx: int | None,
                        title: str, unit_label: str) -> go.Figure:
    # Färger + customdata för hover/click
    colors = []
    custom = []  # (tid, pris text)
    for i, r in df.iterrows():
        orig = r["time_start"]
        if orig in top16:
            c = COLOR_TOP16_PURPLE
        elif orig in next8:
            c = COLOR_NEXT8_RED
        else:
            c = COLOR_OTHER_GREEN
        # Markera vald stapel med svart kant
        if selected_idx is not None and i == selected_idx:
            c = c  # färg bibehålls
        colors.append(c)
        custom.append([r["start"].strftime("%H:%M"), r["price_display"]])

    fig = px.bar(
        df,
        x=df.index,                    # index 0..95
        y="price_display",
        color=colors,                  # färg via list
        labels={"price_display": f"Pris ({unit_label})"},
        height=420,
    )
    # Anpassa hover (tid + pris, utan default trace för kompakt)
    fig.update_traces(
        hovertemplate="<b>%{customdata[0]}</b><br>Pris: %{customdata[1]} " + unit_label + "<extra></extra>",
        customdata=custom,
        marker=dict(color=colors, line=dict(color="black" if selected_idx is not None else "rgba(0,0,0,0)", width=1))
    )
    # Tidsaxel som HH:MM etiketter var 8:e kvart (~2h)
    tick_step = 8
    xlabels = [ts.strftime("%H:%M") for ts in df["start"]]
    fig.update_xaxes(
        tickvals=list(range(0, len(df), tick_step)),
        ticktext=[xlabels[i] for i in range(0, len(df), tick_step)],
        title="Tid på dygnet (kvartstart)"
    )
    fig.update_yaxes(title=f"Pris ({unit_label})", gridcolor="rgba(0,0,0,0.2)")
    fig.update_layout(title=title, showlegend=False, hovermode="closest")
    return fig
# Plotly hovertemplate används för rika etiketter (ex. customdata + <extra></extra>). [3](https://plotly.com/python/hover-text-and-formatting/)

# ------------- UI -------------
st.set_page_config(page_title="SE4 Kvartspriser – interaktiv", layout="wide")
st.title("Interaktiv elpris-app (kvartspriser)")

with st.sidebar:
    area = st.selectbox("Prisområde", AREAS, index=AREAS.index(DEFAULT_AREA))
    day_choice = st.radio("Visa", ["Idag", "Imorgon"], index=0)
    display_ore = st.toggle("Visa i öre/kWh (annars kr/kWh)", value=False)
    include_vat = st.toggle("Inkludera moms (25 %)", value=False)
    auto_refresh = st.toggle("Auto-refresh var 5 min (klientsida)", value=False)

    if st_autorefresh and auto_refresh:
        # Frontend-timer som pingar servern var 5 min för omkörning (ingen evighetsloop)
        st_autorefresh(interval=5 * 60 * 1000, key="autorefresh")  # 5 min
        st.caption("Auto-refresh aktiv (var 5 min).")
    elif not st_autorefresh and auto_refresh:
        st.warning("Installera 'streamlit-autorefresh' för auto-refresh.", icon="⚠️")

date = dt.datetime.now(TZ).date() if day_choice == "Idag" else (dt.datetime.now(TZ) + dt.timedelta(days=1)).date()
rows = fetch_day_rows(date, area)

if not rows:
    st.warning(
        "Data saknas eller ej publicerad ännu. (Morgondagens priser kommer normalt tidigast ~13:00.)",
        icon="ℹ️"
    )
    st.stop()

# Data + färgranking
top16, next8 = rank_sets(rows)
df = to_dataframe(rows, display_ore=display_ore, include_vat=include_vat)
unit_label = "öre/kWh" if display_ore else "SEK/kWh"
title = f"{area} – Dygnets kvartar ({date:%Y-%m-%d})"

# Valt stapelindex (vid click): lagra i session_state
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = None

# Bygg figur
fig = build_plotly_figure(
    df=df,
    top16=top16,
    next8=next8,
    selected_idx=st.session_state.selected_idx,
    title=title,
    unit_label=unit_label
)

# Visa diagram + fånga click/tap (om komponenten finns)
col_plot, col_info = st.columns([3, 2], gap="large")
with col_plot:
    if plotly_events:
        sel = plotly_events(fig, click_event=True, hover_event=False, select_event=False, key="plot")
        st.plotly_chart(fig, use_container_width=True)
        if sel:
            # sel är en lista med dictar; ta första klickade punkten
            pt = sel[0]
            idx = int(pt.get("pointNumber", 0))
            st.session_state.selected_idx = idx

            # Visa panel med detaljer
            t_str = df.iloc[idx]["start"].strftime("%H:%M")
            price_val = df.iloc[idx]["price_display"]
            price_str = f"{int(round(price_val))} {unit_label}" if display_ore else f"{price_val:.2f} {unit_label}"
            st.success(f"Vald kvart: {t_str} — {price_str}")
    else:
        # Fallback: enbart hover + ingen click fångst
        st.plotly_chart(fig, use_container_width=True)
        st.info("Installera 'streamlit-plotly-events' för att fånga click/tap på staplar.", icon="🖱️")

with col_info:
    # Snabb sammanfattning
    st.subheader("Snabbdata")
    st.metric("Antal kvartar", len(df))
    st.metric("Dyraste kvart (pris)", f"{max(df['price_display']):.2f} {unit_label}")
    st.metric("Billigaste kvart (pris)", f"{min(df['price_display']):.2f} {unit_label}")

    if st.session_state.selected_idx is not None:
        i = st.session_state.selected_idx
        t_str = df.iloc[i]["start"].strftime("%H:%M")
        p = df.iloc[i]["price_display"]
        st.write(f"**Vald kvart:** {t_str} — {'%d' % round(p) if display_ore else f'{p:.2f}'} {unit_label}")
        # Extra info/rank
        orig = df.iloc[i]["time_start"]
        if orig in top16:
            st.markdown("**Klass:** LILA (topp 16 dyraste)")
        elif orig in next8:
            st.markdown("**Klass:** RÖD (plats 17–24)")
        else:
            st.markdown("**Klass:** GRÖN (övriga 72)")

