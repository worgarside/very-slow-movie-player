"""Downloads videos from a YouTube playlist for playing on the VSMP."""
from __future__ import annotations

from os import getenv
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel
from requests import get
from wg_utilities.exceptions import on_exception
from youtube_dl import YoutubeDL

load_dotenv()

BASE_URL = "https://www.googleapis.com/youtube/v3/"
API_KEY = getenv("YT_API_KEY")
PLAYLIST_ID = getenv("YT_PLAYLIST_ID")

OUTPUT_DIR = Path.home() / "movies"
YDL_OPTS = {
    "format": "bestvideo[height<=480]/best[height<=480]",
    "outtmpl": f"{OUTPUT_DIR}/%(title)s.%(ext)s",
    "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
}


class YouTubeVideoThumbnailInfo(BaseModel):
    """Model specifically for the thumbnail object."""

    url: str
    width: int
    height: int


class YouTubeVideoResourceIdInfo(BaseModel):
    """Model specifically for the resourceId object."""

    kind: Literal["youtube#video"]
    videoId: str  # noqa: N815


class YouTubeVideoInfo(BaseModel):
    """Pydantic model for the YouTube API response."""

    publishedAt: str  # noqa: N815
    channelId: str  # noqa: N815
    title: str
    description: str
    thumbnails: dict[str, YouTubeVideoThumbnailInfo]
    channelTitle: str  # noqa: N815
    playlistId: str  # noqa: N815
    position: int
    resourceId: YouTubeVideoResourceIdInfo  # noqa: N815
    videoOwnerChannelTitle: str  # noqa: N815
    videoOwnerChannelId: str  # noqa: N815

    @property
    def sanitized_title(self) -> str:
        """Get a version of the title suitable for use as a file name.

        Returns:
            str: the video title, with no characters that will break file names.
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


@on_exception()
def get_playlist_content(playlist_id: str) -> list[YouTubeVideoInfo]:
    """Get the content of a public playlist on YouTube.

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
        timeout=10,
    )

    res.raise_for_status()

    playlist_items = [
        YouTubeVideoInfo.model_validate(v["snippet"])
        for v in res.json().get("items", [])
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
            timeout=10,
        )

        playlist_items.extend(
            [
                YouTubeVideoInfo.parse_obj(v["snippet"])
                for v in res.json().get("items", [])
            ]
        )

    return playlist_items


@on_exception()
def main() -> None:
    """Iterate through the playlist and download each video."""

    if PLAYLIST_ID is None:
        raise ValueError("Env var `YT_PLAYLIST_ID` not set")

    for video in get_playlist_content(PLAYLIST_ID):
        if (OUTPUT_DIR / (video.sanitized_title + ".mp4")).is_file():
            continue

        with YoutubeDL(YDL_OPTS) as ydl:
            ydl.download(
                [f"https://www.youtube.com/watch?v={video.resourceId.videoId}"]
            )


if __name__ == "__main__":
    main()
