from assistant.ui.orb import ListeningOrb
from assistant.voice.state_machine import VoiceMachine, VoiceState


def test_state_cycle_and_vu():
    v = VoiceMachine()
    orb = ListeningOrb()
    v.set_hooks(on_change=lambda s: orb.update(s, vu=v.level, error=v.last_error))
    v.start_listen()
    v.set_vu(0.7)
    assert v.state == VoiceState.LISTENING
    assert orb.render()["vu"] == 0.7
    v.begin_stt()
    assert v.state == VoiceState.THINKING
    assert orb.render()["vu"] == 0.0
    assert orb.render()["shape"] == "orbit"
    v.start_speak()
    assert orb.render()["cancel_visible"] is True
    v.finish_speak()
    assert v.state == VoiceState.IDLE


def test_mic_denied_and_silence():
    v = VoiceMachine()
    v.start_listen()
    v.mic_denied()
    assert v.state == VoiceState.IDLE
    v.start_listen()
    v.silence_timeout()
    assert v.state == VoiceState.IDLE


def test_barge_in_and_late_stt():
    stopped = []
    v = VoiceMachine()
    v.set_hooks(tts_stop=lambda: stopped.append(1))
    v.start_speak()
    v.barge_in()
    assert v.state == VoiceState.LISTENING and stopped
    gen = v.begin_stt()
    v.stt_hang_timeout()
    assert v.stt_result(gen, "open calculator") is None


def test_model_missing():
    v = VoiceMachine()
    v.model_missing()
    assert v.state == VoiceState.IDLE and "model" in (v.last_error or "")
