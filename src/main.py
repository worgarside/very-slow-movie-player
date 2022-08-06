"""Currently just displays photos from an album on Google Photos, but used to display
 videos too"""
from datetime import datetime
from json import dump, load
from logging import DEBUG, getLogger
from os import getenv, listdir
from os.path import abspath, dirname, exists, join
from pathlib import Path
from random import shuffle
from tempfile import gettempdir
from time import sleep
from typing import Dict, Optional, TypedDict, Union

from dotenv import load_dotenv
from PIL import Image
from PIL.Image import Dither, Resampling  # type: ignore[attr-defined]
from wg_utilities.clients import GooglePhotosClient
from wg_utilities.clients.google_photos import MediaType
from wg_utilities.devices.epd import (  # pylint: disable=no-name-in-module
    EPD,
    EPD_HEIGHT,
    EPD_WIDTH,
    FRAME_DELAY,
    implementation,
)
from wg_utilities.exceptions import on_exception  # pylint: disable=no-name-in-module
from wg_utilities.loggers import add_file_handler, add_stream_handler

from ffmpeg import input as ffmpeg_input  # pylint: disable=no-name-in-module
from ffmpeg import probe  # pylint: disable=no-name-in-module

load_dotenv()

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)

add_file_handler(
    LOGGER,
    logfile_path=join(
        Path.home(),
        "logs",
        "very-slow-movie-player",
        f"{datetime.today().strftime('%Y-%m-%d')}.log",
    ),
)
add_stream_handler(LOGGER)

LOGGER.debug("Temp directory is `%s`", gettempdir())

DISPLAY = EPD()
GOOGLE = GooglePhotosClient(
    "very-slow-movie-player",
    [
        "https://www.googleapis.com/auth/photoslibrary",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
    ],
    join(abspath(dirname(__file__)), "client_id.json"),
)

MOVIE_DIRECTORY = join(Path.home(), "movies")
EXTRACT_PATH = join(gettempdir(), "vsmp_extract.jpg")
FRAME_PATH = join(gettempdir(), "vsmp_frame.jpg")
PROGRESS_LOG = join(abspath(dirname(__file__)), "progress_log.json")

INCREMENT = 12


class ProgressInfo(TypedDict):
    """Model for the progress info objects in the log"""

    current: int
    total: int


@on_exception(logger=LOGGER)  # type: ignore[misc]
def extract_frame(
    video_path: str, frame: int, *, extract_output_path: str = EXTRACT_PATH
) -> str:
    """Output a frame from the video file to a JPG image to be displayed on
    the E-Paper display

    Steps:
      - ffmpeg_input: takes a filepath as input and opens the video
        - filename: the name of the file to import
        - ss: the position to seek to
      - filter*:
        - scale: resizes the image
        - force_original_aspect_ratio: set to "decrease", forcing image to be
           downsized if necessary
      - filter*:
        - pad: letterboxes the image
        - -1, -1: x and y coords to place image at within padded area - negative
           defaults to centre

    * These have been replaced by the `format_image` function. Original lines were:
        .filter("scale", EPD_WIDTH, EPD_HEIGHT, force_original_aspect_ratio=1)
        .filter("pad", EPD_WIDTH, EPD_HEIGHT, -1, -1)

    Args:
        video_path (str): the name of the file to extract the frame from
        frame (int): the number of the frame to extract
        extract_output_path (str): the path at which to place the extracted image file

    Returns:
        str: the output path, again provided for ease of use
    """

    LOGGER.info("Extracting frame #%i from `%s`", frame, video_path)

    (
        ffmpeg_input(video_path, ss=f"{frame * 41.666666}ms")
        .output(extract_output_path, vframes=1)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )

    return extract_output_path


