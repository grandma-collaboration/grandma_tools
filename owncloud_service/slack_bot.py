import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackHandler(logging.Handler):
    """Slack handler user to send warning and error logs to a Slack channel"""

    def __init__(self, token, channel):
        super().__init__()
        self.client = WebClient(token=token)
        self.channel = channel
        self.setLevel(logging.WARNING)

    def emit(self, record):
        try:
            emoji = "⚠️" if record.levelname == "WARNING" else "🔴"

            self.client.chat_postMessage(
                channel=self.channel,
                text=f"{emoji} *{record.levelname}*: {self.format(record)}",
            )
        except SlackApiError:
            pass


def setup_logger(name, slack_token=None, slack_channel="#logs"):
    """Logger and Slack (optional) setup"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    if slack_token:
        slack = SlackHandler(slack_token, slack_channel)
        logger.addHandler(slack)

    return logger
