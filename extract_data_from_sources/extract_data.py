import os
import time
from datetime import datetime

import dustmaps.sfd
import pandas as pd
import requests
from astropy import cosmology
from astropy import units as u
from astropy.coordinates import SkyCoord
from dotenv import load_dotenv
from dustmaps.config import config

# Load environment variables from .env file
load_dotenv()

# Configuration - all variables must be set in .env file
token = os.getenv("SKYPORTAL_API_TOKEN")
if not token:
    raise ValueError("SKYPORTAL_API_TOKEN environment variable is not set")

base_url = os.getenv("SKYPORTAL_BASE_URL")
if not base_url:
    raise ValueError("SKYPORTAL_BASE_URL environment variable is not set")

# List of group IDs to fetch sources from
group_ids_str = os.getenv("GROUP_IDS")
if not group_ids_str:
    raise ValueError("GROUP_IDS environment variable is not set")
group_ids = [int(gid.strip()) for gid in group_ids_str.split(",")]

# Time window filter for when sources were saved to the group
# Format: "YYYY-MM-DDTHH:MM:SS" (ISO 8601 format)
# Set to empty string in .env to disable filtering
saved_after = os.getenv("SAVED_AFTER") or None
saved_before = os.getenv("SAVED_BEFORE") or None

headers = {"Authorization": f"token {token}"}

max_retries_str = os.getenv("MAX_RETRIES")
if not max_retries_str:
    raise ValueError("MAX_RETRIES environment variable is not set")
max_retries = int(max_retries_str)

# Setup cosmology (using Planck18 as default, matching common SkyPortal config)
cosmo = cosmology.Planck18

# Setup dustmaps for E(B-V) calculation
dustmaps_data_dir = os.getenv("DUSTMAPS_DATA_DIR")
if not dustmaps_data_dir:
    raise ValueError("DUSTMAPS_DATA_DIR environment variable is not set")
config["data_dir"] = dustmaps_data_dir
required_files = ["sfd/SFD_dust_4096_ngp.fits", "sfd/SFD_dust_4096_sgp.fits"]
if any(
    not os.path.isfile(os.path.join(config["data_dir"], required_file))
    for required_file in required_files
):
    try:
        print("Downloading SFD dust maps (this may take a moment)...")
        dustmaps.sfd.fetch()
    except Exception as e:
        print(f"Warning: Could not download dust maps: {e}")

# Initialize SFD query for E(B-V) calculation
try:
    sfd_query = dustmaps.sfd.SFDQuery()
except Exception as e:
    print(f"Warning: Could not initialize SFD query: {e}")
    sfd_query = None


def get_ebv(ra, dec):
    """Calculate E(B-V) extinction for given coordinates.

    This function replicates the logic from skyportal/models/obj.py:740-747
    """
    if sfd_query is None:
        return None

    try:
        coord = SkyCoord(ra, dec, unit="deg")
        return float(sfd_query(coord))
    except Exception:
        return None


def get_luminosity_distance(source):
    """Calculate luminosity distance in Mpc.

    This function replicates the logic from skyportal/models/obj.py:577-620
    Priority order:
    1. altdata fields (dm, parallax, dist_kpc, dist_Mpc, dist_pc, dist_cm)
    2. redshift using cosmology
    """
    altdata = source.get("altdata", {})

    # Check altdata for distance measurements
    if isinstance(altdata, dict):
        if altdata.get("dm") is not None:
            # Distance modulus: D_L = 10^(dm/5) * 10^-5 Mpc
            return (10 ** (float(altdata.get("dm")) / 5.0)) * 1e-5

        if altdata.get("parallax") is not None:
            # Parallax in arcsec: D = 1 Mpc / parallax
            return 1e-6 / float(altdata.get("parallax"))

        if altdata.get("dist_kpc") is not None:
            return float(altdata.get("dist_kpc")) * 1e-3

        if altdata.get("dist_Mpc") is not None:
            return float(altdata.get("dist_Mpc"))

        if altdata.get("dist_pc") is not None:
            return float(altdata.get("dist_pc")) * 1e-6

        if altdata.get("dist_cm") is not None:
            return float(altdata.get("dist_cm")) / 3.085e18

    # Use redshift with cosmology
    redshift = source.get("redshift")
    if redshift:
        # Check if source is in Hubble flow (cz > 350 km/s)
        if redshift * 2.99e5 < 350:  # km/s
            # Too nearby, not in Hubble flow
            return None
        return cosmo.luminosity_distance(redshift).to(u.Mpc).value

    return None


def is_galactic(ra, dec, threshold=15.0):
    """Determine if a source is galactic based on galactic latitude.

    A source is considered galactic if |b| < threshold degrees.
    This replicates the logic from skyportal/models/obj.py:565-574

    Parameters
    ----------
    ra : float
        Right ascension in degrees
    dec : float
        Declination in degrees
    threshold : float
        Threshold for galactic latitude in degrees (default: 15.0)

    Returns
    -------
    bool
        True if |b| < threshold, False otherwise
    """
    try:
        coord = SkyCoord(ra, dec, unit="deg")
        gal_lat = abs(coord.galactic.b.deg)
        return gal_lat < threshold
    except Exception:
        return None


