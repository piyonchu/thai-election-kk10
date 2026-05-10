import streamlit as st
import json
import os
import pandas as pd

st.set_page_config(layout="wide", page_title="ผลการเลือกตั้ง เขตเลือกตั้งที่ 10")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # go up from pages/ to repo root
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PDF_BASE = os.path.join(DATA_DIR, "เขตเลือกตั้งที่10")
BCH_BASE = os.path.join(DATA_DIR, "aomsin_result", "bch", "เขตเลือกตั้งที่10")
NORMAL_BASE = os.path.join(DATA_DIR, "aomsin_result", "normal", "เขตเลือกตั้งที่10")


@st.cache_data
def build_index():
    index = []
    for dirpath, _, filenames in os.walk(BCH_BASE):
        for fname in filenames:
            if not fname.endswith(".json"):
                continue
            json_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(json_path, BCH_BASE)
            parts = rel.split(os.sep)
            if len(parts) == 3:
                district, sub_district, _ = parts
                stem = os.path.splitext(fname)[0]
                index.append({
                    "district": district,
                    "sub_district": sub_district,
                    "unit": stem,
                    "pdf_path": os.path.join(PDF_BASE, district, sub_district, stem + ".pdf"),
                    "bch_path": json_path,
                    "normal_path": os.path.join(NORMAL_BASE, district, sub_district, fname),
                })
    return sorted(index, key=lambda x: (x["district"], x["sub_district"], x["unit"]))


def render_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        st.warning(f"ไม่พบไฟล์ PDF: {os.path.basename(pdf_path)}")
        return
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    st.pdf(pdf_bytes, height=820)
    st.download_button(
        label="ดาวน์โหลด PDF",
        data=pdf_bytes,
        file_name=os.path.basename(pdf_path),
        mime="application/pdf",
    )


def save_json(path, data):
    """Write JSON back to disk, preserving Thai characters."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


def coerce_int(value, fallback=0):
    """Best-effort conversion to int (JSON numeric fields)."""
    if value is None or value == "":
        return fallback
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return fallback


def to_int_or_none(value):
    """Like coerce_int, but returns None if value isn't a valid number.
    Used by the corruption checker so missing fields don't false-flag."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None


def lookup_dict_value(d, candidate_keys):
    """Return the first matching value from a dict given several possible key names.
    OCR may produce slight key variations, so we try a few."""
    if not isinstance(d, dict):
        return None
    for k in candidate_keys:
        if k in d:
            return d[k]
    return None


# --- Corruption / sanity checks -----------------------------------------------

# Possible OCR variants for the same logical key
KEY_GOOD_BALLOTS = ["บัตรดี"]
KEY_BAD_BALLOTS = ["บัตรเสีย"]
KEY_NO_VOTE_BALLOTS = ["บัตรไม่เลือกผู้สมัครใด", "บัตรไม่เลือกผู้สมัคร", "บัตรไม่ประสงค์ลงคะแนน"]
KEY_USED_BALLOTS = ["บัตรที่ใช้ลงคะแนน", "จำนวนบัตรที่ใช้ลงคะแนน"]
KEY_ELIGIBLE = ["จำนวนผู้มีสิทธิเลือกตั้งทั้งหมด", "ผู้มีสิทธิเลือกตั้งทั้งหมด", "ผู้มีสิทธิเลือกตั้ง"]
KEY_TURNOUT = ["จำนวนผู้มาใช้สิทธิเลือกตั้ง", "ผู้มาใช้สิทธิเลือกตั้ง", "ผู้มาแสดงตน"]


