import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from brain.local_llm import LocalLMStudioBrain


def _response(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode('utf-8')
    response.__enter__.return_value = response
    return response


def test_chat_returns_valid_message_content():
    brain = LocalLMStudioBrain('http://localhost:1234/v1', 'model')

    with patch('brain.local_llm.urllib.request.urlopen', return_value=_response({
        'choices': [{'message': {'content': 'Hello'}}],
    })):
        assert brain.chat([{'role': 'user', 'content': 'Hi'}]) == 'Hello'


def test_chat_reports_malformed_response():
    brain = LocalLMStudioBrain('http://localhost:1234/v1', 'model')

    with patch('brain.local_llm.urllib.request.urlopen', return_value=_response({'choices': []})):
        with pytest.raises(RuntimeError, match='invalid response'):
            brain.chat([{'role': 'user', 'content': 'Hi'}])


def test_chat_limits_http_error_detail():
    brain = LocalLMStudioBrain('http://localhost:1234/v1', 'model')
    error = HTTPError(
        'http://localhost:1234/v1/chat/completions',
        500,
        'Server Error',
        {},
        BytesIO((b'x' * 5000) + b'should-not-appear'),
    )

    with patch('brain.local_llm.urllib.request.urlopen', side_effect=error):
        with pytest.raises(RuntimeError) as exc_info:
            brain.chat([{'role': 'user', 'content': 'Hi'}])

    assert 'LM Studio HTTP 500' in str(exc_info.value)
    assert 'should-not-appear' not in str(exc_info.value)