import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import pydeck as pdk
import sys
import os

# Ensure the app can find the utils module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.data_loader import load_data, get_winner_per_unit

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="Advanced Geospatial Map", page_icon="🗺️", layout="wide")

st.title("🗺️ Advanced Geospatial Analytics")
st.markdown("""
Integrated tactical geospatial intelligence dashboard featuring:

- 📍 Dynamic clustered polling map
- 🏙️ 3D density visualization (GPU Accelerated)
- 🔥 Thermal party support heatmaps
- ⚔️ Spatial battleground mapping
""")
st.markdown("---")

# =========================================================
# DATA INGESTION & TYPE CASTING
# =========================================================
df_units, df_scores, df_merged = load_data()

if df_units.empty:
    st.warning("Data not found. Please ensure the data pipeline has been executed.")
    st.stop()

df_winners = get_winner_per_unit(df_merged)
df_map = pd.merge(df_units, df_winners[['Unit_ID', 'Party_Name', 'Score']], on='Unit_ID', how='left')
df_map.rename(columns={'Party_Name': 'Winning_Party', 'Score': 'Winning_Votes'}, inplace=True)
df_map = df_map.dropna(subset=['Latitude', 'Longitude'])

if df_map.empty:
    st.error("Coordinate data missing. Please update location_coordinates_template.csv.")
    st.stop()

# BUG FIX FOR 3D MAP: Explicitly cast coordinates and numeric columns to float
df_map['Latitude'] = df_map['Latitude'].astype(float)
df_map['Longitude'] = df_map['Longitude'].astype(float)
df_map['Voters_Showed_Up'] = pd.to_numeric(df_map['Voters_Showed_Up'], errors='coerce').fillna(0).astype(float)
df_merged['Latitude'] = df_merged['Latitude'].astype(float)
df_merged['Longitude'] = df_merged['Longitude'].astype(float)

# Spatial Jitter
np.random.seed(42)
df_map['Lat_Jitter'] = df_map['Latitude'] + np.random.normal(0, 0.003, size=len(df_map))
df_map['Lon_Jitter'] = df_map['Longitude'] + np.random.normal(0, 0.003, size=len(df_map))

map_center = [df_map['Latitude'].mean(), df_map['Longitude'].mean()]

# =========================================================
# PARTY COLORS
# =========================================================
PARTY_COLORS_HEX = {
    "พรรคประชาชน": "#F47920", "พรรคเพื่อไทย": "#DA251D", "พรรคภูมิใจไทย": "#203A89",
    "พรรคพลังประชารัฐ": "#0054A6", "พรรครวมไทยสร้างชาติ": "#27488B", "พรรคประชาธิปัตย์": "#00AEEF"
}
def get_hex_color(party):
    return PARTY_COLORS_HEX.get(party, "#808080")

