"""Tkinter desktop window: chat + glowing status orb."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import scrolledtext, font as tkfont
from typing import Callable

from assistant.voice.state_machine import VoiceState


# Colors per state (orb fill / glow)
_ORB = {
    VoiceState.IDLE: ("#1a3a4a", "#3d7a9a"),
    VoiceState.LISTENING: ("#00e5ff", "#80f0ff"),
    VoiceState.THINKING: ("#b388ff", "#7c4dff"),
    VoiceState.SPEAKING: ("#69f0ae", "#00c853"),
    VoiceState.ERROR: ("#ff5252", "#ff8a80"),
}


class JarvisWindow:
    def __init__(
        self,
        *,
        title: str,
        on_submit: Callable[[str], str],
        on_listen_visual: Callable[[VoiceState], None] | None = None,
    ):
        self.on_submit = on_submit
        self.on_listen_visual = on_listen_visual
        self.state = VoiceState.IDLE
        self._pulse = 0.0
        self._anim_job: str | None = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("720x560")
        self.root.minsize(520, 420)
        self.root.configure(bg="#0b1220")

        header = tk.Frame(self.root, bg="#0b1220")
        header.pack(fill=tk.X, padx=16, pady=(16, 8))

        self.canvas = tk.Canvas(
            header, width=120, height=120, bg="#0b1220", highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT)

        status_box = tk.Frame(header, bg="#0b1220")
        status_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))
        title_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.status_label = tk.Label(
            status_box,
            text="Idle — type below and press Send",
            fg="#e3f2fd",
            bg="#0b1220",
            font=title_font,
            anchor="w",
            justify=tk.LEFT,
        )
        self.status_label.pack(fill=tk.X)
        tip = tk.Label(
            status_box,
            text='Try: learn when I say morning do open calculator\nThen: yes   →   morning   →   list skills',
            fg="#90a4ae",
            bg="#0b1220",
            font=("Segoe UI", 10),
            anchor="w",
            justify=tk.LEFT,
        )
        tip.pack(fill=tk.X, pady=(8, 0))

        self.chat = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            height=16,
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            font=("Consolas", 11),
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self.chat.configure(state=tk.DISABLED)
        self.chat.tag_configure("you", foreground="#80cbc4")
        self.chat.tag_configure("jarvis", foreground="#ffe082")
        self.chat.tag_configure("sys", foreground="#90a4ae")

        row = tk.Frame(self.root, bg="#0b1220")
        row.pack(fill=tk.X, padx=16, pady=(0, 16))

        self.entry = tk.Entry(
            row,
            bg="#1f2937",
            fg="#f9fafb",
            insertbackground="#f9fafb",
            font=("Segoe UI", 12),
            relief=tk.FLAT,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._send())
        self.entry.focus_set()

        self.listen_btn = tk.Button(
            row,
            text="Listening demo",
            command=self._demo_listen,
            bg="#1565c0",
            fg="white",
            activebackground="#1976d2",
            relief=tk.FLAT,
            padx=12,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self.listen_btn.pack(side=tk.LEFT, padx=(0, 8))

        send_btn = tk.Button(
            row,
            text="Send",
            command=self._send,
            bg="#00897b",
            fg="white",
            activebackground="#26a69a",
            relief=tk.FLAT,
            padx=16,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        send_btn.pack(side=tk.LEFT)

        self._append_sys(
            "Welcome. Type in the box at the bottom and press Send (or Enter).\n"
            "The glowing circle shows status. “Listening demo” previews the Listening glow "
            "(real mic comes later)."
        )
        self._draw_orb()
        self._tick()

    def _append(self, who: str, text: str, tag: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{who}: ", tag)
        self.chat.insert(tk.END, text.rstrip() + "\n\n")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _append_sys(self, text: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, text.rstrip() + "\n\n", "sys")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def set_state(self, state: VoiceState, detail: str | None = None) -> None:
        self.state = state
        labels = {
            VoiceState.IDLE: "Idle — type below and press Send",
            VoiceState.LISTENING: "Listening — I’m ready for your words",
            VoiceState.THINKING: "Thinking…",
            VoiceState.SPEAKING: "Speaking (reply below)",
            VoiceState.ERROR: "Error",
        }
        msg = labels.get(state, state.value)
        if detail:
            msg = f"{msg} — {detail}"
        self.status_label.configure(text=msg)
        if self.on_listen_visual:
            self.on_listen_visual(state)
        self._draw_orb()

    def _draw_orb(self) -> None:
        self.canvas.delete("all")
        cx, cy = 60, 60
        base, glow = _ORB.get(self.state, _ORB[VoiceState.IDLE])
        # outer glow
        for i, r in enumerate((54, 48, 42)):
            scale = 1.0
            if self.state == VoiceState.LISTENING:
                scale = 1.0 + 0.08 * math.sin(self._pulse)
            elif self.state == VoiceState.SPEAKING:
                scale = 1.0 + 0.06 * math.sin(self._pulse * 1.7)
            elif self.state == VoiceState.THINKING:
                scale = 1.0 + 0.03 * math.sin(self._pulse * 0.8)
            rr = r * scale
            color = glow if i == 0 else base
            self.canvas.create_oval(
                cx - rr, cy - rr, cx + rr, cy + rr, outline=color, width=2 if i else 3
            )
        # core
        core_r = 22 + (4 * math.sin(self._pulse) if self.state != VoiceState.IDLE else 0)
        self.canvas.create_oval(
            cx - core_r,
            cy - core_r,
            cx + core_r,
            cy + core_r,
            fill=base,
            outline=glow,
            width=2,
        )

    def _tick(self) -> None:
        self._pulse += 0.25
        self._draw_orb()
        self._anim_job = self.root.after(50, self._tick)

    def _demo_listen(self) -> None:
        """Visual-only preview of Listening → Thinking → Speaking → Idle."""
        self.set_state(VoiceState.LISTENING)
        self.root.after(1200, lambda: self.set_state(VoiceState.THINKING))
        self.root.after(2200, lambda: self.set_state(VoiceState.SPEAKING))
        self.root.after(3400, lambda: self.set_state(VoiceState.IDLE))

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._append("You", text, "you")
        self.set_state(VoiceState.THINKING)
        self.root.update_idletasks()
        try:
            reply = self.on_submit(text)
        except Exception as e:  # noqa: BLE001
            self.set_state(VoiceState.ERROR, str(e))
            self._append("Jarvis", f"Something went wrong: {e}", "jarvis")
            self.root.after(800, lambda: self.set_state(VoiceState.IDLE))
            return
        self.set_state(VoiceState.SPEAKING)
        self._append("Jarvis", reply or "(no reply)", "jarvis")
        self.root.after(500, lambda: self.set_state(VoiceState.IDLE))

    def run(self) -> None:
        self.root.mainloop()


def run_gui(*, title: str, on_submit: Callable[[str], str]) -> None:
    JarvisWindow(title=title, on_submit=on_submit).run()
