import time

from assistant.ui.ring_timing import (
    IDLE_LISTEN_CYCLE_S,
    LISTEN_BRIGHTEN_MS,
    LISTEN_FIRST_PULSE_MS,
    VU_KILL_MS,
    RingTiming,
)
from assistant.voice.state_machine import VoiceState


def test_listen_brightens_within_120ms():
    r = RingTiming()
    t0 = time.monotonic()
    r.set_state(VoiceState.LISTENING)
    r._entered_at = t0
    early = r.tick(t0 + 0.05)
    late = r.tick(t0 + LISTEN_BRIGHTEN_MS / 1000.0)
    assert early["brightness"] < late["brightness"]
    assert late["brightness"] >= 0.99


def test_first_pulse_by_150ms():
    r = RingTiming()
    t0 = time.monotonic()
    r.set_state(VoiceState.LISTENING)
    r._entered_at = t0
    r.set_level(0.0)  # flat — idle-listen path
    d = r.tick(t0 + LISTEN_FIRST_PULSE_MS / 1000.0)
    assert d["pulse"] > 0.9


def test_thinking_kills_vu_and_shimmers():
    r = RingTiming()
    t0 = time.monotonic()
    r.set_state(VoiceState.LISTENING)
    r.set_level(0.9)
    r.tick(t0)
    r.set_state(VoiceState.THINKING)
    # immediately after transition, target is 0; after kill window smooth near 0
    r.tick(t0 + 0.01)
    d = r.tick(t0 + VU_KILL_MS / 1000.0 + 0.05)
    assert d["level_smooth"] < 0.15
    assert d["shimmer"] >= 0.0  # non-reactive shimmer present
    # not listen-style radius boom from VU
    assert d["radius_mul"] == 1.0


def test_barge_in_hard_cut():
    r = RingTiming()
    r.set_state(VoiceState.SPEAKING)
    r.set_level(0.8)
    r.tick()
    r.set_state(VoiceState.LISTENING, barge_in=True)
    d = r.tick()
    assert d["crossfade"] == 1.0


def test_idle_listen_cycle_constant():
    assert 1.2 <= IDLE_LISTEN_CYCLE_S <= 1.6


def test_reduced_motion_static():
    r = RingTiming(reduced_motion=True)
    r.set_state(VoiceState.LISTENING)
    d = r.tick()
    assert d["reduced_motion"] is True
    assert d["pulse"] == 1.0
    assert d["rot_speed"] == 0.0
