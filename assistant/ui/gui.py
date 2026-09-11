"""Minimal Jarvis HUD: cyan ring visual + tiny input. Voice UI ring timing."""

from __future__ import annotations

import math
import sys
import tkinter as tk
from pathlib import Path
from typing import Callable

from assistant.ui.ring_timing import RingTiming
from assistant.voice.state_machine import VoiceState

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
    def __init__(self, *, title: str, on_submit: Callable[[str], str]):
        self.on_submit = on_submit
        self.state = VoiceState.IDLE
        self._t = 0.0
        self._photo = None
        self._base_img = None
        self.rings = RingTiming()
        self._demo_job: str | None = None

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
            text="Ready — type below or Hold to preview listen/speak",
            fg="#b0bec5",
            bg=BG,
            font=("Segoe UI", 11),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.caption.place(relx=0.5, rely=0.82, anchor="center")

        self.state_label = tk.Label(
            self.root,
            text="idle",
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

        self.listen_btn = tk.Button(
            bar,
            text="● Hold",
            command=self._pulse_listen,
            bg="#102027",
            fg=CYAN,
            activebackground="#1a333d",
            activeforeground=CYAN,
            relief=tk.FLAT,
            padx=14,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self.listen_btn.pack(side=tk.LEFT)

        self.root.bind("<Configure>", lambda _e: self._draw())
        self._load_hud_image()
        self._draw()
        self._tick()

    def _load_hud_image(self) -> None:
        path = _asset("hud_orb.png")
        self._hud_path = path
        self._photo = None
        self._base_img = None
        if path is None:
            return
        try:
            self._base_img = tk.PhotoImage(file=str(path))
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
            self.caption.configure(text=detail)
        self.state_label.configure(text=state.value)
        self._draw()

    def _cancel_demo(self) -> None:
        # best-effort cancel pending after() callbacks by generation
        self._demo_gen = getattr(self, "_demo_gen", 0) + 1

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
            self.root.after(1200, lambda: self.set_state(VoiceState.IDLE, "Ready."))
            return
        self.set_state(VoiceState.SPEAKING, reply or "", level=0.55)
        # fake short TTS envelope then idle
        self.root.after(200, lambda: self.rings.set_level(0.8))
        self.root.after(450, lambda: self.rings.set_level(0.35))
        self.root.after(900, lambda: self.set_state(VoiceState.IDLE, reply or "Ready."))

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
        pulse = float(drive["pulse"])
        radius_mul = float(drive["radius_mul"])
        bright = float(drive["brightness"])
        shimmer = float(drive.get("shimmer", 0.0))
        color = _hex_brightness(CYAN, 0.55 + 0.45 * bright)
        dim = _hex_brightness(CYAN_DIM, 0.7 + 0.3 * bright)

        if drive.get("reduced_motion"):
            for mul in (1.55, 1.35, 1.18, 0.55, 0.35):
                r = base_r * mul
                c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=dim, width=2)
            return

        for i, mul in enumerate((1.55, 1.35, 1.18)):
            r = base_r * mul * radius_mul * pulse
            c.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=color if i == 0 else dim,
                width=2,
            )

        r_tick = base_r * 1.05 * radius_mul * pulse
        for i in range(60):
            ang = math.radians(i * 6 + self._t * float(drive["rot_speed"]) * 0.3)
            x0 = cx + r_tick * math.cos(ang)
            y0 = cy + r_tick * math.sin(ang)
            x1 = cx + (r_tick - 6) * math.cos(ang)
            y1 = cy + (r_tick - 6) * math.sin(ang)
            c.create_line(x0, y0, x1, y1, fill=dim)

        rot = self._t * float(drive["rot_speed"])
        r_seg = base_r * 1.25 * radius_mul * pulse
        # Thinking: arcs driven by shimmer, not VU
        if self.state == VoiceState.THINKING:
            r_seg *= 0.98 + 0.04 * shimmer
        for start, extent in ((rot, 40), (rot + 90, 55), (rot + 200, 35), (rot + 280, 50)):
            c.create_arc(
                cx - r_seg,
                cy - r_seg,
                cx + r_seg,
                cy + r_seg,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=color,
                width=6,
            )

        for mul in (0.55, 0.35):
            r = base_r * mul
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)

        core = base_r * 0.18
        c.create_oval(cx - core, cy - core, cx + core, cy + core, outline=dim, width=1)

    def run(self) -> None:
        self.root.mainloop()


def run_gui(*, title: str, on_submit: Callable[[str], str]) -> None:
    JarvisWindow(title=title, on_submit=on_submit).run()