def check_normal(path):
    """Return list of issues found in a 'normal' (candidate) JSON file."""
    issues = []
    if not os.path.exists(path):
        return issues
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"อ่านไฟล์ไม่ได้: {e}"]

    ballot = data.get("จำนวนบัตรเลือกตั้ง", {}) or {}
    voter = data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}) or {}

    good = to_int_or_none(lookup_dict_value(ballot, KEY_GOOD_BALLOTS))
    bad = to_int_or_none(lookup_dict_value(ballot, KEY_BAD_BALLOTS))
    novote = to_int_or_none(lookup_dict_value(ballot, KEY_NO_VOTE_BALLOTS))
    used = to_int_or_none(lookup_dict_value(ballot, KEY_USED_BALLOTS))

    eligible = to_int_or_none(lookup_dict_value(voter, KEY_ELIGIBLE))
    turnout = to_int_or_none(lookup_dict_value(voter, KEY_TURNOUT))

    total = to_int_or_none(data.get("รวมคะแนนทั้งสิ้น"))
    candidates = data.get("ผลคะแนน", []) or []
    cand_sum = sum(coerce_int(c.get("คะแนน", 0)) for c in candidates)

    # 1) รวมคะแนนทั้งสิ้น == บัตรดี
    if total is not None and good is not None and total != good:
        issues.append(f"รวมคะแนนทั้งสิ้น ({total}) ≠ บัตรดี ({good})")

    # 2) Sum of candidate scores == รวมคะแนนทั้งสิ้น
    if total is not None and candidates and cand_sum != total:
        issues.append(f"ผลรวมคะแนนผู้สมัคร ({cand_sum}) ≠ รวมคะแนนทั้งสิ้น ({total})")

    # 3) บัตรดี + บัตรเสีย + บัตรไม่เลือกฯ == บัตรที่ใช้ลงคะแนน
    if all(v is not None for v in (good, bad, novote, used)):
        s = good + bad + novote
        if s != used:
            issues.append(f"บัตรดี+บัตรเสีย+บัตรไม่เลือก ({s}) ≠ บัตรที่ใช้ลงคะแนน ({used})")

    # 4) ผู้มาใช้สิทธิ <= ผู้มีสิทธิทั้งหมด
    if eligible is not None and turnout is not None and turnout > eligible:
        issues.append(f"ผู้มาใช้สิทธิ ({turnout}) > ผู้มีสิทธิทั้งหมด ({eligible})")

    # 5) ผู้มาใช้สิทธิ == บัตรที่ใช้ลงคะแนน
    if turnout is not None and used is not None and turnout != used:
        issues.append(f"ผู้มาใช้สิทธิ ({turnout}) ≠ บัตรที่ใช้ลงคะแนน ({used})")

    # 6) Negative numbers anywhere
    for label, v in (("บัตรดี", good), ("บัตรเสีย", bad), ("บัตรไม่เลือก", novote),
                     ("บัตรที่ใช้ลงคะแนน", used), ("รวมคะแนน", total)):
        if v is not None and v < 0:
            issues.append(f"{label} ติดลบ ({v})")

    return issues


def check_bch(path):
    """Return list of issues found in a 'bch' (party) JSON file."""
    issues = []
    if not os.path.exists(path):
        return issues
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"อ่านไฟล์ไม่ได้: {e}"]

    ballot = data.get("จำนวนบัตรเลือกตั้ง", {}) or {}
    voter = data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}) or {}

    good = to_int_or_none(lookup_dict_value(ballot, KEY_GOOD_BALLOTS))
    bad = to_int_or_none(lookup_dict_value(ballot, KEY_BAD_BALLOTS))
    novote = to_int_or_none(lookup_dict_value(ballot, KEY_NO_VOTE_BALLOTS))
    used = to_int_or_none(lookup_dict_value(ballot, KEY_USED_BALLOTS))
    eligible = to_int_or_none(lookup_dict_value(voter, KEY_ELIGIBLE))
    turnout = to_int_or_none(lookup_dict_value(voter, KEY_TURNOUT))

    parties = data.get("ผลคะแนนพรรค", []) or []
    party_sum = sum(coerce_int(p.get("คะแนน", p.get("คะคะแนน", 0))) for p in parties)

    # 1) Sum of party scores == บัตรดี
    if good is not None and parties and party_sum != good:
        issues.append(f"ผลรวมคะแนนพรรค ({party_sum}) ≠ บัตรดี ({good})")

    # 2) Ballot accounting
    if all(v is not None for v in (good, bad, novote, used)):
        s = good + bad + novote
        if s != used:
            issues.append(f"บัตรดี+บัตรเสีย+บัตรไม่เลือก ({s}) ≠ บัตรที่ใช้ลงคะแนน ({used})")

    if eligible is not None and turnout is not None and turnout > eligible:
        issues.append(f"ผู้มาใช้สิทธิ ({turnout}) > ผู้มีสิทธิทั้งหมด ({eligible})")

    if turnout is not None and used is not None and turnout != used:
        issues.append(f"ผู้มาใช้สิทธิ ({turnout}) ≠ บัตรที่ใช้ลงคะแนน ({used})")

    for label, v in (("บัตรดี", good), ("บัตรเสีย", bad), ("บัตรไม่เลือก", novote),
                     ("บัตรที่ใช้ลงคะแนน", used)):
        if v is not None and v < 0:
            issues.append(f"{label} ติดลบ ({v})")

    return issues


