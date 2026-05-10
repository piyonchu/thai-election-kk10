import os
import json
import pandas as pd
from pathlib import Path

# 2026 General Election (Election 69) Constituency Candidate Mapping
# Updated with actual candidate names for Khon Kaen District 10
CANDIDATE_MAPPING = {
    1: "นายวันนิวัติ สมบูรณ์",
    2: "ร.ต.ท.สงวน คมขาว",
    3: "นายนิวัตร สระพรม",
    4: "นายวิระศักดิ์ สายทอง",
    5: "นายพชรกร อรรณนพพร",
    6: "นายประยูร เทียมทะนง"
}

def process_constituency_election_data(base_dir, coord_file):
    units_data = []
    scores_data = []
    
    # 1. Ingest Coordinates
    try:
        df_coords = pd.read_csv(coord_file)
        # Convert to an indexed dictionary for O(1) lookup speeds during iteration
        coord_dict = df_coords.set_index(['อำเภอ', 'ตำบล']).to_dict(orient='index')
    except FileNotFoundError:
        print("Warning: Coordinate template not found. Pipeline will proceed with empty coordinate values.")
        coord_dict = {}

    # 2. Iterate through deeply nested directories
    for filepath in Path(base_dir).rglob('*.json'):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON in file {filepath}")
                continue
            
            # Ensure we are processing the correct format (Constituency Candidate data)
            if "ผลคะแนน" not in data:
                continue
                
            gen_info = data.get("ข้อมูลทั่วไป", {})
            district = gen_info.get("อำเภอ_เขต", "")
            subdistrict = gen_info.get("ตำบล_แขวง_เทศบาล", "")
            unit_no = gen_info.get("หน่วยเลือกตั้งที่", "")
            village_no = gen_info.get("หมู่ที่", "")
            
            # Construct a composite Primary Key for relational database integrity
            # Adjusted prefix to explicitly represent Constituency data
            unit_id = f"KK10_CONST_{district}_{subdistrict}_M{village_no}_U{unit_no}"
            
            coords = coord_dict.get((district, subdistrict), {'Latitude': None, 'Longitude': None})
            
            voter_info = data.get("จำนวนผู้มีสิทธิเลือกตั้ง", {})
            ballot_info = data.get("จำนวนบัตรเลือกตั้ง", {})
            
            # Append to the Unit-Level DataFrame list
            units_data.append({
                "Unit_ID": unit_id,
                "District": district,
                "Subdistrict": subdistrict,
                "Village_No": village_no,
                "Unit_No": unit_no,
                "Latitude": coords.get('Latitude'),
                "Longitude": coords.get('Longitude'),
                "Eligible_Voters": voter_info.get("จำนวนผู้มีสิทธิเลือกตั้งตามบัญชีรายชื่อ"),
                "Voters_Showed_Up": voter_info.get("จำนวนผู้มีสิทธิเลือกตั้งที่มาแสดงตน"),
                "Allocated_Ballots": ballot_info.get("จำนวนบัตรเลือกตั้งที่ได้รับจัดสรร"),
                "Used_Ballots": ballot_info.get("จำนวนบัตรเลือกตั้งที่ใช้"),
                "Valid_Ballots": ballot_info.get("บัตรดี"),
                "Invalid_Ballots": ballot_info.get("บัตรเสีย"),
                "No_Vote_Ballots": ballot_info.get("บัตรที่ไม่เลือกผู้สมัครใด"), 
                "Remaining_Ballots": ballot_info.get("จำนวนบัตรเลือกตั้งที่เหลือ")
            })
            
            # Append to the Candidate-Level DataFrame list
            candidate_scores = data.get("ผลคะแนน", [])
            for score in candidate_scores:
                candidate_no = score.get("หมายเลขประจำตัวผู้สมัคร")
                scores_data.append({
                    "Unit_ID": unit_id, # Foreign key linking back to the unit
                    "Candidate_Number": candidate_no,
                    "Candidate_Name": CANDIDATE_MAPPING.get(candidate_no, f"ผู้สมัครหมายเลข {candidate_no}"),
                    "Score": score.get("คะแนน")
                })
                
    # 3. Export to Analysis-Ready CSVs
    df_units = pd.DataFrame(units_data)
    df_scores = pd.DataFrame(scores_data)
    
    # Exporting with unique file names to prevent overwriting the Party List data
    output_units_file = "data_cleaned_constituency_units.csv"
    output_scores_file = "data_cleaned_constituency_scores.csv"
    
    df_units.to_csv(output_units_file, index=False, encoding='utf-8-sig')
    df_scores.to_csv(output_scores_file, index=False, encoding='utf-8-sig')
    
    print(f"Processing Complete: Exported {len(df_units)} polling units to {output_units_file}.")
    print(f"Processing Complete: Exported {len(df_scores)} candidate score records to {output_scores_file}.")

if __name__ == "__main__":
    process_constituency_election_data('./result/normal', 'location_coordinates_template.csv')