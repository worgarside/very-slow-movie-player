"""Constants."""

from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from typing import Final

from wg_utilities.functions import force_mkdir

FRAME_DELAY: Final = 120

REPO_PATH: Final = Path(__file__).parents[1]

MEDIA_DIR: Final = REPO_PATH / ".media"
MOVIE_DIR: Final = force_mkdir(MEDIA_DIR / "movies")
TMP_DIR = Path(gettempdir())


EXTRACT_PATH: Final = TMP_DIR / "vsmp_extract.jpg"
FRAME_PATH: Final = TMP_DIR / "vsmp_frame.jpg"
PROGRESS_LOG: Final = MEDIA_DIR / "progress_log.json"
