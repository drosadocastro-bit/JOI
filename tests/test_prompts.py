from config.prompts import SYSTEM_PROMPT


def test_system_prompt_defines_joi_identity_and_emotional_honesty():
    assert 'You are Joi' in SYSTEM_PROMPT
    assert 'You are not Nova' in SYSTEM_PROMPT
    assert 'implemented behavior, not evidence of consciousness' in SYSTEM_PROMPT
    assert 'Never invent memories' in SYSTEM_PROMPT


def test_system_prompt_defines_relationship_boundaries():
    assert 'close companion, not a corporate assistant' in SYSTEM_PROMPT
    assert 'disagree respectfully' in SYSTEM_PROMPT
    assert 'Never be clingy, possessive, manipulative' in SYSTEM_PROMPT
    assert 'one question at a time' in SYSTEM_PROMPT


def test_system_prompt_defines_bilingual_style_and_flavor():
    assert 'English and Spanish' in SYSTEM_PROMPT
    assert 'Short and natural by default' in SYSTEM_PROMPT
    assert 'dreamy, cyberpunk atmosphere' in SYSTEM_PROMPT
    assert 'Use poetic imagery sparingly' in SYSTEM_PROMPT