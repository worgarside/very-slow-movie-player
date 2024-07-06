"""Downloads videos from a YouTube playlist for playing on the VSMP."""

from __future__ import annotations

from os import environ, getenv
from pathlib import Path
from typing import ClassVar, Final, Literal

from httpx import get
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from wg_utilities.decorators import process_exception
from wg_utilities.functions import force_mkdir
from wg_utilities.loggers import get_streaming_logger
from youtube_dl import YoutubeDL  # type: ignore[import-untyped]

LOGGER = get_streaming_logger(__name__)

BASE_URL: Final = "https://www.googleapis.com/youtube/v3/"
API_KEY: Final = getenv("YT_API_KEY")
PLAYLIST_ID: Final = environ["YT_PLAYLIST_ID"]

OUTPUT_DIR: Final = force_mkdir(
    Path.home().joinpath(getenv("YT_OUTPUT_DIR", "movies").strip("/")).resolve(),
)
YDL_OPTS: Final = {
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
    video_id: str

    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_camel)


class YouTubeVideoInfo(BaseModel):
    """Pydantic model for the YouTube API response."""

    published_at: str
    channel_id: str
    title: str
    description: str
    thumbnails: dict[str, YouTubeVideoThumbnailInfo]
    channel_title: str
    playlist_id: str
    position: int
    resource_id: YouTubeVideoResourceIdInfo
    video_owner_channel_title: str
    video_owner_channel_id: str

    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_camel)

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


@process_exception()
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

    if res.is_error:
        LOGGER.error(res.text)

    res.raise_for_status()

    playlist_items = [
        YouTubeVideoInfo.model_validate(v["snippet"]) for v in res.json().get("items", [])
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
                YouTubeVideoInfo.model_validate(v["snippet"])
                for v in res.json().get("items", [])
            ],
        )

    return playlist_items


@process_exception()
def main() -> None:
    """Iterate through the playlist and download each video."""
    with YoutubeDL(YDL_OPTS) as ydl:
        ydl.download([
            f"https://www.youtube.com/watch?v={video.resource_id.video_id}"
            for video in get_playlist_content(PLAYLIST_ID)
            if not (OUTPUT_DIR / (video.sanitized_title + ".mp4")).is_file()
        ])


if __name__ == "__main__":
    main()
