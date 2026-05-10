"""
Algorithmic anomaly-detection routines for Thai election data.

All functions consume the long-format frames produced by
``utils.data_loader.load_data``:

    df_units  — one row per polling unit
                (Unit_ID, District, Subdistrict, Eligible_Voters,
                 Voters_Showed_Up, Used_Ballots, Valid_Ballots,
                 Invalid_Ballots, No_Vote_Ballots, Turnout_Pct, Invalid_Pct)

    df_scores — one row per (Unit_ID, Entity_Number)
                (Unit_ID, District, Subdistrict, Entity_Number,
                 Entity_Name, Score)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chisquare, zscore
from sklearn.ensemble import IsolationForest


# ---------------------------------------------------------------------------
# 1. Ballot reconciliation
# ---------------------------------------------------------------------------
def check_ballot_reconciliation(df_units: pd.DataFrame):
    """
    Refined ballot reconciliation: separates clerical / missing-data issues
    from real mathematical impossibilities (suspected fraud).

    Returns ``(failed_units, clerical_units)``.
    """
    df = df_units.copy()

    cols_needed = ["Voters_Showed_Up", "Used_Ballots", "Valid_Ballots",
                   "Invalid_Ballots", "No_Vote_Ballots"]

    # 1) Clerical errors — null inputs, or zero turnout (treated as missing)
    clerical_mask = (
        df[["Voters_Showed_Up", "Used_Ballots", "Valid_Ballots"]].isna().any(axis=1)
        | (df["Voters_Showed_Up"] == 0)
    )

    df_clean = df[~clerical_mask].copy()

    # 2) Mathematical fraud
    ghost_voting   = df_clean["Used_Ballots"] > df_clean["Voters_Showed_Up"]
    math_mismatch  = df_clean["Used_Ballots"] != (
        df_clean["Valid_Ballots"]
        + df_clean["Invalid_Ballots"]
        + df_clean["No_Vote_Ballots"]
    )
    over_turnout   = df_clean["Turnout_Pct"] > 100

    df_clean["Anomaly_Type"] = ""
    df_clean.loc[ghost_voting,  "Anomaly_Type"] += "Ghost Voters; "
    df_clean.loc[math_mismatch, "Anomaly_Type"] += "Math Mismatch; "
    df_clean.loc[over_turnout,  "Anomaly_Type"] += "Turnout > 100%; "

    failed_units = df_clean[df_clean["Anomaly_Type"] != ""]

    clerical_units = df[clerical_mask].copy()
    clerical_units["Anomaly_Type"] = "Missing/Zero Data (Clerical)"

    out_cols = ["Unit_ID", "District", "Subdistrict",
                "Voters_Showed_Up", "Used_Ballots", "Anomaly_Type"]

    return failed_units[out_cols], clerical_units[out_cols]


# ---------------------------------------------------------------------------
# 2. Turnout Z-Score
# ---------------------------------------------------------------------------
def calculate_turnout_zscores(df_units: pd.DataFrame) -> pd.DataFrame:
    """Polling units with a turnout Z-score above 3 std-dev."""
    df = df_units.dropna(subset=["Turnout_Pct"]).copy()
    if len(df) < 2 or df["Turnout_Pct"].std(ddof=0) == 0:
        df["Turnout_Z_Score"] = 0.0
        return df.iloc[0:0]

    df["Turnout_Z_Score"] = zscore(df["Turnout_Pct"])
    outliers = df[df["Turnout_Z_Score"].abs() > 3]
    return outliers.sort_values(by="Turnout_Z_Score", ascending=False)


# ---------------------------------------------------------------------------
# 3. Isolation Forest
# ---------------------------------------------------------------------------
def calculate_isolation_forest(df_units: pd.DataFrame) -> pd.DataFrame:
    """
    Multivariate anomaly detection on:
        Turnout_Pct, Invalid_Pct, No_Vote_Pct.
    """
    df = df_units.dropna(subset=["Turnout_Pct", "Invalid_Pct", "No_Vote_Ballots"]).copy()

    # No-vote percentage (no inplace fillna -> safe under Copy-on-Write)
    df["No_Vote_Pct"] = (
        df["No_Vote_Ballots"] / df["Used_Ballots"].replace(0, np.nan) * 100
    ).fillna(0)

    if len(df) < 10:
        return df.iloc[0:0][[
            "Unit_ID", "Subdistrict", "Turnout_Pct",
            "Invalid_Pct", "No_Vote_Pct",
        ]].assign(Anomaly_Severity=[])

    features = ["Turnout_Pct", "Invalid_Pct", "No_Vote_Pct"]
    clf = IsolationForest(n_estimators=100, contamination=0.02, random_state=42)
    df["Anomaly_Score"]    = clf.fit_predict(df[features])
    df["Anomaly_Severity"] = clf.decision_function(df[features])  # lower = more anomalous

    anomalies = (
        df[df["Anomaly_Score"] == -1]
        .sort_values(by="Anomaly_Severity")
    )
    return anomalies[[
        "Unit_ID", "Subdistrict", "Turnout_Pct",
        "Invalid_Pct", "No_Vote_Pct", "Anomaly_Severity",
    ]]


# ---------------------------------------------------------------------------
# 4. Benford's Law
# ---------------------------------------------------------------------------
def calculate_benfords_law(df_scores: pd.DataFrame):
    """First-digit distribution + chi-square p-value vs Benford's Law."""
    valid = df_scores[df_scores["Score"] > 0].copy()
    if valid.empty:
        digits = np.arange(1, 10)
        empty = pd.DataFrame({
            "Digit": digits,
            "Expected_Pct": np.log10(1 + 1 / digits) * 100,
            "Observed_Pct": np.zeros(9),
        })
        return empty, 1.0

    valid["First_Digit"] = valid["Score"].astype(str).str[0].astype(int)
    valid = valid[valid["First_Digit"].between(1, 9)]

    observed_counts = valid["First_Digit"].value_counts().sort_index()
    digits          = np.arange(1, 10)
    observed_counts = observed_counts.reindex(digits, fill_value=0)
    total           = int(observed_counts.sum())

    observed_pct = (observed_counts / total) * 100
    expected_pct = np.log10(1 + 1 / digits) * 100

    results = pd.DataFrame({
        "Digit":        digits,
        "Expected_Pct": expected_pct,
        "Observed_Pct": observed_pct.values,
    })

    expected_counts = (expected_pct / 100) * total
    _, p_val = chisquare(f_obs=observed_counts.values, f_exp=expected_counts)

    return results, float(p_val)