@st.cache_data
def compute_issues(_signature, bch_path, normal_path):
    """Cached per file-pair. _signature lets us bust cache when files change."""
    return {
        "bch": check_bch(bch_path),
        "normal": check_normal(normal_path),
    }


def files_signature(entry):
    """Mtime-based signature so cache invalidates when a file is saved."""
    sig = []
    for p in (entry["bch_path"], entry["normal_path"]):
        try:
            sig.append((p, os.path.getmtime(p)))
        except OSError:
            sig.append((p, None))
    return tuple(sig)


def get_issues(entry):
    return compute_issues(files_signature(entry), entry["bch_path"], entry["normal_path"])


# --- Editors ------------------------------------------------------------------

def edit_kv_dict(title, kv_dict, key_prefix):
    if not kv_dict:
        return kv_dict
    st.markdown(f"##### {title}")
    df = pd.DataFrame({"รายการ": list(kv_dict.keys()), "จำนวน": list(kv_dict.values())})
    edited = st.data_editor(
        df,
        key=key_prefix,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "รายการ": st.column_config.TextColumn("รายการ", disabled=True),
            "จำนวน": st.column_config.NumberColumn("จำนวน", step=1),
        },
    )
    return {row["รายการ"]: coerce_int(row["จำนวน"]) for _, row in edited.iterrows()}


def edit_bch(data, path):
    form_value = st.text_input("แบบฟอร์ม", value=str(data.get("แบบฟอร์ม", "")), key=f"bch_form_{path}")

    voter_edited = edit_kv_dict(
        "จำนวนผู้มีสิทธิเลือกตั้ง", data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}), key_prefix=f"bch_voter_{path}"
    )
    ballot_edited = edit_kv_dict(
        "จำนวนบัตรเลือกตั้ง", data.get("จำนวนบัตรเลือกตั้ง", {}), key_prefix=f"bch_ballot_{path}"
    )

    parties = data.get("ผลคะแนนพรรค", [])
    parties_edited = parties
    if parties:
        st.markdown("##### ผลคะแนนพรรค")
        rows = []
        for p in parties:
            rows.append({
                "หมายเลขพรรค": p.get("หมายเลขบัญชีรายชื่อของพรรคการเมือง", "-"),
                "คะแนน": p.get("คะแนน", p.get("คะคะแนน", 0)),
            })
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            key=f"bch_parties_{path}",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "หมายเลขพรรค": st.column_config.TextColumn("หมายเลขพรรค", disabled=True),
                "คะแนน": st.column_config.NumberColumn("คะแนน", step=1),
            },
        )
        parties_edited = []
        for original, (_, row) in zip(parties, edited.iterrows()):
            new_item = dict(original)
            score_key = "คะแนน" if "คะแนน" in original else ("คะคะแนน" if "คะคะแนน" in original else "คะแนน")
            new_item[score_key] = coerce_int(row["คะแนน"])
            parties_edited.append(new_item)

    if st.button("💾 บันทึกการแก้ไข (บช)", key=f"save_bch_{path}", type="primary"):
        new_data = dict(data)
        new_data["แบบฟอร์ม"] = form_value
        if "จำนวนผู้มีสิทธิเลือกตั้ง" in data:
            new_data["จำนวนผู้มีสิทธิเลือกตั้ง"] = voter_edited
        if "จำนวนบัตรเลือกตั้ง" in data:
            new_data["จำนวนบัตรเลือกตั้ง"] = ballot_edited
        if "ผลคะแนนพรรค" in data:
            new_data["ผลคะแนนพรรค"] = parties_edited

        ok, err = save_json(path, new_data)
        if ok:
            st.success(f"บันทึกแล้ว: {os.path.basename(path)}")
            st.cache_data.clear()
        else:
            st.error(f"บันทึกไม่สำเร็จ: {err}")

    with st.expander("ดูข้อมูล JSON ดิบ"):
        st.json(data)


