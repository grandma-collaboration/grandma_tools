import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("config_handler")


def load_env_file(env_file_path: str) -> None:
    """
    Load environment variables from a .env file.

    Args:
        env_file_path: Path to the .env file
    """
    env_path = Path(env_file_path)
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info(f"Loaded configuration from: {env_file_path}")
    else:
        logger.warning(f".env file not found at {env_file_path}")


def get_required_env(var_name: str) -> str:
    """Handle a required environment variable.

    Args:
        var_name: Environment variable to check.
    """
    value = os.getenv(var_name)
    if not value:
        logger.error(f"Required environment variable missing: {var_name}")
        raise ValueError(f"Required environment variable missing: {var_name}")
    return value
