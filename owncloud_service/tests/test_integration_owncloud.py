import os

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv("../.env")

OWNCLOUD_BASE_URL = os.getenv("OWNCLOUD_BASE_URL")
OWNCLOUD_USERNAME = os.getenv("OWNCLOUD_USERNAME")
OWNCLOUD_TOKEN = os.getenv("OWNCLOUD_TOKEN")
OWNCLOUD_USER_ID = os.getenv("OWNCLOUD_USER_ID")
SAVE_PATH = os.getenv("SAVE_PATH")
TELESCOPE_LIST = os.getenv("TELESCOPE_LIST")

TEST_SOURCES = [
    "RedbackMillisecondPulsar",
    "badsource",
    "ZTF20abwysqy",
    "ZTFinGCN",
    "ZTFJ201825+380316",
    "ZTFrlh6cyjh",
    "ZTFe028h94k",
    "ZTF18aabcvnq",
    "ZTF21aaqjmps",
]


def folder_exists(path):
    """Check if folder exists in ownCloud"""
    auth = HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN)
    url = f"{OWNCLOUD_BASE_URL}/{OWNCLOUD_USER_ID}/{path}/"
    try:
        response = requests.request("PROPFIND", url, auth=auth, timeout=5)
        return response.status_code in [200, 207]
    except:
        return False


def get_telescopes():
    """Get telescope list from config"""
    return [tel.strip() for tel in TELESCOPE_LIST.split(",") if tel.strip()]


@pytest.mark.parametrize("source_id", TEST_SOURCES)
def test_source_folder_exists(source_id):
    """Test that source folder exists"""
    source_path = f"{SAVE_PATH}/{source_id}"
    assert folder_exists(source_path), f"Source folder missing: {source_path}"


@pytest.mark.parametrize("source_id", TEST_SOURCES)
def test_source_has_telescope_folders(source_id):
    """Test that source has telescope subfolders"""
    source_path = f"{SAVE_PATH}/{source_id}"

    telescopes = get_telescopes()
    for telescope in telescopes:
        telescope_path = f"{source_path}/{telescope}"
        assert folder_exists(telescope_path), (
            f"Telescope folder missing: {telescope_path}"
        )
