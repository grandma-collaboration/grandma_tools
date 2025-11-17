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

Before running the script, you need to configure it in `extract_data.py`:

### 1. Authentication Token

Set your Skyportal API token as an environment variable:

```bash
export SKYPORTAL_API_TOKEN="your_skyportal_api_token_here"
```

Or add it to your shell configuration file (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
echo 'export SKYPORTAL_API_TOKEN="your_skyportal_api_token_here"' >> ~/.bashrc
source ~/.bashrc
```

To obtain a Skyportal API token:
1. Log in to your Skyportal instance. Example: https://fritz.science
2. Go to your profile settings
3. Generate an API token

**Note**: The script will raise an error if `SKYPORTAL_API_TOKEN` is not set.

### 2. Group IDs

Specify the group IDs you want to fetch sources from:

```python
group_ids = [1840]  # Replace with your actual group IDs
```

You can add multiple group IDs:

```python
group_ids = [1840, 2050, 3100]
```

### 3. Optional Configuration

- **Base URL**: Default is `https://fritz.science/api`
- **Cosmology**: Uses Planck18 by default
- **Dust map location**: Downloads to `/tmp` by default

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
