from assistant.voice.wake import WakeConfig, WakeListener


def test_strip_wake_and_match():
    w = WakeListener(config=WakeConfig(wake_name="Jarvis"))
    assert w.handle_transcript("hello there") is None
    assert w.handle_transcript("Jarvis what time is it") == "what time is it"
    assert w.handle_transcript("hey JARVIS open calculator") == "open calculator"


def test_mute_blocks():
    w = WakeListener(config=WakeConfig(wake_name="Jarvis"))
    w.set_muted(True)
    assert w.handle_transcript("Jarvis help") is None
    w.set_muted(False)
    assert w.handle_transcript("Jarvis help") == "help"
