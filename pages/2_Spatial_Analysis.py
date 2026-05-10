from __future__ import annotations

import json
import os
import re

import matplotlib.cm as cm
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

RESULT_DIR = os.path.join(DATA_DIR, "result")
BCH_CSV = os.path.join(RESULT_DIR, "bch_results.csv")
NORMAL_CSV = os.path.join(RESULT_DIR, "normal_results.csv")
COORDS_CSV = os.path.join(DATA_DIR, "location_coordinates_template.csv")

MAPS_DIR = os.path.join(RESULT_DIR, "maps")

with open(os.path.join(MAPS_DIR, "party_map.json"), encoding="utf-8") as _f:
    _PARTY_MAP: dict[str, str] = json.load(_f)

with open(os.path.join(MAPS_DIR, "candidate_map.json"), encoding="utf-8") as _f:
    _CANDIDATE_MAP: dict[str, dict] = json.load(_f)


def party_name(number: int) -> str:
    return _PARTY_MAP.get(str(number), f"พรรคหมายเลข {number}")


def candidate_name(number: int) -> str:
    info = _CANDIDATE_MAP.get(str(number), {})
    return info.get("ชื่อ_สกุล", f"ผู้สมัครหมายเลข {number}")


# Center of Khon Kaen Constituency 10 (rough)
DEFAULT_CENTER = {"lat": 15.92, "lon": 102.65}
DEFAULT_ZOOM = 8.6


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bch = pd.read_csv(BCH_CSV)
    norm = pd.read_csv(NORMAL_CSV)
    coords = pd.read_csv(COORDS_CSV)
    coords = coords.rename(columns={"อำเภอ": "อำเภอ_เขต", "ตำบล": "ตำบล_แขวง_เทศบาล"})
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


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------
def aggregate_by_tambon(df: pd.DataFrame, score_cols: list[str]) -> pd.DataFrame:
    base_sum_cols = [
        "ผู้มีสิทธิตามบัญชี",
        "ผู้มาแสดงตน",
        "บัตรที่ใช้",
        "บัตรดี",
        "บัตรเสีย",
        "รวมคะแนนทั้งสิ้น",
    ]
    sum_cols = [c for c in base_sum_cols if c in df.columns] + score_cols
    grouped = (
        df.groupby(["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"], as_index=False)[sum_cols].sum()
    )
    grouped["จำนวนหน่วย"] = (
        df.groupby(["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"]).size().values
    )
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
    return tambon_df.merge(coords, on=["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"], how="left")


# ---------------------------------------------------------------------------
# Pydeck helpers
# ---------------------------------------------------------------------------
_PALETTE = [
    [31, 119, 180], [255, 127, 14], [44, 160, 44], [214, 39, 40],
    [148, 103, 189], [140, 86, 75], [227, 119, 194], [127, 127, 127],
    [188, 189, 34], [23, 190, 207], [174, 199, 232], [255, 187, 120],
    [255, 152, 150], [197, 176, 213], [196, 156, 148], [247, 182, 210],
]

_VIEW = pdk.ViewState(
    latitude=DEFAULT_CENTER["lat"],
    longitude=DEFAULT_CENTER["lon"],
    zoom=DEFAULT_ZOOM,
    pitch=0,
)


def _val_to_rgba(series: pd.Series, cmap_name: str) -> list:
    filled = series.fillna(series.median())
    vmin, vmax = float(filled.min()), float(filled.max())
    norm = (filled - vmin) / (vmax - vmin) if vmax > vmin else pd.Series([0.5] * len(filled))
    cmap_func = cm.get_cmap(cmap_name)
    return [
        [int(r * 255), int(g * 255), int(b * 255), 210]
        for r, g, b, _ in cmap_func(norm.values)
    ]


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


