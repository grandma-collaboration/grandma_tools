import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from config import get_required_env, load_env_file
from requests.auth import HTTPBasicAuth
from slack_bot import setup_logger

header = {}
seen_sources = set()  # Track seen source ids to avoid duplication


def get_new_sources(
    start_time: datetime, last_iteration: Optional[datetime]
) -> Tuple[List[Dict[str, Any]], datetime]:
    """
    Fetch new sources from SkyPortal with an optional tag filter.

    Updates the last_iteration timestamp before making the API call to ensure
    no sources are missed between polling cycles. Only returns sources that
    haven't been seen before (tracked in the global seen_sources set).

    Args:
        start_time: Initial start time for fetching sources
        last_iteration: Timestamp of last successful fetch, or None for first run

    Returns:
        Tuple of (list of new source dictionaries, updated last iteration timestamp)
    """
    since = last_iteration if last_iteration else start_time

    # Update last iteration before fetching new sources to avoid missing any sources
    last_iteration = datetime.utcnow().replace(tzinfo=timezone.utc)

    response = requests.get(
        f"{INSTANCE_URL}/api/sources",
        params={
            "savedAfter": since.isoformat(),
            "group_ids": SKYPORTAL_GROUP_IDS_FILTER,
        },
        headers=header,
    )
    response.raise_for_status()

    sources = response.json()["data"]["sources"]
    new_sources = []
    for source in sources:
        if source["id"] not in seen_sources:
            new_sources.append(source)
            seen_sources.add(source["id"])
    return new_sources, last_iteration


def get_source_telescope_instrument_strings(source_id: str) -> List[str]:
    """
    Fetch instrument and telescope names for a given source and return combined strings.

    If USE_BASE_TELESCOPE_LIST is True, returns the predefined telescope list.
    Otherwise, queries SkyPortal API for photometry and spectroscopy data to get
    actual instrument names, then resolves telescope names via the instrument API.

    Args:
        source_id: SkyPortal source id

    Returns:
        List of telescope-instrument combination strings or predefined telescope list
    """
    if USE_BASE_TELESCOPE_LIST:
        return TELESCOPE_LIST

    instrument_names = set()
    is_photometry = False

    # Photometry instruments
    try:
        response = requests.get(
            f"{INSTANCE_URL}/api/sources/{source_id}/photometry", headers=header
        )
        response.raise_for_status()

        phot = response.json().get("data")
        if phot:
            is_photometry = True
            for p in phot:
                instrument_names.add(p["instrument_name"])
    except requests.RequestException as e:
        logger.error(f"Error fetching photometry for source {source_id}: {e}")

    # Spectroscopy instruments
    try:
        response = requests.get(
            f"{INSTANCE_URL}/api/sources/{source_id}/spectra", headers=header
        )
        response.raise_for_status()

        spec = response.json().get("data")
        if not spec or not spec.get("spectra"):
            logger.error(
                "No spectroscopy" if is_photometry else "No photometry and spectroscopy"
            )
        else:
            for s in spec["spectra"]:
                instrument_names.add(s["instrument_name"])
    except requests.RequestException as e:
        logger.error(f"Error fetching spectra for source {source_id}: {e}")

    # Fetch telescope names and create strings
    telescope_instrument_strings = []
    for instrument_name in instrument_names:
        telescope_name = get_telescope_names(instrument_name)
        telescope_instrument_strings.append(f"{telescope_name}-{instrument_name}")

    return telescope_instrument_strings


def get_telescope_names(instrument_name: str) -> str:
    """
    Fetch telescope name from the instrument name via SkyPortal API.

    Queries the SkyPortal instrument API to resolve the telescope name
    associated with a given instrument name.

    Args:
        instrument_name: Name of the instrument

    Returns:
        Telescope name associated with the instrument, or "Unknown telescope name" if not found
    """
    try:
        response = requests.get(
            f"{INSTANCE_URL}/api/instrument",
            headers=header,
            params={"name": instrument_name},
        )
        response.raise_for_status()

        instruments = response.json().get("data")
        if instruments:
            return instruments[0]["telescope"]["name"]
        else:
            logger.error(f"Instrument not found: {instrument_name}")
            return "Unknown telescope name"
    except requests.RequestException as e:
        logger.error(f"Error fetching instrument '{instrument_name}': {e}")
        return "Unknown telescope name"


