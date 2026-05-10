"""Constituency MP race (ส.ส.เขต) — candidate-level votes, winner, margin, ตำบล map."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import candidate_totals, load_data, winner_by_subdistrict

st.set_page_config(page_title="Constituency MP", page_icon="👤", layout="wide")

_, _, units_normal, candidate_scores = load_data()

st.title("👤 Constituency MP Race (ส.ส.เขต 10)")
st.caption(
    "The MP seat goes to whichever candidate wins the most constituency votes. "
    "Numbers are candidate ballot numbers — fill in real names by editing the "
    "`CANDIDATE_NAME` dict in `pages/2_👤_Constituency.py` if you have them."
)

if candidate_scores.empty:
    st.warning("No constituency ballot data found. Check data/aomsin_result/normal/.")
    st.stop()

# Edit this dict to attach real candidate names + party affiliation if known.
CANDIDATE_NAME: dict[int, str] = {}


def _label(no: int) -> str:
    name = CANDIDATE_NAME.get(int(no))
    return f"#{int(no)} {name}" if name else f"ผู้สมัครหมายเลข {int(no)}"


# ---------------------------------------------------------------- KPI
cand_t = candidate_totals(candidate_scores)
total_valid = int(cand_t["Votes"].sum())
winner = cand_t.iloc[0]
runner = cand_t.iloc[1] if len(cand_t) > 1 else None
margin_pp = (winner["Share"] - runner["Share"]) if runner is not None else 100.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("🏆 Winner", _label(winner["Candidate_Number"]), f"{winner['Share']:.2f}%")
c2.metric(
    "🥈 Runner-up",
    _label(runner["Candidate_Number"]) if runner is not None else "—",
    f"{runner['Share']:.2f}%" if runner is not None else "—",
)
c3.metric("Margin (pp)", f"{margin_pp:+.2f}")
c4.metric("Total valid votes", f"{total_valid:,}")

st.markdown("---")

# ---------------------------------------------------------------- bar
df = cand_t.copy()
df["Label"] = df["Candidate_Number"].map(_label)

left, right = st.columns([3, 2])
with left:
    st.subheader("Candidate vote totals")
    fig = px.bar(
        df.iloc[::-1],
        x="Votes",
        y="Label",
        orientation="h",
        text=df.iloc[::-1]["Share"].map(lambda v: f"{v:.2f}%"),
        color="Label",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        showlegend=False,
        height=480,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title=None,
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Table")
    show = df[["Label", "Votes", "Share"]].copy()
    show["Votes"] = show["Votes"].map(lambda v: f"{int(v):,}")
    show["Share"] = show["Share"].map(lambda v: f"{v:.2f}%")
    show.columns = ["Candidate", "Votes", "Share"]
    st.dataframe(show, hide_index=True, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------- ตำบล winners
st.subheader("Per-ตำบล winners")
wbs = winner_by_subdistrict(
    candidate_scores.assign(
        Candidate_Label=candidate_scores["Candidate_Number"].map(_label)
    ),
    "Candidate_Label",
)
if wbs.empty:
    st.info("No subdistrict-level data.")
else:
    view = wbs.copy()
    view["Winner_Share"] = view["Winner_Share"].round(2)
    view["Margin_pp"] = view["Margin_pp"].round(2)
    st.dataframe(
        view[
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
