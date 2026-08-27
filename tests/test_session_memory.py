from memory.session_memory import SessionMemory


def test_session_memory_reset():
    mem = SessionMemory('system')
    mem.add_user('hello')
    mem.add_assistant('hi')
    assert len(mem.snapshot()) == 3
    mem.reset()
    assert mem.snapshot() == [{'role': 'system', 'content': 'system'}]


def test_session_memory_discards_oldest_complete_turn_at_limit():
    mem = SessionMemory('system', max_messages=5)
    mem.add_user('old question')
    mem.add_assistant('old answer')
    mem.add_user('new question')
    mem.add_assistant('new answer')
    mem.add_user('latest question')

    assert mem.snapshot() == [
        {'role': 'system', 'content': 'system'},
        {'role': 'user', 'content': 'new question'},
        {'role': 'assistant', 'content': 'new answer'},
        {'role': 'user', 'content': 'latest question'},
    ]
