import os
import json
import pandas as pd
from pathlib import Path

# 2026 General Election (Election 69) Official Party List Mapping
PARTY_MAPPING = {
    1: "พรรคไทยทรัพย์ทวี",
    2: "พรรคเพื่อชาติไทย",
    3: "พรรคใหม่",
    4: "พรรคมิติใหม่",
    5: "พรรครวมใจไทย",
    6: "พรรครวมไทยสร้างชาติ",
    7: "พรรคพลวัต",
    8: "พรรคประชาธิปไตยใหม่",
    9: "พรรคเพื่อไทย",
    10: "พรรคทางเลือกใหม่",
    11: "พรรคเศรษฐกิจ",
    12: "พรรคเสรีรวมไทย",
    13: "พรรครวมพลังประชาชน",
    14: "พรรคท้องที่ไทย",
    15: "พรรคอนาคตไทย",
    16: "พรรคพลังเพื่อไทย",
    17: "พรรคไทยชนะ",
    18: "พรรคพลังสังคมใหม่",
    19: "พรรคสังคมประชาธิปไตยไทย",
    20: "พรรคฟิวชัน",
    21: "พรรคไทรวมพลัง",
    22: "พรรคก้าวอิสระ",
    23: "พรรคปวงชนไทย",
    24: "พรรควิชชั่นใหม่",
    25: "พรรคเพื่อชีวิตใหม่",
    26: "พรรคคลองไทย",
    27: "พรรคประชาธิปัตย์",
    28: "พรรคไทยก้าวหน้า",
    29: "พรรคไทยภักดี",
    30: "พรรคแรงงานสร้างชาติ",
    31: "พรรคประชากรไทย",
    32: "พรรคครูไทยเพื่อประชาชน",
    33: "พรรคประชาชาติ",
    34: "พรรคสร้างอนาคตไทย",
    35: "พรรครักชาติ",
    36: "พรรคไทยพร้อม",
    37: "พรรคภูมิใจไทย",
    38: "พรรคพลังธรรมใหม่",
    39: "พรรคกรีน",
    40: "พรรคไทยธรรม",
    41: "พรรคแผ่นดินธรรม",
    42: "พรรคกล้าธรรม",
    43: "พรรคพลังประชารัฐ",
    44: "พรรคโอกาสใหม่",
    45: "พรรคเป็นธรรม",
    46: "พรรคประชาชน",
    47: "พรรคประชาไทย",
    48: "พรรคไทยสร้างไทย",
    49: "พรรคไทยก้าวใหม่",
    50: "พรรคอาสาสมัครประชาชนไทย",
    51: "พรรคพร้อม",
    52: "พรรคเครือข่ายชาวนาแห่งประเทศไทย",
    53: "พรรคไทยพิทักษ์ธรรม",
    54: "พรรคความหวังใหม่",
    55: "พรรคไทยรวมไทย",
    56: "พรรคเพื่อชาติ",
    57: "พรรคพลังไทยรักชาติ"
}

def process_election_data(base_dir, coord_file):
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
            data = json.load(f)
            
            gen_info = data.get("ข้อมูลทั่วไป", {})
            district = gen_info.get("อำเภอ_เขต", "")
            subdistrict = gen_info.get("ตำบล_แขวง_เทศบาล", "")
            unit_no = gen_info.get("หน่วยเลือกตั้งที่", "")
            village_no = gen_info.get("หมู่ที่", "")
            
            # Construct a composite Primary Key for relational database integrity
            unit_id = f"KK10_{district}_{subdistrict}_M{village_no}_U{unit_no}"
            
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
                "No_Vote_Ballots": ballot_info.get("บัตรที่ไม่เลือกบัญชีรายชื่อของพรรคการเมืองใด"),
                "Remaining_Ballots": ballot_info.get("จำนวนบัตรเลือกตั้งที่เหลือ")
            })
            
            # Append to the Party-Level DataFrame list
            party_scores = data.get("ผลคะแนนพรรค", [])
            for score in party_scores:
                party_no = score.get("หมายเลขบัญชีรายชื่อของพรรคการเมือง")
                scores_data.append({
                    "Unit_ID": unit_id, # Foreign key linking back to the unit
                    "Party_Number": party_no,
                    "Party_Name": PARTY_MAPPING.get(party_no, f"พรรคหมายเลข {party_no}"),
                    "Score": score.get("คะแนน")
                })
                
    # 3. Export to Analysis-Ready CSVs
    df_units = pd.DataFrame(units_data)
    df_scores = pd.DataFrame(scores_data)
    
    df_units.to_csv("data_cleaned_units.csv", index=False, encoding='utf-8-sig')
    df_scores.to_csv("data_cleaned_scores.csv", index=False, encoding='utf-8-sig')
    print(f"Phase 1 Complete: Processed {len(df_units)} polling units and {len(df_scores)} specific party score records.")

if __name__ == "__main__":
    process_election_data('./bch', 'location_coordinates_template.csv')