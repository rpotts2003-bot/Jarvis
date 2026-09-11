import time

from assistant.voice.wake import WakeConfig, WakeListener, WakePhase, WakePipeline


def test_strip_wake_and_match():
    w = WakeListener(config=WakeConfig(wake_name="Jarvis", wake_debounce_s=0.0))
    assert w.handle_transcript("hello there") is None
    assert w.handle_transcript("Jarvis what time is it") == "what time is it"
    w.pipeline.cancel_to_idle()
    w.pipeline.last_wake_at = 0.0
    assert w.handle_transcript("hey JARVIS open calculator") == "open calculator"


def test_mute_blocks():
    w = WakeListener(config=WakeConfig(wake_name="Jarvis", wake_debounce_s=0.0))
    w.set_muted(True)
    assert w.handle_transcript("Jarvis help") is None
    w.set_muted(False)
    w.pipeline.last_wake_at = 0.0
    assert w.handle_transcript("Jarvis help") == "help"


def test_low_confidence_rejected():
    p = WakePipeline(config=WakeConfig(wake_confidence_min=0.72))
    assert p.try_wake("Jarvis hello", confidence=0.4) is False
    assert p.phase == WakePhase.IDLE_ARMED
    assert p.false_wakes == 1


def test_debounce():
    p = WakePipeline(config=WakeConfig(wake_debounce_s=1.2))
    t0 = 100.0
    assert p.try_wake("Jarvis a", confidence=1.0, now=t0) is True
    p.cancel_to_idle()
    assert p.try_wake("Jarvis b", confidence=1.0, now=t0 + 0.5) is False
    assert p.try_wake("Jarvis c", confidence=1.0, now=t0 + 1.3) is True


def test_no_speech_timeout():
    cfg = WakeConfig(no_speech_timeout_s=5.5)
    p = WakePipeline(config=cfg)
    t0 = 50.0
    assert p.try_wake("Jarvis", confidence=1.0, now=t0)
    assert p.feed_energy(0.0, 0.1, now=t0 + 1.0) is None
    assert p.feed_energy(0.0, 0.1, now=t0 + 5.6) == "idle_timeout"
    assert p.phase == WakePhase.IDLE_ARMED
    assert p.abandoned_wakes == 1


def test_end_silence_closes_utterance():
    cfg = WakeConfig(end_silence_s=0.8, min_speech_s=0.15, energy_floor=0.01)
    p = WakePipeline(config=cfg)
    t0 = 10.0
    p.try_wake("Jarvis", confidence=1.0, now=t0)
    # speech
    t = t0
    for _ in range(5):
        t += 0.05
        p.feed_energy(0.5, 0.05, now=t)
    # silence
    ev = None
    for _ in range(20):
        t += 0.1
        ev = p.feed_energy(0.0, 0.1, now=t)
        if ev:
            break
    assert ev == "thinking"


def test_busy_blocks_wake_unless_barge_in():
    p = WakePipeline()
    p.set_busy(True)
    assert p.try_wake("Jarvis x", confidence=1.0) is False
    assert p.try_wake("Jarvis x", confidence=1.0, barge_in=True) is True


def test_wake_must_be_at_start():
    p = WakePipeline(config=WakeConfig(wake_name="Jarvis"))
    assert p.wake_at_start("Jarvis")
    assert p.wake_at_start("Hey Jarvis")
    assert p.wake_at_start("Jarvis open calculator")
    assert not p.wake_at_start("please Jarvis help")
    assert not p.wake_at_start("open calculator")
    assert p.try_wake("please Jarvis help", confidence=1.0) is False
    assert p.phase == WakePhase.IDLE_ARMED


def test_vad_alone_never_opens_listening():
    p = WakePipeline()
    assert p.phase == WakePhase.IDLE_ARMED
    # energy while idle must not change phase
    assert p.feed_energy(0.9, 0.1) is None
    assert p.phase == WakePhase.IDLE_ARMED