all_sources = []

print(f"Fetching sources from group IDs: {group_ids}")
if saved_after or saved_before:
    print("Time window filter active:")
    if saved_after:
        print(f"  - Sources saved after: {saved_after}")
    if saved_before:
        print(f"  - Sources saved before: {saved_before}")

for group_id in group_ids:
    print(f"\nProcessing group ID: {group_id}")

    url = f"{base_url}/sources"
    params = {
        "group_ids": str(group_id),
        "includeHosts": True,  # Include host galaxy information
        "includeComments": False,  # Don't need comments
        "pageNumber": 1,
        "numPerPage": 250,
        "totalMatches": None,
        "useCache": True,
        "queryID": None,
    }

    if saved_after is not None:
        params["startDate"] = saved_after
    if saved_before is not None:
        params["endDate"] = saved_before

    retrieved = 0
    retries_remaining = max_retries

    while retries_remaining > 0:
        r: requests.Response = requests.get(url, headers=headers, params=params)

        if r.status_code == 429:
            print("Request rate limit exceeded; waiting 1s before trying again...")
            time.sleep(1)
            continue

        data = r.json()

        if data["status"] == "success":
            retries_remaining = max_retries
        else:
            print(f"Error: {data['message']}; waiting 5s before trying again...")
            retries_remaining -= 1
            time.sleep(5)
            continue

        retrieved += len(data["data"]["sources"])

        for s in data["data"]["sources"]:
            source_id = s["id"]
            ra = s["ra"]
            dec = s["dec"]
            t0 = s.get("t0", None)

            # Calculate E(B-V) from RA/Dec using SFD dust maps
            # This replicates the logic from Obj.ebv property
            ebv = get_ebv(ra, dec)

            # Calculate D_L using the same logic as Obj.luminosity_distance property
            # Priority: altdata fields first, then redshift with cosmology
            dl = get_luminosity_distance(s)

            # Extract values from annotations
            photo_z = None
            w1mpro = None
            w2mpro = None
            w3mpro = None

            annotations = s.get("annotations", [])
            for annotation in annotations:
                ann_data = annotation.get("data", {})

                # Look for photo_z
                if photo_z is None and "photo_z" in ann_data:
                    photo_z = ann_data["photo_z"]

                # Look for WISE magnitudes
                if w1mpro is None and "w1mpro" in ann_data:
                    w1mpro = ann_data["w1mpro"]
                if w2mpro is None and "w2mpro" in ann_data:
                    w2mpro = ann_data["w2mpro"]
                if w3mpro is None and "w3mpro" in ann_data:
                    w3mpro = ann_data["w3mpro"]

            # Calculate WISE color differences if we have the magnitudes
            w1_w2 = None
            w2_w3 = None
            if w1mpro is not None and w2mpro is not None:
                try:
                    w1_w2 = float(w1mpro) - float(w2mpro)
                except (ValueError, TypeError):
                    pass
            if w2mpro is not None and w3mpro is not None:
                try:
                    w2_w3 = float(w2mpro) - float(w3mpro)
                except (ValueError, TypeError):
                    pass

            # Extract classifications
            classifications = s.get("classifications", [])
            classification_list = []
            for classification in classifications:
                class_name = classification.get("classification")
                if class_name:
                    classification_list.append(class_name)
            # Join all classifications with semicolon
            classifications_str = (
                "; ".join(classification_list) if classification_list else None
            )

            # Determine if source is galactic based on different thresholds
            is_galactic_10 = is_galactic(ra, dec, threshold=10.0)
            is_galactic_15 = is_galactic(ra, dec, threshold=15.0)
            is_galactic_20 = is_galactic(ra, dec, threshold=20.0)

            all_sources.append(
                {
                    "source_id": source_id,
                    "ra": ra,
                    "dec": dec,
                    "t0": t0,
                    "E(B-V)": ebv,
                    "D_L": dl,
                    "photo_z": photo_z,
                    "w1mpro": w1mpro,
                    "w2mpro": w2mpro,
                    "w3mpro": w3mpro,
                    "w1mpro-w2mpro": w1_w2,
                    "w2mpro-w3mpro": w2_w3,
                    "classifications": classifications_str,
                    "is_galactic_b10": is_galactic_10,
                    "is_galactic_b15": is_galactic_15,
                    "is_galactic_b20": is_galactic_20,
                    "group_id": group_id,
                }
            )

        print(f"Retrieved {retrieved} sources from group {group_id}")

        total_matches = data["data"]["totalMatches"]
        params["queryID"] = data["data"]["queryID"]

        if retrieved >= total_matches:
            break
        params["pageNumber"] += 1

# Create DataFrame and save to CSV
df_sources = pd.DataFrame(all_sources)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"data_extraction_{timestamp}.csv"
df_sources.to_csv(filename, index=False)
print(f"\nSaved {len(all_sources)} sources to {filename}")
