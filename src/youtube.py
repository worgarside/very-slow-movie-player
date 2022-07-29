"""Downloads videos from a YouTube playlist for playing on the VSMP"""
from os import getenv, listdir
from os.path import join
from pathlib import Path
from typing import Dict, List, Literal

from dotenv import load_dotenv
from pydantic import BaseModel
from requests import get
from wg_utilities.exceptions import on_exception  # pylint: disable=no-name-in-module
from youtube_dl import YoutubeDL

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


# pylint: disable=too-few-public-methods
class YouTubeVideoThumbnailInfo(BaseModel):
    """Model specifically for the thumbnail object"""

    url: str
    width: int
    height: int


# pylint: disable=too-few-public-methods
class YouTubeVideoResourceIdInfo(BaseModel):
    """Model specifically for the resourceId object"""

    kind: Literal["youtube#video"]
    videoId: str


class YouTubeVideoInfo(BaseModel):
    """Pydantic model for the YouTube API response"""

    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: Dict[str, YouTubeVideoThumbnailInfo]
    channelTitle: str
    playlistId: str
    position: int
    resourceId: YouTubeVideoResourceIdInfo
    videoOwnerChannelTitle: str
    videoOwnerChannelId: str

    @property
    def sanitized_title(self) -> str:
        """
        Returns:
            str: the video title, with no characters that will break file names
        """
        return (
            self.title.replace("<", "_")
            .replace(">", "_")
            .replace(":", "_")
            .replace('"', "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace("|", "_")
            .replace("?", "_")
            .replace("*", "_")
        )


@on_exception()  # type: ignore[misc]
def get_playlist_content(playlist_id: str) -> List[YouTubeVideoInfo]:
    """Get the content of a public playlist on YouTube

    Args:
        playlist_id (str): the ID of the playlist to query

    Returns:
        list: a list of videos in the YouTube playlist
    """
    res = get(
        "https://youtube.googleapis.com/youtube/v3/playlistItems",
        params={
            "key": API_KEY,
            "playlistId": playlist_id,
            "maxResults": 50,
            "part": "snippet",
        },
    )

    res.raise_for_status()

    playlist_items = [
        YouTubeVideoInfo.parse_obj(v["snippet"]) for v in res.json().get("items", [])
    ]

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

        playlist_items.extend(
            [
                YouTubeVideoInfo.parse_obj(v["snippet"])
                for v in res.json().get("items", [])
            ]
        )

    return playlist_items


@on_exception()  # type: ignore[misc]
def main() -> None:
    """Iterates through the playlist and downloads each video"""

    if PLAYLIST_ID is None:
        raise ValueError("Env var `YT_PLAYLIST_ID` not set")

    for video in get_playlist_content(PLAYLIST_ID):

        if join(OUTPUT_DIR, video.sanitized_title + ".mp4") in listdir(OUTPUT_DIR):
            continue

        with YoutubeDL(YDL_OPTS) as ydl:
            ydl.download(
                [f"https://www.youtube.com/watch?v={video.resourceId.videoId}"]
            )


if __name__ == "__main__":
    main()