def edit_normal(data, path):
    form_value = st.text_input("แบบฟอร์ม", value=str(data.get("แบบฟอร์ม", "")), key=f"norm_form_{path}")

    info = data.get("ข้อมูลทั่วไป", {})
    info_edited = info
    if info:
        st.markdown("##### ข้อมูลทั่วไป")
        info_edited = {}
        cols = st.columns(min(len(info), 3))
        for i, (k, v) in enumerate(info.items()):
            with cols[i % 3]:
                info_edited[k] = st.text_input(k, value=str(v), key=f"norm_info_{path}_{k}")

    voter_edited = edit_kv_dict(
        "จำนวนผู้มีสิทธิเลือกตั้ง", data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {}), key_prefix=f"norm_voter_{path}"
    )
    ballot_edited = edit_kv_dict(
        "จำนวนบัตรเลือกตั้ง", data.get("จำนวนบัตรเลือกตั้ง", {}), key_prefix=f"norm_ballot_{path}"
    )

    candidates = data.get("ผลคะแนน", [])
    candidates_edited = candidates
    if candidates:
        st.markdown("##### ผลคะแนนผู้สมัคร")
        rows = [
            {
                "หมายเลขผู้สมัคร": c.get("หมายเลขประจำตัวผู้สมัคร", "-"),
                "คะแนน": c.get("คะแนน", 0),
            }
            for c in candidates
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            key=f"norm_cands_{path}",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "หมายเลขผู้สมัคร": st.column_config.TextColumn("หมายเลขผู้สมัคร", disabled=True),
                "คะแนน": st.column_config.NumberColumn("คะแนน", step=1),
            },
        )
        candidates_edited = []
        for original, (_, row) in zip(candidates, edited.iterrows()):
            new_item = dict(original)
            new_item["คะแนน"] = coerce_int(row["คะแนน"])
            candidates_edited.append(new_item)

    total = data.get("รวมคะแนนทั้งสิ้น")
    total_edited = total
    if total is not None:
        total_edited = st.number_input(
            "รวมคะแนนทั้งสิ้น",
            value=coerce_int(total),
            step=1,
            key=f"norm_total_{path}",
        )

    if st.button("💾 บันทึกการแก้ไข (ผู้สมัคร)", key=f"save_norm_{path}", type="primary"):
        new_data = dict(data)
        new_data["แบบฟอร์ม"] = form_value
        if "ข้อมูลทั่วไป" in data:
            new_data["ข้อมูลทั่วไป"] = info_edited
        if "จำนวนผู้มีสิทธิเลือกตั้ง" in data:
            new_data["จำนวนผู้มีสิทธิเลือกตั้ง"] = voter_edited
        if "จำนวนบัตรเลือกตั้ง" in data:
            new_data["จำนวนบัตรเลือกตั้ง"] = ballot_edited
        if "ผลคะแนน" in data:
            new_data["ผลคะแนน"] = candidates_edited
        if "รวมคะแนนทั้งสิ้น" in data:
            new_data["รวมคะแนนทั้งสิ้น"] = coerce_int(total_edited)

        ok, err = save_json(path, new_data)
        if ok:
            st.success(f"บันทึกแล้ว: {os.path.basename(path)}")
            st.cache_data.clear()
        else:
            st.error(f"บันทึกไม่สำเร็จ: {err}")

    with st.expander("ดูข้อมูล JSON ดิบ"):
        st.json(data)


# --- Main ---------------------------------------------------------------------

index = build_index()

