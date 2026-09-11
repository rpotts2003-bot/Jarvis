"""Minimal Jarvis HUD: cyan ring visual + tiny input. Matches user reference aesthetic."""

from __future__ import annotations

import math
import sys
import tkinter as tk
from pathlib import Path
from typing import Callable

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


class JarvisWindow:
    def __init__(self, *, title: str, on_submit: Callable[[str], str]):
        self.on_submit = on_submit
        self.state = VoiceState.IDLE
        self._t = 0.0
        self._photo = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("900x700")
        self.root.minsize(640, 520)
        self.root.configure(bg=BG)
        try:
            self.root.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Caption under orb (last reply) — small, not a chat wall
        self.caption = tk.Label(
            self.root,
            text="Listening for you… type below or press Hold to talk (soon)",
            fg="#b0bec5",
            bg=BG,
            font=("Segoe UI", 11),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.caption.place(relx=0.5, rely=0.82, anchor="center")

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
        if path is None:
            return
        try:
            self._base_img = tk.PhotoImage(file=str(path))
        except tk.TclError:
            self._base_img = None

    def set_state(self, state: VoiceState, detail: str | None = None) -> None:
        self.state = state
        if detail:
            self.caption.configure(text=detail)
        self._draw()

    def _pulse_listen(self) -> None:
        self.set_state(VoiceState.LISTENING, "Listening…")
        self.root.after(1500, lambda: self.set_state(VoiceState.THINKING, "Thinking…"))
        self.root.after(2600, lambda: self.set_state(VoiceState.SPEAKING, "Speaking…"))
        self.root.after(3800, lambda: self.set_state(VoiceState.IDLE, "Ready."))

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self.set_state(VoiceState.THINKING, "Thinking…")
        self.root.update_idletasks()
        try:
            reply = self.on_submit(text)
        except Exception as e:  # noqa: BLE001
            self.set_state(VoiceState.ERROR, f"Error: {e}")
            self.root.after(1200, lambda: self.set_state(VoiceState.IDLE, "Ready."))
            return
        self.set_state(VoiceState.SPEAKING, reply or "")
        self.root.after(900, lambda: self.set_state(VoiceState.IDLE, reply or "Ready."))

    def _tick(self) -> None:
        speed = {
            VoiceState.IDLE: 0.04,
            VoiceState.LISTENING: 0.22,
            VoiceState.THINKING: 0.12,
            VoiceState.SPEAKING: 0.28,
            VoiceState.ERROR: 0.06,
        }.get(self.state, 0.05)
        self._t += speed
        self._draw()
        self.root.after(33, self._tick)

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 2)
        h = max(c.winfo_height(), 2)

        # subtle grid
        step = 40
        for x in range(0, w, step):
            c.create_line(x, 0, x, h, fill="#12202a")
        for y in range(0, h, step):
            c.create_line(0, y, w, y, fill="#12202a")

        cx, cy = w // 2, int(h * 0.42)
        # prefer reference image if available
        if getattr(self, "_base_img", None) is not None:
            img = self._base_img
            self._photo = img  # keep reference
            c.create_image(cx, cy, image=img)
            # light animated arcs over the art
            self._draw_overlay_arcs(c, cx, cy, base_r=min(w, h) * 0.18)
        else:
            self._draw_rings(c, cx, cy, base_r=min(w, h) * 0.22)

    def _draw_rings(self, c: tk.Canvas, cx: int, cy: int, base_r: float) -> None:
        t = self._t
        pulse = 1.0
        if self.state == VoiceState.LISTENING:
            pulse = 1.0 + 0.06 * math.sin(t * 3)
        elif self.state == VoiceState.SPEAKING:
            pulse = 1.0 + 0.08 * math.sin(t * 5)
        elif self.state == VoiceState.THINKING:
            pulse = 1.0 + 0.03 * math.sin(t * 2)

        # outer glow
        for i, mul in enumerate((1.55, 1.35, 1.18)):
            r = base_r * mul * pulse
            color = CYAN if i == 0 else CYAN_DIM
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)

        # tick ring
        r_tick = base_r * 1.05 * pulse
        for i in range(60):
            ang = math.radians(i * 6 + (t * 20 if self.state != VoiceState.IDLE else 0))
            x0 = cx + r_tick * math.cos(ang)
            y0 = cy + r_tick * math.sin(ang)
            x1 = cx + (r_tick - 6) * math.cos(ang)
            y1 = cy + (r_tick - 6) * math.sin(ang)
            c.create_line(x0, y0, x1, y1, fill=CYAN_DIM)

        # segmented arcs (rotate when active)
        rot = t * (80 if self.state in {VoiceState.LISTENING, VoiceState.SPEAKING} else 12)
        r_seg = base_r * 1.25 * pulse
        for start, extent in ((rot, 40), (rot + 90, 55), (rot + 200, 35), (rot + 280, 50)):
            c.create_arc(
                cx - r_seg,
                cy - r_seg,
                cx + r_seg,
                cy + r_seg,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=CYAN,
                width=6,
            )

        # inner rings
        for mul in (0.55, 0.35):
            r = base_r * mul
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=CYAN, width=2)

        # core
        core = base_r * 0.18
        c.create_oval(cx - core, cy - core, cx + core, cy + core, outline=CYAN_DIM, width=1)

    def run(self) -> None:
        self.root.mainloop()


def run_gui(*, title: str, on_submit: Callable[[str], str]) -> None:
    JarvisWindow(title=title, on_submit=on_submit).run()
