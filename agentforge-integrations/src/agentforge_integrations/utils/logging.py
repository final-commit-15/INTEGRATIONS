import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO"):
    """Configure structured JSON logging."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s %(module)s %(funcName)s",
        timestamp=True,
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Set httpx logging to WARNING to avoid noise
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)