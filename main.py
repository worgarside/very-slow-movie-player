from json import dump, load
from logging import getLogger, StreamHandler, FileHandler, DEBUG, Formatter
from os import listdir
from os.path import exists, dirname, abspath, isfile
from pathlib import Path

from PIL import Image
from datetime import datetime
from ffmpeg import input as ffmpeg_input, probe
from sys import stdout
from time import sleep

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)

SH = StreamHandler(stdout)
FH = FileHandler(
    f"{Path.home()}/logs/very-slow-movie-player/{datetime.today().strftime('%Y-%m-%d')}.log"
)

FORMATTER = Formatter(
    "%(asctime)s\t%(name)s\t[%(levelname)s]\t%(message)s", "%Y-%m-%d %H:%M:%S"
)
FH.setFormatter(FORMATTER)
SH.setFormatter(FORMATTER)
LOGGER.addHandler(FH)
LOGGER.addHandler(SH)

try:
    from epd import EPD, EPD_WIDTH, EPD_HEIGHT, implementation

    DISPLAY = EPD()
except RuntimeError:
    DISPLAY = None
    LOGGER.exception("Unable to import E-Paper Driver, running in test mode")

MOVIE_DIRECTORY = f"{Path.home()}/movies"
FRAME_DELAY = 120
INCREMENT = 12
TMP_FRAME_PATH = "/tmp/vsmp_frame.jpg"

PROGRESS_LOG = f"{abspath(dirname(__file__))}/progress_log.json"


def generate_frame(in_filename, frame):
    """Output a frame from the video file to a JPG image to be displayed on
    the E-Paper display

    Args:
        in_filename (str): the name of the file to extract the frame from
        frame (int): the number of the frame to extract
    """

    (
        ffmpeg_input(in_filename, ss=f"{frame * 41.666666}ms")
        .filter("scale", EPD_WIDTH, EPD_HEIGHT, force_original_aspect_ratio=1)
        .filter("pad", EPD_WIDTH, EPD_HEIGHT, -1, -1)
        .output(TMP_FRAME_PATH, vframes=1)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


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


def set_progress(file_name, current_frame, frame_count=None):
    """Update the JSON log file so we can resume if the program is exited

    Args:
        file_name (str): the name of the file being played
        current_frame (int): which frame has been played most recently
        frame_count (int): the total number of frames in the video
    """
    with open(PROGRESS_LOG) as fin:
        log_data = load(fin)

    progress = {file_name: {"current": current_frame}}

    LOGGER.debug("Updating log for `%s` to frame #%i", file_name, current_frame)

    if frame_count:
        progress[file_name]["total"] = frame_count

    log_data.update(progress)

    with open(PROGRESS_LOG, "w") as fout:
        dump(log_data, fout, indent=4)


def play_video(file_name):
    """Play a video file on the E-Paper display

    Args:
        file_name (str): the name of the file to play
    """

    video_path = f"{MOVIE_DIRECTORY}/{file_name}"

    LOGGER.info("Input video is `%s`", video_path)

    if not exists(video_path):
        raise FileNotFoundError(f"Unable to find `{video_path}`")

    # Check how many frames are in the movie
    frame_count = int(probe(video_path)["streams"][0]["nb_frames"])
    LOGGER.info("There are %d frames in this video", frame_count)

    current_frame = get_progress(file_name, 2000)

    LOGGER.info(
        "It's going to take %d hours to play this video",
        (((frame_count - current_frame) / INCREMENT) * FRAME_DELAY) / 3600,
    )

    for frame in range(current_frame, frame_count, INCREMENT):
        set_progress(file_name, frame, frame_count)

        # Use ffmpeg to extract a frame from the movie, crop it,
        # letterbox it and output it as a JPG
        generate_frame(video_path, frame)

        # Open JPG in PIL and dither the image into a 1 bit bitmap
        pil_im = Image.open(TMP_FRAME_PATH).convert(
            mode="1", dither=Image.FLOYDSTEINBERG
        )

        # display the image
        DISPLAY.display(DISPLAY.getbuffer(pil_im))

        sleep(FRAME_DELAY)
        DISPLAY.init()


def choose_next_video():
    """Pick which video to play next. Either find one that hasn't yet been
    finished, or one that hasn't even been started

    Returns:
        str: the name of the video file to start playing
    """

    with open(PROGRESS_LOG) as fin:
        log_data = load(fin)

    LOGGER.info("There are %i videos in the log", len(log_data))

    for file_name in log_data:
        video = log_data[file_name]

        if (total := video.get("total", -1)) - (
            current_frame := video.get("current", -1)
        ) > INCREMENT * 100:
            LOGGER.info(
                "`%s` has only had %i/%i frames played", file_name, current_frame, total
            )
            return file_name

    for file in listdir(MOVIE_DIRECTORY):
        if file not in log_data and file.endswith(".mp4"):
            LOGGER.info("`%s` hasn't been played yet", file)
            return file

        LOGGER.info("Skipping `%s`", file)

    return None


if __name__ == "__main__":
    if not exists(PROGRESS_LOG):
        LOGGER.warning("Progress log not found at `%s`", PROGRESS_LOG)
        with open(PROGRESS_LOG, "w") as _fout:
            dump(dict(), _fout, indent=4)

    if DISPLAY is None:
        raise Exception("EPD Display not initialised")

    # Initialise and clear the screen
    DISPLAY.init()
    DISPLAY.Clear()

    while next_video := choose_next_video():
        play_video(next_video)

    DISPLAY.sleep()
    implementation.module_exit()
