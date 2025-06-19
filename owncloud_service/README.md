# Source watcher README

An automatic monitoring service for new SkyPortal sources that creates structured folders on ownCloud.

## Features

* Real-time monitoring: Watches for new sources saved on SkyPortal
* Automatic folder creation: Organized structure by source and telescope/instrument
* ownCloud integration: Automatic upload to your ownCloud instance
* Slack notifications: Alerts for warnings and errors
* Group filtering: Only processes sources from specified groups
* Duplicate handling: Avoids reprocessing the same sources

## Dependencies

Tool dependencies are available in the `requirements.txt` file.
For now, the only dependencie is the package `slack-sdk`

## Configuration 


1. ownCloud Configuration  

Modify these constants in source_watcher.py:

```python
OWNCLOUD_USERNAME = "your_username"
OWNCLOUD_TOKEN = "your_owncloud_token"
OWNCLOUD_ID = ("your_owncloud_id") 
```

2. Skyportal configuration  

```python
API_TOKEN = "your_skyportal_api_token"
```

3. Slack Configuration (optional)


Environment variables:

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_SERVICE_NAME="owncloud-folder-service"  # ie channel name will be : "#" + SLACK_SERVICE_NAME
```

Bot setup:

1. Create an app at https://api.slack.com/apps
2. OAuth & Permissions → Add chat:write scope
3. Install to Workspace and copy the Bot Token
4. Invite the bot to your channel: /invite @YourBot


## Launch

```bash
python source_watcher.py --token YOUR_API_TOKEN
```

```bash
python source_watcher.py \
  --token "your_api_token" \
  --instance "https://your-skyportal.com" \
  --path "Target/Folder" \
  --interval 30 \
  --start-time "2025-06-01T00:00:00Z"
```


### Options

|    Option    |           Description          |        Default       |
|:------------:|:------------------------------:|:--------------------:|
| --token      | SkyPortal API token (required) | -                    |
| --instance   | SkyPortal instance URL         | Value in code        |
| --path       | Base path in ownCloud          | Candidates/Skyportal |
| --interval   | Polling interval (seconds)     | 60                   |
| --start-time | Start time (ISO format)        | 1 day ago            |

## Advanced configuration

### Modifying the telescope list

Edit the `TELESCOPE_LIST` constant to add/remove telescopes:

```python
TELESCOPE_LIST = [
    "TAROT-TCA",
    "TAROT-TRE", 
    "YourNewTelescope",
    # ...
]
```

### SkyPortal group filtering

Modify `SKYPORTAL_GROUP_IDS_FILTER` to monitor other groups:

```python
SKYPORTAL_GROUP_IDS_FILTER = [1, 2, 3]
```