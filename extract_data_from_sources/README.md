# Extract Data from Sources

A Python script to extract and process source data from Skyportal API, including astronomical calculations for extinction, luminosity distance, and classification data.

## Features

- Fetches sources from specified Skyportal group IDs
- Calculates E(B-V) extinction using SFD dust maps
- Computes luminosity distance using multiple methods (altdata, redshift + cosmology)
- Extracts photometric redshift and WISE magnitudes from annotations
- Calculates WISE color differences (W1-W2, W2-W3)
- Determines if sources are galactic based on galactic latitude thresholds
- Exports data to timestamped CSV files

## Requirements

Install the required Python packages:

```bash
pip install -r requirements.txt
```

The script requires:
- `pandas` - Data manipulation and CSV export
- `requests` - API calls to Skyportal
- `astropy` - Astronomical calculations and cosmology
- `dustmaps` - SFD dust map queries for extinction

## Configuration

The script uses a `.env` file for configuration. Follow these steps to set it up:

### 1. Create .env file

Copy the example configuration file and edit it with your settings:

```bash
cp .env.example .env
```

### 2. Configure settings in .env

Edit the `.env` file with your configuration:

```bash
# Required: Your Skyportal API token
SKYPORTAL_API_TOKEN=your_skyportal_api_token_here

# Required: Skyportal API base URL
SKYPORTAL_BASE_URL=https://fritz.science/api

# Required: Group IDs to fetch sources from (comma-separated for multiple groups)
GROUP_IDS=1840

# Optional: Time window filter (ISO 8601 format: YYYY-MM-DDTHH:MM:SS)
# Leave empty to disable time filtering
SAVED_AFTER=2025-11-07T13:00:00
SAVED_BEFORE=2025-12-04T13:00:00

# Required: Maximum number of retries for failed requests
MAX_RETRIES=3

# Required: Directory for dust map data
DUSTMAPS_DATA_DIR=/tmp
```

**To obtain a Skyportal API token:**
1. Log in to your Skyportal instance (e.g., https://fritz.science)
2. Go to your profile settings
3. Generate an API token

### 3. Multiple Group IDs

To fetch from multiple groups, separate IDs with commas:

```bash
GROUP_IDS=1840,2050,3100
```

### 4. Time Window Filtering

To disable time filtering, leave `SAVED_AFTER` and `SAVED_BEFORE` empty:

```bash
SAVED_AFTER=
SAVED_BEFORE=
```

**Note**: All required environment variables must be set in the `.env` file, or the script will raise an error.

## Usage

Run the script:

```bash
python extract_data.py
```

The script will:
1. Download SFD dust maps if not already present (first run only)
2. Fetch sources from each specified group ID
3. Process and calculate astronomical properties
4. Save results to a timestamped CSV file: `data_extraction{YYYYMMDD_HHMMSS}.csv`

## Output

The script generates a CSV file with the following columns:

| Column | Description |
|--------|-------------|
| `source_id` | Unique source identifier |
| `ra` | Right Ascension (degrees) |
| `dec` | Declination (degrees) |
| `t0` | Reference time/epoch |
| `E(B-V)` | Extinction from SFD dust maps |
| `D_L` | Luminosity distance (Mpc) |
| `photo_z` | Photometric redshift from annotations |
| `w1mpro` | WISE W1 magnitude |
| `w2mpro` | WISE W2 magnitude |
| `w3mpro` | WISE W3 magnitude |
| `w1mpro-w2mpro` | W1-W2 color difference |
| `w2mpro-w3mpro` | W2-W3 color difference |
| `classifications` | Semicolon-separated classification labels |
| `is_galactic_b10` | Galactic if \|b\| < 10° |
| `is_galactic_b15` | Galactic if \|b\| < 15° |
| `is_galactic_b20` | Galactic if \|b\| < 20° |
| `group_id` | Skyportal group ID |


## Notes

- First run downloads ~150MB of dust map data
- Processing time depends on number of sources 
- Script replicates SkyPortal's internal calculation logic for consistency
