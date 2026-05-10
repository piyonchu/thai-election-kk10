# 🗳️ Khon Kaen District 10: Advanced Election Analytics Engine

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)
![Scikit-Learn](https://img.shields.io/badge/Machine%20Learning-Scikit--Learn-F7931E.svg)
![Deck.GL](https://img.shields.io/badge/Geospatial-PyDeck%20%2F%20WebGL-61DBFB.svg)

## 📌 Project Overview
This platform is a graduate-level political science and geospatial analytics engine built to analyze the polling data for **Khon Kaen Constituency 10**. 

Moving beyond standard business intelligence (BI) dashboards, this application utilizes relational data engineering, machine learning (Isolation Forests), 3D GPU-accelerated rendering, and algorithmic anomaly detection to audit electoral integrity and map voter behavior at a hyper-local level.

## 🚀 Core Analytical Modules

### 1. 🗺️ Advanced Geospatial Intelligence (`pages/1_🗺️_Geospatial_Map.py`)
A multi-layered spatial mapping engine handling high-density point data:
* **Clustered Tactical Mapping:** Utilizes `folium` and dynamic bounding-box logic to instantly aggregate regional polling data based on the user's viewport.
* **3D Spatial Density Engine:** Implements `pydeck` (Deck.GL) to render 3D hexagonal bins via WebGL. Elevation correlates to voter turnout volume, while thermal coloring indicates invalid ballot density.
* **Party Support Heatmaps:** Thermal spatial mapping to visualize massive regional concentrations of political support.
* **Hyper-Competitive Battlegrounds:** Algorithmic filtering to isolate and map "knife-edge" races where the Margin of Victory (MoV) was less than 5%.

### 2. 📊 Political Science Dashboard (`pages/2_📊_Election_Dashboard.py`)
Deep-dive electoral metric analysis:
* **Laakso-Taagepera Index (ENP):** Mathematically calculates the Effective Number of Parties to measure regional political fragmentation vs. consolidation.
* **Margin of Victory Competitiveness:** Classifies polling stations into Safe/Landslide, Battleground, and Hyper-Competitive zones.
* **Hierarchical Vote Distribution:** Interactive radial sunburst charts allowing drill-down from District ➔ Subdistrict ➔ Party.

### 3. 🚨 Algorithmic Anomaly & Fraud Detection (`pages/3_🚨_Anomaly_Detection.py`)
Rigorous statistical auditing of polling station returns:
* **Multivariate Machine Learning:** Deploys an `IsolationForest` model to evaluate Turnout %, Invalid Ballot %, and No-Vote % simultaneously, trapping complex anomalies that evade simple standard deviation checks.
* **The "Double-X" Vote-Buying Footprint:** Detects statistically impossible, isolated surges for minor parties that share the same ballot number as local constituency candidates (identifying simplified, symmetric vote-buying instructions).
* **Benford's Law of First Digits:** Runs a Chi-Square Goodness of Fit test ($P < 0.05$) to measure deviations in the expected logarithmic distribution of leading digits, flagging potential manual fabrication of vote counts.
* **Ballot Math Reconciliation:** Hard-logic checks to isolate clerical data-entry errors (NaNs) from mathematically impossible fraud (e.g., Ghost Voting or Box Stuffing).

### 4. 📑 Raw Data Explorer (`pages/4_📑_Raw_Data_Explorer.py`)
End-user interface to query, filter, and export the flattened relational `.csv` datasets.

---

## 🏗️ System Architecture & Data Pipeline
The raw data is ingested from deeply nested government JSON files structured by `District/Subdistrict/File.pdf`. 
1. **Extraction & Relational Flattening:** Python iteratively parses the JSONs and normalizes the 1-to-Many relationships into two core tables (`df_units` for unit-level metadata, `df_scores` for specific party results).
2. **Geospatial Enrichment:** Coordinates are mapped at the Subdistrict level, and a mathematical spatial jitter ($\mu=0, \sigma=0.003$) is applied to prevent coordinate overlapping in the visualization layer.
3. **RAM Caching:** `st.cache_data` is heavily utilized to hold the cleaned Pandas DataFrames in memory, preventing lag during user interactions.

## 📂 Directory Structure
```text
election-project/
│
├── data/ 
│   ├── data_cleaned_units.csv      # Primary Key table (Unit Level)
│   └── data_cleaned_scores.csv     # Foreign Key table (Party Level)
│
├── utils/
│   ├── __init__.py                 
│   ├── data_loader.py              # Caching and merging logic
│   └── anomalies.py                # Scikit-Learn and SciPy math engines
│
├── app.py                          # Application Entry Point
├── pages/
│   ├── 1_🗺️_Geospatial_Map.py
│   ├── 2_📊_Election_Dashboard.py
│   ├── 3_🚨_Anomaly_Detection.py
│   └── 4_📑_Raw_Data_Explorer.py
│
├── requirements.txt                # Deployment dependencies
└── README.md

```

## ⚙️ Installation & Local Deployment

1. **Clone the repository:**
```bash
git clone [https://github.com/YourUsername/election-project.git](https://github.com/YourUsername/election-project.git)
cd election-project
```


2. **Install the dependencies:**
It is recommended to use a virtual environment.
```bash
pip install -r requirements.txt
```
3. **Download the PDF data:**

The original PDF ballot documents (~1.5 GB) are not included in this repository due to GitHub size limits. Download them separately:

📁 **[Download from Google Drive](https://drive.google.com/drive/folders/1wrya7xjIXfQbefILKzi6myTa92pJ0m07?usp=drive_link)**

Extract the archive and place the `เขตเลือกตั้งที่10` folder inside the `data/` directory so the structure looks like:

```
election-project/
└── data/
    ├── เขตเลือกตั้งที่10/      ← extracted PDFs go here
    │   ├── อำเภอ.../
    │   │   └── ตำบล.../
    │   │       └── *.pdf
    │   └── ...
    └── results/                 ← already in repo
        ├── bch/
        └── normal/
```

> **Note:** The application will still run without the PDFs — the OCR Data Cleaning page just won't show the document preview alongside the JSON editor. Other analytical modules work entirely from the JSON/CSV data.

1. **Launch the application:**
```bash
streamlit run app.py
```


The platform will be available locally at `http://localhost:8501`.

## ☁️ Cloud Deployment

This application is designed to be deployed seamlessly on **Streamlit Community Cloud**.
Because the application utilizes heavy machine learning libraries (`scikit-learn`, `scipy`), Serverless deployment environments with tight memory limits (like Vercel) are not supported.

To deploy:

1. Push this repository to GitHub.
2. Log into [share.streamlit.io](https://share.streamlit.io/).
3. Connect your repository and select `app.py` as the entry point. The cloud container will automatically provision the requirements and host the live application.