def create_base_folder_on_owncloud() -> bool:
    """Ensure SAVE_PATH directory structure exists."""
    logger.info(f"Checking if SAVE_PATH exists: {SAVE_PATH}")

    check_url = f"{BASE_URL}/{OWNCLOUD_USER_ID}/{SAVE_PATH}/"
    response = requests.request(
        "PROPFIND", check_url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN)
    )

    if response.status_code in [200, 207]:
        logger.info(f"SAVE_PATH already exists: {SAVE_PATH}")
        return True

    logger.info(f"Creating SAVE_PATH hierarchy: {SAVE_PATH}")
    parts = SAVE_PATH.split("/")
    current_path = ""
    logger.info(parts)
    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part

        if not create_folder_on_owncloud(
            f"{BASE_URL}/{OWNCLOUD_USER_ID}/", current_path
        ):
            return False

    logger.info(f"SAVE_PATH ready: {SAVE_PATH}")
    return True


def create_folder_on_owncloud(base_url: str, folder_name: str) -> bool:
    """
    Create a folder on ownCloud.

    Args:
        base_url: Path where to create the new folder
        folder_name: Name or path of the folder to create (relative to SAVE_PATH)

    Returns:
        True if folder was created successfully or already exists, False otherwise
    """
    url = f"{base_url}/{folder_name}"
    response = requests.request(
        "MKCOL", url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN)
    )
    if response.status_code == 201:
        logger.info("✅ Folder " + folder_name + " created successfully.")
        return True
    elif response.status_code == 405:
        logger.warning("⚠️ Folder " + folder_name + " already exists.")
        return True
    elif response.status_code == 401:
        logger.error("❌ Unauthorized — check your username or password.")
    else:
        logger.error(f"❌ Error {response.status_code}: {response.text}")
    return False


def create_owncloud_directory_structure(
    source_id: str, telescope_instrument_strings: List[str]
) -> None:
    """
    Create source and instrument directories on ownCloud.

    Creates a hierarchical folder structure with the source ID as the main folder
    and telescope-instrument combinations as subfolders. Continues processing
    remaining instruments even if individual folder creation fails.

    Args:
        source_id: SkyPortal source id
        telescope_instrument_strings: List of telescope-instrument combinations for subfolders
    """
    if not create_folder_on_owncloud(
        f"{BASE_URL}/{OWNCLOUD_USER_ID}/{SAVE_PATH}", source_id
    ):
        logger.error(f"Failed to create source folder {source_id} on ownCloud.")
        return

    for instrument in telescope_instrument_strings:
        if not create_folder_on_owncloud(
            f"{BASE_URL}/{OWNCLOUD_USER_ID}/{SAVE_PATH}", source_id + "/" + instrument
        ):
            logger.error(
                f"Failed to create instrument folder {instrument} on ownCloud."
            )
            continue


