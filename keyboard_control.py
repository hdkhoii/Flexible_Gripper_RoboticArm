"""Real-time keyboard controller for the PCA9685 robotic arm."""

from __future__ import annotations

import argparse
import sys
import time
import tkinter as tk
from tkinter import messagebox

import serial
from serial.tools import list_ports


BAUD_RATE = 115200
SEND_INTERVAL_MS = 40
CONTROL_KEYS = set("qawsedrftg")
KEY_ORDER = "qawsedrftg"
DEFAULT_SPEED_LEVEL = 3
SPEED_LEVELS_DEG_S = (25, 50, 80, 120)

JOINTS = (
    ("Hand", "Q / A"),
    ("Wrist", "W / S"),
    ("Elbow", "E / D"),
    ("Shoulder", "R / F"),
    ("Base", "T / G"),
)


def available_ports():
    return list(list_ports.comports())


def choose_port(requested_port: str | None) -> str:
    if requested_port:
        return requested_port

    ports = available_ports()
    arduino_ports = [
        port
        for port in ports
        if "arduino" in port.description.lower()
        or (port.vid == 0x2341 and port.pid is not None)
    ]
    if len(arduino_ports) == 1:
        return arduino_ports[0].device
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        raise RuntimeError("Khong tim thay cong COM. Hay ket noi Arduino.")

    joined = ", ".join(port.device for port in ports)
    raise RuntimeError(
        f"Co nhieu cong COM ({joined}). Chay lai voi: --port COMx"
    )


