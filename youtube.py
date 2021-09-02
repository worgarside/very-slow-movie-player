from os import listdir
from os.path import join
from pathlib import Path

from requests import get
from youtube_dl import YoutubeDL
from dotenv import load_dotenv
from os import getenv

load_dotenv()

BASE_URL = "https://www.googleapis.com/youtube/v3/"
API_KEY = getenv("YT_API_KEY")
PLAYLIST_ID = getenv("YT_PLAYLIST_ID")

OUTPUT_DIR = f"{Path.home()}/movies"
YDL_OPTS = {
    "format": "bestvideo[height<=480]/best[height<=480]",
    "outtmpl": f"{OUTPUT_DIR}/%(title)s.%(ext)s",
    "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
}


def get_playlist_content(playlist_id):
    res = get(
        "https://youtube.googleapis.com/youtube/v3/playlistItems",
        params={
            "key": API_KEY,
            "playlistId": playlist_id,
            "maxResults": 50,
            "part": "snippet",
        },
    )

    playlist_items = [v["snippet"] for v in res.json().get("items", [])]

    while token := res.json().get("nextPageToken"):
        res = get(
            f"{BASE_URL}playlistItems",
            params={
                "key": API_KEY,
                "playlistId": playlist_id,
                "maxResults": 50,
                "part": "snippet",
                "pageToken": token,
            },
        )

        playlist_items.extend([v["snippet"] for v in res.json().get("items", [])])

    return playlist_items


def main():
    for video in get_playlist_content(PLAYLIST_ID):
        sanitized_title = (
            video["title"]
            .replace("<", "_")
            .replace(">", "_")
            .replace(":", "_")
            .replace('"', "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace("|", "_")
            .replace("?", "_")
            .replace("*", "_")
        )

        if join(OUTPUT_DIR, sanitized_title + ".mp4") in listdir(OUTPUT_DIR):
            continue

        video_id = video["resourceId"]["videoId"]
        with YoutubeDL(YDL_OPTS) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])


if __name__ == "__main__":
    main()
