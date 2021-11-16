"""Custom client for interacting with Google's APIs"""

from copy import deepcopy
from enum import Enum, auto
from json import dump, load, dumps
from logging import getLogger, DEBUG, StreamHandler, Formatter
from os import remove
from os.path import dirname, abspath, join, isfile
from pathlib import Path
from sys import stdout
from tempfile import NamedTemporaryFile
from webbrowser import open as open_browser

from dateutil import parser as date_parser
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from requests import get

with open(join(abspath(dirname(__file__)), "client_id.json")) as fin:
    CLIENT_ID_JSON = load(fin)

LOCAL_MEDIA_DIRECTORY = join(abspath(dirname(__file__)), "media_downloads")

SH = StreamHandler(stdout)

FORMATTER = Formatter(
    "%(asctime)s\t%(name)s\t[%(levelname)s]\t%(message)s", "%Y-%m-%d %H:%M:%S"
)
SH.setFormatter(FORMATTER)
LOGGER = getLogger(__name__)
LOGGER.addHandler(SH)
LOGGER.setLevel(DEBUG)


def mkdir(target_path, path_is_file=False):
    """Creates all directories needed for the given path

    Args:
        target_path (str): the path to the directory which needs to be created
        path_is_file (bool): flag for whether the path is for a file, in which case
         the final part of the path will not be created

    Returns:
        str: directory_path that was passed in
    """
    if path_is_file:
        Path(dirname(target_path)).mkdir(exist_ok=True, parents=True)
    else:
        Path(target_path).mkdir(exist_ok=True, parents=True)

    return target_path


class MediaType(Enum):
    """Enum for all potential media types"""

    IMAGE = auto()
    VIDEO = auto()


class Album:
    """Class for Google Photos albums and their metadata/content

    Args:
        json (dict): the JSON which is returned from the Google Photos API when
         describing the album
        google_client (GoogleClient): an active Google client which can be used to
         list media items

    """

    def __init__(self, json, google_client=None):
        self.json = json
        self._media_items = None

        self.google_client = google_client

    @property
    def media_items(self):
        """Lists all media items in the album

        Returns:
            list: a list of MediaItem instances, representing the contents of the album
        """
        if not self._media_items:
            self._media_items = [
                MediaItem(item)
                for item in self.google_client.list_items(
                    self.google_client.session.post,
                    "https://photoslibrary.googleapis.com/v1/mediaItems:search",
                    "mediaItems",
                    params={"albumId": self.id},
                )
            ]

        return self._media_items

    @property
    def title(self):
        """
        Returns:
            str: the title of the album
        """
        return self.json.get("title")

    @property
    def id(self):
        """
        Returns:
            str: the ID of the album
        """
        return self.json.get("id")

    @property
    def media_items_count(self):
        """
        Returns:
            int: the number of media items within the album
        """
        return int(self.json.get("mediaItemsCount", "-1"))

    def __str__(self):
        return f"{self.title}: {self.id}"


class MediaItem:
    """Class for representing a MediaItem and its metadata/content

    Args:
        json (dict): the JSON returned from the Google Photos API, which describes
        this media item
    """

    def __init__(self, json):
        self.json = json
        self.local_path = join(
            LOCAL_MEDIA_DIRECTORY,
            date_parser.parse(
                json.get("mediaMetadata", {}).get("creationTime")
            ).strftime("%Y/%m/%d"),
            json["filename"],
        )

    def download(self, width_override=None, height_override=None, force_download=False):
        """Download the media item to local storage. The width/height overrides do
        not apply to videos

        Args:
            width_override (int): the width override to use when downloading the file
            height_override (int): the height override to use when downloading the file
            force_download (bool): flag for forcing a download, even if it exists
             locally already
        """
        if not self.stored_locally or force_download:
            width = width_override or self.width
            height = height_override or self.height

            LOGGER.debug("Downloading %s (%sx%s)", self.filename, width, height)

            param_str = {
                MediaType.IMAGE: f"=w{width}-h{height}",
                MediaType.VIDEO: "=dv",
            }.get(self.media_type, "")

            with open(mkdir(self.local_path, path_is_file=True), "wb") as fout:
                fout.write(get(f"{self.json['baseUrl']}{param_str}").content)

    @property
    def bytes(self):
        """Opens the local copy of the file (downloading it first if necessary) and
        reads the binary content of it

        Returns:
            bytes: the binary content of the file
        """
        if not self.stored_locally:
            self.download()

        with open(self.local_path, "rb") as fin:
            bytes_content = fin.read()

        return bytes_content

    @property
    def stored_locally(self):
        """
        Returns:
            bool: flag for if the file exists locally
        """
        return isfile(self.local_path)

    @property
    def filename(self):
        """
        Returns:
            str: the media item's file name
        """
        return self.json.get("filename")

    @property
    def height(self):
        """
        Returns:
            int: the media item's height
        """
        return int(self.json.get("mediaMetadata", {}).get("height", "-1"))

    @property
    def width(self):
        """
        Returns:
            int: the media item's width
        """
        return int(self.json.get("mediaMetadata", {}).get("width", "-1"))

    @property
    def media_type(self):
        """Determines the media item's file type from the JSON

        Returns:
            MediaType: the media type (image, video, etc.) for this item
        """
        mime_type = self.json.get("mimeType", "")

        return {
            "image" in mime_type: MediaType.IMAGE,
            "video" in mime_type: MediaType.VIDEO,
        }.get(True)

    def __str__(self):
        return dumps(self.json, indent=4, default=str)