# =========================================================
# STATE-BASED ROUTING (Fixes the WebGL 0x0 Pixel Bug)
# =========================================================
st.markdown("### Select Geospatial View")
macro_view_mode = st.radio(
    "Select Geospatial Layer:",
    [
        "📍 Dynamic Cluster Map", 
        "🏙️ 3D Hexagonal Density", 
        "🔥 Electoral Heatmaps & Battlegrounds"
    ],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("---")

# =========================================================
# VIEW 1 — DYNAMIC CLUSTER MAP
# =========================================================
if macro_view_mode == "📍 Dynamic Cluster Map":
    col_map, col_info = st.columns([7, 3])

    with col_map:
        m = folium.Map(location=map_center, zoom_start=11, tiles="CartoDB positron")
        marker_cluster = MarkerCluster(name="Polling Units")

        for row in df_map.itertuples():
            folium.CircleMarker(
                location=[row.Lat_Jitter, row.Lon_Jitter],
                radius=8,
                tooltip=f"Unit {row.Unit_No}, {row.Subdistrict}",
                color=get_hex_color(row.Winning_Party),
                fill=True, fill_color=get_hex_color(row.Winning_Party), fill_opacity=0.8, weight=1.5
            ).add_to(marker_cluster)

        marker_cluster.add_to(m)
        map_data = st_folium(m, width="100%", height=650, returned_objects=["bounds", "last_object_clicked"])

    with col_info:
        st.subheader("📊 Tactical Intelligence Panel")

        if map_data and map_data.get("last_object_clicked"):
            clicked_lat = map_data["last_object_clicked"]["lat"]
            clicked_lon = map_data["last_object_clicked"]["lng"]

            matched_unit = df_map[
                np.isclose(df_map['Lat_Jitter'], clicked_lat, atol=1e-5) &
                np.isclose(df_map['Lon_Jitter'], clicked_lon, atol=1e-5)
            ]

            if not matched_unit.empty:
                unit = matched_unit.iloc[0]
                st.success(f"**{unit['District']} District** ➔ {unit['Subdistrict']}")
                st.write(f"**Village No:** {unit['Village_No']} | **Unit No:** {unit['Unit_No']}")
                st.markdown("---")
                st.metric("🏆 Winning Party", unit['Winning_Party'], f"{unit['Winning_Votes']} votes")
                st.markdown("---")

                col_m1, col_m2 = st.columns(2)
                col_m1.metric("Turnout", f"{unit['Turnout_Pct']:.2f}%")
                col_m2.metric("Valid Ballots", int(unit['Valid_Ballots']))

                col_m3, col_m4 = st.columns(2)
                col_m3.metric("Invalid Rate", f"{unit['Invalid_Pct']:.2f}%")
                col_m4.metric("No Vote Ballots", int(unit['No_Vote_Ballots']))

                st.markdown("---")
                st.markdown("### Full Party Scoreboard")
                unit_scores = df_scores[df_scores['Unit_ID'] == unit['Unit_ID']].sort_values(by='Score', ascending=False)
                st.dataframe(unit_scores[['Party_Number', 'Party_Name', 'Score']].reset_index(drop=True), width="stretch")

                if st.button("Clear Selection"):
                    st.rerun()
                st.stop()

        if map_data and map_data.get("bounds"):
            bounds = map_data["bounds"]
            sw, ne = bounds["_southWest"], bounds["_northEast"]

            visible_units = df_map[
                (df_map['Lat_Jitter'] >= sw['lat']) & (df_map['Lat_Jitter'] <= ne['lat']) &
                (df_map['Lon_Jitter'] >= sw['lng']) & (df_map['Lon_Jitter'] <= ne['lng'])
            ]

            st.info("Showing aggregate data for all polling stations currently visible on the map.")
            st.metric("Visible Polling Units", len(visible_units))

            if not visible_units.empty:
                col_v1, col_v2 = st.columns(2)
                col_v1.metric("Total Voters Showed Up", f"{visible_units['Voters_Showed_Up'].sum():,}")
                
                avg_turnout = (visible_units['Voters_Showed_Up'].sum() / visible_units['Eligible_Voters'].sum()) * 100
                col_v2.metric("Regional Turnout", f"{avg_turnout:.2f}%")

                st.markdown("### Party Performance in Visible Area")
                visible_scores = df_scores[df_scores['Unit_ID'].isin(visible_units['Unit_ID'])]
                regional_totals = visible_scores.groupby('Party_Name')['Score'].sum().sort_values(ascending=False).head(10).reset_index()
                st.dataframe(regional_totals.style.background_gradient(cmap='Blues'), width="stretch")
        else:
            st.info("👈 Zoom and pan around the map to generate regional summaries.")

# =========================================================
# VIEW 2 — 3D GPU DENSITY (FIXED AGGREGATION & TOOLTIP)
# =========================================================
elif macro_view_mode == "🏙️ 3D Hexagonal Density":
    st.header("🏙️ 3D Spatial Density Engine")
    st.write("""
    This model aggregates localized polling data into a **3D Hexagonal Grid**.
    - Tower height = Total Voter Turnout (SUM)
    - Tower color = Total Invalid Ballots (SUM)
    - WebGL rendering = GPU accelerated analytics
    """)

    df_hex = df_map[['Longitude', 'Latitude', 'Voters_Showed_Up', 'Invalid_Ballots', 'District', 'Subdistrict']].copy()

    layer = pdk.Layer(
        "HexagonLayer",
        df_hex,
        get_position=["Longitude", "Latitude"],
        auto_highlight=True,
        elevation_scale=50, 
        pickable=True,
        extruded=True,
        coverage=1,
        color_range=[
            [255, 255, 204], [255, 237, 160], [254, 217, 118],
            [254, 178, 76], [253, 141, 60], [227, 26, 28]
        ],
        get_elevation_weight="Voters_Showed_Up",
        elevation_aggregation='"SUM"',
        get_color_weight="Invalid_Ballots",
        color_aggregation='"SUM"',
    )

    view_state = pdk.ViewState(longitude=map_center[1], latitude=map_center[0], zoom=10, min_zoom=5, max_zoom=15, pitch=45, bearing=-27.36)

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={
            "html": """
                <div style="font-family: Arial, sans-serif;">
                    <b style="color: #F47920; font-size: 16px;">📍 {points.0.District} District</b><br/>
                    <b style="color: #cccccc;">ตำบล (Subdistrict): {points.0.Subdistrict}</b>
                    <hr style="margin: 8px 0; border: 1px solid #555;">
                    <b>Total Voters (Summed Height):</b> {elevationValue} voters<br/>
                    <b>Total Invalid Ballots (Summed Color):</b> {colorValue} ballots
                </div>
            """,
            "style": {
                "backgroundColor": "#1e1e1e",
                "color": "#ffffff",
                "padding": "15px",
                "borderRadius": "8px",
                "boxShadow": "0px 4px 15px rgba(0,0,0,0.7)",
                "border": "1px solid #333"
            }
        }
    )
    st.pydeck_chart(deck, width="stretch")

