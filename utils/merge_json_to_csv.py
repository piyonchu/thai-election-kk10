from __future__ import annotations

import csv
import json
import os
from glob import glob
from typing import Any

# ---------------------------------------------------------------------------
# Paths — mirror the app's layout
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)        # adjust if you place this elsewhere
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

BCH_BASE = os.path.join(DATA_DIR, "result", "bch", "เขตเลือกตั้งที่10")
NORMAL_BASE = os.path.join(DATA_DIR, "result", "normal", "เขตเลือกตั้งที่10")

OUTPUT_DIR = os.path.join(DATA_DIR, "result")
BCH_CSV = os.path.join(OUTPUT_DIR, "bch_results.csv")
NORMAL_CSV = os.path.join(OUTPUT_DIR, "normal_results.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_json_files(base: str) -> list[str]:
    """Recursively find every .json under base."""
    if not os.path.isdir(base):
        return []
    return sorted(glob(os.path.join(base, "**", "*.json"), recursive=True))


def safe_get(d: dict, *keys, default: Any = "") -> Any:
    """Walk nested dict keys, returning default if any step is missing."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def is_bch(record: dict) -> bool:
    """Detect a BCH (party-list) record."""
    form = str(record.get("แบบฟอร์ม", ""))
    if "(บช)" in form or "บช" in form:
        return True
    # Fallback: structural detection
    return "ผลคะแนนพรรค" in record


def base_row(record: dict, source_path: str) -> dict:
    """Common columns shared by both CSVs."""
    info = record.get("ข้อมูลทั่วไป", {}) or {}
    voters = record.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}) or {}
    ballots = record.get("จำนวนบัตรเลือกตั้ง", {}) or {}

    return {
        "source_file": os.path.relpath(source_path, DATA_DIR) if source_path.startswith(DATA_DIR) else source_path,
        "filepath_in_json": record.get("filepath", ""),
        "แบบฟอร์ม": record.get("แบบฟอร์ม", ""),
        "จังหวัด": info.get("จังหวัด", ""),
        "เขตเลือกตั้งที่": info.get("เขตเลือกตั้งที่", ""),
        "อำเภอ_เขต": info.get("อำเภอ_เขต", ""),
        "ตำบล_แขวง_เทศบาล": info.get("ตำบล_แขวง_เทศบาล", ""),
        "หมู่ที่": info.get("หมู่ที่", ""),
        "หน่วยเลือกตั้งที่": info.get("หน่วยเลือกตั้งที่", ""),
        "ผู้มีสิทธิตามบัญชี": voters.get("จำนวนผู้มีสิทธิเลือกตั้งตามบัญชีรายชื่อ", ""),
        "ผู้มาแสดงตน": voters.get("จำนวนผู้มีสิทธิเลือกตั้งที่มาแสดงตน", ""),
        "บัตรที่ได้รับจัดสรร": ballots.get("จำนวนบัตรเลือกตั้งที่ได้รับจัดสรร", ""),
        "บัตรที่ใช้": ballots.get("จำนวนบัตรเลือกตั้งที่ใช้", ""),
        "บัตรดี": ballots.get("บัตรดี", ""),
        "บัตรเสีย": ballots.get("บัตรเสีย", ""),
        "บัตรที่เหลือ": ballots.get("จำนวนบัตรเลือกตั้งที่เหลือ", ""),
        "รวมคะแนนทั้งสิ้น": record.get("รวมคะแนนทั้งสิ้น", ""),
    }


def parse_bch(record: dict, source_path: str) -> tuple[dict, dict[int, int]]:
    """Return (base_row_with_bch_extras, {party_no: score})."""
    row = base_row(record, source_path)
    ballots = record.get("จำนวนบัตรเลือกตั้ง", {}) or {}
    row["บัตรไม่เลือกพรรคใด"] = ballots.get("บัตรที่ไม่เลือกบัญชีรายชื่อของพรรคการเมืองใด", "")

    scores: dict[int, int] = {}
    for item in record.get("ผลคะแนนพรรค", []) or []:
        no = item.get("หมายเลขบัญชีรายชื่อของพรรคการเมือง")
        pts = item.get("คะแนน")
        if isinstance(no, int):
            scores[no] = pts if isinstance(pts, int) else 0
    return row, scores


def parse_normal(record: dict, source_path: str) -> tuple[dict, dict[int, int]]:
    """Return (base_row_with_normal_extras, {candidate_no: score})."""
    row = base_row(record, source_path)
    ballots = record.get("จำนวนบัตรเลือกตั้ง", {}) or {}
    row["บัตรไม่เลือกผู้สมัครใด"] = ballots.get("บัตรที่ไม่เลือกผู้สมัครใด", "")

    scores: dict[int, int] = {}
    for item in record.get("ผลคะแนน", []) or []:
        no = item.get("หมายเลขประจำตัวผู้สมัคร")
        pts = item.get("คะแนน")
        if isinstance(no, int):
            scores[no] = pts if isinstance(pts, int) else 0
    return row, scores


def write_csv(
    out_path: str,
    rows: list[dict],
    score_maps: list[dict[int, int]],
    score_col_prefix: str,
) -> None:
    """
    Write a wide CSV. Score columns are sorted numerically and appended after
    the base columns, so every row gets the same column for the same number.
    """
    if not rows:
        print(f"  (no records — skipping {out_path})")
        return

    all_numbers = sorted({n for m in score_maps for n in m.keys()})
    score_cols = [f"{score_col_prefix}{n}" for n in all_numbers]

    base_cols = list(rows[0].keys())
    fieldnames = base_cols + score_cols

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row, scores in zip(rows, score_maps):
            full = dict(row)
            for n in all_numbers:
                full[f"{score_col_prefix}{n}"] = scores.get(n, 0)
            writer.writerow(full)

    print(f"  wrote {len(rows)} rows → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def collect(base: str, kind: str) -> tuple[list[dict], list[dict[int, int]]]:
    """
    Walk a base folder and parse every JSON. `kind` is "bch" or "normal" and
    determines which parser is preferred, but the form code is checked too:
    a misfiled JSON (e.g. a normal file under bch/) is logged as a warning
    and parsed according to its actual form, so it lands in the right CSV.
    """
    rows: list[dict] = []
    scores: list[dict[int, int]] = []
    skipped: list[tuple[str, str]] = []

    for path in find_json_files(base):
        try:
            with open(path, encoding="utf-8") as f:
                record = json.load(f)
        except Exception as e:
            skipped.append((path, f"read/parse error: {e}"))
            continue

        actual_is_bch = is_bch(record)
        expected_is_bch = kind == "bch"

        if actual_is_bch != expected_is_bch:
            skipped.append((
                path,
                f"form mismatch (folder={kind}, file looks like {'bch' if actual_is_bch else 'normal'})",
            ))
            continue

        if actual_is_bch:
            row, sc = parse_bch(record, path)
        else:
            row, sc = parse_normal(record, path)
        rows.append(row)
        scores.append(sc)

    if skipped:
        print(f"  warnings under {base}:")
        for p, why in skipped:
            print(f"    - {p}: {why}")

    return rows, scores


def main() -> None:
    print(f"DATA_DIR    = {DATA_DIR}")
    print(f"BCH_BASE    = {BCH_BASE}")
    print(f"NORMAL_BASE = {NORMAL_BASE}")
    print()

    print("Scanning BCH (party-list) JSON files…")
    bch_rows, bch_scores = collect(BCH_BASE, kind="bch")
    write_csv(BCH_CSV, bch_rows, bch_scores, score_col_prefix="คะแนน_พรรค_")
    print()

    print("Scanning Normal (constituency) JSON files…")
    norm_rows, norm_scores = collect(NORMAL_BASE, kind="normal")
    write_csv(NORMAL_CSV, norm_rows, norm_scores, score_col_prefix="คะแนน_ผู้สมัคร_")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
