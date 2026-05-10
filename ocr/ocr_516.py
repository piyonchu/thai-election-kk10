"""
Process single PDF: กนค ชุด10 เขต10.pdf (Form ส.ส. 5/16)
"""

from google import genai
from google.genai import types
import json
import os
import io

API_KEY = "[ENCRYPTION_KEY]"
MODEL_NAME = "gemini-3-flash-preview"

PDF_PATH = r"C:\Users\aomsi\Downloads\เขตเลือกตั้งที่ 10 -20260501T150038Z-3-001\เขตเลือกตั้งที่ 10\อำเภอ หนองสองห้อง\ใน นอก นอกราช\กนค ชุด10 เขต10.pdf"
OUT_PATH = r"C:\Users\aomsi\Code\dsde\final\forjson\อำเภอ หนองสองห้อง\ใน นอก นอกราช\กนค_ชุด10.json"

PROMPT = """
You are an expert at extracting text from official Thai election documents.
Analyze the attached PDF of a Thai election vote counting report (ส.ส. 5/16).
Extract all handwritten and printed numbers accurately.

Form ส.ส. 5/16 reports votes from ballots cast BEFORE election day, counted at the constituency level (การนับคะแนนบัตรเลือกตั้งที่ออกเสียงลงคะแนนก่อนวันเลือกตั้งในเขตเลือกตั้ง).

A single PDF typically contains BOTH:
- ส.ส. 5/16        : constituency form (แบ่งเขตเลือกตั้ง) — up to 11 candidates
- ส.ส. 5/16 (บช)   : party-list form (บัญชีรายชื่อ) — 57 parties

Extract every form present.

Respond with ONLY valid JSON, no extra text. Include only the keys for forms actually present. Use this exact structure:

{
  "form_5_16": {
    "location": "<สถานที่นับคะแนน>",
    "constituency": <number>,
    "province": "<name>",
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
  "form_5_16_bch": {
    "location": "<สถานที่นับคะแนน>",
    "constituency": <number>,
    "province": "<name>",
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
- Form 5/16 has NO voter-turnout section (no 1.1 / 1.2 / 2.2.1 / 2.2.2 / 2.2.3). Only "1" (total ballots received), "2.1" (good), "2.2" (spoiled), "2.3" (no-vote).
- The constituency form has up to 11 numbered candidate slots; the party-list form has 57 numbered parties — skip any with no votes.
- If a field is illegible or blank, use null.
"""

client = genai.Client(api_key=API_KEY)

print(f"Processing: {os.path.basename(PDF_PATH)}")
with open(PDF_PATH, "rb") as f:
    file_bytes = f.read()

uploaded = client.files.upload(
    file=io.BytesIO(file_bytes),
    config=types.UploadFileConfig(mime_type="application/pdf", display_name=os.path.basename(PDF_PATH))
)

try:
    resp = client.models.generate_content(model=MODEL_NAME, contents=[PROMPT, uploaded])
    text = resp.text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    data = json.loads(text)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved: {OUT_PATH}")
finally:
    try:
        client.files.delete(name=uploaded.name)
    except:
        pass
