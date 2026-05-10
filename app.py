"""Khon Kaen Constituency 10 — Election Analyst Dashboard.

Entry page. Vote-centric: leads with winner, vote share, and margin.
Turnout sits in the footnote view, not the headline.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import (
    absentee_summary,
    candidate_totals,
    load_data,
    party_totals,
    winner_by_subdistrict,
)
from utils.parties import color_map, party_color

st.set_page_config(
    page_title="KK10 Election Analyst",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _share_str(v: float) -> str:
    return f"{v:.2f}%"


def _kpi_row(party_t: pd.DataFrame) -> None:
    if party_t.empty:
        st.info("No party-list data found under data/aomsin_result/bch/.")
        return
    total_valid = int(party_t["Votes"].sum())
    winner = party_t.iloc[0]
    runner = party_t.iloc[1] if len(party_t) > 1 else None
    margin_pp = (winner["Share"] - runner["Share"]) if runner is not None else 100.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 Winning party", winner["Party_Name"], _share_str(winner["Share"]))
    c2.metric(
        "🥈 Runner-up",
        runner["Party_Name"] if runner is not None else "—",
        _share_str(runner["Share"]) if runner is not None else "—",
    )
    c3.metric("Margin (pp)", f"{margin_pp:+.2f}")
    c4.metric("Total valid party-list votes", f"{total_valid:,}")


def _top_parties_chart(party_t: pd.DataFrame, top_n: int = 10):
    top = party_t.head(top_n).iloc[::-1]  # reverse so #1 sits at top of horiz bar
    cmap = color_map(top["Party_Name"])
    fig = px.bar(
        top,
        x="Votes",
        y="Party_Name",
        orientation="h",
        text=top["Share"].map(lambda v: f"{v:.1f}%"),
        color="Party_Name",
        color_discrete_map=cmap,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        showlegend=False,
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title=None,
        xaxis_title="Votes",
    )
    return fig


def _candidate_chart(cand_t: pd.DataFrame):
    if cand_t.empty:
        return None
    df = cand_t.copy()
    df["Label"] = df["Candidate_Number"].apply(lambda n: f"ผู้สมัครหมายเลข {int(n)}")
    df = df.iloc[::-1]
    fig = px.bar(
        df,
        x="Votes",
        y="Label",
        orientation="h",
        text=df["Share"].map(lambda v: f"{v:.1f}%"),
        color="Label",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        showlegend=False,
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title=None,
        xaxis_title="Votes",
    )
    return fig


def main() -> None:
    st.title("🗳️ Khon Kaen Constituency 10 — Election Analyst")
    st.caption(
        "Vote-centric view of the 2026 General Election (Election 69). Numbers below "
        "are aggregated from the OCR'd ballot tally sheets (ส.ส. ๕/๑๘) for every "
        "polling unit in เขตเลือกตั้งที่ 10."
    )

    units_bch, party_scores, units_normal, candidate_scores = load_data()
    party_t = party_totals(party_scores)
    cand_t = candidate_totals(candidate_scores)

    st.subheader("Party-list (บัญชีรายชื่อ) — top line")
    _kpi_row(party_t)

    st.markdown(" ")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**Top 10 parties by votes**")
        st.plotly_chart(_top_parties_chart(party_t), use_container_width=True)
    with right:
        st.markdown("**Constituency MP race — candidate totals**")
        cand_fig = _candidate_chart(cand_t)
        if cand_fig is None:
            st.info("No constituency ballot data found under data/aomsin_result/normal/.")
        else:
            st.plotly_chart(cand_fig, use_container_width=True)
            cwin = cand_t.iloc[0]
            crun = cand_t.iloc[1] if len(cand_t) > 1 else None
            margin = (cwin["Share"] - crun["Share"]) if crun is not None else 100.0
            st.caption(
                f"Winning candidate: **#{int(cwin['Candidate_Number'])}** "
                f"({cwin['Share']:.1f}% • {int(cwin['Votes']):,} votes) — "
                f"margin **{margin:+.2f} pp** over runner-up."
            )

    st.markdown("---")
    st.subheader("Absentee / out-of-area block (นอกเขต / นอกราชอาณาจักร)")
    abs_party = absentee_summary(party_scores, "Party_Name")
    if not abs_party:
        st.caption("No absentee/advance ballots in this dataset.")
    else:
        st.caption(
            "Advance votes from people who registered to vote outside their home "
            "ตำบล (in-district advance, out-of-district advance, and overseas). "
            "Votes count toward the constituency total but have no geographic location."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Absentee votes (party-list)", f"{abs_party['total_votes']:,}")
        c2.metric("Share of all votes", f"{abs_party['share_of_total']:.2f}%")
        c3.metric("Ballot sets (ชุด)", f"{abs_party['n_sets']}")

        bd = abs_party["breakdown"].head(8).copy()
        bd["Skew_pp"] = bd["Share_in_absentee"] - bd["Share_overall"]
        bd_view = bd.rename(
            columns={
                "Party_Name": "Party",
                "Votes": "Absentee votes",
                "Share_in_absentee": "Share among absentee (%)",
                "Share_overall": "Share overall (%)",
                "Skew_pp": "Skew vs overall (pp)",
            }
        )
        bd_view["Share among absentee (%)"] = bd_view["Share among absentee (%)"].round(2)
        bd_view["Share overall (%)"] = bd_view["Share overall (%)"].round(2)
        bd_view["Skew vs overall (pp)"] = bd_view["Skew vs overall (pp)"].round(2)
        st.dataframe(bd_view, hide_index=True, use_container_width=True)
        leader = abs_party["breakdown"].iloc[0]
        st.caption(
            f"Absentee voters skew toward **{leader['Party_Name']}** "
            f"({leader['Share_in_absentee']:.1f}% of absentee, "
            f"{leader['Share_overall']:.1f}% overall — "
            f"{leader['Share_in_absentee'] - leader['Share_overall']:+.1f} pp)."
        )

    st.markdown("---")
    st.subheader("Subdistrict (ตำบล) winners — party-list")
    st.caption("Absentee ballots are excluded here since they have no ตำบล of origin.")
    wbs = winner_by_subdistrict(party_scores, "Party_Name")
    if wbs.empty:
        st.info("No subdistrict-level data to summarize.")
    else:
        wbs_view = wbs.copy()
        wbs_view["Winner_Share"] = wbs_view["Winner_Share"].round(2)
        wbs_view["Margin_pp"] = wbs_view["Margin_pp"].round(2)
        wbs_view = wbs_view[
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
        ].sort_values(["District", "Subdistrict"])
        st.dataframe(wbs_view, use_container_width=True, hide_index=True)

        wins = wbs.groupby("Winner").size().sort_values(ascending=False)
        st.caption(
            "ตำบล won by party: "
            + " · ".join(f"**{p}** ({n})" for p, n in wins.items())
        )

    st.markdown("---")
    with st.expander("Pipeline & coverage"):
        st.write(
            f"- Polling units (party-list): **{len(units_bch)}**\n"
            f"- Polling units (constituency): **{len(units_normal)}**\n"
            f"- Party score rows: **{len(party_scores):,}**\n"
            f"- Candidate score rows: **{len(candidate_scores):,}**\n"
        )
        st.write(
            "Use the sidebar pages for: party-list deep dive, constituency race, "
            "winner-by-ตำบล map, and competitiveness analysis."
        )


if __name__ == "__main__":
    main()