@on_exception(logger=LOGGER)  # type: ignore[misc]
def format_image(image_path: str, frame_output_path: str = FRAME_PATH) -> str:
    """Formats an image for displaying on the EPD

    Args:
        image_path (str): the name of the file to format
        frame_output_path (str): the path at which to place the frame image file

    Returns:
        str: the output path - the user will know this anyway, but it's done for ease
         of use
    """

    LOGGER.debug(
        "Formatting image `%s`, outputting to `%s`", image_path, frame_output_path
    )

    pil_im = Image.open(image_path)

    scale_factor = min(EPD_WIDTH / pil_im.size[0], EPD_HEIGHT / pil_im.size[1])

    resize_width = round(pil_im.size[0] * scale_factor)
    resize_height = round(pil_im.size[1] * scale_factor)

    pil_im = pil_im.resize((resize_width, resize_height), Resampling.LANCZOS)

    letterboxed = Image.new("RGB", (EPD_WIDTH, EPD_HEIGHT))
    offset = (
        round((EPD_WIDTH - resize_width) / 2),
        round((EPD_HEIGHT - resize_height) / 2),
    )

    letterboxed.paste(pil_im, offset)

    letterboxed.save(frame_output_path)

    return frame_output_path


@on_exception(logger=LOGGER)  # type: ignore[misc]
def get_progress(file_name: str, default: int = 0) -> int:
    """Get the number of the most recently played frame from the JSON log file,
     so we can resume in the case of an early exit

    Args:
        file_name (str): the name of the file being played
        default (int): a default value to return if the file isn't logged

    Returns:
        int: the number of the frame that was played most recently
    """
    with open(PROGRESS_LOG, encoding="UTF-8") as fin:
        log_data: Dict[str, ProgressInfo] = load(fin)

    LOGGER.info("Getting progress for `%s`", file_name)

    try:
        return log_data[file_name]["current"]
    except KeyError:
        return default


@on_exception(logger=LOGGER)  # type: ignore[misc]
def set_progress(
    video_path: str, current_frame: int, frame_count: Optional[int] = None
) -> None:
    """Update the JSON log file, so we can resume if the program is exited

    Args:
        video_path (str): the path to the file being played
        current_frame (int): which frame has been played most recently
        frame_count (int): the total number of frames in the video
    """
    with open(PROGRESS_LOG, encoding="UTF-8") as fin:
        log_data = load(fin)

    progress = {video_path: {"current": current_frame}}

    LOGGER.debug("Updating log for `%s` to frame #%i", video_path, current_frame)

    if frame_count:
        progress[video_path]["total"] = frame_count

    log_data.update(progress)

    with open(PROGRESS_LOG, "w", encoding="UTF-8") as fout:
        dump(log_data, fout, indent=2)


@on_exception(logger=LOGGER)  # type: ignore[misc]
def display_image(
    image_path: str = FRAME_PATH, display_time: Union[int, float] = FRAME_DELAY
) -> None:
    """Display an image on the EPD

    Args:
        image_path (str): the path to the file to display on the EPD
        display_time (Union([int, float])): the number of seconds to display the
         image for
    """

    output_path = format_image(image_path)

    LOGGER.info("Displaying `%s` for %s seconds", image_path, display_time)

    # Open JPG in PIL and dither the image into a 1 bit bitmap
    pil_im = Image.open(output_path).convert(mode="1", dither=Dither.FLOYDSTEINBERG)

    # display the image
    DISPLAY.display(DISPLAY.getbuffer(pil_im))

    sleep(display_time)


