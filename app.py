import streamlit as st
import pandas as pd
from utils.data_loader import load_data

# Must be the very first Streamlit command
st.set_page_config(
    page_title="Khon Kaen District 10 Analytics",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    st.title("🗳️ Khon Kaen District 10: Advanced Election Analytics")
    st.markdown("---")
    
    st.write("""
    ### Welcome to the Election Analytical Engine
    This platform provides an exhaustive, mathematically rigorous analysis of the polling data for Khon Kaen Constituency 10. 
    It bypasses basic business intelligence to provide graduate-level political science and geospatial analytics.
    
    **System Navigation:**
    Please use the sidebar on the left to navigate through the modules:
    
    * **🗺️ Advanced Geospatial Map:** Features 3D GPU-accelerated density rendering, thermal vote-concentration heatmaps, and spatial mapping of hyper-competitive battlegrounds.
    * **📊 Election Dashboard:** Deep-dive fragmentation metrics (Laakso-Taagepera Index), competitiveness categorization, and hierarchical vote distribution.
    * **🚨 Algorithmic Anomaly Detection:** Multivariate machine learning (Isolation Forests), symmetric vote-buying footprint detection, and Benford's Law analysis.
    * **📑 Raw Data Explorer:** Direct querying and CSV exportation of the flattened relational datasets.
    """)
    
    st.markdown("---")

    # Pre-load data to trigger the cache mechanism on startup
    with st.spinner("Initializing Data Pipelines and Machine Learning Models..."):
        df_units, df_scores, df_merged = load_data()
        
    if not df_units.empty:
        st.success(f"System Online: Successfully ingested {len(df_units)} polling units and {len(df_scores)} relational party score records.")
        
        st.subheader("Macro-Level Constituency Summary")
        
        # Display top-level metadata
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Eligible Voters", f"{df_units['Eligible_Voters'].sum():,}")
        with col2:
            st.metric("Total Voters Showed Up", f"{df_units['Voters_Showed_Up'].sum():,}")
        with col3:
            overall_turnout = (df_units['Voters_Showed_Up'].sum() / df_units['Eligible_Voters'].sum()) * 100
            st.metric("Constituency Turnout", f"{overall_turnout:.2f}%")
            
        with col4:
            # Calculate the overall winner of the entire constituency
            if not df_scores.empty:
                overall_totals = df_scores.groupby('Party_Name')['Score'].sum().sort_values(ascending=False)
                winner_name = overall_totals.index[0]
                winner_votes = overall_totals.iloc[0]
                st.metric("🏆 Projected Winner", winner_name, f"{int(winner_votes):,} Total Votes")

        # Add an expander for methodology transparency
        with st.expander("System Methodology & Dependencies"):
            st.write("""
            * **Frontend Framework:** Streamlit (Python)
            * **Geospatial Engine:** PyDeck (Deck.GL WebGL) & Folium
            * **Machine Learning:** Scikit-Learn (Isolation Forest algorithm)
            * **Statistical Mathematics:** SciPy & Numpy
            * **Data Architecture:** The raw nested JSON data has been flattened into a relational schema (Unit-Level primary keys mapped to Party-Level foreign keys) to allow rapid O(1) filtering and aggregation.
            """)

if __name__ == "__main__":
    main()