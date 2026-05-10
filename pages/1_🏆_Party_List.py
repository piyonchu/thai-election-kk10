"""Party-list (บัญชีรายชื่อ) deep dive — vote share, stronghold map, ตำบล breakdown."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import load_data, party_totals, winner_by_subdistrict
from utils.parties import color_map

st.set_page_config(page_title="Party-List", page_icon="🏆", layout="wide")

units_bch, party_scores, _, _ = load_data()

st.title("🏆 Party-List Deep Dive")
st.caption("All charts weight by *votes* (บัตรดี for the party-list ballot).")

if party_scores.empty:
    st.warning("No party-list data found. Check data/aomsin_result/bch/.")
    st.stop()

party_t = party_totals(party_scores)

# ---------------------------------------------------------------- filters
top_n = st.sidebar.slider("Show top N parties", 5, min(30, len(party_t)), 10)
include_absentee = st.sidebar.checkbox(
    "Include absentee/out-of-area votes",
    value=True,
    help=(
        "Absentee votes are advance/overseas ballots with no ตำบล. They count "
        "toward the headline total but cannot be charted by location."
    ),
)
districts_real = sorted(
    party_scores[~party_scores["Is_Absentee"]]["District"].unique()
)
sel_districts = st.sidebar.multiselect(
    "Filter by อำเภอ", districts_real, default=districts_real
)

base = party_scores if include_absentee else party_scores[~party_scores["Is_Absentee"]]
# Geographic filter only applies to non-absentee rows; keep absentee in if toggled on.
geo_mask = base["District"].isin(sel_districts) & (~base["Is_Absentee"])
abs_mask = base["Is_Absentee"] & include_absentee
filtered = base[geo_mask | abs_mask]
filtered_totals = party_totals(filtered)
top = filtered_totals.head(top_n)

# ---------------------------------------------------------------- vote share
left, right = st.columns([3, 2])

with left:
    st.subheader(f"Top {top_n} — vote share")
    cmap = color_map(top["Party_Name"])
    fig = px.bar(
        top.iloc[::-1],
        x="Share",
        y="Party_Name",
        orientation="h",
        text=top.iloc[::-1]["Share"].map(lambda v: f"{v:.2f}%"),
        color="Party_Name",
        color_discrete_map=cmap,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        showlegend=False,
        height=520,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Vote share (%)",
        yaxis_title=None,
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Totals table")
    show = top.copy()
    show["Votes"] = show["Votes"].map(lambda v: f"{int(v):,}")
    show["Share"] = show["Share"].map(lambda v: f"{v:.2f}%")
    st.dataframe(show, hide_index=True, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------- stacked by ตำบล
st.subheader("Vote share by ตำบล — top parties stacked")
st.caption("Geographic view — absentee votes always excluded here.")
top_names = top["Party_Name"].tolist()
geo_only = filtered[~filtered["Is_Absentee"]]
sub = (
    geo_only.groupby(["District", "Subdistrict", "Party_Name"], as_index=False)["Score"]
    .sum()
    .rename(columns={"Score": "Votes"})
)
sub["TambonLabel"] = sub["District"] + " / " + sub["Subdistrict"]
sub_top = sub[sub["Party_Name"].isin(top_names)].copy()
totals_by_tambon = sub.groupby("TambonLabel")["Votes"].sum().rename("TotalVotes")
sub_top = sub_top.join(totals_by_tambon, on="TambonLabel")
sub_top["Share"] = sub_top["Votes"] / sub_top["TotalVotes"] * 100

fig2 = px.bar(
    sub_top,
    x="TambonLabel",
    y="Share",
    color="Party_Name",
    color_discrete_map=color_map(top_names),
    custom_data=["Votes"],
)
fig2.update_traces(
    hovertemplate="%{x}<br>%{fullData.name}: %{y:.1f}%% (%{customdata[0]:,} votes)<extra></extra>"
)
fig2.update_layout(
    barmode="stack",
    height=520,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title=None,
    yaxis_title="Vote share (%)",
    legend_title=None,
)
fig2.update_xaxes(tickangle=-40)
st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------- subdistrict winners
st.subheader("ตำบล winners (party-list)")
wbs = winner_by_subdistrict(filtered, "Party_Name")
if wbs.empty:
    st.info("No subdistrict winner data for the current filter.")
else:
    wbs_view = wbs.copy()
    wbs_view["Winner_Share"] = wbs_view["Winner_Share"].round(2)
    wbs_view["Margin_pp"] = wbs_view["Margin_pp"].round(2)
    st.dataframe(
        wbs_view[
            [
                "District",
                "Subdistrict",
                "Winner",
                "Winner_Votes",
                "Winner_Share",
                "Runner_Up",
                "Runner_Up_Votes",
                "Margin_pp",
                "Total_Votes",
            ]
        ].sort_values(["District", "Subdistrict"]),
        hide_index=True,
        use_container_width=True,
    )

    wins_count = wbs.groupby("Winner").size().rename("ตำบล won").reset_index()
    wins_count = wins_count.sort_values("ตำบล won", ascending=False)
    fig3 = px.bar(
        wins_count,
        x="Winner",
        y="ตำบล won",
        color="Winner",
        color_discrete_map=color_map(wins_count["Winner"]),
        text="ตำบล won",
    )
    fig3.update_traces(textposition="outside")
    fig3.update_layout(
        showlegend=False,
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=None,
    )
    st.plotly_chart(fig3, use_container_width=True)
