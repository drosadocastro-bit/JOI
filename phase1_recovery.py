import logging
import subprocess

from config.prompts import SYSTEM_PROMPT
from config.settings import Settings
from core.orchestrator import JoiOrchestrator


def run_lms(*args):
    return subprocess.run(
        ['lms', 'server', *args],
        check=True,
        capture_output=True,
        text=True,
    )


def main():
    settings = Settings.load()
    logger = logging.getLogger('joi.phase1.recovery')
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    joi = JoiOrchestrator(settings, SYSTEM_PROMPT, logger)
    marker = 'RECOVERY-27'

    initial_health = joi.status()['brain']
    if not initial_health.get('ok') or not initial_health.get('selected_model_visible'):
        raise RuntimeError('LM Studio and the configured model must be online before this test')

    first_reply = joi.chat(
        f'Remember the marker {marker}. Reply with exactly PRE-RESTART OK.'
    )
    if first_reply.strip() != 'PRE-RESTART OK':
        raise RuntimeError(f'Unexpected pre-restart reply: {first_reply!r}')
    history_before_outage = joi.memory.snapshot()

    server_restarted = False
    try:
        run_lms('stop')
        offline_health = joi.status()['brain']
        if offline_health.get('ok'):
            raise RuntimeError('JOI still reports LM Studio online after server stop')

        try:
            joi.chat('This request must fail while LM Studio is offline.')
        except RuntimeError:
            pass
        else:
            raise RuntimeError('Chat unexpectedly succeeded while LM Studio was offline')
        if joi.memory.snapshot() != history_before_outage:
            raise RuntimeError('Session history changed after the failed offline request')

        run_lms('start', '--port', '1234', '--bind', '127.0.0.1')
        server_restarted = True
        recovered_health = joi.status()['brain']
        if not recovered_health.get('ok'):
            raise RuntimeError('JOI did not detect LM Studio after restart')
        if not recovered_health.get('selected_model_visible'):
            raise RuntimeError('Configured model is not visible after restart')

        recovered_reply = joi.chat(
            'Reply with only the marker I asked you to remember before the server restart.'
        )
        if recovered_reply.strip() != marker:
            raise RuntimeError(f'Context recall failed after restart: {recovered_reply!r}')
    finally:
        if not server_restarted:
            run_lms('start', '--port', '1234', '--bind', '127.0.0.1')

    print({
        'outage_detected': True,
        'failed_turn_rolled_back': True,
        'server_recovered': True,
        'session_context_preserved': True,
        'model': settings.local_model,
    })


if __name__ == '__main__':
    main()