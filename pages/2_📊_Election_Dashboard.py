import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# =========================================================
# IMPORTS
# =========================================================
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')
    )
)

from utils.data_loader import load_data

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Advanced Election Dashboard",
    page_icon="📊",
    layout="wide"
)

# Sidebar Election Type Selector
st.sidebar.header("📊 Data Source")
election_mode = st.sidebar.radio("Select Election Mode:", ["Party List", "Constituency"])

st.title("📊 Advanced Election Analytics Dashboard")

st.markdown("""
Comprehensive election intelligence dashboard featuring:

- Macro-level election statistics
- Entity performance analysis
- Ballot composition insights
- Voter turnout analytics
- Political fragmentation metrics
- Battleground competitiveness analysis
- Hierarchical vote distribution mapping
""")

st.markdown("---")

# =========================================================
# LOAD DATA
# =========================================================
df_units, df_scores, df_merged = load_data(election_mode)

if df_units.empty:
    st.warning(
        "Data not found. Please ensure the data pipeline has been executed."
    )
    st.stop()

# =========================================================
# SIDEBAR FILTERS
# =========================================================
st.sidebar.header("🔍 Filter Options")

# District filter
districts = ["All"] + sorted(df_units['District'].dropna().unique().tolist())

selected_district = st.sidebar.selectbox(
    "Select District (อำเภอ)",
    districts
)

# Apply district filter
if selected_district != "All":
    filtered_units = df_units[
        df_units['District'] == selected_district
    ].copy()

    filtered_merged = df_merged[
        df_merged['District'] == selected_district
    ].copy()

else:
    filtered_units = df_units.copy()
    filtered_merged = df_merged.copy()

# Subdistrict filter
subdistricts = ["All"] + sorted(
    filtered_units['Subdistrict']
    .dropna()
    .unique()
    .tolist()
)

selected_subdistrict = st.sidebar.selectbox(
    "Select Subdistrict (ตำบล)",
    subdistricts
)

# Apply subdistrict filter
if selected_subdistrict != "All":
    filtered_units = filtered_units[
        filtered_units['Subdistrict'] == selected_subdistrict
    ]

    filtered_merged = filtered_merged[
        filtered_merged['Subdistrict'] == selected_subdistrict
    ]

# =========================================================
# TOP KPI METRICS
# =========================================================
eligible_voters = filtered_units['Eligible_Voters'].sum()
voters_showed_up = filtered_units['Voters_Showed_Up'].sum()

turnout_pct = (
    (voters_showed_up / eligible_voters) * 100
    if eligible_voters > 0 else 0
)

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Polling Units",
    len(filtered_units)
)

col2.metric(
    "Eligible Voters",
    f"{eligible_voters:,}"
)

col3.metric(
    "Voters Showed Up",
    f"{voters_showed_up:,}"
)

col4.metric(
    "Turnout Percentage",
    f"{turnout_pct:.2f}%"
)

st.markdown("---")

# =========================================================
# SECTION 1 — TOP ENTITIES
# =========================================================
entity_label = "Parties" if election_mode == "Party List" else "Candidates"
st.subheader(f"🏆 Top 10 {entity_label} by Total Votes")

entity_totals = (
    filtered_merged
    .groupby('Entity_Name')['Score']
    .sum()
    .reset_index()
    .sort_values(by='Score', ascending=False)
    .head(10)
)

fig_bar = px.bar(
    entity_totals,
    x='Score',
    y='Entity_Name',
    orientation='h',
    text='Score',
    color='Score',
    color_continuous_scale='Viridis',
    labels={
        'Entity_Name': 'Political Entity',
        'Score': 'Total Votes'
    },
    height=500
)

fig_bar.update_layout(
    yaxis={'categoryorder': 'total ascending'}
)

st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# =========================================================
# SECTION 2 — BALLOT BREAKDOWN + TURNOUT DISTRIBUTION
# =========================================================
col_chart1, col_chart2 = st.columns(2)

