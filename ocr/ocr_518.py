"""
Election PDF OCR Pipeline
=========================
Walks an input folder structured as:
    input_dir/
        amphoe_name/
            tambon_name/
                *.pdf  (one PDF per polling station)

For each PDF:
  1. Uploads to Gemini API
  2. Extracts election data as JSON
  3. Saves to output_dir/ with the same amphoe/tambon structure
  4. Renames the output file to <station_number>.json

Usage:
    python pipeline.py
    python pipeline.py --input <custom_input> --output <custom_output>
"""

from google import genai
from google.genai import types
import json
import os
import argparse
import time
import sys
import re
from collections import Counter

# ── Configuration ───────────────────────────────────────────────────────────
API_KEY = "[ENCRYPTION_KEY]"
MODEL_NAME = "gemini-3-flash-preview"

# Default paths
DEFAULT_INPUT = r"C:\Users\aomsi\Downloads\เขตเลือกตั้งที่ 10 -20260501T150038Z-3-001\เขตเลือกตั้งที่ 10"
DEFAULT_OUTPUT = r"C:\Users\aomsi\Code\dsde\forjson"

# ── Prompt Template ─────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """
You are an expert at extracting text from official Thai election documents.
Analyze the attached PDF of Thai election vote counting reports.
Extract all handwritten and printed numbers accurately.

The file path of this PDF is: {pdf_path}
The folder structure encodes amphoe and tambon names. Use the file path as the PRIMARY source for tambon, amphoe, and station info. Only fall back to extracted text if the path does not contain this info.

Respond with ONLY valid JSON, no extra text. Use this exact structure:

{
  "form_5_18": {
    "station": <number>,
    "moo": <number>,
    "tambon": "<name>",
    "amphoe": "<name>",
    "constituency": <number>,
    "province": "<name>",
    "1.1": <number>,
    "1.2": <number>,
    "2.1": <number>,
    "2.2": <number>,
    "2.2.1": <number>,
    "2.2.2": <number>,
    "2.2.3": <number>,
    "2.3": <number>,
    "candidates": {
      "<candidate_full_name>": <votes>,
      ...
    },
    "total": <number>
  },
  "form_5_18_bch": {
    "2.1": <number>,
    "2.2": <number>,
    "2.2.1": <number>,
    "2.2.2": <number>,
    "2.2.3": <number>,
    "2.3": <number>,
    "candidates": {
      "<party_number>": <votes>,
      ...
    },
    "total": <number>
  }
}

Rules:
- In form_5_18 "candidates", use the candidate's full Thai name as the key and votes received as the value. Include ALL candidates, even those with 0 votes.
- In form_5_18_bch "candidates", use the party candidate number as the key (e.g. "1", "2", "3") and votes as the value. Only include parties with votes > 0 (skip 0 or "-").
- For form_5_18_bch (สส5/18 บช), only extract parts 2 and 3.
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

    # Read file as bytes to avoid ASCII encoding issues with Thai paths
    import io
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    uploaded_file = client.files.upload(
        file=io.BytesIO(file_bytes),
        config=types.UploadFileConfig(
            mime_type="application/pdf",
            display_name=os.path.basename(pdf_path)
        )
    )

    # Inject the absolute file path into the prompt for context
    prompt = PROMPT_TEMPLATE.replace("{pdf_path}", os.path.abspath(pdf_path))

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, uploaded_file]
        )
        data = extract_json_from_response(response.text)
        return data
    finally:
        # Clean up uploaded file from Gemini servers
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass


def get_station_number(data):
    """Extract polling station number from the parsed JSON data."""
    try:
        station = data.get("form_5_18", {}).get("station")
        if station is not None:
            return str(station)
    except (AttributeError, TypeError):
        pass
    return None


def find_all_pdfs(input_dir):
    """Walk the input directory and return list of (pdf_path, amphoe, tambon)."""
    pdfs = []
    for root, dirs, files in os.walk(input_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, f)
                # Determine relative path to figure out amphoe/tambon
                rel = os.path.relpath(root, input_dir)
                parts = rel.split(os.sep)

                if len(parts) >= 2:
                    amphoe, tambon = parts[0], parts[1]
                elif len(parts) == 1 and parts[0] != ".":
                    amphoe, tambon = parts[0], ""
                else:
                    amphoe, tambon = "", ""

                pdfs.append((pdf_path, amphoe, tambon))
    return pdfs


