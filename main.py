from datetime import datetime
from json import dump, load
from logging import getLogger, StreamHandler, FileHandler, DEBUG, Formatter
from os import listdir, mkdir
from os.path import exists, dirname, abspath
from pathlib import Path
from sys import stdout
from time import sleep

from PIL import Image

from epd import EPD, EPD_WIDTH, EPD_HEIGHT, implementation, FRAME_DELAY
from ffmpeg import input as ffmpeg_input, probe
from google_client import GoogleClient, MediaType

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)

LOG_DIR = f"{Path.home()}/logs/very-slow-movie-player"

try:
    mkdir(f"{Path.home()}/logs")
except FileExistsError:
    pass

try:
    mkdir(LOG_DIR)
except FileExistsError:
    pass

SH = StreamHandler(stdout)
FH = FileHandler(f"{LOG_DIR}/{datetime.today().strftime('%Y-%m-%d')}.log")

FORMATTER = Formatter(
    "%(asctime)s\t%(name)s\t[%(levelname)s]\t%(message)s", "%Y-%m-%d %H:%M:%S"
)
FH.setFormatter(FORMATTER)
SH.setFormatter(FORMATTER)
LOGGER.addHandler(FH)
LOGGER.addHandler(SH)

DISPLAY = EPD()
GOOGLE = GoogleClient(
    "very-slow-movie-player",
    [
        "https://www.googleapis.com/auth/photoslibrary",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
    ],
)

MOVIE_DIRECTORY = f"{Path.home()}/movies"
INCREMENT = 12
EXTRACT_PATH = "/tmp/vsmp_extract.jpg"
FRAME_PATH = "/tmp/vsmp_frame2.jpg"

PROGRESS_LOG = f"{abspath(dirname(__file__))}/progress_log.json"


def extract_frame(video_path, frame, extract_output_path=EXTRACT_PATH):
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
    """

    LOGGER.info("Extracting frame %i from `%s`", frame, video_path)

    (
        ffmpeg_input(video_path, ss=f"{frame * 41.666666}ms")
        .output(extract_output_path, vframes=1)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


def format_image(image_path, frame_output_path=FRAME_PATH):
    """Formats an image for displaying on the EPD

    Args:
        image_path (str): the name of the file to format
        frame_output_path (str): the path at which to place the frame image file
    """
    pil_im = Image.open(image_path)

    scale_factor = min(EPD_WIDTH / pil_im.size[0], EPD_HEIGHT / pil_im.size[1])

    resize_width = round(pil_im.size[0] * scale_factor)
    resize_height = round(pil_im.size[1] * scale_factor)

    pil_im = pil_im.resize((resize_width, resize_height), Image.ANTIALIAS)

    letterboxed = Image.new("RGB", (EPD_WIDTH, EPD_HEIGHT))
    offset = (
        round((EPD_WIDTH - resize_width) / 2),
        round((EPD_HEIGHT - resize_height) / 2),
    )

    letterboxed.paste(pil_im, offset)

    letterboxed.save(frame_output_path)


def get_progress(file_name, default=0):
    """Get the number of the most recently played frame from the JSON log file
     so we can resume in the case of an early exit

    Args:
        file_name (str): the name of the file being played
        default (int): a default value to return if the file isn't logged

    Returns:
        int: the number of the frame that was played most recently
    """
    with open(PROGRESS_LOG) as fin:
        log_data = load(fin)

    LOGGER.info("Getting progress for `%s`", file_name)

    return log_data.get(file_name, {}).get("current", default)


def set_progress(video_path, current_frame, frame_count=None):
    """Update the JSON log file so we can resume if the program is exited

    Args:
        video_path (str): the path to the file being played
        current_frame (int): which frame has been played most recently
        frame_count (int): the total number of frames in the video
    """
    with open(PROGRESS_LOG) as fin:
        log_data = load(fin)

    progress = {video_path: {"current": current_frame}}

    LOGGER.debug("Updating log for `%s` to frame #%i", video_path, current_frame)

    if frame_count:
        progress[video_path]["total"] = frame_count

    log_data.update(progress)

    with open(PROGRESS_LOG, "w") as fout:
        dump(log_data, fout, indent=2)


def display_image(image_path=FRAME_PATH, display_time=FRAME_DELAY):
    """Display an image on the EPD

    Args:
        image_path (str): the path to the file to display on the EPD
        display_time (Union([int, float])): the number of seconds to display the
         image for
    """

    format_image(image_path)

    LOGGER.info("Displaying `%s` for %s seconds", image_path, display_time)

    # Open JPG in PIL and dither the image into a 1 bit bitmap
    pil_im = Image.open(FRAME_PATH).convert(mode="1", dither=Image.FLOYDSTEINBERG)

    # display the image
    DISPLAY.display(DISPLAY.getbuffer(pil_im))

    sleep(display_time)


def play_video(video_path):
    """Play a video file on the E-Paper display

    Args:
        video_path (str): the path to the file to play

    Raises:
        FileNotFoundError: if the video path doesn't exist
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

    current_frame = get_progress(video_path, 2000 if frame_count >= 10000 else 0)

    h, s = divmod((((frame_count - current_frame) / INCREMENT) * FRAME_DELAY), 3600)
    m, s = divmod(s, 60)

    LOGGER.info(
        "It's going to take %ih%im%is to play this video",
        h,
        m,
        s,
    )

    for frame in range(current_frame, frame_count, INCREMENT):
        set_progress(video_path, frame, frame_count)

        # Use ffmpeg to extract a frame from the movie, crop it,
        # letterbox it and output it as a JPG
        extract_frame(video_path, frame)

        display_image(EXTRACT_PATH)


def choose_next_video():
    """Pick which video to play next. Either find one that hasn't yet been
    finished, or one that hasn't even been started

    Returns:
        str: the name of the video file to start playing
    """

    with open(PROGRESS_LOG) as fin:
        log_data = load(fin)

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
        file_path = f"{MOVIE_DIRECTORY}/{file_name}"
        if skip_reason := {
            not file_name.lower().endswith(".mp4"): f"`{file_name}` is not an mp4",
            file_path in log_data: f"`{file_path}` has already been played",
        }.get(True):
            LOGGER.debug("Skipping: %s", skip_reason)
            continue

        LOGGER.info("`%s` hasn't been played yet, returning", file_path)
        return file_path

    return None


def main():
    """Loops through all videos in the movie directory and then the VSMP Google
    Photos album
    """

    if not exists(PROGRESS_LOG):
        LOGGER.warning("Progress log not found at `%s`", PROGRESS_LOG)
        with open(PROGRESS_LOG, "w") as _fout:
            dump({}, _fout, indent=2)

    # Initialise and clear the screen
    DISPLAY.init()
    DISPLAY.Clear()

    while next_video := choose_next_video():
        try:
            play_video(next_video)
        except Exception as exc:  # pylint: disable=broad-except
            # raise
            LOGGER.exception(
                "Unable to play video: `%s - %s`", type(exc).__name__, exc.__str__()
            )

    for item in GOOGLE.get_album_from_name("Very Slow Movie Player").media_items:
        item.download(width_override=EPD_WIDTH, height_override=EPD_HEIGHT)

        if item.media_type == MediaType.VIDEO:
            play_video(item.local_path)
        elif item.media_type == MediaType.IMAGE:
            display_image(item.local_path, 300)

    DISPLAY.sleep()
    implementation.module_exit()


if __name__ == "__main__":
    main()