# =========================================================
# VIEW 3 — HEATMAPS & BATTLEGROUNDS
# =========================================================
elif macro_view_mode == "🔥 Electoral Heatmaps & Battlegrounds":
    st.header("🔥 Electoral Heatmaps & Battlegrounds")
    st.write("Visualizing spatial intensity and highly contested polling stations.")

    sub_view_mode = st.radio(
        "Select Spatial Layer:", 
        ["🔥 Party Support Heatmap", "⚔️ Hyper-Competitive Battlegrounds (Margin < 5%)"], 
        horizontal=True
    )
    st.markdown("---")

    if sub_view_mode == "🔥 Party Support Heatmap":
        st.write("**Thermal mapping of vote concentration.** Brightly glowing areas indicate massive regional support.")
        
        top_parties = df_merged.groupby('Party_Name')['Score'].sum().nlargest(6).index
        selected_party = st.selectbox("Select Party to Visualize:", top_parties)

        party_data = df_merged[(df_merged['Party_Name'] == selected_party) & (df_merged['Score'] > 0)].copy()

        if not party_data.empty:
            heatmap_layer = pdk.Layer(
                "HeatmapLayer",
                data=party_data,
                opacity=0.9,
                get_position=["Longitude", "Latitude"],
                aggregation="SUM",
                get_weight="Score",
                radiusPixels=50, 
                intensity=1,
                threshold=0.25,
            )

            deck_heatmap = pdk.Deck(
                layers=[heatmap_layer],
                initial_view_state=pdk.ViewState(longitude=map_center[1], latitude=map_center[0], zoom=10, pitch=0),
                map_style="dark" 
            )
            st.pydeck_chart(deck_heatmap, width="stretch")
        else:
            st.warning("No coordinate data available for this party.")

    elif sub_view_mode == "⚔️ Hyper-Competitive Battlegrounds (Margin < 5%)":
        st.write("""
        **Knife-edge races.** These are specific polling units where the difference between the 1st place and 2nd place 
        party was less than 5%. In political science, these are critical units that decide the entire election.
        """)
        
        sorted_scores = df_merged.sort_values(by=['Unit_ID', 'Score'], ascending=[True, False])
        ranked = sorted_scores.groupby('Unit_ID').head(2)

        mov_data = []
        for unit, group in ranked.groupby('Unit_ID'):
            if len(group) == 2:
                margin = group.iloc[0]['Score'] - group.iloc[1]['Score']
                total_valid = df_units[df_units['Unit_ID'] == unit]['Valid_Ballots'].values[0]
                
                if total_valid > 0:
                    margin_pct = (margin / total_valid) * 100
                    if margin_pct < 5: 
                        mov_data.append({
                            'Unit_ID': unit,
                            'Subdistrict': group.iloc[0]['Subdistrict'],
                            'Latitude': float(group.iloc[0]['Latitude']),
                            'Longitude': float(group.iloc[0]['Longitude']),
                            'Winner': group.iloc[0]['Party_Name'],
                            'RunnerUp': group.iloc[1]['Party_Name'],
                            'Margin_Pct': margin_pct
                        })

        df_mov = pd.DataFrame(mov_data)

        if not df_mov.empty:
            col_b1, col_b2 = st.columns([1, 2])
            
            with col_b1:
                st.error(f"🚨 Detected {len(df_mov)} highly contested battleground units.")
                st.dataframe(
                    df_mov[['Subdistrict', 'Winner', 'RunnerUp', 'Margin_Pct']].style.format({'Margin_Pct': '{:.2f}%'}).background_gradient(cmap='Reds_r'),
                    width="stretch"
                )
                
            with col_b2:
                battle_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=df_mov,
                    get_position=["Longitude", "Latitude"],
                    get_fill_color=[220, 20, 60, 200], 
                    get_radius=800,
                    pickable=True,
                )
                
                deck_battle = pdk.Deck(
                    layers=[battle_layer],
                    initial_view_state=pdk.ViewState(longitude=map_center[1], latitude=map_center[0], zoom=10, pitch=0),
                    tooltip={"text": "Subdistrict: {Subdistrict}\nWinner: {Winner}\nRunner Up: {RunnerUp}\nMargin: {Margin_Pct}%"}
                )
                st.pydeck_chart(deck_battle, width="stretch")
        else:
            st.success("No hyper-competitive battlegrounds found. All units were won by a comfortable margin (> 5%).")
