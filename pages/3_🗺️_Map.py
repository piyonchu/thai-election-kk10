"""Geospatial winner-by-ตำบล map. Markers colored by winning party (party-list)."""
from __future__ import annotations

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from utils.data_loader import load_data, winner_by_subdistrict
from utils.parties import party_color

st.set_page_config(page_title="Map", page_icon="🗺️", layout="wide")

units_bch, party_scores, _, _ = load_data()

st.title("🗺️ Winner-by-ตำบล Map")
st.caption(
    "Each marker = one ตำบล. Color = winning party-list party. "
    "Marker radius scales with total valid votes cast there."
)

if party_scores.empty or units_bch.empty:
    st.warning("No party-list data or coordinates available.")
    st.stop()

# Absentee/out-of-area votes have no geography — exclude from the map (still
# counted in the headline totals on the overview page).
absentee_votes = int(party_scores[party_scores["Is_Absentee"]]["Score"].sum())
total_votes = int(party_scores["Score"].sum())

wbs = winner_by_subdistrict(party_scores, "Party_Name")  # excludes absentee by default

coords = (
    units_bch[~units_bch["Is_Absentee"]][["District", "Subdistrict", "Latitude", "Longitude"]]
    .dropna(subset=["Latitude", "Longitude"])
    .drop_duplicates(["District", "Subdistrict"])
)
mapped = wbs.merge(coords, on=["District", "Subdistrict"], how="left")
unmapped = mapped[mapped["Latitude"].isna()][["District", "Subdistrict"]]
mapped = mapped.dropna(subset=["Latitude", "Longitude"])

if mapped.empty:
    st.error(
        "None of the ตำบล could be matched to coordinates. "
        "Update `data/location_coordinates_template.csv`."
    )
    st.stop()

if absentee_votes:
    pct = absentee_votes / total_votes * 100 if total_votes else 0
    st.info(
        f"📮 {absentee_votes:,} absentee votes ({pct:.1f}% of all party-list votes) "
        f"are excluded from this map — they have no ตำบล of origin. "
        f"See the overview page for the absentee breakdown."
    )

if not unmapped.empty:
    rows = ", ".join(f"{d}/{s}" for d, s in unmapped.itertuples(index=False, name=None))
    st.warning(
        f"{len(unmapped)} ตำบล missing coordinates and skipped: {rows}. "
        f"Add them to `data/location_coordinates_template.csv` to plot."
    )

# ---------------------------------------------------------------- map
center = [mapped["Latitude"].mean(), mapped["Longitude"].mean()]
m = folium.Map(location=center, zoom_start=10, tiles="cartodbpositron")

# Radius scaled to votes
vmin, vmax = mapped["Total_Votes"].min(), mapped["Total_Votes"].max()
span = max(vmax - vmin, 1)


def _radius(v: int) -> float:
    return 8 + 22 * (v - vmin) / span


for _, r in mapped.iterrows():
    color = party_color(r["Winner"])
    popup_html = (
        f"<b>{r['District']} / {r['Subdistrict']}</b><br>"
        f"🏆 <b>{r['Winner']}</b> — {int(r['Winner_Votes']):,} votes "
        f"({r['Winner_Share']:.1f}%)<br>"
        f"🥈 {r['Runner_Up']} — {int(r['Runner_Up_Votes']):,} votes<br>"
        f"Margin: <b>{r['Margin_pp']:+.2f} pp</b><br>"
        f"Total valid votes: {int(r['Total_Votes']):,}"
    )
    folium.CircleMarker(
        location=[r["Latitude"], r["Longitude"]],
        radius=_radius(r["Total_Votes"]),
        color=color,
        weight=2,
        fill=True,
        fill_color=color,
        fill_opacity=0.7,
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=f"{r['Subdistrict']} → {r['Winner']} ({r['Winner_Share']:.1f}%)",
    ).add_to(m)

# Legend (top parties only)
top_parties = (
    mapped.groupby("Winner")["Total_Votes"].sum().sort_values(ascending=False).index.tolist()
)
legend_rows = "".join(
    f'<div><span style="display:inline-block;width:14px;height:14px;background:{party_color(p)};'
    f'border:1px solid #555;margin-right:6px;vertical-align:middle"></span>{p}</div>'
    for p in top_parties
)
legend = (
    '<div style="position: fixed; bottom: 20px; left: 20px; z-index:9999; '
    "background: white; padding: 10px 14px; border: 1px solid #999; "
    'border-radius: 6px; font-size: 13px; max-width: 280px;">'
    '<b style="font-size:14px">Winning party</b><br>'
    f"{legend_rows}</div>"
)
m.get_root().html.add_child(folium.Element(legend))

st_folium(m, use_container_width=True, height=620, returned_objects=[])

st.markdown("---")
st.subheader("ตำบล on the map")
view = mapped[
    ["District", "Subdistrict", "Winner", "Winner_Share", "Margin_pp", "Total_Votes"]
].copy()
view["Winner_Share"] = view["Winner_Share"].round(2)
view["Margin_pp"] = view["Margin_pp"].round(2)
st.dataframe(view.sort_values(["District", "Subdistrict"]), hide_index=True, use_container_width=True)
