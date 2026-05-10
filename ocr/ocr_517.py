"""
Election PDF OCR Pipeline — Form ส.ส. 5/17
============================================
Processes vote counting reports for ballots cast OUTSIDE the constituency
and OVERSEAS (การนับคะแนนบัตรเลือกตั้งนอกเขตเลือกตั้งและนอกราชอาณาจักร).

Processes PDFs ชุด1–ชุด8 from the "ใน นอก นอกราช" folder.

Usage:
    python ocr_517.py
"""

from google import genai
from google.genai import types
import json
import os
import io
import time
import sys

# ── Configuration ───────────────────────────────────────────────────────────
API_KEY = "AIzaSyAyD_QwL1nTzwprwOwxqv9A-owYdx4GC2w"
MODEL_NAME = "gemini-3-flash-preview"

INPUT_DIR = r"C:\Users\aomsi\Downloads\เขตเลือกตั้งที่ 10 -20260501T150038Z-3-001\เขตเลือกตั้งที่ 10\อำเภอ หนองสองห้อง\ใน นอก นอกราช"
OUTPUT_DIR = r"C:\Users\aomsi\Code\dsde\final\forjson\อำเภอ หนองสองห้อง\ใน นอก นอกราช"

# Process only ชุด1 through ชุด8
TARGET_FILES = [f"กนค ชุด{i} เขต10.pdf" for i in range(1, 10)]

# ── Prompt Template ─────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """
You are an expert at extracting text from official Thai election documents.
Analyze the attached PDF of a Thai election vote counting report (ส.ส. 5/17).
Extract all handwritten and printed numbers accurately.

Form ส.ส. 5/17 reports votes cast OUTSIDE the constituency and OVERSEAS (การนับคะแนนบัตรเลือกตั้งนอกเขตเลือกตั้งและนอกราชอาณาจักร). Ballots arrive in envelopes from Thailand Post (บริษัท ไปรษณีย์ไทย จำกัด).

A single PDF typically contains BOTH:
- ส.ส. 5/17        : constituency form (แบ่งเขตเลือกตั้ง) — up to 11 candidates
- ส.ส. 5/17 (บช)   : party-list form (บัญชีรายชื่อ) — 57 parties

Extract every form present.

Respond with ONLY valid JSON, no extra text. Include only the keys for forms actually present. Use this exact structure:

{
  "form_5_17": {
    "location": "<สถานที่นับคะแนน>",
    "constituency": <number>,
    "province": "<name>",
    "envelopes_received": <number>,
    "ballots_in_envelopes": <number>,
    "1": <number>,
    "2.1": <number>,
    "2.2": <number>,
    "2.3": <number>,
    "candidates": {
      "<candidate_number>": <votes>,
      ...
    },
    "total": <number>
  },
  "form_5_17_bch": {
    "location": "<สถานที่นับคะแนน>",
    "constituency": <number>,
    "province": "<name>",
    "envelopes_received": <number>,
    "ballots_in_envelopes": <number>,
    "1": <number>,
    "2.1": <number>,
    "2.2": <number>,
    "2.3": <number>,
    "parties": {
      "<party_number>": <votes>,
      ...
    },
    "total": <number>
  }
}

Rules:
- Only include top-level keys for forms actually present in the PDF; omit any form not in the document.
- In "candidates" / "parties", only include entries with votes > 0 (skip 0, blank, "-", or "ศูนย์").
- Use the candidate/party number as the JSON key (e.g. "1", "2", "9", "37").
- Numbers are written in BOTH Arabic/Thai digits AND Thai words in parentheses — use the digits, but cross-check against the Thai words to resolve ambiguous handwriting.
- Form 5/17 has NO voter-turnout section (no 1.1 / 1.2 / 2.2.1 / 2.2.2 / 2.2.3). Only "1" (total ballots received), "2.1" (good), "2.2" (spoiled), "2.3" (no-vote).
- Extract "envelopes_received" and "ballots_in_envelopes" from the header paragraph that begins "ได้รับซองใส่บัตรเลือกตั้งจาก บริษัท ไปรษณีย์ไทย จำกัด ... จำนวน ___ ซอง ... มีจำนวน ___ บัตร".
- The constituency form has up to 11 numbered candidate slots; the party-list form has 57 numbered parties — skip any with no votes.
- If a field is illegible or blank, use null.
"""


def setup_api():
    """Configure Gemini API and return the client."""
    return genai.Client(api_key=API_KEY)


def extract_json_from_response(text):
    """Parse JSON from model response, handling markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])
    return json.loads(cleaned)


def process_pdf(client, pdf_path):
    """Upload a PDF and extract election data via Gemini API."""
    print(f"  Uploading: {os.path.basename(pdf_path)}")

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    uploaded_file = client.files.upload(
        file=io.BytesIO(file_bytes),
        config=types.UploadFileConfig(
            mime_type="application/pdf",
            display_name=os.path.basename(pdf_path)
        )
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[PROMPT_TEMPLATE, uploaded_file]
        )
        data = extract_json_from_response(response.text)
        return data
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass


def main():
    print(f"Input folder:  {INPUT_DIR}")
    print(f"Output folder: {OUTPUT_DIR}")
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = setup_api()

    success_count = 0
    fail_count = 0
    failed_files = []

    for i, filename in enumerate(TARGET_FILES, 1):
        pdf_path = os.path.join(INPUT_DIR, filename)

        if not os.path.isfile(pdf_path):
            print(f"[{i}/{len(TARGET_FILES)}] NOT FOUND: {filename}")
            fail_count += 1
            failed_files.append(filename)
            continue

        # Extract ชุด number for output filename
        # "กนค ชุด1 เขต10.pdf" -> "1"
        import re
        match = re.search(r'ชุด(\d+)', filename)
        chud_num = match.group(1) if match else str(i)

        # Check if output already exists
        out_path = os.path.join(OUTPUT_DIR, f"กนค_ชุด{chud_num}.json")
        if os.path.exists(out_path):
            print(f"[{i}/{len(TARGET_FILES)}] SKIP (already exists): {filename}")
            continue

        print(f"\n[{i}/{len(TARGET_FILES)}] Processing: {filename}")

        try:
            data = process_pdf(client, pdf_path)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"  ✓ Saved: {os.path.basename(out_path)}")
            success_count += 1

        except json.JSONDecodeError as e:
            print(f"  FAIL - JSON parse error: {e}")
            fail_count += 1
            failed_files.append(filename)
        except Exception as e:
            print(f"  FAIL - Error: {e}")
            fail_count += 1
            failed_files.append(filename)

        # Brief pause between API calls
        if i < len(TARGET_FILES):
            time.sleep(2)

    # Summary
    print("\n" + "=" * 60)
    print(f"DONE! {success_count} succeeded, {fail_count} failed out of {len(TARGET_FILES)} files")
    if failed_files:
        print("\nFailed files:")
        for f in failed_files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