class GoogleClient:
    """Custom client for interacting with the Google APIs

    Args:
        project (str): the name of the project which this client is being used for
        scopes (list): a list of scopes the client can be given
    """

    DEFAULT_PARAMS = {
        "pageSize": "50",
    }
    CREDS_FILE_PATH = join(abspath(dirname(__file__)), "google_api_creds.json")

    def __init__(self, project, scopes=None):
        self.project = project
        self.scopes = scopes or []

        self._all_credentials = None
        self._session = None

        self._albums = None

    def list_items(self, method, url, list_key, *, params=None):
        """Generic method for listing items on Google's API(s)

        Args:
            method (callable): the Google client session method to use
            url (str): the API endpoint to send a request to
            list_key (str): the key to use in extracting the data from the response
            params (dict): any extra params to be passed in the request

        Returns:
            list: a list of dicts, each representing an item from the API
        """
        params = (
            {**self.DEFAULT_PARAMS, **params}
            if params
            else deepcopy(self.DEFAULT_PARAMS)
        )
        LOGGER.info(
            "Listing all items at endpoint `%s` with params %s", url, dumps(params)
        )

        res = method(url, params=params)

        item_list = res.json().get(list_key, [])

        while next_token := res.json().get("nextPageToken"):
            res = method(
                url,
                params={**params, "pageToken": next_token},
            )
            item_list.extend(res.json().get(list_key, []))
            LOGGER.debug("Found %i items so far", len(item_list))

        return item_list

    def delete_creds_file(self):
        """Delete the local creds file"""
        try:
            remove(self.CREDS_FILE_PATH)
        except FileNotFoundError:
            pass

    def get_album_from_name(self, album_name):
        """Gets an album definition from the Google API based on the album name

        Args:
            album_name (str): the name of the album to find

        Returns:
            Album: an Album instance, with all metadata etc.

        Raises:
            FileNotFoundError: if the client can't find an album with the correct name
        """

        LOGGER.info("Getting metadata for album `%s`", album_name)
        for album in self.albums:
            if album.title == album_name:
                return album

        raise FileNotFoundError(f"Unable to find album with name {album_name}")

    @property
    def albums(self):
        """Lists all albums in the active Google account

        Returns:
            list: a list of Album instances
        """
        if not self._albums:
            self._albums = [
                Album(res, self)
                for res in self.list_items(
                    self.session.get,
                    "https://photoslibrary.googleapis.com/v1/albums",
                    "albums",
                )
            ]

        return self._albums

    @property
    def credentials(self):
        try:
            with open(self.CREDS_FILE_PATH) as fin:
                self._all_credentials = load(fin)
        except FileNotFoundError:
            LOGGER.info("Unable to find local creds file")
            self._all_credentials = {}

        with NamedTemporaryFile() as tmp_client_id_json:
            if self.project not in self._all_credentials:
                LOGGER.info("Performing first time login for `%s`", self.project)

                with open(tmp_client_id_json.name, "w") as fout:
                    dump(CLIENT_ID_JSON, fout)

                flow = Flow.from_client_secrets_file(
                    tmp_client_id_json.name,
                    scopes=self.scopes,
                    redirect_uri="urn:ietf:wg:oauth:2.0:oob",
                )

                auth_uri = flow.authorization_url()
                auth_url = auth_uri[0]
                LOGGER.debug("Opening %s", auth_url)
                open_browser(auth_url)
                code = input("Enter the authorization code: ")
                flow.fetch_token(code=code)

                self.credentials = {
                    "token": flow.credentials.token,
                    "refresh_token": flow.credentials.refresh_token,
                    "id_token": flow.credentials.id_token,
                    "scopes": flow.credentials.scopes,
                    "token_uri": flow.credentials.token_uri,
                    "client_id": flow.credentials.client_id,
                    "client_secret": flow.credentials.client_secret,
                }

            with open(tmp_client_id_json.name, "w") as fout:
                dump(self._all_credentials[self.project], fout)

            return Credentials.from_authorized_user_file(
                tmp_client_id_json.name, self.scopes
            )

    @credentials.setter
    def credentials(self, value):
        """
        Args:
            value (dict): the new values to use for the creds for this project
        """
        self._all_credentials[self.project] = value

        with open(self.CREDS_FILE_PATH, "w") as fout:
            dump(self._all_credentials, fout)

    @property
    def session(self):
        """Uses the Credentials object to sign into an authorized Google API session

        Returns:
            AuthorizedSession: an active, authorized Google API session
        """
        if not self._session:
            self._session = AuthorizedSession(self.credentials)

        return self._session