# -----------------------------
# BALLOT BREAKDOWN
# -----------------------------
with col_chart1:
    st.subheader("🗳️ Ballot Composition Breakdown")

    valid_sum = filtered_units['Valid_Ballots'].sum()
    invalid_sum = filtered_units['Invalid_Ballots'].sum()
    no_vote_sum = filtered_units['No_Vote_Ballots'].sum()

    ballot_data = pd.DataFrame({
        'Ballot Type': [
            'Valid Ballots (บัตรดี)',
            'Invalid Ballots (บัตรเสีย)',
            'No Vote (ไม่ประสงค์ลงคะแนน)'
        ],
        'Count': [
            valid_sum,
            invalid_sum,
            no_vote_sum
        ]
    })

    fig_pie = px.pie(
        ballot_data,
        names='Ballot Type',
        values='Count',
        hole=0.4,
        color='Ballot Type',
        color_discrete_map={
            'Valid Ballots (บัตรดี)': '#2ca02c',
            'Invalid Ballots (บัตรเสีย)': '#d62728',
            'No Vote (ไม่ประสงค์ลงคะแนน)': '#7f7f7f'
        }
    )

    st.plotly_chart(fig_pie, use_container_width=True)

# -----------------------------
# TURNOUT DISTRIBUTION
# -----------------------------
with col_chart2:
    st.subheader("📈 Voter Turnout Distribution")

    fig_hist = px.histogram(
        filtered_units,
        x="Turnout_Pct",
        nbins=20,
        labels={
            'Turnout_Pct': 'Voter Turnout (%)'
        },
        color_discrete_sequence=['#1f77b4'],
        marginal="box"
    )

    fig_hist.update_layout(
        yaxis_title="Number of Polling Units"
    )

    st.plotly_chart(fig_hist, use_container_width=True)

st.markdown("---")

# =========================================================
# SECTION 3 — EFFECTIVE NUMBER OF PARTIES (ENP)
# =========================================================
st.subheader("🧩 Political Fragmentation Analysis")

st.write("""
The **Effective Number of Parties (ENP)** measures how fragmented
the political landscape is.

- ENP ≈ 2 → Strong two-way competition
- ENP > 4 → Highly fragmented multi-way competition
""")

st.latex(r"ENP = \frac{1}{\sum_{i=1}^{n} p_i^2}")

# Calculate total valid votes per polling unit
unit_totals = (
    filtered_merged
    .groupby('Unit_ID')['Score']
    .sum()
    .reset_index()
    .rename(columns={'Score': 'Total_Valid_Votes'})
)

# Merge totals back into detailed data
enp_df = pd.merge(
    filtered_merged,
    unit_totals,
    on='Unit_ID'
)

# Prevent division by zero
enp_df = enp_df[
    enp_df['Total_Valid_Votes'] > 0
]

# Calculate vote shares
enp_df['p_i'] = (
    enp_df['Score']
    / enp_df['Total_Valid_Votes']
)

enp_df['p_i_squared'] = enp_df['p_i'] ** 2

# Aggregate ENP per unit
enp_per_unit = (
    enp_df
    .groupby(['Unit_ID', 'Subdistrict'])['p_i_squared']
    .sum()
    .reset_index()
)

enp_per_unit['ENP'] = (
    1 / enp_per_unit['p_i_squared']
)

mean_enp = enp_per_unit['ENP'].mean()

col_enp1, col_enp2 = st.columns([1, 2])

with col_enp1:
    st.metric(
        "Average ENP",
        f"{mean_enp:.2f} Options"
    )

    st.info(
        "Higher ENP values indicate greater vote fragmentation."
    )

with col_enp2:
    fig_enp = px.box(
        enp_per_unit, x="Subdistrict", y="ENP", color="Subdistrict",
        title="Vote Fragmentation by Subdistrict"
    )
    fig_enp.update_layout(showlegend=False)
    fig_enp.update_yaxes(range=[0, 10]) # FIX: Cap Y-axis to 10 so the box plots are readable
    st.plotly_chart(fig_enp, use_container_width=True)

st.markdown("---")

# =========================================================
# SECTION 4 — BATTLEGROUND ANALYSIS
# =========================================================
st.subheader("⚔️ Battleground Analysis")

st.write("""
Measures the competitiveness of each polling unit by comparing
the margin between the 1st-place and 2nd-place entity.
""")

