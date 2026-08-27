import pytest

from config.settings import Settings


def test_settings_rejects_invalid_request_timeout(monkeypatch):
    monkeypatch.setenv('REQUEST_TIMEOUT_SECONDS', 'not-a-number')

    with pytest.raises(ValueError, match='REQUEST_TIMEOUT_SECONDS must be a positive integer'):
        Settings.load()


def test_settings_rejects_non_positive_request_timeout(monkeypatch):
    monkeypatch.setenv('REQUEST_TIMEOUT_SECONDS', '0')

    with pytest.raises(ValueError, match='REQUEST_TIMEOUT_SECONDS must be a positive integer'):
        Settings.load()