def pdk_continuous_map(
    df: pd.DataFrame,
    value_col: str,
    tooltip_cols: list[str],
    cmap_name: str = "viridis",
    size_col: str = "ผู้มาแสดงตน",
) -> pdk.Deck:
    plot_df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    plot_df["_color"] = _val_to_rgba(plot_df[value_col], cmap_name)
    plot_df["_radius"] = _radius_scale(plot_df[size_col])
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=plot_df,
        get_position=["Longitude", "Latitude"],
        get_fill_color="_color",
        get_radius="_radius",
        pickable=True,
        auto_highlight=True,
        opacity=0.85,
        stroked=True,
        line_width_min_pixels=1,
        get_line_color=[255, 255, 255, 80],
    )
    tooltip_html = (
        "<b>{ตำบล_แขวง_เทศบาล}</b> ({อำเภอ_เขต})<br>"
        + "<br>".join(f"{c}: {{{c}}}" for c in tooltip_cols)
    )
    return pdk.Deck(
        layers=[layer],
        initial_view_state=_VIEW,
        tooltip={"html": tooltip_html},
        map_style="road",
    )


def pdk_categorical_map(
    df: pd.DataFrame,
    color_col: str,
    tooltip_cols: list[str],
    size_col: str = "ผู้มาแสดงตน",
) -> tuple[pdk.Deck, dict]:
    plot_df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    plot_df[color_col] = plot_df[color_col].astype(str)
    colors, color_map = _cat_to_rgba(plot_df[color_col])
    plot_df["_color"] = colors
    plot_df["_radius"] = _radius_scale(plot_df[size_col])
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=plot_df,
        get_position=["Longitude", "Latitude"],
        get_fill_color="_color",
        get_radius="_radius",
        pickable=True,
        auto_highlight=True,
        opacity=0.9,
        stroked=True,
        line_width_min_pixels=1,
        get_line_color=[255, 255, 255, 80],
    )
    tooltip_html = (
        "<b>{ตำบล_แขวง_เทศบาล}</b> ({อำเภอ_เขต})<br>"
        + "<br>".join(f"{c}: {{{c}}}" for c in tooltip_cols)
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=_VIEW,
        tooltip={"html": tooltip_html},
        map_style="road",
    )
    return deck, color_map


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Spatial Analysis", layout="wide")
st.title("🗺️ Spatial analysis — เขตเลือกตั้งที่ 10 (ขอนแก่น)")

bch_raw, norm_raw, coords = load_data()

bch_score_cols = party_score_columns(bch_raw)
norm_score_cols = candidate_score_columns(norm_raw)

bch_tambon = attach_coords(aggregate_by_tambon(bch_raw, bch_score_cols), coords)
norm_tambon = attach_coords(aggregate_by_tambon(norm_raw, norm_score_cols), coords)

missing_bch = bch_tambon[bch_tambon["Latitude"].isna()][
    ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"]
].drop_duplicates()
if not missing_bch.empty:
    st.warning(
        "พบตำบลที่ไม่มีพิกัดในไฟล์ `location_coordinates_template.csv` "
        "(จะไม่แสดงบนแผนที่):\n\n"
        + "\n".join(
            f"- {getattr(r, 'อำเภอ_เขต')} / {getattr(r, 'ตำบล_แขวง_เทศบาล')}"
            for r in missing_bch.itertuples()
        )
    )

# -- Top-line numbers --------------------------------------------------------
total_eligible = int(bch_raw["ผู้มีสิทธิตามบัญชี"].sum())
total_voters = int(bch_raw["ผู้มาแสดงตน"].sum())
total_units = len(bch_raw)
overall_turnout = 100 * total_voters / total_eligible if total_eligible else 0
overall_spoiled = 100 * bch_raw["บัตรเสีย"].sum() / max(bch_raw["บัตรที่ใช้"].sum(), 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("หน่วยเลือกตั้ง", f"{total_units:,}")
c2.metric("ผู้มีสิทธิทั้งหมด", f"{total_eligible:,}")
c3.metric("Turnout รวม", f"{overall_turnout:.1f}%")
c4.metric("บัตรเสีย รวม (บช)", f"{overall_spoiled:.1f}%")

st.divider()

# -- Tabs --------------------------------------------------------------------
tab_turnout, tab_spoiled, tab_party, tab_winner, tab_summary = st.tabs(
    [
        "Turnout",
        "บัตรเสีย",
        "คะแนนพรรค / ผู้สมัคร",
        "ผู้ชนะรายตำบล (บช)",
        "สรุปรายอำเภอ",
    ]
)

# --- Turnout map ------------------------------------------------------------
with tab_turnout:
    st.subheader("Turnout ตามตำบล")
    st.caption(
        "ขนาดวงกลม = จำนวนผู้มาแสดงตน, สี = สัดส่วนผู้มาใช้สิทธิเทียบกับผู้มีสิทธิตามบัญชี"
    )
    st.pydeck_chart(
        pdk_continuous_map(
            bch_tambon,
            value_col="turnout_pct",
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
                ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "ผู้มาแสดงตน",
                 "ผู้มีสิทธิตามบัญชี", "turnout_pct"]
            ].round(2),
            hide_index=True, use_container_width=True,
        )
    with col_b:
        st.markdown("**5 ตำบลที่มี turnout ต่ำสุด**")
        st.dataframe(
            bch_tambon.nsmallest(5, "turnout_pct")[
                ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "ผู้มาแสดงตน",
                 "ผู้มีสิทธิตามบัญชี", "turnout_pct"]
            ].round(2),
            hide_index=True, use_container_width=True,
        )

