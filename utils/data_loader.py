"""
Data loader for the Thai election dashboard.

Reads the raw wide-format CSVs produced by the OCR / extraction pipeline:
    data/result/bch_results.csv      (Party List - บัญชีรายชื่อ)
    data/result/normal_results.csv   (Constituency - เขต)

and reshapes them into the long-format ``df_units`` / ``df_scores`` schema
that the rest of the application (Election Overview, Anomaly Detection)
already expects.

This removes the dependency on the previously generated
``data_cleaned_*.csv`` files.
"""

from __future__ import annotations

import json
import os
import re

import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_FILE   = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_FILE))   # .../thai-election-kk10
_RESULT_DIR  = os.path.join(_PROJECT_ROOT, "data", "result")
_MAPS_DIR    = os.path.join(_RESULT_DIR, "maps")

BCH_CSV    = os.path.join(_RESULT_DIR, "bch_results.csv")
NORMAL_CSV = os.path.join(_RESULT_DIR, "normal_results.csv")


# ---------------------------------------------------------------------------
# Name maps
# ---------------------------------------------------------------------------
def _load_json_map(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_PARTY_MAP:     dict = _load_json_map(os.path.join(_MAPS_DIR, "party_map.json"))
_CANDIDATE_MAP: dict = _load_json_map(os.path.join(_MAPS_DIR, "candidate_map.json"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_int(v) -> int:
    """Convert to int, treating NaN as 0."""
    try:
        if pd.isna(v):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def _build_unit_id(row: pd.Series, tag: str) -> str:
    """
    Produce a stable Unit_ID, e.g.  KK10_PARTY_ปอแดง_M3_U3
    The CONST/PARTY tag lets ``detect_symmetric_vote_buying`` strip it
    and merge across the two ballot types.
    """
    dist = _safe_int(row.get("เขตเลือกตั้งที่"))
    muu  = _safe_int(row.get("หมู่ที่"))
    unit = _safe_int(row.get("หน่วยเลือกตั้งที่"))
    sub  = str(row.get("ตำบล_แขวง_เทศบาล", "")).strip()
    return f"KK{dist}_{tag}_{sub}_M{muu}_U{unit}"


def _score_columns(df: pd.DataFrame, prefix: str) -> list[str]:
    """All score columns matching ``prefix``, sorted by their numeric suffix."""
    return sorted(
        [c for c in df.columns if c.startswith(prefix)],
        key=lambda c: int(re.search(r"\d+", c).group()),
    )


def _entity_number(col: str) -> int:
    return int(re.search(r"\d+", col).group())


# ---------------------------------------------------------------------------
# Per-mode reshapers
# ---------------------------------------------------------------------------
def _entity_name_from_map(num: int, name_map: dict, fallback_label: str) -> str:
    """Resolve a human-readable name from a JSON lookup map."""
    entry = name_map.get(str(num))
    if entry is None:
        return f"{fallback_label} {num}"
    if isinstance(entry, dict):
        name  = entry.get("ชื่อ_สกุล", "")
        party = entry.get("พรรค", "")
        if name and party:
            return f"{name} ({party})"
        return name or f"{fallback_label} {num}"
    return str(entry)


def _reshape(
    raw_path: str,
    score_prefix: str,
    no_vote_col: str,
    unit_tag: str,
    entity_label: str,
    name_map: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read one wide-format CSV (party-list or constituency) and return
    ``(df_units, df_scores)`` in the long-format the dashboard uses.
    """
    raw = pd.read_csv(raw_path)

    # Drop only true header artefacts (rows with no tambon name).
    # Rows with a valid tambon but no unit number are กนค (out-of-district)
    # ballots that must be kept so the district totals are complete.
    raw = raw.dropna(subset=["ตำบล_แขวง_เทศบาล"]).reset_index(drop=True).copy()

    # ----- Unit_ID ---------------------------------------------------------
    # Regular rows use the standard scheme; กนค rows (no unit number) get a
    # unique GNC-prefixed ID so they don't collapse into one another.
    has_unit = raw["หน่วยเลือกตั้งที่"].notna()
    raw["Unit_ID"] = None
    raw.loc[has_unit, "Unit_ID"] = raw[has_unit].apply(
        lambda r: _build_unit_id(r, unit_tag), axis=1
    )
    raw.loc[~has_unit, "Unit_ID"] = raw[~has_unit].apply(
        lambda r: (
            f"KK{_safe_int(r.get('เขตเลือกตั้งที่'))}_{unit_tag}_"
            f"{str(r.get('ตำบล_แขวง_เทศบาล', '')).strip()}_GNC{r.name}"
        ),
        axis=1,
    )

    # ----- df_units --------------------------------------------------------
    df_units = pd.DataFrame({
        "Unit_ID":          raw["Unit_ID"],
        "District":         raw["อำเภอ_เขต"],
        "Subdistrict":      raw["ตำบล_แขวง_เทศบาล"],
        "Eligible_Voters":  pd.to_numeric(raw["ผู้มีสิทธิตามบัญชี"], errors="coerce"),
        "Voters_Showed_Up": pd.to_numeric(raw["ผู้มาแสดงตน"],         errors="coerce"),
        "Used_Ballots":     pd.to_numeric(raw["บัตรที่ใช้"],          errors="coerce"),
        "Valid_Ballots":    pd.to_numeric(raw["บัตรดี"],              errors="coerce"),
        "Invalid_Ballots":  pd.to_numeric(raw["บัตรเสีย"],            errors="coerce"),
        "No_Vote_Ballots":  pd.to_numeric(raw[no_vote_col],            errors="coerce"),
    })

    # Derived percentages (used everywhere downstream)
    df_units["Turnout_Pct"] = (
        df_units["Voters_Showed_Up"]
        / df_units["Eligible_Voters"].replace(0, np.nan)
    ) * 100
    df_units["Invalid_Pct"] = (
        df_units["Invalid_Ballots"]
        / df_units["Used_Ballots"].replace(0, np.nan)
    ) * 100

    # ----- df_scores (wide → long) ----------------------------------------
    score_cols = _score_columns(raw, score_prefix)
    long_df = raw[["Unit_ID", "อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"] + score_cols].melt(
        id_vars=["Unit_ID", "อำเภอ_เขต", "ตำบล_แขวง_เทศบาล"],
        value_vars=score_cols,
        var_name="_score_col",
        value_name="Score",
    )
    long_df["Entity_Number"] = long_df["_score_col"].map(_entity_number)
    if name_map:
        long_df["Entity_Name"] = long_df["Entity_Number"].map(
            lambda n: _entity_name_from_map(n, name_map, entity_label)
        )
    else:
        long_df["Entity_Name"] = entity_label + " " + long_df["Entity_Number"].astype(str)
    long_df["Score"]         = pd.to_numeric(long_df["Score"], errors="coerce").fillna(0).astype(int)
    long_df = long_df.rename(columns={
        "อำเภอ_เขต":         "District",
        "ตำบล_แขวง_เทศบาล": "Subdistrict",
    })

    df_scores = long_df[
        ["Unit_ID", "District", "Subdistrict", "Entity_Number", "Entity_Name", "Score"]
    ].reset_index(drop=True)

    return df_units, df_scores


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(election_type: str = "Party List"):
    """
    Returns ``(df_units, df_scores, df_merged)``.

    ``df_units``  — one row per polling unit, with English-named columns the
                    dashboard expects (Eligible_Voters, Voters_Showed_Up,
                    Used_Ballots, Valid_Ballots, Invalid_Ballots,
                    No_Vote_Ballots, Turnout_Pct, Invalid_Pct).
    ``df_scores`` — long format: one row per (Unit_ID, Entity_Number).
    ``df_merged`` — df_scores left-joined with df_units on Unit_ID.
    """
    try:
        if election_type == "Constituency":
            df_units, df_scores = _reshape(
                raw_path=NORMAL_CSV,
                score_prefix="คะแนน_ผู้สมัคร_",
                no_vote_col="บัตรไม่เลือกผู้สมัครใด",
                unit_tag="CONST",
                entity_label="ผู้สมัครหมายเลข",
                name_map=_CANDIDATE_MAP,
            )
        else:  # "Party List"
            df_units, df_scores = _reshape(
                raw_path=BCH_CSV,
                score_prefix="คะแนน_พรรค_",
                no_vote_col="บัตรไม่เลือกพรรคใด",
                unit_tag="PARTY",
                entity_label="พรรคหมายเลข",
                name_map=_PARTY_MAP,
            )

        df_merged = pd.merge(df_scores, df_units, on="Unit_ID",
                             how="left", suffixes=("", "_unit"))

        return df_units, df_scores, df_merged

    except FileNotFoundError as e:
        st.error(
            f"Data file not found: `{e.filename}`.\n"
            f"Expected CSVs in `{_RESULT_DIR}` "
            "(`bch_results.csv` and `normal_results.csv`)."
        )
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    except Exception as e:                          # noqa: BLE001
        st.error(f"Failed to load election data: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


@st.cache_data(show_spinner=False)
def get_winner_per_unit(df_merged: pd.DataFrame) -> pd.DataFrame:
    """
    Highest-scoring entity per polling unit. Latitude / Longitude are kept
    only if they exist in ``df_merged`` so callers without spatial data
    don't break.
    """
    if df_merged.empty:
        return df_merged

    winners = (
        df_merged.sort_values("Score", ascending=False)
        .drop_duplicates(["Unit_ID"])
    )
    cols = ["Unit_ID", "Entity_Name", "Score", "District", "Subdistrict"]
    for opt in ("Latitude", "Longitude"):
        if opt in winners.columns:
            cols.append(opt)
    return winners[cols]
