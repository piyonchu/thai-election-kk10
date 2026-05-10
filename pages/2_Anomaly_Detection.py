import os
import sys

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Make the parent project importable regardless of where Streamlit launches
# ---------------------------------------------------------------------------
_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BASE_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.data_loader import load_data
from utils.anomalies import (
    calculate_benfords_law,
    calculate_isolation_forest,
    calculate_turnout_zscores,
    check_ballot_reconciliation,
    detect_symmetric_vote_buying,
)

st.set_page_config(
    page_title="Anomaly Detection",
    page_icon="🚨",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.header("📊 Data Source")
election_mode = st.sidebar.radio(
    "Select Election Mode:",
    ["Party List", "Constituency"],
    help=(
        "Party List → ข้อมูลจาก data/result/bch_results.csv\n"
        "Constituency → ข้อมูลจาก data/result/normal_results.csv"
    ),
)

st.title("🚨 Advanced Algorithmic Fraud Detection")
st.markdown(
    "Applying statistical analysis and machine-learning techniques "
    "to identify irregularities in polling-unit returns. Source data is read "
    "directly from the OCR-extracted CSVs in `data/result/`."
)
st.markdown("---")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_units, df_scores, df_merged = load_data(election_mode)

if df_units.empty:
    st.warning(
        "Data not found. Please ensure `data/result/bch_results.csv` "
        "and `data/result/normal_results.csv` exist."
    )
    st.stop()

# Quick sanity counters in the sidebar
st.sidebar.metric("Polling Units", f"{len(df_units):,}")
st.sidebar.metric("Districts",     f"{df_units['District'].nunique():,}")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. Ballot Reconciliation",
    "2. Turnout Outliers (Z-Score)",
    "3. Isolation Forest ML",
    "4. Benford's Law",
    "5. Vote-Buying Footprint",
])

# =========================================================
# TAB 1 — BALLOT RECONCILIATION
# =========================================================
with tab1:
    st.header("Ballot Math Reconciliation")
    st.write("""
    This algorithm checks for mathematical impossibilities at the polling-unit level:

    - **Ghost Voting** → More ballots used than accredited voters.
    - **Box Stuffing / Math Mismatch** → Valid + Invalid + No-Vote ≠ Used Ballots.
    - **Data Entry Errors** → Missing or zero values in key fields.
    """)

    failed_units, clerical_units = check_ballot_reconciliation(df_units)

    st.subheader("🚨 Severe Mathematical Fraud")
    if failed_units.empty:
        st.success("✅ No severe mathematical impossibilities detected.")
    else:
        st.error(f"Detected {len(failed_units)} suspicious polling units.")
        st.dataframe(
            failed_units.style.apply(
                lambda x: ["background-color: #ffcccc; color: black"] * len(x),
                axis=1,
            ),
            use_container_width=True,
        )

    st.subheader("📝 Clerical / Missing Data Errors")
    if clerical_units.empty:
        st.success("✅ No clerical or missing-data issues detected.")
    else:
        st.write(
            "These units contain null values or zeros, indicating possible "
            "data-entry problems rather than direct ballot manipulation."
        )
        st.dataframe(
            clerical_units.style.apply(
                lambda x: ["background-color: #fff3cd; color: black"] * len(x),
                axis=1,
            ),
            use_container_width=True,
        )

# =========================================================
# TAB 2 — TURNOUT Z-SCORE
# =========================================================
with tab2:
    st.header("Extreme Turnout Outliers")
    st.write("""
    Using standard deviations (Z-Scores) to flag polling stations with
    unnaturally high or low voter turnout compared to the dataset average.

    A Z-score greater than 3 or less than -3 indicates an extreme statistical anomaly.
    """)

    outliers = calculate_turnout_zscores(df_units)
    col1, col2 = st.columns([1, 2])

    with col1:
        st.metric("Total Outliers Detected (|Z| > 3)", len(outliers))
        if not outliers.empty:
            st.dataframe(
                outliers[["Unit_ID", "Subdistrict", "Turnout_Pct", "Turnout_Z_Score"]]
                .style.format({
                    "Turnout_Pct":     "{:.2f}%",
                    "Turnout_Z_Score": "{:.2f}",
                }),
                use_container_width=True,
            )
        else:
            st.success("✅ No extreme turnout outliers detected.")

    with col2:
        mean_t = df_units["Turnout_Pct"].mean()
        std_t  = df_units["Turnout_Pct"].std()

        fig_z = px.histogram(
            df_units, x="Turnout_Pct", nbins=30,
            title="Turnout Distribution with Z=3 Thresholds",
        )
        fig_z.add_vline(x=mean_t, line_dash="dash", line_color="green",
                        annotation_text="Mean")
        fig_z.add_vline(x=mean_t + 3 * std_t, line_dash="solid", line_color="red",
                        annotation_text="+3σ")
        fig_z.add_vline(x=mean_t - 3 * std_t, line_dash="solid", line_color="red",
                        annotation_text="-3σ")
        st.plotly_chart(fig_z, use_container_width=True)

