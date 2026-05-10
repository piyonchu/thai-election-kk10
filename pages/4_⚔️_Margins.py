"""Competitiveness analysis — margin of victory at the polling-unit level."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import load_data
from utils.parties import color_map, party_color

st.set_page_config(page_title="Margins", page_icon="⚔️", layout="wide")

units_bch, party_scores, units_normal, candidate_scores = load_data()

st.title("⚔️ Competitiveness & Margins")
st.caption(
    "Polling-unit-level analysis of how decisively each unit was won. "
    "Margin = (winner share − runner-up share), in percentage points."
)

ballot_kind = st.radio(
    "Ballot type",
    ["Party-list (บช)", "Constituency MP"],
    horizontal=True,
)

if ballot_kind.startswith("Party"):
    if party_scores.empty:
        st.warning("No party-list data.")
        st.stop()
    score_df = party_scores.rename(columns={"Party_Name": "Contender"})
else:
    if candidate_scores.empty:
        st.warning("No constituency data.")
        st.stop()
    score_df = candidate_scores.copy()
    score_df["Contender"] = score_df["Candidate_Number"].map(
        lambda n: f"ผู้สมัครหมายเลข {int(n)}"
    )

# Absentee is a single aggregated bucket, not a polling unit — exclude so the
# margin distribution reflects actual booths.
absentee_excluded = int(score_df[score_df["Is_Absentee"]]["Unit_ID"].nunique())
score_df = score_df[~score_df["Is_Absentee"]]
if absentee_excluded:
    st.caption(
        f"Excluded {absentee_excluded} absentee ชุด (advance/overseas votes) — "
        "these are aggregated batches, not individual polling units."
    )

# ---------------------------------------------------------------- per-unit margin
unit_top = (
    score_df.groupby(["Unit_ID", "District", "Subdistrict", "Contender"], as_index=False)["Score"]
    .sum()
    .rename(columns={"Score": "Votes"})
    .sort_values(["Unit_ID", "Votes"], ascending=[True, False])
)

rows = []
for uid, grp in unit_top.groupby("Unit_ID"):
    total = grp["Votes"].sum()
    if total <= 0:
        continue
    first = grp.iloc[0]
    second = grp.iloc[1] if len(grp) > 1 else None
    margin = (
        (first["Votes"] - (second["Votes"] if second is not None else 0)) / total * 100
    )
    rows.append(
        {
            "Unit_ID": uid,
            "District": first["District"],
            "Subdistrict": first["Subdistrict"],
            "Winner": first["Contender"],
            "Winner_Votes": int(first["Votes"]),
            "Total_Votes": int(total),
            "Margin_pp": margin,
        }
    )
unit_margin = pd.DataFrame(rows)

if unit_margin.empty:
    st.info("No competitive units to analyze.")
    st.stop()


# ---------------------------------------------------------------- categorize
def _bucket(m: float) -> str:
    if m < 5:
        return "Hyper-competitive (<5pp)"
    if m < 15:
        return "Battleground (5–15pp)"
    if m < 30:
        return "Comfortable (15–30pp)"
    return "Stronghold (≥30pp)"


unit_margin["Competitiveness"] = unit_margin["Margin_pp"].apply(_bucket)
order = [
    "Hyper-competitive (<5pp)",
    "Battleground (5–15pp)",
    "Comfortable (15–30pp)",
    "Stronghold (≥30pp)",
]

c1, c2, c3, c4 = st.columns(4)
counts = unit_margin["Competitiveness"].value_counts()
for col, label in zip((c1, c2, c3, c4), order):
    col.metric(label, int(counts.get(label, 0)))

st.markdown("---")

# ---------------------------------------------------------------- distribution
left, right = st.columns([3, 2])
with left:
    st.subheader("Margin distribution")
    fig = px.histogram(
        unit_margin,
        x="Margin_pp",
        nbins=30,
        color_discrete_sequence=["#1f77b4"],
    )
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Margin (pp)",
        yaxis_title="Polling units",
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Who is winning the close ones?")
    close = unit_margin[unit_margin["Margin_pp"] < 15]
    close_winners = (
        close.groupby("Winner").size().rename("units").sort_values(ascending=False).reset_index()
    )
    if close_winners.empty:
        st.info("No battleground units.")
    else:
        cmap = (
            color_map(close_winners["Winner"]) if ballot_kind.startswith("Party") else None
        )
        fig2 = px.bar(
            close_winners,
            x="Winner",
            y="units",
            color="Winner" if cmap else None,
            color_discrete_map=cmap,
            text="units",
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(
            showlegend=False,
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Winner of <15pp races",
        )
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")
st.subheader("Hyper-competitive polling units (<5pp)")
tight = unit_margin[unit_margin["Margin_pp"] < 5].sort_values("Margin_pp")
view = tight.copy()
view["Margin_pp"] = view["Margin_pp"].round(2)
st.dataframe(
    view[["District", "Subdistrict", "Unit_ID", "Winner", "Winner_Votes", "Total_Votes", "Margin_pp"]],
    hide_index=True,
    use_container_width=True,
)

st.markdown("---")
st.subheader("Strongholds (≥30pp)")
strong = unit_margin[unit_margin["Margin_pp"] >= 30].sort_values("Margin_pp", ascending=False)
view2 = strong.copy()
view2["Margin_pp"] = view2["Margin_pp"].round(2)
st.dataframe(
    view2[["District", "Subdistrict", "Unit_ID", "Winner", "Winner_Votes", "Total_Votes", "Margin_pp"]].head(50),
    hide_index=True,
    use_container_width=True,
)
