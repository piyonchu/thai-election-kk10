import streamlit as st
import sys
import os

# Ensure the app can find the utils module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.data_loader import load_data

st.set_page_config(page_title="Raw Data Explorer", page_icon="📑", layout="wide")

# Sidebar Election Type Selector
st.sidebar.header("📊 Data Source")
election_mode = st.sidebar.radio("Select Election Mode:", ["Party List", "Constituency"])

st.title("📑 Raw Data Explorer")
st.markdown(f"Inspect, filter, and export the flattened relational datasets for **{election_mode}**.")
st.markdown("---")

df_units, df_scores, df_merged = load_data(election_mode)

if df_units.empty:
    st.warning("Data not found. Please ensure the data pipeline has been executed.")
    st.stop()

# Use a selectbox to toggle between the tables to save vertical space
view_selection = st.radio("Select Table to View:", ["Unit-Level Data (df_units)", "Score Data (df_scores)", "Merged Full Dataset"])

prefix = "constituency" if election_mode == "Constituency" else "partylist"

if view_selection == "Unit-Level Data (df_units)":
    st.subheader("Polling Unit Master Table")
    st.dataframe(df_units, use_container_width=True)
    
    csv_units = df_units.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Download df_units.csv",
        data=csv_units,
        file_name=f'khonkaen_{prefix}_units_data.csv',
        mime='text/csv',
    )

elif view_selection == "Score Data (df_scores)":
    st.subheader(f"Individual {'Candidate' if election_mode == 'Constituency' else 'Party'} Scores Table")
    st.dataframe(df_scores, use_container_width=True)
    
    csv_scores = df_scores.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Download df_scores.csv",
        data=csv_scores,
        file_name=f'khonkaen_{prefix}_scores_data.csv',
        mime='text/csv',
    )

else:
    st.subheader("Fully Merged Dataset")
    st.dataframe(df_merged, use_container_width=True)
    
    csv_merged = df_merged.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Download merged_data.csv",
        data=csv_merged,
        file_name=f'khonkaen_{prefix}_merged_data.csv',
        mime='text/csv',
    )