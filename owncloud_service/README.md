# Source watcher README

An automatic monitoring service for new SkyPortal sources that creates structured folders on ownCloud.

## Features

* Real-time monitoring: Watches for new sources saved on SkyPortal
* Automatic folder creation: Organized structure by source and telescope/instrument
* ownCloud integration: Automatic upload to your ownCloud instance
* Slack notifications: Alerts for warnings and errors
* Group filtering: Only processes sources from specified groups
* Duplicate handling: Avoids reprocessing the same sources
* Environment-based configuration: Uses .env files for easy configuration management

## Dependencies

Tool dependencies are available in the `requirements.txt` file.
Required packages:
* `slack-sdk`
* `requests`
* `python-dotenv`

## Configuration 

Create a .env file (or specify a custom path) with the following variables (an example is available in the file .env.default):

1. ownCloud Configuration  

```bash
OWNCLOUD_USERNAME="your_username" # required
OWNCLOUD_TOKEN="your_owncloud_token" # required
OWNCLOUD_USER_ID="your_owncloud_user_id" # required
OWNCLOUD_BASE_URL="https://your-owncloud-instance.com/remote.php/dav/files" # optional, default is Owncloud Grandma url
SAVE_PATH="Candidates/Skyportal" # optional

```

2. Skyportal configuration  

```bash
SKYPORTAL_TOKEN="your_skyportal_api_token" # required
SKYPORTAL_URL="https://your-skyportal-instance.com" # optional, default is Icare instance of Skyportal url
SOURCE_TAG=""  # optional
```

3. Slack Configuration (optional)


Environment variables:

```bash
SLACK_BOT_TOKEN="xoxb-your-bot-token" # optional
SLACK_SERVICE_NAME="owncloud-folder-service"  # optional, ie channel name will be : "#" + SLACK_SERVICE_NAME
```

Bot setup:

1. Create an app at https://api.slack.com/apps
2. OAuth & Permissions → Add chat:write scope
3. Install to Workspace and copy the Bot Token
4. Invite the bot to your channel: /invite @YourBot


## Launch

```bash
python source_watcher.py # use default env file
```

```bash
python source_watcher.py --env-file path/to/your/env/file/.env
```

## Advanced configuration

### Modifying the telescope list

The service supports two modes for handling telescopes and instruments:

#### Predefined List Mode

Uses the telescope list defined in `TELESCOPE_LIST`
Faster processing, no API calls needed.

```bash
USE_BASE_TELESCOPE_LIST="true"
TELESCOPE_LIST="TAROT-TCA,TAROT-TRE,YourNewTelescope, ..."
```

#### Dynamic Mode

Fetches actual telescope and instrument names from SkyPortal API.
Creates folders based on real photometry and spectroscopy data.
More accurate but requires additional API calls.

```bash
USE_BASE_TELESCOPE_LIST="false"
```

### SkyPortal group filtering

Modify `GROUP_IDS` to monitor other groups:

```bash
GROUP_IDS=1,2,3
```

### Monitoring Settings
You can specify when to start monitoring sources:

Via environment variable: `START_TIME="2025-06-01T00:00:00Z"`  
If not specified, defaults to 24 hours ago from startup.

You can also specify the poll internal between the api call to find new sources:

Via environment variable: `POLL_INTERVAL="60"`  
If not specified, defaults to 60 seconds between each api call.
