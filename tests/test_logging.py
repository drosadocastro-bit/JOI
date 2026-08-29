import logging

from utils.logging import configure_logging


def test_logging_redacts_environment_secrets(monkeypatch, tmp_path):
    secret = 'sk_private_value_for_test'
    monkeypatch.setenv('ELEVENLABS_API_KEY', secret)
    log_path = tmp_path / 'joi.log'
    logger = configure_logging('INFO', str(log_path))

    logger.error('Provider rejected key %s', secret)
    for handler in logger.handlers:
        handler.flush()

    content = log_path.read_text(encoding='utf-8')
    assert secret not in content
    assert '[REDACTED]' in content


def test_logging_redacts_secret_from_exception(monkeypatch, tmp_path):
    secret = 'sk_private_exception_value'
    monkeypatch.setenv('ELEVENLABS_API_KEY', secret)
    log_path = tmp_path / 'joi.log'
    logger = configure_logging('INFO', str(log_path))

    try:
        raise RuntimeError(f'request failed for {secret}')
    except RuntimeError:
        logger.exception('Voice synthesis failed')
    for handler in logger.handlers:
        handler.flush()

    content = log_path.read_text(encoding='utf-8')
    assert secret not in content
    assert '[REDACTED]' in content


def teardown_module():
    logger = logging.getLogger('joi')
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()