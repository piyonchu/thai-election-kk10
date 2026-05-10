# 🗳️ Khon Kaen Constituency 10 — Election Analyst

A Streamlit app for analyzing the 2026 Thai General Election (Election 69) results
in **เขตเลือกตั้งที่ 10, ขอนแก่น**. Built around the OCR'd ballot tally sheets
(ส.ส. ๕/๑๘ and ส.ส. ๕/๑๘ บช) for every polling unit.

The view is **vote-centric**: who won, by how much, and where each party is strong.
Turnout sits in the footnote view, not the headline.

## Pages

| Page | What it shows |
|------|---------------|
| `app.py` | Top-line: winning party, runner-up, margin, top 10 chart, candidate race, ตำบล winners |
| `1_🏆_Party_List.py` | Party-list deep dive — vote share, stacked-by-ตำบล, ตำบล wins |
| `2_👤_Constituency.py` | Constituency MP race — candidates, margin, ตำบล breakdown |
| `3_🗺️_Map.py` | Winner-by-ตำบล map (folium); markers colored by winning party |
| `4_⚔️_Margins.py` | Polling-unit competitiveness — battlegrounds vs. strongholds |
| `5_📑_Raw_Data.py` | View & download the four flattened tables |

## Data layout expected

```
data/
├── aomsin_result/
│   ├── bch/เขตเลือกตั้งที่10/<อำเภอ>/<ตำบล>/<หน่วย>.json     # party-list ballots
│   └── normal/เขตเลือกตั้งที่10/<อำเภอ>/<ตำบล>/<หน่วย>.json  # constituency ballots
└── location_coordinates_template.csv                              # ตำบล → lat/lon
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open <http://localhost:8501>.

## Party colors

Colors come from the Thai Wikipedia template
[`สีประจำพรรคการเมืองไทย`](https://th.wikipedia.org/wiki/แม่แบบ:สีประจำพรรคการเมืองไทย),
encoded in `utils/parties.py` as `PARTY_HEX`. Parties not in that template fall back
to neutral grey.
