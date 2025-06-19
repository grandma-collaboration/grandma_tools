import argparse
import time
from datetime import datetime, timedelta, timezone

import requests
from requests.auth import HTTPBasicAuth

# ----- OwnCloud Configuration -----
BASE_URL = "https://grandma-owncloud.lal.in2p3.fr/remote.php/dav/files"
OWNCLOUD_USERNAME = "OWNCLOUD_USERNAME"  # Replace with your ownCloud username
OWNCLOUD_TOKEN = "OWNCLOUD_TOKEN"  # Replace with your ownCloud token
OWNCLOUD_ID = (
    "OWNCLOUD_ID"  # Replace with your ownCloud ID (from settings, WebDAV section)
)
# -----------------------------------

# ----- Configuration -----
INSTANCE_URL = "https://skyportal-icare.ijclab.in2p3.fr"  # Instance URL
API_TOKEN = "API_TOKEN"  # Replace with your API token
SAVE_PATH = (
    "Candidates/Skyportal"  # Base directory where source folders will be created
)
SOURCE_TAG = ""  # Optional tag to filter sources
POLL_INTERVAL = 60  # Polling interval in seconds
SKYPORTAL_GROUP_IDS_FILTER = [
    3
]  # save only sources saved to one of these skyportal groups IDs (GRANDNMA group ID is 3)
USE_BASE_TELESCOPE_LIST = True  # Use predefined telescope list or fetch from SkyPortal
# ----------------------------------

TELESCOPE_LIST = [
    "TAROT-TCA",
    "TAROT-TRE",
    "TAROT-TCH",
    "Les-Makes-T60",
    "UBAI-NT-60",
    "UBAI-ST-60",
    "FRAM-CTA-N",
    "FRAM-Auger",
    "OHP-IRIS",
    "AbAO-T150",
    "VIRT",
    "TRT-SBO",
    "TRT-GAO",
    "TRT-SRO",
    "TRT-CTO",
    "TNT",
    "ShAO-T60",
    "AbAO-T70",
    "GMG-2.4",
    "Xinglong-2.16m",
    "OST-CDK",
    "HAO",
    "KAO",
    "OPD-60cm",
]

header = {}
seen_sources = set()  # Track seen source ids to avoid duplication


def get_new_sources(start_time, last_iteration):
    """Fetch new sources from SkyPortal with an optional tag filter."""
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


def get_source_telescope_instrument_strings(source_id):
    """Fetch instrument and telescope names for a given source and return combined strings."""
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
        print(f"Error fetching photometry for source {source_id}: {e}")

    # Spectroscopy instruments
    try:
        response = requests.get(
            f"{INSTANCE_URL}/api/sources/{source_id}/spectra", headers=header
        )
        response.raise_for_status()

        spec = response.json().get("data")
        if not spec or not spec.get("spectra"):
            print(
                "No spectroscopy" if is_photometry else "No photometry and spectroscopy"
            )
        else:
            for s in spec["spectra"]:
                instrument_names.add(s["instrument_name"])
    except requests.RequestException as e:
        print(f"Error fetching spectra for source {source_id}: {e}")

    # Fetch telescope names and create strings
    telescope_instrument_strings = []
    for instrument_name in instrument_names:
        telescope_name = get_telescope_names(instrument_name)
        telescope_instrument_strings.append(f"{telescope_name}-{instrument_name}")

    return telescope_instrument_strings


def get_telescope_names(instrument_name):
    """Fetch telescope name from the instrument name."""
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
            print(f"Instrument not found: {instrument_name}")
            return "Unknown telescope name"
    except requests.RequestException as e:
        print(f"Error fetching instrument '{instrument_name}': {e}")
        return "Unknown telescope name"


def create_folder_on_owncloud(folder_name):
    """Create a folder on ownCloud."""
    url = f"{BASE_URL}/{OWNCLOUD_ID}/{SAVE_PATH}/{folder_name}"
    response = requests.request(
        "MKCOL", url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN)
    )
    if response.status_code == 201:
        print("✅ Folder " + folder_name + " created successfully.")
        return True
    elif response.status_code == 405:
        print("⚠️ Folder " + folder_name + " already exists.")
        return True
    elif response.status_code == 401:
        print("❌ Unauthorized — check your username or password.")
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
    return False


def create_owncloud_directory_structure(source_id, telescope_instrument_strings):
    """Create source and instrument directories on ownCloud."""
    if not create_folder_on_owncloud(source_id):
        print(f"Failed to create source folder {source_id} on ownCloud.")
        return

    for instrument in telescope_instrument_strings:
        if not create_folder_on_owncloud(source_id + "/" + instrument):
            print(f"Failed to create instrument folder {instrument} on ownCloud.")
            continue


def main_loop(start_time):
    if not create_folder_on_owncloud(""):
        print("Failed to create base folder on ownCloud. Exiting.")
        return
    print("Listening for new sources...\n")

    last_iteration = None
    while True:
        try:
            new_sources, last_iteration = get_new_sources(start_time, last_iteration)
            for source in new_sources:
                try:
                    source_id = source["id"]
                    print(f"New source detected: {source_id}")
                    telescope_instrument_strings = (
                        get_source_telescope_instrument_strings(source_id)
                    )
                    create_owncloud_directory_structure(
                        source_id, telescope_instrument_strings
                    )
                    print()
                    if not USE_BASE_TELESCOPE_LIST:
                        time.sleep(0.3)  # Sleep to avoid overwhelming the server
                except Exception as e:
                    print(f"Error processing source: {e}")
                    print("Waiting for 5 seconds and skipping to the next source...")
                    time.sleep(5)
            if new_sources:
                print("Listening for new sources...")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(POLL_INTERVAL)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "SkyPortal source watcher\nAuto-create folders in ownCloud for new sources.\n\n"
            "Example:\n"
            "  python source_watcher.py --start-time '2025-05-15T00:00:00Z'\n\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--instance",
        type=str,
        default=INSTANCE_URL,
        help="SkyPortal instance URL (default: %(default)s)",
    )
    parser.add_argument("--token", type=str, help="API token")
    parser.add_argument(
        "--path",
        type=str,
        default=SAVE_PATH,
        help="Base directory where source folders will be created (default: %(default)s)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=POLL_INTERVAL,
        help="Polling interval in seconds (default: %(default)s)",
    )
    # parser.add_argument("--tag", type=str, default=SOURCE_TAG,
    #                     help="Source tag to filter (default: %(default)s)")
    parser.add_argument(
        "--start-time",
        type=str,
        help="Start UTC time for fetching new sources in ISO format, e.g. '2025-05-15T00:00:00Z' (default: 1 day ago)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Override default values with command line arguments
    INSTANCE_URL = args.instance
    API_TOKEN = args.token or API_TOKEN
    SAVE_PATH = args.path
    # SOURCE_TAG = args.tag
    POLL_INTERVAL = args.interval

    if not API_TOKEN:
        print("API token is required. Please provide it using --token.")
        exit(1)
    header = {"Authorization": f"token {API_TOKEN}"}

    if args.start_time:
        try:
            start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
        except ValueError:
            print(
                "Invalid start time format. Use ISO format, e.g. '2025-10-20T00:00:00Z'"
            )
            exit(1)
    else:
        start_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=1)

    main_loop(start_time)
