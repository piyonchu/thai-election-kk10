"""Raw data explorer — view and download the four flattened tables."""
from __future__ import annotations

import streamlit as st

from utils.data_loader import load_data

st.set_page_config(page_title="Raw Data", page_icon="📑", layout="wide")

units_bch, party_scores, units_normal, candidate_scores = load_data()

st.title("📑 Raw Data Explorer")
st.caption("All four flattened tables loaded from the OCR'd JSON ballots.")

tabs = st.tabs(
    [
        f"Units (party-list) · {len(units_bch):,}",
        f"Party scores · {len(party_scores):,}",
        f"Units (constituency) · {len(units_normal):,}",
        f"Candidate scores · {len(candidate_scores):,}",
    ]
)

for tab, df, name in zip(
    tabs,
    (units_bch, party_scores, units_normal, candidate_scores),
    ("units_bch", "party_scores", "units_normal", "candidate_scores"),
):
    with tab:
        st.dataframe(df, use_container_width=True, hide_index=True)
        if not df.empty:
            st.download_button(
                label=f"Download {name}.csv",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{name}.csv",
                mime="text/csv",
            )