def run_pipeline(input_dir, output_dir):
    """Main pipeline: discover PDFs, OCR each, save as JSON."""
    print(f"Input folder:  {input_dir}")
    print(f"Output folder: {output_dir}")
    print()

    # Discover all PDFs
    pdfs = find_all_pdfs(input_dir)
    if not pdfs:
        print("No PDF files found in the input directory!")
        return

    total = len(pdfs)
    print(f"Found {total} PDF file(s)")
    print("=" * 60)

    client = setup_api()

    success_count = 0
    fail_count = 0
    failed_files = []

    skipped_count = 0

    # Pre-compute how many PDFs map to each (out_dir, station_number)
    # so the skip logic knows when ALL PDFs for a station have been processed
    pdf_station_counts = Counter()
    for pdf_path_tmp, amphoe_tmp, tambon_tmp in pdfs:
        if tambon_tmp:
            od = os.path.join(output_dir, amphoe_tmp, tambon_tmp)
        elif amphoe_tmp:
            od = os.path.join(output_dir, amphoe_tmp)
        else:
            od = output_dir
        bn = os.path.splitext(os.path.basename(pdf_path_tmp))[0]
        ns = re.findall(r'\d+', bn)
        if ns:
            pdf_station_counts[(od, ns[-1])] += 1

    for i, (pdf_path, amphoe, tambon) in enumerate(pdfs, 1):
        # Check if output already exists (resume support)
        if tambon:
            out_dir = os.path.join(output_dir, amphoe, tambon)
        elif amphoe:
            out_dir = os.path.join(output_dir, amphoe)
        else:
            out_dir = output_dir

        # Skip if enough JSONs already exist for this station number
        existing_jsons = set()
        if os.path.isdir(out_dir):
            existing_jsons = {f for f in os.listdir(out_dir) if f.endswith(".json")}

        basename_noext = os.path.splitext(os.path.basename(pdf_path))[0]
        nums = re.findall(r'\d+', basename_noext)
        if nums:
            station_num = nums[-1]
            expected = pdf_station_counts.get((out_dir, station_num), 1)
            # Count existing JSONs for this station: e.g. 5.json, 5_1.json, 5_2.json
            existing_for_station = sum(
                1 for j in existing_jsons
                if j == f"{station_num}.json" or j.startswith(f"{station_num}_")
            )
            if existing_for_station >= expected:
                skipped_count += 1
                print(f"  [{i}/{total}] SKIP ({existing_for_station}/{expected} exist): {os.path.basename(pdf_path)}")
                continue

        print(f"\n[{i}/{total}] Processing: {os.path.basename(pdf_path)}")
        print(f"  Location: {amphoe}/{tambon}")

        try:
            data = process_pdf(client, pdf_path)

            # Get station number for filename
            station = get_station_number(data)
            if station is None:
                # Fallback: use original filename without extension
                station = os.path.splitext(os.path.basename(pdf_path))[0]
                print(f"  Warning: Could not extract station number, using filename: {station}")

            # Build output path: output_dir/amphoe/tambon/<station>.json
            if tambon:
                out_dir = os.path.join(output_dir, amphoe, tambon)
            elif amphoe:
                out_dir = os.path.join(output_dir, amphoe)
            else:
                out_dir = output_dir

            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{station}.json")

            # Handle duplicate station numbers
            counter = 1
            while os.path.exists(out_path):
                out_path = os.path.join(out_dir, f"{station}_{counter}.json")
                counter += 1

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"  Saved: {os.path.relpath(out_path, output_dir)}")
            success_count += 1

        except json.JSONDecodeError as e:
            print(f"  FAIL - JSON parse error: {e}")
            fail_count += 1
            failed_files.append(pdf_path)
        except Exception as e:
            print(f"  FAIL - Error: {e}")
            fail_count += 1
            failed_files.append(pdf_path)

    # Summary
    print("\n" + "=" * 60)
    print(f"DONE! {success_count} succeeded, {fail_count} failed, {skipped_count} skipped out of {total} files")
    if failed_files:
        print("\nFailed files:")
        for f in failed_files:
            print(f"  - {f}")


def reprocess_pdfs(pdf_paths, output_dir):
    """Force-reprocess specific PDF files, bypassing skip logic."""
    client = setup_api()
    success_count = 0
    fail_count = 0

    for pdf_path in pdf_paths:
        pdf_path = os.path.abspath(pdf_path)
        if not os.path.isfile(pdf_path):
            print(f"  NOT FOUND: {pdf_path}")
            fail_count += 1
            continue

        # Derive amphoe/tambon from path relative to input root
        # Just use parent and grandparent folder names
        tambon = os.path.basename(os.path.dirname(pdf_path))
        amphoe = os.path.basename(os.path.dirname(os.path.dirname(pdf_path)))
        out_dir = os.path.join(output_dir, amphoe, tambon)

        print(f"\nProcessing: {os.path.basename(pdf_path)}")
        print(f"  Location: {amphoe}/{tambon}")

        try:
            data = process_pdf(client, pdf_path)

            station = get_station_number(data)
            if station is None:
                station = os.path.splitext(os.path.basename(pdf_path))[0]
                print(f"  Warning: Could not extract station number, using filename: {station}")

            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{station}.json")

            counter = 1
            while os.path.exists(out_path):
                out_path = os.path.join(out_dir, f"{station}_{counter}.json")
                counter += 1

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"  Saved: {os.path.relpath(out_path, output_dir)}")
            success_count += 1

        except json.JSONDecodeError as e:
            print(f"  FAIL - JSON parse error: {e}")
            fail_count += 1
        except Exception as e:
            print(f"  FAIL - Error: {e}")
            fail_count += 1

    print(f"\nDONE! {success_count} succeeded, {fail_count} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Election PDF OCR Pipeline")
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT,
                        help="Input folder with PDFs (amphoe/tambon structure)")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT,
                        help="Output folder for JSON files")
    parser.add_argument("--reprocess", "-r", nargs="+", metavar="PDF",
                        help="Force-reprocess specific PDF file(s), bypassing skip logic")
    args = parser.parse_args()

    if args.reprocess:
        reprocess_pdfs(args.reprocess, args.output)
    else:
        if not os.path.isdir(args.input):
            print(f"Error: Input directory not found: {args.input}")
            sys.exit(1)
        run_pipeline(args.input, args.output)