@on_exception(logger=LOGGER)  # type: ignore[misc]
def play_video(video_path: str) -> None:
    """Play a video file on the E-Paper display

    Args:
        video_path (str): the path to the file to play

    Raises:
        FileNotFoundError: if the video path doesn't exist
        Exception: if the video file is un-usable for some reason
    """

    LOGGER.info("Input video is `%s`", video_path)

    if not exists(video_path):
        raise FileNotFoundError(f"Unable to find `{video_path}`")

    # Check how many frames are in the movie
    probe_streams = probe(video_path).get("streams")
    if not probe_streams:
        raise Exception("No streams found in ffmpeg probe")

    frame_count = int(
        probe_streams[0].get("nb_frames") or 24 * float(probe_streams[0]["duration"])
    )

    LOGGER.info("There are %d frames in this video", frame_count)

    if getenv("ALWAYS_RESTART_VIDEOS", "true").lower() == "true":
        LOGGER.debug("Resetting progress log for `%s`", video_path)
        set_progress(video_path, 0, frame_count)

    current_frame = get_progress(video_path, 2000 if frame_count >= 10000 else 0)

    hrs, secs = divmod(
        (((frame_count - current_frame) / INCREMENT) * FRAME_DELAY), 3600
    )
    mins, secs = divmod(secs, 60)

    LOGGER.info(
        "It's going to take %ih%im%is to play this video",
        hrs,
        mins,
        secs,
    )

    for frame in range(current_frame, frame_count, INCREMENT):
        set_progress(video_path, frame, frame_count)

        # Use ffmpeg to extract a frame from the movie, crop it,
        # letterbox it and output it as a JPG
        output_path = extract_frame(video_path, frame)

        display_image(output_path)


@on_exception(logger=LOGGER)  # type: ignore[misc]
def choose_next_video() -> Optional[str]:
    """Pick which video to play next. Either find one that hasn't yet been
    finished, or one that hasn't even been started

    Returns:
        str: the name of the video file to start playing
    """

    with open(PROGRESS_LOG, encoding="UTF-8") as fin:
        log_data: Dict[str, ProgressInfo] = load(fin)

    LOGGER.info("There are %i videos in the log", len(log_data))

    for file_path in log_data:
        if not exists(file_path):
            LOGGER.debug("`%s` no longer available", file_path)
            continue

        video = log_data[file_path]

        if (total := video.get("total", -1)) - (
            current_frame := video.get("current", -1)
        ) > INCREMENT:
            LOGGER.info(
                "`%s` has only had %i/%i frames played", file_path, current_frame, total
            )
            return file_path

    for file_name in listdir(MOVIE_DIRECTORY):
        file_path = join(MOVIE_DIRECTORY, file_name)
        if skip_reason := {
            not file_name.lower().endswith(".mp4"): f"`{file_name}` is not an mp4",
            file_path in log_data: f"`{file_path}` has already been played",
        }.get(True):
            LOGGER.debug("Skipping: %s", skip_reason)
            continue

        LOGGER.info("`%s` hasn't been played yet, returning", file_path)
        return file_path

    return None


@on_exception(logger=LOGGER)  # type: ignore[misc]
def main() -> None:
    """Loops through all videos in the movie directory and then the VSMP Google
    Photos album
    """

    if not exists(PROGRESS_LOG):
        LOGGER.warning("Progress log not found at `%s`", PROGRESS_LOG)
        with open(PROGRESS_LOG, "w", encoding="UTF-8") as _fout:
            dump({}, _fout, indent=2)

    # Initialise and clear the screen
    DISPLAY.init()
    DISPLAY.clear()

    # while next_video := choose_next_video():
    #     try:
    #         play_video(next_video)
    #     except Exception as exc:  # pylint: disable=broad-except
    #         # raise
    #         LOGGER.exception(
    #             "Unable to play video: `%s - %s`", type(exc).__name__, exc.__str__()
    #         )

    media_items = GOOGLE.get_album_from_name("Very Slow Movie Player").media_items
    shuffle(media_items)
    for item in media_items:
        item.download(width_override=EPD_WIDTH, height_override=EPD_HEIGHT)

        if item.media_type == MediaType.VIDEO:
            play_video(item.local_path)
        elif item.media_type == MediaType.IMAGE:
            display_image(item.local_path, 300)

    DISPLAY.sleep()
    implementation.module_exit()


if __name__ == "__main__":
    main()