# Sort by score descending
sorted_scores = filtered_merged.sort_values(
    by=['Unit_ID', 'Score'],
    ascending=[True, False]
)

# Keep top 2 entities per unit
ranked_scores = (
    sorted_scores
    .groupby('Unit_ID')
    .head(2)
    .reset_index(drop=True)
)

mov_data = []

for unit, group in ranked_scores.groupby('Unit_ID'):

    if len(group) == 2:

        first_place = group.iloc[0]
        second_place = group.iloc[1]

        vote_diff = (
            first_place['Score']
            - second_place['Score']
        )

        total_votes = unit_totals[
            unit_totals['Unit_ID'] == unit
        ]['Total_Valid_Votes'].values[0]

        pct_diff = (
            (vote_diff / total_votes) * 100
            if total_votes > 0 else 0
        )

        # Categorize competitiveness
        if pct_diff < 5:
            category = "Hyper-Competitive (<5%)"

        elif pct_diff < 15:
            category = "Battleground (5-15%)"

        else:
            category = "Safe / Landslide (>15%)"

        mov_data.append({
            'Unit_ID': unit,
            'Subdistrict': first_place['Subdistrict'],
            'Winner': first_place['Entity_Name'],
            'Runner_Up': second_place['Entity_Name'],
            'Vote_Margin': vote_diff,
            'Margin_Pct': pct_diff,
            'Category': category
        })

df_mov = pd.DataFrame(mov_data)

if not df_mov.empty:

    col_mov1, col_mov2 = st.columns(2)

    # -----------------------------
    # COMPETITIVENESS PIE
    # -----------------------------
    with col_mov1:

        fig_mov_pie = px.pie(
            df_mov,
            names='Category',
            hole=0.5,
            title="Polling Unit Competitiveness",
            color='Category',
            color_discrete_map={
                "Hyper-Competitive (<5%)": "red",
                "Battleground (5-15%)": "orange",
                "Safe / Landslide (>15%)": "blue"
            }
        )

        st.plotly_chart(fig_mov_pie, use_container_width=True)

    # -----------------------------
    # CLOSEST RACES
    # -----------------------------
    with col_mov2:

        st.write("### Top 10 Closest Races")

        closest_races = (
            df_mov
            .sort_values('Vote_Margin')
            .head(10)
        )

        st.dataframe(
            closest_races[
                [
                    'Subdistrict',
                    'Winner',
                    'Runner_Up',
                    'Vote_Margin'
                ]
            ].style.background_gradient(
                subset=['Vote_Margin'],
                cmap='Reds_r'
            ),
            use_container_width=True
        )

st.markdown("---")

# =========================================================
# SECTION 5 — HIERARCHICAL VOTE DISTRIBUTION
# =========================================================
st.subheader("🎯 Hierarchical Vote Distribution")

st.write("""
Interactive drill-down visualization:

District ➔ Subdistrict ➔ Entity
""")

sunburst_data = filtered_merged.copy()

# Total votes per entity
entity_totals_sb = (
    sunburst_data
    .groupby('Entity_Name')['Score']
    .sum()
    .reset_index()
)

# Keep top entities only
top_entities_list = (
    entity_totals_sb
    .sort_values('Score', ascending=False)
    .head(6)['Entity_Name']
    .tolist()
)

sunburst_data['Entity_Grouped'] = (
    sunburst_data['Entity_Name']
    .apply(
        lambda x:
        x if x in top_entities_list
        else 'Other Minor'
    )
)

# Aggregate for sunburst
sunburst_agg = (
    sunburst_data
    .groupby(
        ['District', 'Subdistrict', 'Entity_Grouped']
    )['Score']
    .sum()
    .reset_index()
)

sunburst_agg = sunburst_agg[
    sunburst_agg['Score'] > 0
]

fig_sunburst = px.sunburst(
    sunburst_agg,
    path=[
        'District',
        'Subdistrict',
        'Entity_Grouped'
    ],
    values='Score',
    title="Vote Distribution Hierarchy",
    color='Entity_Grouped',
    color_discrete_sequence=px.colors.qualitative.Pastel
)

fig_sunburst.update_layout(height=700)

st.plotly_chart(fig_sunburst, use_container_width=True)