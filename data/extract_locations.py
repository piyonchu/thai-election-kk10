import os
import json
import pandas as pd
from pathlib import Path

def generate_coordinate_template(base_dir):
    locations = set()
    
    # Recursively find all JSON files traversing your nested folders
    for filepath in Path(base_dir).rglob('*.json'):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Extract location data from the "ข้อมูลทั่วไป" block
            gen_info = data.get("ข้อมูลทั่วไป", {})
            district = gen_info.get("อำเภอ_เขต", "Unknown")
            subdistrict = gen_info.get("ตำบล_แขวง_เทศบาล", "Unknown")
            
            # A Python Set automatically deduplicates the entries
            locations.add((district, subdistrict))
            
    # Convert the set to a Pandas DataFrame and append empty coordinate columns
    df_locations = pd.DataFrame(list(locations), columns=['อำเภอ', 'ตำบล'])
    df_locations['Latitude'] = ""
    df_locations['Longitude'] = ""
    
    # Save to a CSV with utf-8-sig to perfectly preserve Thai characters in Excel
    output_path = "location_coordinates_template.csv"
    df_locations.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"Generated template with {len(df_locations)} unique locations at {output_path}")

if __name__ == "__main__":
    # Point this to the root directory containing your JSON folders
    generate_coordinate_template('./bch')