#!/usr/bin/env python3
from config.settings import Settings
from config.prompts import SYSTEM_PROMPT
from core.orchestrator import JoiOrchestrator
from interface.terminal import TerminalInterface
from utils.logging import configure_logging


def main():
    settings = Settings.load()
    logger = configure_logging(settings.log_level, settings.log_file)
    joi = JoiOrchestrator(settings, SYSTEM_PROMPT, logger)
    try:
        TerminalInterface(joi).run()
    finally:
        joi.close()


if __name__ == '__main__':
    main()
