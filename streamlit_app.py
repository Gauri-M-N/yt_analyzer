# streamlit_app.py
import streamlit as st
import requests, certifi, ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
import plotly.express as px

# Backend URL
API_BASE = "https://yt-analyzer-md98.onrender.com"  # <-- replace if different

# HTTPS session with certifi-backed context
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(cafile=certifi.where())
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://", SSLAdapter())

st.set_page_config(page_title="YouTube Channel Analyzer", layout="wide")
st.title("YouTube Channel Analyzer")

channel = st.text_input("Enter channel handle or ID (e.g., Google)")
max_videos = st.slider("Max videos to analyze", 10, 200, 50, step=10)

if st.button("Analyze") and channel.strip():
    try:
        url = f"{API_BASE}/analyze?channel={requests.utils.quote(channel.strip())}&max_videos={max_videos}"
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            st.error(f"API error {resp.status_code}: {resp.text}")
            st.stop()

        data = resp.json()
        st.subheader(f"Channel: {data['channel']['title']}")
        st.caption(f"Analyzed {data['sampled_videos']} videos | Quota units: {data.get('quota_estimate_units','?')}")

        # Table
        table = [
            {
                "Title": v["title"],
                "Views": v["views"],
                "Likes": v["likes"],
                "Comments": v["comments"],
                "Engagement (%)": round(v["engagement_rate"] * 100, 2),
            }
            for v in data["videos"]
        ]
        st.dataframe(table, use_container_width=True)

        # Top by engagement
        top = data.get("top_engagement", [])
        if top:
            fig = px.bar(
                x=[t["title"][:60] for t in top],
                y=[round(t["engagement_rate"] * 100, 2) for t in top],
                labels={"x": "Video Title", "y": "Engagement (%)"},
                title="Top by Engagement",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Views vs Engagement scatter
        vids = data["videos"]
        if vids:
            fig2 = px.scatter(
                x=[v["views"] for v in vids],
                y=[round(v["engagement_rate"] * 100, 2) for v in vids],
                hover_name=[v["title"][:80] for v in vids],
                labels={"x": "Views", "y": "Engagement (%)"},
                title="Views vs Engagement",
            )
            st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
