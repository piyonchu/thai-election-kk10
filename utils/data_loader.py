import pandas as pd
import streamlit as st

@st.cache_data
def load_data():
    """
    Loads and caches the cleaned election data.
    Returns df_units, df_scores, and a merged dataset.
    """
    try:
        df_units = pd.read_csv("data/data_cleaned_units.csv")
        df_scores = pd.read_csv("data/data_cleaned_scores.csv")
        
        # Calculate Turnout Percentage safely to avoid division by zero
        df_units['Turnout_Pct'] = (df_units['Voters_Showed_Up'] / df_units['Eligible_Voters']) * 100
        df_units['Invalid_Pct'] = (df_units['Invalid_Ballots'] / df_units['Used_Ballots']) * 100
        
        # Create a merged DataFrame for easier querying later
        df_merged = pd.merge(df_scores, df_units, on="Unit_ID", how="left")
        
        return df_units, df_scores, df_merged
    except FileNotFoundError:
        st.error("Data files not found. Please ensure CSVs are in the 'data' directory.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data
def get_winner_per_unit(df_merged):
    """
    Identifies the winning party for each specific polling unit.
    """
    # Sort by score descending and drop duplicates on Unit_ID to keep the highest score
    winners = df_merged.sort_values('Score', ascending=False).drop_duplicates(['Unit_ID'])
    return winners[['Unit_ID', 'Party_Name', 'Score', 'District', 'Subdistrict', 'Latitude', 'Longitude']]