with st.sidebar:
    st.title("เลือกหน่วยเลือกตั้ง")

    # ---- Filter row ----
    fcol, icol = st.columns([5, 1])
    with fcol:
        only_suspect = st.toggle(
            "🔎 กรองเฉพาะหน่วยที่อาจ OCR ผิดพลาด",
            value=False,
            key="filter_toggle",
        )
    with icol:
        with st.popover("ℹ️", use_container_width=True):
            st.markdown("**เงื่อนไขการตรวจสอบ**")
            st.markdown(
                "หน่วยจะถูกทำเครื่องหมายว่า *เสี่ยง* หากพบอย่างน้อยหนึ่งข้อต่อไปนี้:\n\n"
                "- **รวมคะแนนทั้งสิ้น ≠ บัตรดี** (ไฟล์ผู้สมัคร)\n"
                "- **ผลรวมคะแนนผู้สมัคร ≠ รวมคะแนนทั้งสิ้น**\n"
                "- **ผลรวมคะแนนพรรค ≠ บัตรดี** (ไฟล์ บช)\n"
                "- **บัตรดี + บัตรเสีย + บัตรไม่เลือกผู้สมัครใด ≠ บัตรที่ใช้ลงคะแนน**\n"
                "- **ผู้มาใช้สิทธิ > ผู้มีสิทธิทั้งหมด**\n"
                "- **ผู้มาใช้สิทธิ ≠ บัตรที่ใช้ลงคะแนน**\n"
                "- **มีค่าติดลบ** ในช่องจำนวน\n"
                "- **อ่านไฟล์ JSON ไม่ได้**\n\n"
                "ระบบจะข้ามการตรวจอัตโนมัติเมื่อหาคีย์ในไฟล์ไม่เจอ "
                "(เพื่อลด false positive จากชื่อคีย์ที่ต่างกัน)"
            )

    # Apply filter
    if only_suspect:
        filtered = [e for e in index if any(get_issues(e).values())]
        st.caption(f"พบหน่วยที่เสี่ยง: {len(filtered)} / {len(index)}")
    else:
        filtered = index

    if not filtered:
        st.warning("ไม่มีหน่วยที่ตรงเงื่อนไข")
        st.stop()

    districts = sorted(set(e["district"] for e in filtered))
    district = st.selectbox("อำเภอ", districts)

    subs = sorted(set(e["sub_district"] for e in filtered if e["district"] == district))
    sub_district = st.selectbox("ตำบล", subs)

    units_with_status = []
    for e in filtered:
        if e["district"] == district and e["sub_district"] == sub_district:
            has_issue = any(get_issues(e).values())
            label = f"⚠️ {e['unit']}" if has_issue else e["unit"]
            units_with_status.append((label, e["unit"]))

    unit_label = st.selectbox(
        "หน่วยเลือกตั้ง",
        [label for label, _ in units_with_status],
    )
    unit = next(u for label, u in units_with_status if label == unit_label)

entry = next(
    (e for e in filtered if e["district"] == district and e["sub_district"] == sub_district and e["unit"] == unit),
    None,
)

st.title("ผลการเลือกตั้ง เขตเลือกตั้งที่ 10")
if entry:
    st.caption(f"อำเภอ{district} / ตำบล{sub_district} / {unit}")

if not entry:
    st.info("เลือกหน่วยเลือกตั้งจากแถบด้านซ้าย")
    st.stop()

# Inline summary of issues for the currently-selected unit
issues = get_issues(entry)
all_issues = [("บช", i) for i in issues["bch"]] + [("ผู้สมัคร", i) for i in issues["normal"]]
if all_issues:
    with st.expander(f"⚠️ พบความผิดปกติ {len(all_issues)} รายการในหน่วยนี้", expanded=True):
        for src, msg in all_issues:
            st.markdown(f"- **[{src}]** {msg}")

col_pdf, col_data = st.columns(2)

with col_pdf:
    st.subheader("เอกสาร PDF")
    render_pdf(entry["pdf_path"])

with col_data:
    st.subheader("ข้อมูลผลการเลือกตั้ง")
    tab_bch, tab_normal = st.tabs(["บัญชีรายชื่อพรรค (บช)", "ผู้สมัคร (ส.ส. ๕/๑๘)"])

    with tab_bch:
        bch_path = entry["bch_path"]
        if os.path.exists(bch_path):
            with open(bch_path, encoding="utf-8") as f:
                data = json.load(f)
            edit_bch(data, bch_path)
        else:
            st.warning("ไม่พบไฟล์ JSON (bch)")

    with tab_normal:
        normal_path = entry["normal_path"]
        if os.path.exists(normal_path):
            with open(normal_path, encoding="utf-8") as f:
                data = json.load(f)
            edit_normal(data, normal_path)
        else:
            st.warning("ไม่พบไฟล์ JSON (normal)")