# ---------------------------------------------------------------------------
# 5. Symmetric vote-buying (Double-X)
# ---------------------------------------------------------------------------
def detect_symmetric_vote_buying(df_party: pd.DataFrame,
                                 df_const: pd.DataFrame) -> pd.DataFrame:
    """
    'Double-X' (กาเบอร์เดียวกัน) detector.

    Cross-references constituency winners with party-list scores at the same
    polling unit; flags units where the winning constituency candidate's
    *number* matches a party-list party number AND that party shows an
    abnormally high vote spike (Z-score on the per-party distribution).
    """
    if df_party.empty or df_const.empty:
        return pd.DataFrame()

    df_p = df_party.copy()
    df_c = df_const.copy()

    # Strip ballot tag so PARTY/CONST unit IDs become comparable
    df_p["Merge_ID"] = (
        df_p["Unit_ID"]
        .str.replace("_PARTY", "", regex=False)
        .str.replace("_CONST", "", regex=False)
    )
    df_c["Merge_ID"] = (
        df_c["Unit_ID"]
        .str.replace("_PARTY", "", regex=False)
        .str.replace("_CONST", "", regex=False)
    )

    # Top constituency candidate per unit
    top_const = (
        df_c.sort_values(["Merge_ID", "Score"], ascending=[True, False])
        .drop_duplicates("Merge_ID")
        [["Merge_ID", "Entity_Number", "Entity_Name"]]
        .rename(columns={
            "Entity_Number": "Candidate_Number",
            "Entity_Name":   "Candidate_Name",
        })
    )

    # Per-party Z-score on raw vote counts
    df_p["Party_Mean"] = df_p.groupby("Entity_Number")["Score"].transform("mean")
    df_p["Party_Std"]  = (
        df_p.groupby("Entity_Number")["Score"]
        .transform("std")
        .replace(0, np.nan)
    )
    df_p["Party_Spike_Z_Score"] = (df_p["Score"] - df_p["Party_Mean"]) / df_p["Party_Std"]

    merged = pd.merge(df_p, top_const, on="Merge_ID", how="inner")

    matched = merged[merged["Entity_Number"] == merged["Candidate_Number"]].copy()
    matched = matched.sort_values(by="Party_Spike_Z_Score", ascending=False)

    matched = matched.rename(columns={
        "Entity_Number": "Party_Number",
        "Entity_Name":   "Party_Name",
    })

    return matched[[
        "Unit_ID", "Party_Name", "Party_Number",
        "Candidate_Name", "Score", "Party_Spike_Z_Score",
    ]]