class ArmController:
    def __init__(self, root: tk.Tk, port: str) -> None:
        self.root = root
        self.port = port
        self.serial = serial.Serial(port, BAUD_RATE, timeout=0, write_timeout=0.1)
        self.held_keys: set[str] = set()
        self.closed = False
        self.receive_buffer = ""
        self.speed_level = DEFAULT_SPEED_LEVEL

        self.root.title(f"Robotic Arm - {port}")
        self.root.geometry("510x410")
        self.root.resizable(False, False)

        title = tk.Label(
            root,
            text="DIEU KHIEN TAY MAY REAL-TIME",
            font=("Segoe UI", 16, "bold"),
        )
        title.pack(pady=(18, 8))

        tk.Label(
            root,
            text="Bam va giu phim de di chuyen - co the giu nhieu phim cung luc",
            font=("Segoe UI", 10),
        ).pack()

        grid = tk.Frame(root)
        grid.pack(pady=16)
        self.angle_labels: list[tk.Label] = []

        for row, (joint, keys) in enumerate(JOINTS):
            tk.Label(grid, text=joint, width=12, anchor="w", font=("Segoe UI", 11)).grid(
                row=row, column=0, padx=8, pady=4
            )
            tk.Label(grid, text=keys, width=9, font=("Consolas", 11, "bold")).grid(
                row=row, column=1, padx=8, pady=4
            )
            angle_label = tk.Label(
                grid, text="--- deg", width=10, anchor="e", font=("Consolas", 11)
            )
            angle_label.grid(row=row, column=2, padx=8, pady=4)
            self.angle_labels.append(angle_label)

        tk.Label(
            root,
            text="0: ve 0 deg (tat ca)   |   9: ve 90 deg (tat ca)   |   1-4: toc do   |   Esc: thoat",
            font=("Segoe UI", 10),
        ).pack(pady=(2, 2))

        tk.Label(
            root,
            text="H: rieng Hand ve 0 deg",
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(0, 12))

        self.keys_label = tk.Label(
            root, text="Phim dang giu: (khong)", font=("Consolas", 11, "bold")
        )
        self.keys_label.pack()

        self.speed_label = tk.Label(
            root,
            text=f"Toc do: 3/4 ({SPEED_LEVELS_DEG_S[2]} deg/s)",
            font=("Segoe UI", 10, "bold"),
            fg="#8a4b08",
        )
        self.speed_label.pack(pady=(8, 0))

        self.status_label = tk.Label(
            root, text=f"Da ket noi {port} @ {BAUD_RATE} baud", fg="#167a32"
        )
        self.status_label.pack(pady=12)

        self.root.bind_all("<KeyPress>", self.on_key_press)
        self.root.bind_all("<KeyRelease>", self.on_key_release)
        self.root.bind("<FocusOut>", self.on_focus_lost)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.focus_window)
        self.root.after(SEND_INTERVAL_MS, self.communication_tick)

    def focus_window(self) -> None:
        self.root.focus_force()

    def on_key_press(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        if key in CONTROL_KEYS:
            self.held_keys.add(key)
            self.update_keys_label()
        elif key in {"0", "9"}:
            self.send_line(key)
        elif key == "h":
            self.send_line("H")
        elif key in {"1", "2", "3", "4"}:
            self.speed_level = int(key)
            self.update_speed_label()
            self.send_speed()
        elif key == "escape":
            self.close()

    def on_key_release(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        if key in CONTROL_KEYS:
            self.held_keys.discard(key)
            self.update_keys_label()
            self.send_key_state()

    def on_focus_lost(self, _event: tk.Event) -> None:
        self.held_keys.clear()
        self.update_keys_label()
        self.send_key_state()

    def update_keys_label(self) -> None:
        keys = " ".join(key.upper() for key in KEY_ORDER if key in self.held_keys)
        self.keys_label.config(text=f"Phim dang giu: {keys or '(khong)'}")

    def update_speed_label(self) -> None:
        degrees_per_second = SPEED_LEVELS_DEG_S[self.speed_level - 1]
        self.speed_label.config(
            text=f"Toc do: {self.speed_level}/4 ({degrees_per_second} deg/s)"
        )

    def send_line(self, message: str) -> None:
        if not self.closed:
            self.serial.write((message + "\n").encode("ascii"))

    def send_key_state(self) -> None:
        keys = "".join(key for key in KEY_ORDER if key in self.held_keys)
        self.send_line("K" + keys)

    def send_speed(self) -> None:
        self.send_line(f"V{self.speed_level}")

    def read_status(self) -> None:
        waiting = self.serial.in_waiting
        if waiting <= 0:
            return

        self.receive_buffer += self.serial.read(waiting).decode("ascii", errors="ignore")
        lines = self.receive_buffer.replace("\r", "").split("\n")
        self.receive_buffer = lines.pop()

        for line in lines:
            if line.startswith("V,"):
                try:
                    self.speed_level = max(1, min(4, int(line.split(",")[1])))
                    self.update_speed_label()
                except (ValueError, IndexError):
                    pass
                continue
            if not line.startswith("A,"):
                continue
            fields = line.split(",")[1:]
            if len(fields) == len(self.angle_labels):
                for label, angle in zip(self.angle_labels, fields):
                    label.config(text=f"{angle:>3} deg")

    def communication_tick(self) -> None:
        if self.closed:
            return
        try:
            self.send_key_state()
            self.send_speed()
            self.read_status()
        except (serial.SerialException, serial.SerialTimeoutException) as error:
            self.status_label.config(text=f"Mat ket noi: {error}", fg="#b00020")
            self.held_keys.clear()
        self.root.after(SEND_INTERVAL_MS, self.communication_tick)

    def close(self) -> None:
        if self.closed:
            return
        self.held_keys.clear()
        try:
            self.send_key_state()
            time.sleep(0.05)
            self.serial.close()
        finally:
            self.closed = True
            self.root.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dieu khien tay may bang ban phim")
    parser.add_argument("--port", help="Cong Arduino, vi du COM3")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        port = choose_port(args.port)
        root = tk.Tk()
        ArmController(root, port)
        root.mainloop()
        return 0
    except (RuntimeError, serial.SerialException) as error:
        message = str(error)
        print(f"Loi: {message}", file=sys.stderr)
        try:
            messagebox.showerror("Khong the ket noi", message)
        except tk.TclError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
