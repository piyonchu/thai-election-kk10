"""Load and flatten Khon Kaen Constituency 10 ballot JSONs into tidy DataFrames.

Two ballot trees are read:
  data/aomsin_result/bch/...     — party-list ballots (ส.ส. ๕/๑๘ บช)
  data/aomsin_result/normal/...  — constituency MP ballots (ส.ส. ๕/๑๘)

Returned tables (long-form, joinable on Unit_ID):

  units_bch       — one row per polling unit, party-list ballot stats
  party_scores    — (Unit_ID, Party_Number, Party_Name, Score)
  units_normal    — one row per polling unit, constituency ballot stats
  candidate_scores — (Unit_ID, Candidate_Number, Score)

Absentee/out-of-area ballots (the "ในนอกนอกราช" pseudo-ตำบล — in-district +
out-of-district + overseas advance votes) are tagged with Is_Absentee=True and
relabeled to ABSENTEE_LABEL. They have no geographic location, so the map page
filters them out, but they are still counted in every vote total.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.parties import party_name

REPO_ROOT = Path(__file__).resolve().parents[1]
BCH_DIR = REPO_ROOT / "data" / "aomsin_result" / "bch"
NORMAL_DIR = REPO_ROOT / "data" / "aomsin_result" / "normal"
COORDS_CSV = REPO_ROOT / "data" / "location_coordinates_template.csv"

# OCR'd/raw labels that mean "advance/absentee/overseas" rather than a real ตำบล.
_ABSENTEE_RAW = {"ในนอกนอกราช"}
ABSENTEE_LABEL = "[นอกเขต/นอกราชอาณาจักร]"


def _is_absentee_subdistrict(sub: str) -> bool:
    if sub in _ABSENTEE_RAW:
        return True
    # Defensive: anything mentioning both นอก and ราช is the overseas/absentee bucket.
    return ("นอก" in sub) and ("ราช" in sub)


def _unit_id(district: str, subdistrict: str, village: str, unit: str) -> str:
    return f"KK10|{district}|{subdistrict}|M{village}|U{unit}"


def _parse_unit(data: dict, filepath: Path) -> dict:
    g = data.get("ข้อมูลทั่วไป", {})
    voters = data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}) or {}
    ballots = data.get("จำนวนบัตรเลือกตั้ง", {}) or {}
    district = g.get("อำเภอ_เขต", "")
    sub_raw = g.get("ตำบล_แขวง_เทศบาล", "")
    moo = str(g.get("หมู่ที่", ""))
    no = str(g.get("หน่วยเลือกตั้งที่", ""))

    is_absentee = _is_absentee_subdistrict(sub_raw)
    if is_absentee:
        # Pull the ชุด (set) number out of filenames like กนค_ชุด10_เขต10.json so each
        # absentee batch becomes its own logical "unit" instead of colliding.
        m = re.search(r"ชุด\s*(\d+)", filepath.name)
        set_no = m.group(1) if m else filepath.stem
        sub = ABSENTEE_LABEL
        unit_id = f"KK10|ABSENTEE|set{set_no}"
        moo = ""
        no = f"set{set_no}"
    else:
        sub = sub_raw
        unit_id = _unit_id(district, sub, moo, no)

    return {
        "Unit_ID": unit_id,
        "District": district,
        "Subdistrict": sub,
        "Village_No": moo,
        "Unit_No": no,
        "Is_Absentee": is_absentee,
        "Eligible_Voters": voters.get("จำนวนผู้มีสิทธิเลือกตั้งตามบัญชีรายชื่อ"),
        "Voters_Showed_Up": voters.get("จำนวนผู้มีสิทธิเลือกตั้งที่มาแสดงตน"),
        "Allocated_Ballots": ballots.get("จำนวนบัตรเลือกตั้งที่ได้รับจัดสรร"),
        "Used_Ballots": ballots.get("จำนวนบัตรเลือกตั้งที่ใช้"),
        "Valid_Ballots": ballots.get("บัตรดี"),
        "Invalid_Ballots": ballots.get("บัตรเสีย"),
        "No_Vote_Ballots": (
            ballots.get("บัตรที่ไม่เลือกบัญชีรายชื่อของพรรคการเมืองใด")
            if "บัตรที่ไม่เลือกบัญชีรายชื่อของพรรคการเมืองใด" in ballots
            else ballots.get("บัตรที่ไม่เลือกผู้สมัครใด")
        ),
        "Total_Score": data.get("รวมคะแนนทั้งสิ้น"),
    }


def _walk_bch(root: Path):
    units, scores = [], []
    for fp in root.rglob("*.json"):
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        u = _parse_unit(d, fp)
        units.append(u)
        for s in d.get("ผลคะแนนพรรค", []) or []:
            no = s.get("หมายเลขบัญชีรายชื่อของพรรคการเมือง")
            if no is None:
                continue
            scores.append(
                {
                    "Unit_ID": u["Unit_ID"],
                    "District": u["District"],
                    "Subdistrict": u["Subdistrict"],
                    "Is_Absentee": u["Is_Absentee"],
                    "Party_Number": int(no),
                    "Party_Name": party_name(no),
                    "Score": s.get("คะแนน") or 0,
                }
            )
    return pd.DataFrame(units), pd.DataFrame(scores)


def _walk_normal(root: Path):
    units, scores = [], []
    for fp in root.rglob("*.json"):
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        u = _parse_unit(d, fp)
        units.append(u)
        for s in d.get("ผลคะแนน", []) or []:
            no = s.get("หมายเลขประจำตัวผู้สมัคร")
            if no is None:
                continue
            scores.append(
                {
                    "Unit_ID": u["Unit_ID"],
                    "District": u["District"],
                    "Subdistrict": u["Subdistrict"],
                    "Is_Absentee": u["Is_Absentee"],
                    "Candidate_Number": int(no),
                    "Score": s.get("คะแนน") or 0,
                }
            )
    return pd.DataFrame(units), pd.DataFrame(scores)


def _attach_coords(df: pd.DataFrame, coords: pd.DataFrame) -> pd.DataFrame:
    if df.empty or coords.empty:
        return df
    return df.merge(
        coords.rename(columns={"อำเภอ": "District", "ตำบล": "Subdistrict"}),
        on=["District", "Subdistrict"],
        how="left",
    )


@st.cache_data(show_spinner="Loading ballot JSONs…")
def load_data():
    coords = (
        pd.read_csv(COORDS_CSV)
        if COORDS_CSV.exists()
        else pd.DataFrame(columns=["อำเภอ", "ตำบล", "Latitude", "Longitude"])
    )

    units_bch = pd.DataFrame()
    party_scores = pd.DataFrame()
    if BCH_DIR.exists():
        units_bch, party_scores = _walk_bch(BCH_DIR)
        units_bch = _attach_coords(units_bch, coords)

    units_normal = pd.DataFrame()
    candidate_scores = pd.DataFrame()
    if NORMAL_DIR.exists():
        units_normal, candidate_scores = _walk_normal(NORMAL_DIR)
        units_normal = _attach_coords(units_normal, coords)

    return units_bch, party_scores, units_normal, candidate_scores


def absentee_summary(scores: pd.DataFrame, label_col: str) -> dict:
    """Headline stats for the [นอกเขต/นอกราชอาณาจักร] block.

    Returns {} if no absentee rows are present.
    """
    if scores.empty or "Is_Absentee" not in scores.columns:
        return {}
    abs_df = scores[scores["Is_Absentee"]]
    if abs_df.empty:
        return {}
    total_abs = int(abs_df["Score"].sum())
    total_all = int(scores["Score"].sum())
    by_label = (
        abs_df.groupby(label_col, as_index=False)["Score"]
        .sum()
        .rename(columns={"Score": "Votes"})
        .sort_values("Votes", ascending=False)
        .reset_index(drop=True)
    )
    by_label["Share_in_absentee"] = (
        by_label["Votes"] / total_abs * 100 if total_abs else 0
    )
    overall = (
        scores.groupby(label_col, as_index=False)["Score"].sum().set_index(label_col)["Score"]
    )
    by_label["Share_overall"] = by_label[label_col].map(
        lambda n: (overall.get(n, 0) / total_all * 100) if total_all else 0
    )
    return {
        "total_votes": total_abs,
        "share_of_total": (total_abs / total_all * 100) if total_all else 0,
        "n_sets": int(abs_df["Unit_ID"].nunique()),
        "breakdown": by_label,
    }


def party_totals(party_scores: pd.DataFrame) -> pd.DataFrame:
    """Sum votes across all units, per party. Sorted desc."""
    if party_scores.empty:
        return pd.DataFrame(columns=["Party_Name", "Votes", "Share"])
    t = (
        party_scores.groupby("Party_Name", as_index=False)["Score"]
        .sum()
        .rename(columns={"Score": "Votes"})
        .sort_values("Votes", ascending=False)
        .reset_index(drop=True)
    )
    total = t["Votes"].sum()
    t["Share"] = t["Votes"] / total * 100 if total else 0
    return t


def candidate_totals(candidate_scores: pd.DataFrame) -> pd.DataFrame:
    if candidate_scores.empty:
        return pd.DataFrame(columns=["Candidate_Number", "Votes", "Share"])
    t = (
        candidate_scores.groupby("Candidate_Number", as_index=False)["Score"]
        .sum()
        .rename(columns={"Score": "Votes"})
        .sort_values("Votes", ascending=False)
        .reset_index(drop=True)
    )
    total = t["Votes"].sum()
    t["Share"] = t["Votes"] / total * 100 if total else 0
    return t


def winner_by_subdistrict(
    scores: pd.DataFrame, label_col: str, include_absentee: bool = False
) -> pd.DataFrame:
    """For each (District, Subdistrict): winner, runner-up, vote totals, margin pp.

    Absentee/out-of-area votes (Is_Absentee=True) are excluded by default since
    they are not tied to any geographic ตำบล. Pass include_absentee=True to keep
    them as a separate row labeled `[นอกเขต/นอกราชอาณาจักร]`.
    """
    if scores.empty:
        return pd.DataFrame()
    src = scores if include_absentee else scores[~scores.get("Is_Absentee", False)]
    if src.empty:
        return pd.DataFrame()
    agg = (
        src.groupby(["District", "Subdistrict", label_col], as_index=False)["Score"]
        .sum()
        .rename(columns={"Score": "Votes"})
    )
    agg = agg.sort_values(["District", "Subdistrict", "Votes"], ascending=[True, True, False])
    rows = []
    for (d, s), grp in agg.groupby(["District", "Subdistrict"]):
        total = grp["Votes"].sum()
        if total == 0 or len(grp) == 0:
            continue
        first = grp.iloc[0]
        second = grp.iloc[1] if len(grp) > 1 else None
        rows.append(
            {
                "District": d,
                "Subdistrict": s,
                "Total_Votes": int(total),
                "Winner": first[label_col],
                "Winner_Votes": int(first["Votes"]),
                "Winner_Share": first["Votes"] / total * 100,
                "Runner_Up": (second[label_col] if second is not None else None),
                "Runner_Up_Votes": int(second["Votes"]) if second is not None else 0,
                "Margin_pp": (
                    (first["Votes"] - second["Votes"]) / total * 100
                    if second is not None
                    else 100.0
                ),
            }
        )
    return pd.DataFrame(rows)
