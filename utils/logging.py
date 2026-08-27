import logging
from pathlib import Path


def configure_logging(level: str, log_file: str):
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('joi')
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.handlers.clear()
    handler = logging.FileHandler(path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(handler)
    return logger