# =========================================================
# TAB 3 — ISOLATION FOREST
# =========================================================
with tab3:
    st.header("Multivariate Anomalies (Isolation Forest)")
    st.write("""
    Unlike simple Z-scores, this machine-learning model analyses multiple
    variables simultaneously:

    - Turnout %
    - Invalid Ballot %
    - No-Vote %

    It flags polling units that exhibit suspicious combinations of metrics.
    """)

    anomalies_ml = calculate_isolation_forest(df_units)
    st.metric("Complex Anomalies Detected", len(anomalies_ml))

    if anomalies_ml.empty:
        st.success("✅ No complex multivariate anomalies detected.")
    else:
        st.dataframe(
            anomalies_ml.style.format({
                "Turnout_Pct":       "{:.2f}%",
                "Invalid_Pct":       "{:.2f}%",
                "No_Vote_Pct":       "{:.2f}%",
                "Anomaly_Severity":  "{:.3f}",
            }).background_gradient(subset=["Anomaly_Severity"], cmap="Reds_r"),
            use_container_width=True,
        )

        plot_df = df_units.dropna(subset=["Turnout_Pct", "Invalid_Pct"]).copy()
        plot_df["Is_Anomaly"] = plot_df["Unit_ID"].isin(anomalies_ml["Unit_ID"])

        fig_3d = px.scatter_3d(
            plot_df, x="Turnout_Pct", y="Invalid_Pct", z="No_Vote_Ballots",
            color="Is_Anomaly",
            color_discrete_map={True: "red", False: "blue"},
            title="3D Visualisation of Normal vs. Anomalous Polling Units",
        )
        st.plotly_chart(fig_3d, use_container_width=True)

# =========================================================
# TAB 4 — BENFORD'S LAW
# =========================================================
with tab4:
    st.header("Benford's Law of First Digits")
    st.write("""
    In naturally occurring datasets, leading digits follow a logarithmic distribution.
    Human-fabricated numbers often fail to replicate this distribution, creating
    detectable statistical deviations.
    """)
    st.latex(r"P(d) = \log_{10}\left(1 + \frac{1}{d}\right)")

    benford_results, p_val = calculate_benfords_law(df_scores)

    if p_val < 0.05:
        st.warning(
            f"⚠️ Chi-Square P-Value: {p_val:.5f}. "
            "The data significantly deviates from Benford's Law."
        )
    else:
        st.success(
            f"✅ Chi-Square P-Value: {p_val:.5f}. "
            "The data conforms to Benford's Law expectations."
        )

    fig_b = go.Figure()
    fig_b.add_trace(go.Bar(
        x=benford_results["Digit"], y=benford_results["Observed_Pct"],
        name="Observed (Actual Data)", marker_color="royalblue",
    ))
    fig_b.add_trace(go.Scatter(
        x=benford_results["Digit"], y=benford_results["Expected_Pct"],
        mode="lines+markers", name="Expected (Benford's Law)",
        line=dict(color="red", width=3),
        marker=dict(size=8, symbol="diamond"),
    ))
    fig_b.update_layout(
        title="Expected vs. Observed First Digit Distribution",
        xaxis_title="Leading Digit (1-9)", yaxis_title="Frequency (%)",
        xaxis=dict(tickmode="linear", tick0=1, dtick=1),
    )
    st.plotly_chart(fig_b, use_container_width=True)

    benford_results["Delta (Difference)"] = (
        benford_results["Observed_Pct"] - benford_results["Expected_Pct"]
    )
    st.dataframe(
        benford_results.style.format({
            "Expected_Pct":        "{:.2f}%",
            "Observed_Pct":        "{:.2f}%",
            "Delta (Difference)":  "{:.2f}%",
        }),
        use_container_width=True,
    )

# =========================================================
# TAB 5 — VOTE-BUYING FOOTPRINT
# =========================================================
with tab5:
    st.header("💸 Symmetric Vote-Buying Footprint (Double-X)")
    st.write("""
    **Hypothesis (การกาเบอร์เดียวกัน):** Vote-buyers instruct voters to mark the
    *same number* on both the Constituency (เขต) and Party-List (บัญชีรายชื่อ) ballots.

    This cross-references **both datasets** to flag polling units where a
    Party-List party received a statistically impossible spike in votes **AND**
    that party's number exactly matched the local Constituency Candidate.
    """)

    # Always load BOTH datasets for this cross-reference (independent of sidebar)
    _, df_party_scores, _ = load_data("Party List")
    _, df_const_scores, _ = load_data("Constituency")

    all_matches = detect_symmetric_vote_buying(df_party_scores, df_const_scores)

    if all_matches.empty:
        st.warning(
            "⚠️ No data available to cross-reference "
            "(ensure both `bch_results.csv` and `normal_results.csv` exist)."
        )
    else:
        suspicious = all_matches[all_matches["Party_Spike_Z_Score"] > 2.5]
        if suspicious.empty:
            st.success(
                "✅ No extreme 'Double-X' symmetric vote-buying anomalies detected "
                "(Z-Score > 2.5). Showing general matching trends below."
            )
        else:
            st.error(
                f"🚨 Detected {len(suspicious)} highly suspicious units matching "
                "the 'Double-X' footprint (Z-Score > 2.5)."
            )

        st.markdown("### 📋 All 'Double-X' Match Occurrences (Sorted by Anomaly Spike)")
        st.dataframe(
            all_matches.style.format({"Party_Spike_Z_Score": "{:.2f}"})
            .background_gradient(cmap="Reds", subset=["Party_Spike_Z_Score"]),
            use_container_width=True,
        )