# --- Spoiled-ballot map -----------------------------------------------------
with tab_spoiled:
    st.subheader("สัดส่วนบัตรเสียตามตำบล")
    st.caption(
        "อัตราบัตรเสียที่สูงผิดปกติเป็นสัญญาณเตือน "
        "(อาจเกิดจากบัตรลงคะแนนซับซ้อน ผู้ลงคะแนนสับสน หรือปัญหาการนับ)"
    )
    ballot_kind = st.radio(
        "ดูข้อมูลจาก",
        options=["บัตรพรรค (บช)", "บัตรผู้สมัคร (เขต)"],
        horizontal=True,
        key="spoiled_kind",
    )
    src = bch_tambon if ballot_kind.startswith("บัตรพรรค") else norm_tambon
    st.pydeck_chart(
        pdk_continuous_map(
            src,
            value_col="spoiled_pct",
            tooltip_cols=["บัตรเสีย", "บัตรที่ใช้", "spoiled_pct", "จำนวนหน่วย"],
            cmap_name="Reds",
        ),
        use_container_width=True,
    )

    st.markdown("**10 ตำบลที่มีบัตรเสียสูงสุด**")
    st.dataframe(
        src.nlargest(10, "spoiled_pct")[
            ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", "บัตรเสีย", "บัตรที่ใช้", "spoiled_pct"]
        ].round(2),
        hide_index=True, use_container_width=True,
    )

