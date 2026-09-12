"""Minimal Jarvis HUD: cyan ring visual + tiny input. Voice UI ring timing."""

from __future__ import annotations

import math
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable
import queue

from assistant.ui.ring_timing import RingTiming
from assistant.voice.state_machine import VoiceState
from assistant.voice.wake import WakeListener

CYAN = "#00e5ff"
CYAN_DIM = "#00838f"
BG = "#0a0e14"


def _asset(name: str) -> Path | None:
    here = Path(__file__).resolve().parent / "assets" / name
    if here.exists():
        return here
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "assistant" / "ui" / "assets" / name  # type: ignore[attr-defined]
        if p.exists():
            return p
    return None


def _hex_brightness(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


class JarvisWindow:
    def __init__(
        self,
        *,
        title: str,
        on_submit: Callable[[str], str],
        wake: WakeListener | None = None,
        status_hint: str = "",
        speak: Callable[[str], None] | None = None,
        hear: Callable[[], str | None] | None = None,
        speak_muted: bool = False,
    ):
        self.on_submit = on_submit
        self.wake = wake
        self.speak = speak
        self.hear = hear if hear is not None else (wake.hear if wake is not None else None)
        self._speak_muted = speak_muted
        self._cmd_q: queue.Queue[str] = queue.Queue()
        self.state = VoiceState.IDLE
        self._t = 0.0
        self._photo = None
        self._base_img = None
        self.rings = RingTiming()
        self._demo_job: str | None = None
        self._mic_muted = False
        self._speak_gen = 0
        self._armed_caption = (
            'Say "Jarvis …" or tap Listen'
            if self.hear is not None
            else "Type below — voice deps missing; re-run Start Jarvis.bat"
        )
        if status_hint:
            # Keep short status chips but prefer beginner caption as primary
            self._status_hint = status_hint
        else:
            self._status_hint = ""

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("900x700")
        self.root.minsize(640, 520)
        self.root.configure(bg=BG)
        try:
            self.root.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        # Reduced motion: Windows ease of access isn't exposed; env or future setting
        import os

        self.rings.reduced_motion = os.environ.get("JARVIS_REDUCED_MOTION", "").lower() in {
            "1",
            "true",
            "yes",
        }

        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.caption = tk.Label(
            self.root,
            text=self._armed_caption,
            fg="#b0bec5",
            bg=BG,
            font=("Segoe UI", 11),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.caption.place(relx=0.5, rely=0.82, anchor="center")

        self.state_label = tk.Label(
            self.root,
            text=self._status_hint or "idle",
            fg=CYAN_DIM,
            bg=BG,
            font=("Segoe UI", 9),
        )
        self.state_label.place(relx=0.5, rely=0.08, anchor="center")

        bar = tk.Frame(self.root, bg=BG)
        bar.place(relx=0.5, rely=0.93, anchor="center", relwidth=0.7)

        self.entry = tk.Entry(
            bar,
            bg="#121820",
            fg="#e0f7fa",
            insertbackground=CYAN,
            relief=tk.FLAT,
            font=("Segoe UI", 12),
            highlightthickness=1,
            highlightbackground=CYAN_DIM,
            highlightcolor=CYAN,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._send())
        self.entry.focus_set()

        self.mute_btn = tk.Button(
            bar,
            text="🎤 Mute",
            command=self._toggle_mute,
            bg="#102027",
            fg=CYAN,
            activebackground="#1a333d",
            activeforeground=CYAN,
            relief=tk.FLAT,
            padx=14,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self.mute_btn.pack(side=tk.LEFT)

        self.listen_btn = tk.Button(
            bar,
            text="Listen",
            command=self._listen_once,
            bg="#102027",
            fg=CYAN,
            activebackground="#1a333d",
            activeforeground=CYAN,
            relief=tk.FLAT,
            padx=12,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self.listen_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.test_mic_btn = tk.Button(
            bar,
            text="Test mic",
            command=self._test_mic,
            bg="#102027",
            fg=CYAN_DIM,
            activebackground="#1a333d",
            activeforeground=CYAN,
            relief=tk.FLAT,
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        self.test_mic_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.root.bind("<Configure>", lambda _e: self._draw())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_hud_image()
        self._draw()
        self._tick()
        self._poll_commands()
        if self.wake is not None:
            self.wake.on_command = self._queue_command
            self.wake.on_state = self._on_wake_state
            self.wake.start()
            if self.wake.muted:
                self._apply_mute_chrome(True)
            if self.wake.hear is None and self.hear is None:
                self.caption.configure(
                    text="Voice deps missing / run Start Jarvis.bat again — typing still works"
                )
            elif self.hear is None:
                self.caption.configure(
                    text="Voice deps missing / run Start Jarvis.bat again — typing still works"
                )
        if self.wake is None and self.hear is None:
            self.caption.configure(
                text="Voice deps missing / run Start Jarvis.bat again — typing still works"
            )
        self.root.after(400, self._maybe_first_mic_probe)

    def _load_hud_image(self) -> None:
        # Procedural canvas arc-reactor is the default look.
        # Opt-in legacy photo: JARVIS_HUD_PHOTO=1
        self._photo = None
        self._base_img = None
        self._hud_path = None
        import os

        if os.environ.get("JARVIS_HUD_PHOTO", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return
        for name in ("hud_orb_tk.png", "hud_orb.png"):
            path = _asset(name)
            if path is None:
                continue
            try:
                self._base_img = tk.PhotoImage(file=str(path))
                self._hud_path = path
                break
            except tk.TclError:
                self._base_img = None
    def set_state(
        self,
        state: VoiceState,
        detail: str | None = None,
        *,
        barge_in: bool = False,
        level: float | None = None,
    ) -> None:
        self.state = state
        self.rings.set_state(state, barge_in=barge_in)
        if level is not None:
            self.rings.set_level(level)
        if detail:
            # Red caption for hard mic / permission / missing-deps failures
            fg = "#ff8a80" if state == VoiceState.ERROR else "#b0bec5"
            self.caption.configure(text=detail, fg=fg)
        self.state_label.configure(text=state.value)
        self._draw()

    def _cancel_demo(self) -> None:
        # best-effort cancel pending after() callbacks by generation
        self._demo_gen = getattr(self, "_demo_gen", 0) + 1



    def _maybe_first_mic_probe(self) -> None:
        try:
            from assistant.voice.mic_health import (
                mark_probed,
                needs_first_run_probe,
                probe_microphone,
            )
        except Exception:
            return
        if not needs_first_run_probe():
            return
        result = probe_microphone()
        mark_probed(status=result.status.value)
        if result.ok:
            return
        self._show_mic_panel(result.message)

    def _show_mic_panel(self, message: str) -> None:
        self.set_state(VoiceState.ERROR, message)
        self.state_label.configure(text="mic check")
        self.test_mic_btn.configure(fg=CYAN)

    def _armed_idle_caption(self) -> str:
        if self._mic_muted:
            return "Mic muted — tap Mute to arm wake, or type below."
        return self._armed_caption

    def _speak_async(self, text: str, *, idle_detail: str | None = None) -> None:
        """Speak on a background thread; never block the Tk main loop with runAndWait."""
        reply = (text or "").strip()
        if not reply:
            self.set_state(VoiceState.IDLE, idle_detail or self._armed_idle_caption())
            return
        if self._speak_muted:
            self.set_state(VoiceState.IDLE, idle_detail or reply)
            return
        if not self.speak:
            self.set_state(VoiceState.IDLE, idle_detail or reply)
            return

        self._speak_gen += 1
        gen = self._speak_gen
        self.set_state(VoiceState.SPEAKING, reply, level=0.55)

        def worker() -> None:
            err: str | None = None
            try:
                self.speak(reply)
            except Exception as e:  # noqa: BLE001
                err = str(e) or e.__class__.__name__

            def done() -> None:
                if gen != self._speak_gen:
                    return
                if err:
                    self.set_state(
                        VoiceState.ERROR,
                        f"TTS error: {err[:120]}",
                    )
                    self.root.after(
                        2500,
                        lambda: self.set_state(
                            VoiceState.IDLE, self._armed_idle_caption()
                        ),
                    )
                else:
                    self.set_state(
                        VoiceState.IDLE, idle_detail or self._armed_idle_caption()
                    )
                    if not self._mic_muted:
                        self.state_label.configure(text="idle · wake armed")

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, name="jarvis-tts", daemon=True).start()

    def _listen_once(self) -> None:
        """Push-to-talk: VAD record without requiring the wake word."""
        if self._mic_muted:
            self.set_state(
                VoiceState.IDLE,
                "Mic muted — unmute first, then tap Listen.",
            )
            return
        if self.hear is None:
            self.set_state(
                VoiceState.ERROR,
                "Voice deps missing / run Start Jarvis.bat again — typing still works",
            )
            return

        if self.wake is not None:
            self.wake.set_busy(True)
        self.set_state(VoiceState.LISTENING, "Speak now…", level=0.35)
        self.state_label.configure(text="listen")

        # Live VU while recording (orb level)
        def _vu(level: float) -> None:
            def apply(lv: float = level) -> None:
                self.rings.set_level(lv)
                self._draw()

            try:
                self.root.after(0, apply)
            except Exception:
                pass

        prev_level = getattr(self.hear, "on_level", None)
        try:
            self.hear.on_level = _vu  # type: ignore[attr-defined]
        except Exception:
            pass

        def worker() -> None:
            text = None
            err_kind = None
            try:
                text = self.hear()
                err_kind = getattr(self.hear, "last_error", None)
            except PermissionError:
                err_kind = "denied"
            except Exception:  # noqa: BLE001
                err_kind = "mic"
                text = None
            finally:
                try:
                    self.hear.on_level = prev_level  # type: ignore[attr-defined]
                except Exception:
                    pass

            def finish() -> None:
                if self.wake is not None and not text:
                    self.wake.set_busy(False)
                if text and text.strip():
                    # Same speak path as typing after transcript
                    self._handle_voice_command(text.strip())
                    return
                peak = float(getattr(self.hear, "last_peak", 0.0) or 0.0)
                peak_hint = f" (mic peak {peak:.3f})" if peak > 0 else ""
                if err_kind == "network":
                    msg = "Need internet for speech recognition — check connection, then tap Listen."
                    st = VoiceState.ERROR
                elif err_kind == "stt":
                    msg = "Speech recognition failed — try again, or type below."
                    st = VoiceState.ERROR
                elif err_kind == "denied":
                    msg = "Microphone denied — enable mic privacy, then try Listen again."
                    st = VoiceState.ERROR
                elif err_kind == "mic":
                    msg = (
                        "Didn't catch that (mic level flat — check Mute / Windows mic)"
                        + peak_hint
                    )
                    st = VoiceState.ERROR
                else:
                    # unknown / Google heard nothing useful
                    if peak < 1e-4:
                        msg = (
                            "Didn't catch that (mic level flat — check Mute / Windows mic)"
                            + peak_hint
                        )
                    else:
                        msg = (
                            "Didn't catch that — tap Listen and speak clearly"
                            + peak_hint
                        )
                    st = VoiceState.IDLE
                self.set_state(st, msg)
                self.state_label.configure(text="idle" if st == VoiceState.IDLE else "error")
                self.root.after(
                    2800,
                    lambda: self.set_state(VoiceState.IDLE, self._armed_idle_caption()),
                )

            try:
                self.root.after(0, finish)
            except Exception:
                pass

        threading.Thread(target=worker, name="jarvis-listen", daemon=True).start()

    def _test_mic(self) -> None:
        from assistant.voice.mic_health import mark_probed, probe_microphone

        result = probe_microphone()
        mark_probed(status=result.status.value)
        if result.ok:
            self.set_state(VoiceState.IDLE, "Microphone OK.")
            self.state_label.configure(text="mic ok")
            self._speak_async("Microphone OK.", idle_detail="Microphone OK.")
        else:
            self._show_mic_panel(result.message)

    def _toggle_mute(self) -> None:
        if self.wake is None:
            self.caption.configure(text="Voice not active — typing still works.")
            return
        muted = self.wake.toggle_mute()
        self._apply_mute_chrome(muted)

    def _queue_command(self, cmd: str) -> None:
        self._cmd_q.put(cmd)

    def _apply_mute_chrome(self, muted: bool) -> None:
        self._mic_muted = muted
        if muted:
            self.mute_btn.configure(text="🔇 Muted", fg="#78909c")
            self.set_state(VoiceState.IDLE, "Mic muted — tap Mute to arm wake.", barge_in=False)
            self.state_label.configure(text="muted")
            # Static desaturated rings (no listen pulse)
            self.rings.reduced_motion = True
        else:
            self.mute_btn.configure(text="🎤 Mute", fg=CYAN)
            import os
            self.rings.reduced_motion = os.environ.get("JARVIS_REDUCED_MOTION", "").lower() in {
                "1", "true", "yes"
            }
            self.set_state(VoiceState.IDLE, self._armed_caption)
            self.state_label.configure(text="idle · wake armed")

    def _on_wake_state(self, state: str) -> None:
        def apply() -> None:
            if state in {"muted"}:
                self._apply_mute_chrome(True)
            elif state in {"idle_armed", "idle"}:
                if not self._mic_muted:
                    self.set_state(VoiceState.IDLE, self._armed_caption)
                    self.state_label.configure(text="idle · wake armed")
            elif state == "wake":
                self.set_state(VoiceState.LISTENING, "Listening… Go ahead.", level=0.5)
                self.state_label.configure(text="listening")
            elif state == "listening":
                self.set_state(
                    VoiceState.LISTENING,
                    "Listening for command…",
                    level=0.35,
                )
                self.state_label.configure(text="listening")
            elif state == "busy":
                self.set_state(VoiceState.THINKING)
            elif state == "idle_timeout":
                self.set_state(VoiceState.IDLE, self._armed_caption)
            elif state == "mic_denied":
                self.set_state(
                    VoiceState.ERROR,
                    "Microphone denied or muted in Windows — enable mic privacy, then unmute here.",
                )
                self.state_label.configure(text="mic denied")
        try:
            self.root.after(0, apply)
        except Exception:
            pass

    def _poll_commands(self) -> None:
        try:
            while True:
                cmd = self._cmd_q.get_nowait()
                self._handle_voice_command(cmd)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_commands)

    def _handle_voice_command(self, cmd: str) -> None:
        if self.wake is not None:
            self.wake.set_busy(True)
        self.set_state(VoiceState.THINKING, f"You: {cmd}")
        self.root.update_idletasks()
        try:
            reply = self.on_submit(cmd)
        except Exception as e:  # noqa: BLE001
            self.set_state(VoiceState.ERROR, f"Error: {e}")
            if self.wake is not None:
                self.wake.set_busy(False)
            return

        def after_speak() -> None:
            if self.wake is not None:
                self.wake.set_busy(False)
            if not self._mic_muted:
                self.state_label.configure(text="idle · wake armed")

        # Speak once on background thread; clear busy after TTS finishes
        reply_s = (reply or "").strip()
        if not reply_s:
            self.set_state(VoiceState.IDLE, self._armed_idle_caption())
            after_speak()
            return

        self._speak_gen += 1
        gen = self._speak_gen
        self.set_state(VoiceState.SPEAKING, reply_s, level=0.55)

        if self._speak_muted or not self.speak:
            self.set_state(VoiceState.IDLE, reply_s)
            after_speak()
            return

        def worker() -> None:
            err: str | None = None
            try:
                self.speak(reply_s)
            except Exception as e:  # noqa: BLE001
                err = str(e) or e.__class__.__name__

            def done() -> None:
                if gen != self._speak_gen:
                    return
                after_speak()
                if err:
                    self.set_state(VoiceState.ERROR, f"TTS error: {err[:120]}")
                    self.root.after(
                        2500,
                        lambda: self.set_state(
                            VoiceState.IDLE, self._armed_idle_caption()
                        ),
                    )
                else:
                    self.set_state(VoiceState.IDLE, self._armed_idle_caption())

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, name="jarvis-tts", daemon=True).start()

    def _on_close(self) -> None:
        if self.wake is not None:
            self.wake.stop()
        self.root.destroy()

    def _pulse_listen(self) -> None:
        """Demo state machine with synthetic VU / TTS envelope."""
        self._cancel_demo()
        gen = self._demo_gen

        self.set_state(VoiceState.LISTENING, "Listening…", level=0.15)

        def later(ms: int, fn: Callable[[], None]) -> None:
            def wrap() -> None:
                if getattr(self, "_demo_gen", 0) != gen:
                    return
                fn()

            self.root.after(ms, wrap)

        # ramp synthetic VU while listening
        for i, lvl in enumerate((0.2, 0.45, 0.7, 0.35, 0.55)):
            later(150 + i * 200, lambda L=lvl: self.rings.set_level(L))

        later(1500, lambda: self.set_state(VoiceState.THINKING, "Thinking…"))
        later(
            2600,
            lambda: self.set_state(VoiceState.SPEAKING, "Speaking…", level=0.4),
        )
        for i, lvl in enumerate((0.6, 0.9, 0.5, 0.75, 0.3)):
            later(2700 + i * 150, lambda L=lvl: self.rings.set_level(L))
        later(3800, lambda: self.set_state(VoiceState.IDLE, "Ready."))

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._cancel_demo()
        self.set_state(VoiceState.THINKING, "Thinking…")
        self.root.update_idletasks()
        try:
            reply = self.on_submit(text)
        except Exception as e:  # noqa: BLE001
            self.set_state(VoiceState.ERROR, f"Error: {e}")
            self.root.after(
                1200, lambda: self.set_state(VoiceState.IDLE, self._armed_idle_caption())
            )
            return
        self.root.after(200, lambda: self.rings.set_level(0.8))
        self.root.after(450, lambda: self.rings.set_level(0.35))
        # Typed replies: single speak path on background thread (mic mute does not skip)
        self._speak_async(reply or "", idle_detail=self._armed_idle_caption())

    def _tick(self) -> None:
        drive = self.rings.tick()
        self._t += 0.033 * (1.0 + float(drive.get("rot_speed", 8)) / 80.0)
        self._last_drive = drive
        self._draw()
        self.root.after(33, self._tick)  # ~30 fps

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 2)
        h = max(c.winfo_height(), 2)

        step = 40
        for x in range(0, w, step):
            c.create_line(x, 0, x, h, fill="#12202a")
        for y in range(0, h, step):
            c.create_line(0, y, w, y, fill="#12202a")

        cx, cy = w // 2, int(h * 0.42)
        drive = getattr(self, "_last_drive", None) or self.rings.tick()

        if self._base_img is not None:
            self._photo = self._base_img
            c.create_image(cx, cy, image=self._base_img)
            self._draw_overlay_arcs(c, cx, cy, base_r=min(w, h) * 0.18, drive=drive)
        else:
            self._draw_rings(c, cx, cy, base_r=min(w, h) * 0.22, drive=drive)

        if drive.get("reduced_motion"):
            c.create_text(
                cx,
                cy + int(min(w, h) * 0.28),
                text=str(drive.get("label", "")),
                fill=CYAN,
                font=("Segoe UI", 12),
            )

    def _draw_overlay_arcs(
        self, c: tk.Canvas, cx: int, cy: int, base_r: float, drive: dict
    ) -> None:
        if drive.get("reduced_motion"):
            r = base_r * 1.35
            for mul in (1.0, 0.75, 0.5):
                rr = r * mul
                c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=CYAN_DIM, width=2)
            return

        pulse = float(drive["pulse"])
        radius_mul = float(drive["radius_mul"])
        bright = float(drive["brightness"])
        rot = self._t * float(drive["rot_speed"])
        r_seg = base_r * 1.35 * radius_mul * pulse
        color = _hex_brightness(CYAN, 0.6 + 0.4 * bright)
        for start, extent in ((rot, 45), (rot + 120, 40), (rot + 240, 50)):
            c.create_arc(
                cx - r_seg,
                cy - r_seg,
                cx + r_seg,
                cy + r_seg,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=color,
                width=4,
            )

    def _draw_rings(
        self, c: tk.Canvas, cx: int, cy: int, base_r: float, drive: dict
    ) -> None:
        """Procedural arc-reactor: layered cyan glow rings + rotating segments."""
        pulse = float(drive["pulse"])
        radius_mul = float(drive["radius_mul"])
        bright = float(drive["brightness"])
        shimmer = float(drive.get("shimmer", 0.0))
        level = float(drive.get("level_smooth", 0.0) or 0.0)
        color = _hex_brightness(CYAN, 0.55 + 0.45 * bright)
        hot = _hex_brightness(CYAN, 0.75 + 0.25 * bright)
        dim = _hex_brightness(CYAN_DIM, 0.7 + 0.3 * bright)
        glow = _hex_brightness("#004d5c", 0.8 + 0.4 * bright)

        if drive.get("reduced_motion"):
            for mul in (1.55, 1.35, 1.18, 0.55, 0.35):
                r = base_r * mul
                c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=dim, width=2)
            core = base_r * 0.2
            c.create_oval(
                cx - core, cy - core, cx + core, cy + core, outline=color, width=2, fill="#062029"
            )
            return

        scale = radius_mul * pulse

        # Soft outer glow discs (arc-reactor bloom)
        for i, (mul, w) in enumerate(((1.72, 1), (1.58, 2), (1.45, 2))):
            r = base_r * mul * scale
            c.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=glow if i else dim,
                width=w,
            )

        # Main concentric rings
        for i, mul in enumerate((1.32, 1.18, 1.05)):
            r = base_r * mul * scale
            c.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=color if i == 0 else dim,
                width=3 if i == 0 else 2,
            )

        # Tick marks (reactor teeth)
        r_tick = base_r * 0.98 * scale
        rot_ticks = self._t * float(drive["rot_speed"]) * 0.25
        n_ticks = 48
        for i in range(n_ticks):
            ang = math.radians(i * (360 / n_ticks) + rot_ticks)
            long = (i % 6 == 0)
            inner = r_tick - (10 if long else 5)
            x0 = cx + r_tick * math.cos(ang)
            y0 = cy + r_tick * math.sin(ang)
            x1 = cx + inner * math.cos(ang)
            y1 = cy + inner * math.sin(ang)
            c.create_line(x0, y0, x1, y1, fill=hot if long else dim, width=2 if long else 1)

        # Counter-rotating arc segments
        rot = self._t * float(drive["rot_speed"])
        rot2 = -self._t * float(drive["rot_speed"]) * 0.65
        r_seg = base_r * 1.22 * scale
        if self.state == VoiceState.THINKING:
            r_seg *= 0.98 + 0.05 * shimmer
        elif self.state == VoiceState.LISTENING:
            r_seg *= 1.0 + 0.06 * level
        elif self.state == VoiceState.SPEAKING:
            r_seg *= 1.0 + 0.1 * level

        arcs = (
            (rot, 48, 7, hot),
            (rot + 110, 36, 5, color),
            (rot + 210, 55, 6, hot),
            (rot + 300, 28, 4, color),
            (rot2, 40, 3, dim),
            (rot2 + 180, 50, 3, dim),
        )
        for start, extent, width, col in arcs:
            c.create_arc(
                cx - r_seg,
                cy - r_seg,
                cx + r_seg,
                cy + r_seg,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=col,
                width=width,
            )

        # Inner reactor rings + core
        for mul, w in ((0.62, 2), (0.45, 2), (0.28, 3)):
            r = base_r * mul * (0.96 + 0.04 * pulse)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=w)

        # Pulsing core fill (state-aware)
        core = base_r * (0.16 + 0.04 * pulse + 0.03 * level)
        core_fill = "#0a3040" if self.state == VoiceState.IDLE else "#0c4a5c"
        if self.state == VoiceState.ERROR:
            core_fill = "#3a1520"
        c.create_oval(
            cx - core,
            cy - core,
            cx + core,
            cy + core,
            outline=hot,
            width=2,
            fill=core_fill,
        )
        # Tiny inner spark
        spark = core * 0.35
        c.create_oval(
            cx - spark,
            cy - spark,
            cx + spark,
            cy + spark,
            outline=CYAN,
            width=1,
            fill=_hex_brightness(CYAN, 0.35 + 0.4 * bright),
        )

    def run(self) -> None:
        self.root.mainloop()


def run_gui(
    *,
    title: str,
    on_submit: Callable[[str], str],
    wake: WakeListener | None = None,
    status_hint: str = "",
    speak: Callable[[str], None] | None = None,
    hear: Callable[[], str | None] | None = None,
    speak_muted: bool = False,
) -> None:
    JarvisWindow(
        title=title,
        on_submit=on_submit,
        wake=wake,
        status_hint=status_hint,
        speak=speak,
        hear=hear,
        speak_muted=speak_muted,
    ).run()
