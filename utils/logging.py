import logging
import os
from pathlib import Path


SECRET_SUFFIXES = ('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD')


class SecretRedactingFormatter(logging.Formatter):
    def __init__(self, format_string: str, secrets):
        super().__init__(format_string)
        self.secrets = tuple(secret for secret in secrets if len(secret) >= 8)

    def format(self, record):
        message = super().format(record)
        for secret in self.secrets:
            message = message.replace(secret, '[REDACTED]')
        return message


def configure_logging(level: str, log_file: str):
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('joi')
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.FileHandler(path, encoding='utf-8')
    secrets = [
        value
        for name, value in os.environ.items()
        if value and name.upper().endswith(SECRET_SUFFIXES)
    ]
    handler.setFormatter(SecretRedactingFormatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        secrets,
    ))
    logger.addHandler(handler)
    return logger