# --- Party / candidate strength map ----------------------------------------
with tab_party:
    st.subheader("ฐานเสียงรายพรรค / รายผู้สมัคร")

    kind = st.radio(
        "ประเภท",
        options=["บัญชีรายชื่อ (พรรค)", "เขต (ผู้สมัคร)"],
        horizontal=True,
        key="strength_kind",
    )
    if kind.startswith("บัญชี"):
        cols = bch_score_cols
        src = bch_tambon
        label_prefix = "พรรคหมายเลข"
        score_col_template = "คะแนน_พรรค_{}"
    else:
        cols = norm_score_cols
        src = norm_tambon
        label_prefix = "ผู้สมัครหมายเลข"
        score_col_template = "คะแนน_ผู้สมัคร_{}"

    numbers = [number_from_col(c) for c in cols]
    _fmt = (
        (lambda n: f"{n} – {party_name(n)}")
        if kind.startswith("บัญชี")
        else (lambda n: f"{n} – {candidate_name(n)}")
    )
    selected = st.selectbox(f"เลือก{label_prefix}", options=numbers, format_func=_fmt)
    score_col = score_col_template.format(selected)

    metric = st.radio(
        "แสดงผลเป็น",
        options=["จำนวนคะแนน (ดิบ)", "สัดส่วนของคะแนนรวมในตำบล (%)"],
        horizontal=True,
        key="strength_metric",
    )

    plot_src = src.copy()
    if metric.startswith("สัดส่วน"):
        plot_src["value"] = pd.to_numeric(
            100 * plot_src[score_col] / plot_src["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA),
            errors="coerce",
        )
    else:
        plot_src["value"] = plot_src[score_col]

    st.pydeck_chart(
        pdk_continuous_map(
            plot_src,
            value_col="value",
            tooltip_cols=[score_col, "รวมคะแนนทั้งสิ้น", "value"],
            cmap_name="plasma",
        ),
        use_container_width=True,
    )

    _name_label = party_name(selected) if kind.startswith("บัญชี") else candidate_name(selected)
    st.markdown(f"**10 ตำบลที่ {label_prefix} {selected} ({_name_label}) ได้คะแนนมากที่สุด**")
    top = src.nlargest(10, score_col)[
        ["อำเภอ_เขต", "ตำบล_แขวง_เทศบาล", score_col, "รวมคะแนนทั้งสิ้น"]
    ].copy()
    top["สัดส่วน (%)"] = (
        100 * top[score_col] / top["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA)
    ).round(2)
    st.dataframe(top, hide_index=True, use_container_width=True)

# --- Winning party per tambon (BCH) ----------------------------------------
with tab_winner:
    st.subheader("พรรคที่ได้คะแนนสูงสุดในแต่ละตำบล (บช)")
    st.caption(
        "ขนาดวงกลม = จำนวนผู้มาแสดงตน · "
        "ในเขตเลือกตั้งที่พรรคหนึ่งครอง map ของผู้ชนะอาจเป็นสีเดียว — "
        "ลองดู 'อันดับ 2' เพื่อเห็นความแตกต่างเชิงพื้นที่"
    )

    rank_choice = st.radio(
        "ดู",
        options=["พรรคอันดับ 1", "พรรคอันดับ 2"],
        horizontal=True,
        key="winner_rank",
    )

    score_only = bch_tambon[bch_score_cols].copy()
    rank_idx = score_only.values.argsort(axis=1)[:, ::-1]
    first_idx = rank_idx[:, 0]
    second_idx = rank_idx[:, 1]
    pick_idx = first_idx if rank_choice == "พรรคอันดับ 1" else second_idx

    cols_arr = list(score_only.columns)
    picked_party_no = [number_from_col(cols_arr[i]) for i in pick_idx]
    picked_score = [score_only.iat[r, i] for r, i in enumerate(pick_idx)]

    winner_df = bch_tambon.copy()
    winner_df["พรรคที่เลือก"] = [party_name(n) for n in picked_party_no]
    winner_df["คะแนนของพรรคนี้"] = picked_score
    winner_df["margin_pct"] = pd.to_numeric(
        100 * winner_df["คะแนนของพรรคนี้"]
        / winner_df["รวมคะแนนทั้งสิ้น"].replace(0, pd.NA),
        errors="coerce",
    )

    deck, color_map = pdk_categorical_map(
        winner_df,
        color_col="พรรคที่เลือก",
        tooltip_cols=["พรรคที่เลือก", "คะแนนของพรรคนี้", "รวมคะแนนทั้งสิ้น", "margin_pct"],
    )
    st.pydeck_chart(deck, use_container_width=True)

    legend_html = "".join(
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'background:rgb({c[0]},{c[1]},{c[2]});border-radius:50%;'
        f'margin-right:6px;vertical-align:middle"></span>{party}<br>'
        for party, c in color_map.items()
    )
    with st.expander("ดูคำอธิบายสี"):
        st.markdown(legend_html, unsafe_allow_html=True)

    summary = (
        winner_df.groupby("พรรคที่เลือก")
        .agg(**{
            "จำนวนตำบล": ("ตำบล_แขวง_เทศบาล", "count"),
            "คะแนนรวม": ("คะแนนของพรรคนี้", "sum"),
            "ส่วนแบ่งเฉลี่ย": ("margin_pct", "mean"),
        })
        .reset_index()
        .sort_values("จำนวนตำบล", ascending=False)
        .round(2)
    )
    st.markdown(f"**สรุปจำนวนตำบลที่แต่ละพรรคเป็น{rank_choice}**")
    st.dataframe(summary, hide_index=True, use_container_width=True)

# --- Amphoe summary ---------------------------------------------------------
with tab_summary:
    st.subheader("สรุปรายอำเภอ")

    amphoe = (
        bch_raw.groupby("อำเภอ_เขต")
        .agg(**{
            "จำนวนหน่วย": ("หน่วยเลือกตั้งที่", "count"),
            "ผู้มีสิทธิ": ("ผู้มีสิทธิตามบัญชี", "sum"),
            "ผู้มาแสดงตน": ("ผู้มาแสดงตน", "sum"),
            "บัตรดี": ("บัตรดี", "sum"),
            "บัตรเสีย": ("บัตรเสีย", "sum"),
        })
        .reset_index()
    )
    amphoe["turnout (%)"] = (100 * amphoe["ผู้มาแสดงตน"] / amphoe["ผู้มีสิทธิ"]).round(2)
    amphoe["บัตรเสีย (%)"] = (
        100 * amphoe["บัตรเสีย"] / (amphoe["บัตรดี"] + amphoe["บัตรเสีย"])
    ).round(2)

    party_by_amphoe = bch_raw.groupby("อำเภอ_เขต")[bch_score_cols].sum()
    top_party_no = party_by_amphoe.idxmax(axis=1).map(number_from_col)
    top_party_score = party_by_amphoe.max(axis=1)
    total_party_score = party_by_amphoe.sum(axis=1)
    amphoe = amphoe.merge(
        pd.DataFrame({
            "อำเภอ_เขต": top_party_no.index,
            "พรรคอันดับ 1": top_party_no.map(party_name).values,
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
        x="turnout (%)",
        y="อำเภอ_เขต",
        orientation="h",
        text="turnout (%)",
        height=320,
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_bar.update_layout(margin={"l": 0, "r": 20, "t": 10, "b": 10})
    st.plotly_chart(fig_bar, use_container_width=True)

    # -- Pie charts: party score breakdown by amphoe and tambon ---------------
    st.divider()
    st.subheader("สัดส่วนคะแนนพรรค (บัญชีรายชื่อ) รายอำเภอ / รายตำบล")

    pie_col1, pie_col2 = st.columns(2)

    with pie_col1:
        amphoe_list = sorted(bch_raw["อำเภอ_เขต"].unique())
        sel_amphoe = st.selectbox("เลือกอำเภอ", options=amphoe_list, key="pie_amphoe")

        amphoe_scores = bch_raw[bch_raw["อำเภอ_เขต"] == sel_amphoe][bch_score_cols].sum()
        amphoe_pie_df = pd.DataFrame({
            "พรรค": [party_name(number_from_col(c)) for c in bch_score_cols],
            "คะแนน": amphoe_scores.values,
        })
        amphoe_pie_df = amphoe_pie_df[amphoe_pie_df["คะแนน"] > 0]

        fig_pie_a = px.pie(
            amphoe_pie_df,
            names="พรรค",
            values="คะแนน",
            title=f"คะแนนพรรค — {sel_amphoe}",
            hole=0.35,
        )
        fig_pie_a.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie_a.update_layout(showlegend=False, margin={"t": 40, "b": 0, "l": 0, "r": 0})
        st.plotly_chart(fig_pie_a, use_container_width=True)

    with pie_col2:
        tambon_list = sorted(
            bch_raw[bch_raw["อำเภอ_เขต"] == sel_amphoe]["ตำบล_แขวง_เทศบาล"].unique()
        )
        sel_tambon = st.selectbox("เลือกตำบล", options=tambon_list, key="pie_tambon")

        tambon_scores = bch_raw[
            (bch_raw["อำเภอ_เขต"] == sel_amphoe)
            & (bch_raw["ตำบล_แขวง_เทศบาล"] == sel_tambon)
        ][bch_score_cols].sum()
        tambon_pie_df = pd.DataFrame({
            "พรรค": [party_name(number_from_col(c)) for c in bch_score_cols],
            "คะแนน": tambon_scores.values,
        })
        tambon_pie_df = tambon_pie_df[tambon_pie_df["คะแนน"] > 0]

        fig_pie_t = px.pie(
            tambon_pie_df,
            names="พรรค",
            values="คะแนน",
            title=f"คะแนนพรรค — {sel_tambon}",
            hole=0.35,
        )
        fig_pie_t.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie_t.update_layout(showlegend=False, margin={"t": 40, "b": 0, "l": 0, "r": 0})
        st.plotly_chart(fig_pie_t, use_container_width=True)
