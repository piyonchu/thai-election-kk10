from __future__ import annotations

import json
import os
import re
import sys

import matplotlib as mpl
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
#
# All data flows from the OCR-extracted CSVs in ``data/result/``:
#     bch_results.csv     — Party-List results (บัญชีรายชื่อ)
#     normal_results.csv  — Constituency results (เขต)
#
# These are the same CSVs the dashboard data-loader (utils.data_loader)
# reads, so the spatial maps and the statistics dashboard now share a single
# source of truth.
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
RESULT_DIR   = os.path.join(DATA_DIR, "result")

BCH_CSV    = os.path.join(RESULT_DIR, "bch_results.csv")
NORMAL_CSV = os.path.join(RESULT_DIR, "normal_results.csv")
COORDS_CSV = os.path.join(DATA_DIR,   "location_coordinates_template.csv")
MAPS_DIR   = os.path.join(RESULT_DIR, "maps")


def _load_json_map(path: str) -> dict:
    """Load a name-lookup JSON file; return ``{}`` if it doesn't exist."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_PARTY_MAP:     dict[str, str]  = _load_json_map(os.path.join(MAPS_DIR, "party_map.json"))
_CANDIDATE_MAP: dict[str, dict] = _load_json_map(os.path.join(MAPS_DIR, "candidate_map.json"))

# Dashboard pipeline (long-format frames built from the same raw CSVs)
sys.path.insert(0, PROJECT_ROOT)
from utils.data_loader import load_data as _load_dashboard  # noqa: E402

DEFAULT_CENTER = {"lat": 15.92, "lon": 102.65}
DEFAULT_ZOOM   = 8.6


# ---------------------------------------------------------------------------
# Name-lookup helpers
# ---------------------------------------------------------------------------
def party_name(number: int) -> str:
    return _PARTY_MAP.get(str(number), f"พรรคหมายเลข {number}")


def candidate_name(number: int) -> str:
    info = _CANDIDATE_MAP.get(str(number), {})
    name  = info.get("ชื่อ_สกุล", f"ผู้สมัครหมายเลข {number}")
    party = info.get("พรรค", "")
    if party:
        return f"{name} ({party})"
    return name


# ---------------------------------------------------------------------------
# Spatial data loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_spatial() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bch  = pd.read_csv(BCH_CSV)
    norm = pd.read_csv(NORMAL_CSV)

    if os.path.exists(COORDS_CSV):
        coords = pd.read_csv(COORDS_CSV).rename(
            columns={"อำเภอ": "อำเภอ_เขต", "ตำบล": "ตำบล_แขวง_เทศบาล"}
        )
    else:
        # Empty stub so the rest of the page still loads
        coords = pd.DataFrame(
            columns=["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "Latitude", "Longitude"]
        )
    return bch, norm, coords


def party_score_columns(df: pd.DataFrame) -> list[str]:
    return sorted(
        [c for c in df.columns if c.startswith("คะแนน_พรรค_")],
        key=lambda c: int(re.search(r"\d+", c).group()),
    )


def candidate_score_columns(df: pd.DataFrame) -> list[str]:
    return sorted(
        [c for c in df.columns if c.startswith("คะแนน_ผู้สมัคร_")],
        key=lambda c: int(re.search(r"\d+", c).group()),
    )


def number_from_col(col: str) -> int:
    return int(re.search(r"\d+", col).group())


def aggregate_by_tambon(df: pd.DataFrame, score_cols: list[str]) -> pd.DataFrame:
    base = [
        "ผู้มีสิทธิตามบัญชี", "ผู้มาแสดงตน",
        "บัตรที่ใช้", "บัตรดี", "บัตรเสีย", "รวมคะแนนทั้งสิ้น",
    ]
    sum_cols = [c for c in base if c in df.columns] + score_cols
    grouped = df.groupby(["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"], as_index=False)[sum_cols].sum()
    grouped["จำนวนหน่วย"] = df.groupby(["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"]).size().values
    grouped["turnout_pct"] = pd.to_numeric(
        100 * grouped["ผู้มาแสดงตน"] / grouped["ผู้มีสิทธิตามบัญชี"].replace(0, pd.NA),
        errors="coerce",
    )
    grouped["spoiled_pct"] = pd.to_numeric(
        100 * grouped["บัตรเสีย"] / grouped["บัตรที่ใช้"].replace(0, pd.NA),
        errors="coerce",
    )
    return grouped


def attach_coords(tambon_df: pd.DataFrame, coords: pd.DataFrame) -> pd.DataFrame:
    if coords.empty:
        out = tambon_df.copy()
        out["Latitude"]  = pd.NA
        out["Longitude"] = pd.NA
        return out
    return tambon_df.merge(coords, on=["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"], how="left")


# ---------------------------------------------------------------------------
# Pydeck helpers
# ---------------------------------------------------------------------------
_PALETTE = [
    [31, 119, 180], [255, 127, 14], [44, 160, 44],  [214, 39, 40],
    [148, 103, 189],[140, 86, 75],  [227, 119, 194], [127, 127, 127],
    [188, 189, 34], [23, 190, 207], [174, 199, 232], [255, 187, 120],
    [255, 152, 150],[197, 176, 213],[196, 156, 148], [247, 182, 210],
]

_VIEW = pdk.ViewState(
    latitude=DEFAULT_CENTER["lat"], longitude=DEFAULT_CENTER["lon"],
    zoom=DEFAULT_ZOOM, pitch=0,
)


def _val_to_rgba(series: pd.Series, cmap_name: str) -> list:
    filled = series.fillna(series.median())
    vmin, vmax = float(filled.min()), float(filled.max())
    norm = (filled - vmin) / (vmax - vmin) if vmax > vmin else pd.Series([0.5] * len(filled))
    # mpl.colormaps[name] is the modern (matplotlib >= 3.7) replacement for cm.get_cmap
    cmap_func = mpl.colormaps[cmap_name]
    return [[int(r*255), int(g*255), int(b*255), 210]
            for r, g, b, _ in cmap_func(norm.values)]


def _cat_to_rgba(series: pd.Series) -> tuple[list, dict]:
    cats = sorted(series.unique().tolist(), key=str)
    color_map = {cat: _PALETTE[i % len(_PALETTE)] + [220] for i, cat in enumerate(cats)}
    return [color_map[v] for v in series], color_map


def _radius_scale(series: pd.Series, r_min: int = 300, r_max: int = 3000) -> list:
    vmin, vmax = float(series.min()), float(series.max())
    if vmax == vmin:
        return [int((r_min + r_max) / 2)] * len(series)
    norm = (series - vmin) / (vmax - vmin)
    return [int(r_min + v * (r_max - r_min)) for v in norm]


def _scatter_layer(plot_df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer", data=plot_df,
        get_position=["Longitude", "Latitude"],
        get_fill_color="_color", get_radius="_radius",
        pickable=True, auto_highlight=True, opacity=0.85,
        stroked=True, line_width_min_pixels=1,
        get_line_color=[255, 255, 255, 80],
    )


def pdk_continuous_map(
    df: pd.DataFrame, value_col: str, tooltip_cols: list[str],
    cmap_name: str = "viridis", size_col: str = "ผู้มาแสดงตน",
) -> pdk.Deck:
    plot_df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    plot_df["_color"]  = _val_to_rgba(plot_df[value_col], cmap_name)
    plot_df["_radius"] = _radius_scale(plot_df[size_col])
    tooltip_html = (
        "<b>{ตำบล_แขวง_เทศบาล}</b> ({อำเภอ_เขต})<br>"
        + "<br>".join(f"{c}: {{{c}}}" for c in tooltip_cols)
    )
    return pdk.Deck(
        layers=[_scatter_layer(plot_df)], initial_view_state=_VIEW,
        tooltip={"html": tooltip_html}, map_style="road",
    )


def pdk_categorical_map(
    df: pd.DataFrame, color_col: str, tooltip_cols: list[str],
    size_col: str = "ผู้มาแสดงตน",
) -> tuple[pdk.Deck, dict]:
    plot_df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    plot_df[color_col] = plot_df[color_col].astype(str)
    colors, color_map = _cat_to_rgba(plot_df[color_col])
    plot_df["_color"]  = colors
    plot_df["_radius"] = _radius_scale(plot_df[size_col])
    tooltip_html = (
        "<b>{ตำบล_แขวง_เทศบาล}</b> ({อำเภอ_เขต})<br>"
        + "<br>".join(f"{c}: {{{c}}}" for c in tooltip_cols)
    )
    deck = pdk.Deck(
        layers=[_scatter_layer(plot_df)], initial_view_state=_VIEW,
        tooltip={"html": tooltip_html}, map_style="road",
    )
    return deck, color_map


# ===========================================================================
# PAGE
# ===========================================================================
st.set_page_config(page_title="Election Overview", page_icon="🗺️", layout="wide")
st.title("🗺️ Election Overview — เขตเลือกตั้งที่ 10 (ขอนแก่น)")
st.caption(
    "Source data: `data/result/bch_results.csv` (Party-List) "
    "and `data/result/normal_results.csv` (Constituency)."
)

# ---------------------------------------------------------------------------
# Load spatial data
# ---------------------------------------------------------------------------
try:
    bch_raw, norm_raw, coords = load_spatial()
except FileNotFoundError as e:
    st.error(
        f"Required CSV not found: `{e.filename}`. "
        f"Please make sure both `bch_results.csv` and `normal_results.csv` "
        f"exist in `{RESULT_DIR}`."
    )
    st.stop()

bch_score_cols  = party_score_columns(bch_raw)
norm_score_cols = candidate_score_columns(norm_raw)

bch_tambon  = attach_coords(aggregate_by_tambon(bch_raw,  bch_score_cols),  coords)
norm_tambon = attach_coords(aggregate_by_tambon(norm_raw, norm_score_cols), coords)

missing_bch = bch_tambon[bch_tambon["Latitude"].isna()][
    ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"]
].drop_duplicates()
if not missing_bch.empty:
    st.warning(
        "พบตำบลที่ไม่มีพิกัดใน `location_coordinates_template.csv` "
        "(จะไม่แสดงบนแผนที่):\n\n"
        + "\n".join(
            f"- {getattr(r, 'อำเภอ_เขต')} / {getattr(r, 'ตำบล_แขวง_เทศบาล')}"
            for r in missing_bch.itertuples()
        )
    )

# Top-line KPIs (spatial data)
total_eligible = int(bch_raw["ผู้มีสิทธิตามบัญชี"].sum())
total_voters   = int(bch_raw["ผู้มาแสดงตน"].sum())
total_units    = len(bch_raw)
overall_turnout = 100 * total_voters / total_eligible if total_eligible else 0
overall_spoiled = 100 * bch_raw["บัตรเสีย"].sum() / max(bch_raw["บัตรที่ใช้"].sum(), 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("หน่วยเลือกตั้ง",    f"{total_units:,}")
c2.metric("ผู้มีสิทธิทั้งหมด", f"{total_eligible:,}")
c3.metric("Turnout รวม",        f"{overall_turnout:.1f}%")
c4.metric("บัตรเสีย รวม (บช)", f"{overall_spoiled:.1f}%")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
(tab_turnout, tab_spoiled, tab_party,
 tab_winner, tab_summary, tab_stats) = st.tabs([
    "Turnout",
    "บัตรเสีย",
    "คะแนนพรรค / ผู้สมัคร",
    "ผู้ชนะรายตำบล (บช)",
    "สรุปรายอำเภอ",
    "📊 Statistics",
])

# --- Turnout map ------------------------------------------------------------
with tab_turnout:
    st.subheader("Turnout ตามตำบล")
    st.caption("ขนาดวงกลม = ผู้มาแสดงตน · สี = % turnout")
    st.pydeck_chart(
        pdk_continuous_map(
            bch_tambon, value_col="turnout_pct",
            tooltip_cols=["ผู้มีสิทธิตามบัญชี", "ผู้มาแสดงตน", "turnout_pct", "จำนวนหน่วย"],
            cmap_name="viridis",
        ),
        use_container_width=True,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**5 ตำบลที่มี turnout สูงสุด**")
        st.dataframe(
            bch_tambon.nlargest(5, "turnout_pct")[
                ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "ผู้มาแสดงตน", "ผู้มีสิทธิตามบัญชี", "turnout_pct"]
            ].round(2), hide_index=True, use_container_width=True,
        )
    with col_b:
        st.markdown("**5 ตำบลที่มี turnout ต่ำสุด**")
        st.dataframe(
            bch_tambon.nsmallest(5, "turnout_pct")[
                ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "ผู้มาแสดงตน", "ผู้มีสิทธิตามบัญชี", "turnout_pct"]
            ].round(2), hide_index=True, use_container_width=True,
        )

# --- Spoiled-ballot map -----------------------------------------------------
with tab_spoiled:
    st.subheader("สัดส่วนบัตรเสียตามตำบล")
    st.caption("อัตราบัตรเสียที่สูงผิดปกติเป็นสัญญาณเตือน")
    ballot_kind = st.radio(
        "ดูข้อมูลจาก",
        options=["บัตรพรรค (บช)", "บัตรผู้สมัคร (เขต)"],
        horizontal=True, key="spoiled_kind",
    )
    _src_spoiled = bch_tambon if ballot_kind.startswith("บัตรพรรค") else norm_tambon
    st.pydeck_chart(
        pdk_continuous_map(
            _src_spoiled, value_col="spoiled_pct",
            tooltip_cols=["บัตรเสีย", "บัตรที่ใช้", "spoiled_pct", "จำนวนหน่วย"],
            cmap_name="Reds",
        ),
        use_container_width=True,
    )
    st.markdown("**10 ตำบลที่มีบัตรเสียสูงสุด**")
    st.dataframe(
        _src_spoiled.nlargest(10, "spoiled_pct")[
            ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "บัตรเสีย", "บัตรที่ใช้", "spoiled_pct"]
        ].round(2), hide_index=True, use_container_width=True,
    )

# --- Party / candidate strength map ----------------------------------------
with tab_party:
    st.subheader("ฐานเสียงรายพรรค / รายผู้สมัคร")
    kind = st.radio(
        "ประเภท",
        options=["บัญชีรายชื่อ (พรรค)", "เขต (ผู้สมัคร)"],
        horizontal=True, key="strength_kind",
    )
    if kind.startswith("บัญชี"):
        _cols_p, _src_p = bch_score_cols,  bch_tambon
        label_prefix       = "พรรคหมายเลข"
        score_col_template = "คะแนน_พรรค_{}"
    else:
        _cols_p, _src_p = norm_score_cols, norm_tambon
        label_prefix       = "ผู้สมัครหมายเลข"
        score_col_template = "คะแนน_ผู้สมัคร_{}"

    numbers = [number_from_col(c) for c in _cols_p]
    _fmt = (
        (lambda n: f"{n} – {party_name(n)}")
        if kind.startswith("บัญชี")
        else (lambda n: f"{n} – {candidate_name(n)}")
    )
    selected  = st.selectbox(f"เลือก{label_prefix}", options=numbers, format_func=_fmt)
    score_col = score_col_template.format(selected)

    metric = st.radio(
        "แสดงผลเป็น",
        options=["จำนวนคะแนน (ดิบ)", "สัดส่วนของคะแนนรวมในตำบล (%)"],
        horizontal=True, key="strength_metric",
    )
    plot_src = _src_p.copy()
    if metric.startswith("สัดส่วน"):
        plot_src["value"] = pd.to_numeric(
            100 * plot_src[score_col] / plot_src["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA),
            errors="coerce",
        )
    else:
        plot_src["value"] = plot_src[score_col]

    st.pydeck_chart(
        pdk_continuous_map(
            plot_src, value_col="value",
            tooltip_cols=[score_col, "รวมคะแนนทั้งสิ้น", "value"],
            cmap_name="plasma",
        ),
        use_container_width=True,
    )
    _name_label = party_name(selected) if kind.startswith("บัญชี") else candidate_name(selected)
    st.markdown(f"**10 ตำบลที่ {label_prefix} {selected} ({_name_label}) ได้คะแนนมากที่สุด**")
    top = _src_p.nlargest(10, score_col)[
        ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", score_col, "รวมคะแนนทั้งสิ้น"]
    ].copy()
    top["สัดส่วน (%)"] = (100 * top[score_col] / top["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA)).round(2)
    st.dataframe(top, hide_index=True, use_container_width=True)

# --- Winning party per tambon (BCH) ----------------------------------------
with tab_winner:
    st.subheader("พรรคที่ได้คะแนนสูงสุดในแต่ละตำบล (บช)")
    st.caption(
        "ขนาดวงกลม = ผู้มาแสดงตน · "
        "ลองดู 'อันดับ 2' เพื่อเห็นความแตกต่างเชิงพื้นที่"
    )
    rank_choice = st.radio("ดู", options=["พรรคอันดับ 1", "พรรคอันดับ 2"],
                           horizontal=True, key="winner_rank")

    score_only = bch_tambon[bch_score_cols].copy()
    rank_idx   = score_only.values.argsort(axis=1)[:, ::-1]
    pick_idx   = rank_idx[:, 0] if rank_choice == "พรรคอันดับ 1" else rank_idx[:, 1]
    cols_arr   = list(score_only.columns)
    picked_party_no = [number_from_col(cols_arr[i]) for i in pick_idx]
    picked_score    = [score_only.iat[r, i] for r, i in enumerate(pick_idx)]

    winner_df = bch_tambon.copy()
    winner_df["พรรคที่เลือก"]    = [party_name(n) for n in picked_party_no]
    winner_df["คะแนนของพรรคนี้"] = picked_score
    winner_df["margin_pct"] = pd.to_numeric(
        100 * winner_df["คะแนนของพรรคนี้"] / winner_df["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA),
        errors="coerce",
    )

    deck, color_map = pdk_categorical_map(
        winner_df, color_col="พรรคที่เลือก",
        tooltip_cols=["พรรคที่เลือก", "คะแนนของพรรคนี้", "รวมคะแนนทั้งสิ้น", "margin_pct"],
    )
    st.pydeck_chart(deck, use_container_width=True)

    with st.expander("ดูคำอธิบายสี"):
        legend_html = "".join(
            f'<span style="display:inline-block;width:12px;height:12px;'
            f'background:rgb({c[0]},{c[1]},{c[2]});border-radius:50%;'
            f'margin-right:6px;vertical-align:middle"></span>{party}<br>'
            for party, c in color_map.items()
        )
        st.markdown(legend_html, unsafe_allow_html=True)

    summary = (
        winner_df.groupby("พรรคที่เลือก")
        .agg(**{
            "จำนวนตำบล":     ("ตำบล_แขวง_เทศบาล",   "count"),
            "คะแนนรวม":       ("คะแนนของพรรคนี้",    "sum"),
            "ส่วนแบ่งเฉลี่ย": ("margin_pct",         "mean"),
        })
        .reset_index()
        .sort_values("จำนวนตำบล", ascending=False)
        .round(2)
    )
    st.markdown(f"**สรุปจำนวนตำบลที่แต่ละพรรคเป็น{rank_choice}**")
    st.dataframe(summary, hide_index=True, use_container_width=True)

# --- Amphoe summary + pie charts --------------------------------------------
with tab_summary:
    st.subheader("สรุปรายอำเภอ")

    amphoe = (
        bch_raw.groupby("อำเภอ_เขต")
        .agg(**{
            "จำนวนหน่วย":  ("หน่วยเลือกตั้งที่",   "count"),
            "ผู้มีสิทธิ":  ("ผู้มีสิทธิตามบัญชี", "sum"),
            "ผู้มาแสดงตน": ("ผู้มาแสดงตน",          "sum"),
            "บัตรดี":       ("บัตรดี",               "sum"),
            "บัตรเสีย":     ("บัตรเสีย",             "sum"),
        })
        .reset_index()
    )
    amphoe["turnout (%)"]  = (100 * amphoe["ผู้มาแสดงตน"] / amphoe["ผู้มีสิทธิ"]).round(2)
    amphoe["บัตรเสีย (%)"] = (
        100 * amphoe["บัตรเสีย"] / (amphoe["บัตรดี"] + amphoe["บัตรเสีย"])
    ).round(2)

    party_by_amphoe   = bch_raw.groupby("อำเภอ_เขต")[bch_score_cols].sum()
    top_party_no      = party_by_amphoe.idxmax(axis=1).map(number_from_col)
    top_party_score   = party_by_amphoe.max(axis=1)
    total_party_score = party_by_amphoe.sum(axis=1)
    amphoe = amphoe.merge(
        pd.DataFrame({
            "อำเภอ_เขต":          top_party_no.index,
            "พรรคอันดับ 1":       top_party_no.map(party_name).values,
            "คะแนนพรรคอันดับ 1": top_party_score.values,
            "ส่วนแบ่ง (%)": (
                100 * top_party_score / total_party_score.replace(0, pd.NA)
            ).round(2).values,
        }),
        on="อำเภอ_เขต",
    )
    st.dataframe(amphoe, hide_index=True, use_container_width=True)

    st.markdown("**Turnout เปรียบเทียบรายอำเภอ**")
    fig_bar = px.bar(
        amphoe.sort_values("turnout (%)", ascending=True),
        x="turnout (%)", y="อำเภอ_เขต", orientation="h",
        text="turnout (%)", height=320,
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_bar.update_layout(margin={"l": 0, "r": 20, "t": 10, "b": 10})
    st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()
    st.subheader("สัดส่วนคะแนนพรรค (บัญชีรายชื่อ) รายอำเภอ / รายตำบล")

    pie_col1, pie_col2 = st.columns(2)
    with pie_col1:
        amphoe_list = sorted(bch_raw["อำเภอ_เขต"].unique())
        sel_amphoe  = st.selectbox("เลือกอำเภอ", options=amphoe_list, key="pie_amphoe")
        a_scores = bch_raw[bch_raw["อำเภอ_เขต"] == sel_amphoe][bch_score_cols].sum()
        a_pie_df = pd.DataFrame({
            "พรรค":  [party_name(number_from_col(c)) for c in bch_score_cols],
            "คะแนน": a_scores.values,
        })
        a_pie_df = a_pie_df[a_pie_df["คะแนน"] > 0]
        fig_pa = px.pie(a_pie_df, names="พรรค", values="คะแนน",
                        title=f"คะแนนพรรค — {sel_amphoe}", hole=0.35)
        fig_pa.update_traces(textposition="inside", textinfo="percent+label")
        fig_pa.update_layout(showlegend=False, margin={"t": 40, "b": 0, "l": 0, "r": 0})
        st.plotly_chart(fig_pa, use_container_width=True)

    with pie_col2:
        tambon_list = sorted(
            bch_raw[bch_raw["อำเภอ_เขต"] == sel_amphoe]["ตำบล_แขวง_เทศบาล"].unique()
        )
        sel_tambon = st.selectbox("เลือกตำบล", options=tambon_list, key="pie_tambon")
        t_scores = bch_raw[
            (bch_raw["อำเภอ_เขต"] == sel_amphoe)
            & (bch_raw["ตำบล_แขวง_เทศบาล"] == sel_tambon)
        ][bch_score_cols].sum()
        t_pie_df = pd.DataFrame({
            "พรรค":  [party_name(number_from_col(c)) for c in bch_score_cols],
            "คะแนน": t_scores.values,
        })
        t_pie_df = t_pie_df[t_pie_df["คะแนน"] > 0]
        fig_pt = px.pie(t_pie_df, names="พรรค", values="คะแนน",
                        title=f"คะแนนพรรค — {sel_tambon}", hole=0.35)
        fig_pt.update_traces(textposition="inside", textinfo="percent+label")
        fig_pt.update_layout(showlegend=False, margin={"t": 40, "b": 0, "l": 0, "r": 0})
        st.plotly_chart(fig_pt, use_container_width=True)

# --- Statistics Dashboard ---------------------------------------------------
with tab_stats:
    st.subheader("📊 Statistical Dashboard")

    s_col1, s_col2, s_col3 = st.columns(3)
    with s_col1:
        election_mode = st.radio(
            "Election Mode", ["Party List", "Constituency"],
            horizontal=True, key="stats_mode",
        )
    with s_col2:
        df_units, df_scores, df_merged = _load_dashboard(election_mode)
        if df_units.empty:
            st.warning("Data not found — verify the CSVs in `data/result/`.")
            st.stop()
        districts    = ["All"] + sorted(df_units["District"].dropna().unique().tolist())
        sel_district = st.selectbox("District (อำเภอ)", districts, key="stats_dist")
    with s_col3:
        _fu = df_units  if sel_district == "All" else df_units[df_units["District"] == sel_district]
        _fm = df_merged if sel_district == "All" else df_merged[df_merged["District"] == sel_district]
        subdistricts = ["All"] + sorted(_fu["Subdistrict"].dropna().unique().tolist())
        sel_sub      = st.selectbox("Subdistrict (ตำบล)", subdistricts, key="stats_sub")

    filtered_units  = _fu if sel_sub == "All" else _fu[_fu["Subdistrict"] == sel_sub]
    filtered_merged = _fm if sel_sub == "All" else _fm[_fm["Subdistrict"] == sel_sub]

    st.divider()

    # KPIs
    eligible  = filtered_units["Eligible_Voters"].sum()
    showed_up = filtered_units["Voters_Showed_Up"].sum()
    turnout_p = (showed_up / eligible * 100) if eligible > 0 else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Polling Units",    len(filtered_units))
    k2.metric("Eligible Voters",  f"{int(eligible):,}")
    k3.metric("Voters Showed Up", f"{int(showed_up):,}")
    k4.metric("Turnout",          f"{turnout_p:.2f}%")

    st.divider()

    # Top 10 entities
    entity_label = "Parties" if election_mode == "Party List" else "Candidates"
    st.subheader(f"🏆 Top 10 {entity_label} by Total Votes")
    entity_totals = (
        filtered_merged.groupby("Entity_Name")["Score"]
        .sum().reset_index()
        .sort_values("Score", ascending=False).head(10)
    )
    fig_ebar = px.bar(
        entity_totals, x="Score", y="Entity_Name", orientation="h", text="Score",
        color="Score", color_continuous_scale="Viridis",
        labels={"Entity_Name": "Political Entity", "Score": "Total Votes"}, height=500,
    )
    fig_ebar.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_ebar, use_container_width=True)

    st.divider()

    # Ballot breakdown + turnout histogram
    bc1, bc2 = st.columns(2)
    with bc1:
        st.subheader("🗳️ Ballot Composition")
        ballot_data = pd.DataFrame({
            "Ballot Type": ["Valid (บัตรดี)", "Invalid (บัตรเสีย)", "No Vote (ไม่ประสงค์)"],
            "Count": [
                filtered_units["Valid_Ballots"].sum(),
                filtered_units["Invalid_Ballots"].sum(),
                filtered_units["No_Vote_Ballots"].sum(),
            ],
        })
        fig_bpie = px.pie(
            ballot_data, names="Ballot Type", values="Count", hole=0.4,
            color="Ballot Type",
            color_discrete_map={
                "Valid (บัตรดี)":      "#2ca02c",
                "Invalid (บัตรเสีย)":   "#d62728",
                "No Vote (ไม่ประสงค์)": "#7f7f7f",
            },
        )
        st.plotly_chart(fig_bpie, use_container_width=True)

    with bc2:
        st.subheader("📈 Turnout Distribution")
        fig_hist = px.histogram(
            filtered_units, x="Turnout_Pct", nbins=20,
            labels={"Turnout_Pct": "Voter Turnout (%)"},
            color_discrete_sequence=["#1f77b4"], marginal="box",
        )
        fig_hist.update_layout(yaxis_title="Polling Units")
        st.plotly_chart(fig_hist, use_container_width=True)

    st.divider()

    # Battleground analysis
    st.subheader("⚔️ Battleground Analysis")
    unit_totals = (
        filtered_merged.groupby("Unit_ID")["Score"].sum()
        .reset_index().rename(columns={"Score": "Total_Valid_Votes"})
    )
    sorted_scores = filtered_merged.sort_values(["Unit_ID", "Score"], ascending=[True, False])
    ranked_scores = sorted_scores.groupby("Unit_ID").head(2).reset_index(drop=True)

    mov_data = []
    for unit, grp in ranked_scores.groupby("Unit_ID"):
        if len(grp) == 2:
            tot   = unit_totals.loc[unit_totals["Unit_ID"] == unit, "Total_Valid_Votes"].values
            total = tot[0] if len(tot) else 0
            diff  = grp.iloc[0]["Score"] - grp.iloc[1]["Score"]
            pct   = (diff / total * 100) if total > 0 else 0
            cat   = ("Hyper-Competitive (<5%)" if pct < 5
                     else "Battleground (5-15%)" if pct < 15
                     else "Safe / Landslide (>15%)")
            mov_data.append({
                "Unit_ID":     unit,
                "Subdistrict": grp.iloc[0]["Subdistrict"],
                "Winner":      grp.iloc[0]["Entity_Name"],
                "Runner_Up":   grp.iloc[1]["Entity_Name"],
                "Vote_Margin": diff,
                "Margin_Pct":  pct,
                "Category":    cat,
            })

    if mov_data:
        df_mov = pd.DataFrame(mov_data)
        bg1, bg2 = st.columns(2)
        with bg1:
            fig_bgpie = px.pie(
                df_mov, names="Category", hole=0.5, title="Polling Unit Competitiveness",
                color="Category",
                color_discrete_map={
                    "Hyper-Competitive (<5%)": "red",
                    "Battleground (5-15%)":    "orange",
                    "Safe / Landslide (>15%)": "blue",
                },
            )
            st.plotly_chart(fig_bgpie, use_container_width=True)
        with bg2:
            st.markdown("### Top 10 Closest Races")
            st.dataframe(
                df_mov.sort_values("Vote_Margin").head(10)[
                    ["Subdistrict", "Winner", "Runner_Up", "Vote_Margin"]
                ].style.background_gradient(subset=["Vote_Margin"], cmap="Reds_r"),
                use_container_width=True,
            )

    st.divider()

    # Sunburst
    st.subheader("🎯 Hierarchical Vote Distribution")
    sb_data = filtered_merged.copy()
    top6 = (
        sb_data.groupby("Entity_Name")["Score"].sum()
        .sort_values(ascending=False).head(6).index.tolist()
    )
    sb_data["Entity_Grouped"] = sb_data["Entity_Name"].apply(
        lambda x: x if x in top6 else "Other"
    )
    sb_agg = (
        sb_data.groupby(["District", "Subdistrict", "Entity_Grouped"])["Score"]
        .sum().reset_index()
    )
    sb_agg = sb_agg[sb_agg["Score"] > 0]
    fig_sb = px.sunburst(
        sb_agg, path=["District", "Subdistrict", "Entity_Grouped"], values="Score",
        title="District → Subdistrict → Party/Candidate",
        color="Entity_Grouped",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_sb.update_layout(height=700)
    st.plotly_chart(fig_sb, use_container_width=True)
