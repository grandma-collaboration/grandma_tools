import logging
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackHandler(logging.Handler):
    """Slack handler used to send warning and error logs to a Slack channel.

    This handler automatically sends WARNING and ERROR level logs to a specified
    Slack channel using the Slack Web API.
    """

    def __init__(self, token: str, channel: str) -> None:
        """
        Initialize the Slack handler.

        Args:
            token: Slack bot token for authentication
            channel: Slack channel name to send messages to
        """
        super().__init__()
        self.logger = logging.getLogger("slack_bot")
        self.client = WebClient(token=token)
        self.channel = channel
        self.setLevel(logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to Slack.

        Args:
            record: The log record to send to Slack
        """
        try:
            emoji = "⚠️" if record.levelname == "WARNING" else "🔴"

            self.client.chat_postMessage(
                channel=self.channel,
                text=f"{emoji} *{record.levelname}*: {self.format(record)}",
            )
        except SlackApiError as e:
            self.logger.error(
                f"Failed to send log message to Slack channel {self.channel}: {e.response['error']}"
            )


def setup_logger(
    name: str, slack_token: Optional[str] = None, slack_channel: str = "#logs"
) -> logging.Logger:
    """
    Set up a logger with console output and optional Slack notifications.

    Args:
        name: Name of the logger
        slack_token: Optional Slack bot token for notifications
        slack_channel: Slack channel for notifications (default: "#logs")

    Returns:
        Configured logger instance
    """

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    if slack_token:
        slack = SlackHandler(slack_token, slack_channel)
        logger.addHandler(slack)

    return logger
