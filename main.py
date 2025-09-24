from fastapi import FastAPI, HTTPException, Query
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os, time, math

# Load YT_API_KEY from .env
load_dotenv()
API_KEY = os.getenv("YT_API_KEY")
if not API_KEY:
    raise RuntimeError("YT_API_KEY not found in environment")

# Build youtube client
youtube = build("youtube", "v3", developerKey=API_KEY)

app = FastAPI()


# Allow Anvil frontend to call API
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.anvil.app", "https://*.anvil.works"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


start_time = time.time()

@app.get("/")
def root():
    return {"message": "FastAPI YouTube analyzer is running"}

@app.get("/health")
def health():
    uptime = round(time.time() - start_time, 1)
    return {"status": "ok", "api_key_loaded": bool(API_KEY), "uptime_s": uptime, "version": "0.1"}

@app.get("/channel")
def get_channel(handle: str):
    try:
        if handle.startswith("UC"):  # channelId
            resp = youtube.channels().list(
                part="snippet,contentDetails,statistics",
                id=handle
            ).execute()
        else:  # handle
            resp = youtube.channels().list(
                part="snippet,contentDetails,statistics",
                forHandle=handle
            ).execute()
        items = resp.get("items", [])
        if not items:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel = items[0]
        return {
            "id": channel["id"],
            "title": channel["snippet"]["title"],
            "description": channel["snippet"]["description"],
            "uploads_playlist": channel["contentDetails"]["relatedPlaylists"]["uploads"],
            "stats": channel["statistics"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analyze")
def analyze_channel(
    channel: str,
    max_videos: int = Query(50, le=200),
    limit: int = Query(5, le=20)
):
    try:
        # Step 1: resolve channel
        if channel.startswith("UC"):
            ch_resp = youtube.channels().list(
                part="snippet,contentDetails,statistics",
                id=channel
            ).execute()
        else:
            ch_resp = youtube.channels().list(
                part="snippet,contentDetails,statistics",
                forHandle=channel
            ).execute()
        items = ch_resp.get("items", [])
        if not items:
            raise HTTPException(status_code=404, detail="Channel not found")
        ch = items[0]
        uploads_playlist = ch["contentDetails"]["relatedPlaylists"]["uploads"]

        # Step 2: collect video IDs
        video_ids = []
        next_page = None
        while len(video_ids) < max_videos:
            pl_resp = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist,
                maxResults=50,
                pageToken=next_page
            ).execute()
            for it in pl_resp.get("items", []):
                video_ids.append(it["contentDetails"]["videoId"])
                if len(video_ids) >= max_videos:
                    break
            next_page = pl_resp.get("nextPageToken")
            if not next_page:
                break

        if not video_ids:
            return {
                "channel": {"id": ch["id"], "title": ch["snippet"]["title"]},
                "sampled_videos": 0,
                "top_engagement": [],
                "top_views": [],
                "videos": []
            }

        # Step 3: fetch stats
        videos_data = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            v_resp = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(batch)
            ).execute()
            for v in v_resp.get("items", []):
                s = v.get("statistics", {})
                views = int(s.get("viewCount", 0))
                likes = int(s.get("likeCount", 0)) if "likeCount" in s else 0
                comments = int(s.get("commentCount", 0)) if "commentCount" in s else 0
                engagement = (likes + comments) / views if views > 0 else 0.0
                incomplete = not ("likeCount" in s and "commentCount" in s)
                videos_data.append({
                    "id": v["id"],
                    "title": v["snippet"]["title"],
                    "publishedAt": v["snippet"]["publishedAt"],
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": engagement,
                    "incomplete": incomplete
                })

        # Step 4: rankings
        top_engagement = sorted(
            videos_data,
            key=lambda x: (x["engagement_rate"], x["views"], x["publishedAt"]),
            reverse=True
        )[:limit]
        top_views = sorted(videos_data, key=lambda x: x["views"], reverse=True)[:limit]

        # Quota estimate
        quota_units = 1 + 2 * math.ceil(len(video_ids) / 50)

        return {
            "channel": {
                "id": ch["id"],
                "title": ch["snippet"]["title"],
                "description": ch["snippet"]["description"],
                "stats": ch["statistics"]
            },
            "sampled_videos": len(videos_data),
            "quota_estimate_units": quota_units,
            "top_engagement": top_engagement,
            "top_views": top_views,
            "videos": videos_data
        }

    except Exception as e:
        # Catch quota errors
        msg = str(e)
        if "quota" in msg.lower() or "403" in msg:
            raise HTTPException(status_code=503, detail="Quota exceeded or restricted")
        raise HTTPException(status_code=500, detail=msg)
