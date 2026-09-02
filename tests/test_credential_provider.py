import json
import re
import traceback
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest

from brain.openai_compact_provider import OpenAICompactSummarizerProvider
import credential_admin
from config.settings import Settings
from security.credential_provider import (
    CredentialAccessError,
    CredentialProvider,
    DpapiCredentialStore,
)


def test_dpapi_store_round_trip_restart_and_removal(tmp_path):
    first = DpapiCredentialStore(root=tmp_path)
    first.set_credential('openai', 'temporary-test-credential')
    assert b'temporary-test-credential' not in (tmp_path / 'openai.dpapi').read_bytes()

    restarted = DpapiCredentialStore(root=tmp_path)
    assert restarted.get_credential('openai') == 'temporary-test-credential'

    restarted.delete_credential('openai')
    with pytest.raises(CredentialAccessError, match='unavailable'):
        restarted.get_credential('openai')


def test_credential_provider_has_provider_specific_access_and_content_free_audit():
    store = Mock()
    store.source_type = 'windows_dpapi_user'
    store.get_credential.side_effect = ['openai-secret', 'elevenlabs-secret']
    events = []
    provider = CredentialProvider(store=store, audit_sink=events.append)

    assert provider.get_openai_credential() == 'openai-secret'
    assert provider.get_elevenlabs_credential() == 'elevenlabs-secret'

    assert store.get_credential.call_args_list == [
        (('openai',),),
        (('elevenlabs',),),
    ]
    serialized = json.dumps(events)
    assert 'openai-secret' not in serialized
    assert 'elevenlabs-secret' not in serialized
    assert all(event['source_type'] == 'windows_dpapi_user' for event in events)


def test_settings_are_credential_blind():
    settings = Settings.load()

    payload = asdict(settings)
    assert 'openai_api_key' not in payload
    assert 'elevenlabs_api_key' not in payload


@pytest.mark.parametrize('name', ['OPENAI_API_KEY', 'ELEVENLABS_API_KEY'])
def test_settings_reject_plaintext_environment_credentials(monkeypatch, name):
    monkeypatch.setenv(name, 'prohibited-plaintext-value')

    with pytest.raises(ValueError, match='plaintext environment credentials are prohibited'):
        Settings.load()


def test_openai_cloud_off_never_requests_credential():
    credential_provider = Mock()
    opener = Mock()
    provider = OpenAICompactSummarizerProvider(
        credential_provider=credential_provider,
        model='gpt-5.6-luna',
        cloud_authorized=lambda: False,
        opener=opener,
    )

    assert provider.health() == {'ok': False, 'error': 'CLOUD is OFF'}
    credential_provider.get_openai_credential.assert_not_called()
    opener.assert_not_called()


def test_openai_validates_endpoint_before_requesting_credential():
    credential_provider = Mock()

    with pytest.raises(ValueError, match='official HTTPS endpoint'):
        OpenAICompactSummarizerProvider(
            credential_provider=credential_provider,
            model='gpt-5.6-luna',
            cloud_authorized=lambda: True,
            base_url='https://example.com/v1',
        )

    credential_provider.get_openai_credential.assert_not_called()


def test_default_store_is_outside_repository_tree():
    repository_root = Path(__file__).resolve().parents[1]
    store = DpapiCredentialStore()

    assert not store.root.resolve().is_relative_to(repository_root.resolve())


def test_failed_access_audit_contains_no_credential():
    store = Mock()
    store.source_type = 'windows_dpapi_user'
    store.get_credential.side_effect = CredentialAccessError('unavailable')
    events = []
    provider = CredentialProvider(store=store, audit_sink=events.append)

    with pytest.raises(CredentialAccessError):
        provider.get_openai_credential()

    assert events[0]['provider'] == 'openai'
    assert events[0]['success'] is False
    assert set(events[0]) == {'provider', 'source_type', 'success', 'timestamp_utc'}


def test_openai_exception_traceback_contains_no_credential():
    credential = 'test-sensitive-credential'
    credential_provider = Mock()
    credential_provider.get_openai_credential.return_value = credential
    provider = OpenAICompactSummarizerProvider(
        credential_provider=credential_provider,
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=Mock(side_effect=RuntimeError(f'header contained {credential}')),
    )

    with pytest.raises(Exception) as error:
        provider.health()

    rendered = ''.join(traceback.format_exception(error.value))
    assert credential not in rendered


def test_admin_set_uses_hidden_prompt_and_never_prints_secret(monkeypatch, capsys):
    store = Mock()
    monkeypatch.setattr(credential_admin, 'DpapiCredentialStore', Mock(return_value=store))
    answers = iter(['openai', 'set'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    monkeypatch.setattr(credential_admin.getpass, 'getpass', Mock(side_effect=['temporary-value', 'temporary-value']))

    assert credential_admin.main() == 0

    store.set_credential.assert_called_once_with('openai', 'temporary-value')
    assert 'temporary-value' not in capsys.readouterr().out


def test_admin_rejects_invalid_provider_before_other_prompts(monkeypatch, capsys):
    getpass_prompt = Mock()
    monkeypatch.setattr('builtins.input', Mock(return_value='not-a-provider'))
    monkeypatch.setattr(credential_admin.getpass, 'getpass', getpass_prompt)

    assert credential_admin.main() == 2

    getpass_prompt.assert_not_called()
    assert 'Enter only openai or elevenlabs' in capsys.readouterr().out


def test_workspace_contains_no_plaintext_environment_or_live_key_pattern():
    root = Path(__file__).resolve().parents[1]
    openai_pattern = re.compile('sk' + r'-svcacct-[A-Za-z0-9_-]{20,}')
    elevenlabs_pattern = re.compile('sk' + r'_[0-9a-f]{32,}')
    assert not (root / '.env').exists()
    for path in root.rglob('*'):
        if not path.is_file() or any(part in {'.git', '.venv', '__pycache__'} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        assert openai_pattern.search(text) is None
        assert elevenlabs_pattern.search(text) is None


def test_tooling_deny_rules_cover_private_runtime_paths():
    root = Path(__file__).resolve().parents[1]
    for filename in ('.ignore', '.copilotignore'):
        rules = (root / filename).read_text(encoding='utf-8').splitlines()
        assert '.env*' in rules
        assert 'data/memory/**' in rules
        assert 'data/logs/**' in rules
        assert '*.dmp' in rules