def main_loop(start_time: datetime) -> None:
    """
    Main monitoring loop that watches for new sources and creates folders.

    Continuously polls SkyPortal for new sources and creates corresponding folder
    structures on ownCloud.

    Args:
        start_time: Datetime to start monitoring from
    """
    try:
        create_base_folder_on_owncloud()
    except Exception as e:
        logger.error(f"Error during base folder creation: {e}")

    logger.info("Listening for new sources...\n")

    last_iteration = None
    while True:
        try:
            new_sources, last_iteration = get_new_sources(start_time, last_iteration)
            for source in new_sources:
                try:
                    source_id = source["id"]
                    logger.info(f"New source detected: {source_id}")
                    telescope_instrument_strings = (
                        get_source_telescope_instrument_strings(source_id)
                    )
                    create_owncloud_directory_structure(
                        source_id, telescope_instrument_strings
                    )
                    if not USE_BASE_TELESCOPE_LIST:
                        time.sleep(0.3)  # Sleep to avoid overwhelming the server
                except Exception as e:
                    logger.error(f"Error processing source: {e}")
                    logger.info(
                        "Waiting for 5 seconds and skipping to the next source..."
                    )
                    time.sleep(5)
            if new_sources:
                logger.info("Listening for new sources...")
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(POLL_INTERVAL)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed command line arguments namespace
    """
    parser = argparse.ArgumentParser(
        description=(
            "SkyPortal source watcher\nAuto-create folders in ownCloud for new sources.\n\n"
            "Example:\n"
            "  python source_watcher.py --env-file .env.local\n"
            "  python source_watcher.py --start-time '2025-05-15T00:00:00Z'\n\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env configuration file (default: .env)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Parse arguments and load environment
    args = parse_args()
    load_env_file(args.env_file)

    # Setup logger
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    service_name = os.getenv("SLACK_SERVICE_NAME", "owncloud-folder-service")
    channel = "#" + service_name
    logger = setup_logger(service_name, slack_token, channel)

    try:
        BASE_URL = os.getenv(
            "OWNCLOUD_BASE_URL",
            "https://grandma-owncloud.lal.in2p3.fr/remote.php/dav/files",
        )
        OWNCLOUD_USERNAME = get_required_env("OWNCLOUD_USERNAME")
        OWNCLOUD_TOKEN = get_required_env("OWNCLOUD_TOKEN")
        OWNCLOUD_USER_ID = get_required_env("OWNCLOUD_USER_ID")
        INSTANCE_URL = os.getenv(
            "SKYPORTAL_URL", "https://skyportal-icare.ijclab.in2p3.fr"
        )
        SKYPORTAL_TOKEN = get_required_env("SKYPORTAL_TOKEN")

        SAVE_PATH = os.getenv("SAVE_PATH", "Candidates/Skyportal")
        SOURCE_TAG = os.getenv("SOURCE_TAG", "")
        POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
        SKYPORTAL_GROUP_IDS_FILTER = [
            int(x.strip()) for x in os.getenv("GROUP_IDS", "3").split(",") if x.strip()
        ]
        USE_BASE_TELESCOPE_LIST = (
            os.getenv("USE_BASE_TELESCOPE_LIST", "true").lower() == "true"
        )

        # Default telescope list
        TELESCOPE_LIST = [
            tel.strip()
            for tel in os.getenv(
                "TELESCOPE_LIST",
                "TAROT-TCA,TAROT-TRE,TAROT-TCH,Les-Makes-T60,UBAI-NT-60,UBAI-ST-60,"
                "FRAM-CTA-N,FRAM-Auger,OHP-IRIS,AbAO-T150,VIRT,TRT-SBO,TRT-GAO,"
                "TRT-SRO,TRT-CTO,TNT,ShAO-T60,AbAO-T70,GMG-2.4,Xinglong-2.16m,"
                "OST-CDK,HAO,KAO,OPD-60cm",
            ).split(",")
            if tel.strip()
        ]

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error(
            "Required variables: OWNCLOUD_USERNAME, OWNCLOUD_TOKEN, OWNCLOUD_USER_ID, SKYPORTAL_TOKEN"
        )
        exit(1)
    header = {"Authorization": f"token {SKYPORTAL_TOKEN}"}

    # Parse start time from environment variable
    start_time_str = os.getenv("START_TIME")
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except ValueError:
            logger.error(
                "Invalid START_TIME format. Use ISO format, e.g. '2025-10-20T00:00:00Z'"
            )
            exit(1)
    else:
        start_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=1)

    main_loop(start_time)
