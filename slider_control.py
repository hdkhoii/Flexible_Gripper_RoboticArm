"""Dieu khien tay may bang slider keo goc — GUI Python (Tkinter).

Moi slider tuong ung voi mot khop servo. Keo slider den goc mong muon,
Arduino se di chuyen servo den dung goc do (co gia toc / phanh mem).

Firmware phai duoc nap voi lenh G<joint_index>,<angle>.
Vi du: G0,120  -> dat HAND ve 120 do.

Chay: python slider_control.py [--port COMx]
"""

from __future__ import annotations

import argparse
import sys
import time
import tkinter as tk
from tkinter import messagebox

import serial
from serial.tools import list_ports

# ---------------------------------------------------------------------------
# Cau hinh
# ---------------------------------------------------------------------------

BAUD_RATE = 115200
POLL_MS = 50          # Tan suat cap nhat UI (ms)
ARRIVAL_TOLERANCE_DEG = 2.0
ARRIVAL_STABLE_SAMPLES = 3
MOVE_TIMEOUT_S = 20.0
GRIP_SETTLE_S = 0.8
HAND_INDEX = 0
ARM_JOINTS = (1, 2, 3, 4)

# Ten va thong so tung khop (phai khop voi thu tu trong firmware)
# (ten, min_deg, max_deg, initial_deg)
JOINTS = [
    ("Hand",     100, 160, 150),
    ("Wrist",    0, 180,  90),
    ("Elbow",    0, 180, 180),
    ("Shoulder", 0, 180,   0),
    ("Base",     0, 180,  90),
]

# Mau sac giao dien
BG_COLOR         = "#1e1e2e"
PANEL_COLOR      = "#2a2a3e"
ACCENT_COLOR     = "#7c6af7"
TEXT_COLOR       = "#cdd6f4"
LABEL_COLOR      = "#a6adc8"
VALUE_COLOR      = "#cba6f7"
TRACK_COLOR      = "#45475a"
THUMB_COLOR      = "#7c6af7"
FEEDBACK_COLOR   = "#a6e3a1"
STATUS_OK_COLOR  = "#a6e3a1"
STATUS_ERR_COLOR = "#f38ba8"


# ---------------------------------------------------------------------------
# Quet cong
# ---------------------------------------------------------------------------

def available_ports():
    return list(list_ports.comports())


def choose_port(requested):
    if requested:
        return requested
    ports = available_ports()
    arduino_ports = [
        p for p in ports
        if "arduino" in p.description.lower()
        or (p.vid == 0x2341 and p.pid is not None)
    ]
    if len(arduino_ports) == 1:
        return arduino_ports[0].device
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        raise RuntimeError("Khong tim thay cong COM. Hay ket noi Arduino.")
    joined = ", ".join(p.device for p in ports)
    raise RuntimeError(f"Co nhieu cong COM ({joined}). Chay lai voi --port COMx")


# ---------------------------------------------------------------------------
# Widget Slider tuy chinh
# ---------------------------------------------------------------------------

class JointSlider(tk.Frame):
    """Mot hang slider cho mot khop servo."""

    SLIDER_W = 420
    SLIDER_H = 44
    THUMB_R  = 11
    TRACK_Y  = 20
    PAD_X    = 16

    def __init__(self, parent, joint_index, name, min_deg, max_deg, initial_deg, on_change, **kwargs):
        super().__init__(parent, bg=PANEL_COLOR, **kwargs)
        self.joint_index = joint_index
        self.min_deg = min_deg
        self.max_deg = max_deg
        self._value = float(initial_deg)
        self._feedback = float(initial_deg)
        self._on_change = on_change
        self._dragging = False

        tk.Label(
            self, text=name, width=10, anchor="w",
            font=("Segoe UI", 11, "bold"),
            bg=PANEL_COLOR, fg=TEXT_COLOR,
        ).grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=6)

        self.canvas = tk.Canvas(
            self,
            width=self.SLIDER_W, height=self.SLIDER_H,
            bg=PANEL_COLOR, highlightthickness=0,
        )
        self.canvas.grid(row=0, column=1, rowspan=2, padx=6, pady=4)
        self._draw()

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.set_label = tk.Label(
            self, text=f"{int(initial_deg):>3}\u00b0", width=5,
            font=("Consolas", 12, "bold"),
            bg=PANEL_COLOR, fg=VALUE_COLOR,
        )
        self.set_label.grid(row=0, column=2, padx=(4, 12), sticky="s")

        self.fb_label = tk.Label(
            self, text=f"[{int(initial_deg):>3}\u00b0]", width=7,
            font=("Consolas", 10),
            bg=PANEL_COLOR, fg=FEEDBACK_COLOR,
        )
        self.fb_label.grid(row=1, column=2, padx=(4, 12), sticky="n")

    def _px(self, value):
        ratio = (value - self.min_deg) / max(self.max_deg - self.min_deg, 1)
        return self.PAD_X + ratio * (self.SLIDER_W - 2 * self.PAD_X)

    def _val(self, x):
        ratio = (x - self.PAD_X) / max(self.SLIDER_W - 2 * self.PAD_X, 1)
        return self.min_deg + max(0.0, min(1.0, ratio)) * (self.max_deg - self.min_deg)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        tx1 = self.PAD_X
        tx2 = self.SLIDER_W - self.PAD_X
        ty  = self.TRACK_Y
        tr  = 5

        # Track background
        c.create_rectangle(tx1, ty - tr, tx2, ty + tr, fill=TRACK_COLOR, outline="")
        c.create_oval(tx1 - tr, ty - tr, tx1 + tr, ty + tr, fill=TRACK_COLOR, outline="")
        c.create_oval(tx2 - tr, ty - tr, tx2 + tr, ty + tr, fill=TRACK_COLOR, outline="")

        # Filled portion
        thumb_x = self._px(self._value)
        if thumb_x > tx1:
            c.create_rectangle(tx1, ty - tr, thumb_x, ty + tr, fill=ACCENT_COLOR, outline="")
            c.create_oval(tx1 - tr, ty - tr, tx1 + tr, ty + tr, fill=ACCENT_COLOR, outline="")
            c.create_oval(thumb_x - tr, ty - tr, thumb_x + tr, ty + tr, fill=ACCENT_COLOR, outline="")

        # Feedback triangle (Arduino actual position)
        fb_x = self._px(self._feedback)
        tri_top = ty + self.THUMB_R + 1
        c.create_polygon(
            fb_x, tri_top,
            fb_x - 5, tri_top + 8,
            fb_x + 5, tri_top + 8,
            fill=FEEDBACK_COLOR, outline="",
        )

        # Thumb
        c.create_oval(
            thumb_x - self.THUMB_R, ty - self.THUMB_R,
            thumb_x + self.THUMB_R, ty + self.THUMB_R,
            fill=THUMB_COLOR, outline="#89b4fa", width=2,
        )

        # Tick marks
        step = 30
        for deg in range(self.min_deg, self.max_deg + 1, step):
            px = self._px(deg)
            c.create_line(px, ty - self.THUMB_R - 2, px, ty - self.THUMB_R - 7,
                          fill=LABEL_COLOR, width=1)
            c.create_text(px, ty - self.THUMB_R - 14, text=str(deg),
                          fill=LABEL_COLOR, font=("Segoe UI", 7))

    def _on_press(self, event):
        self._dragging = True
        self._update_from_pixel(event.x)

    def _on_drag(self, event):
        if self._dragging:
            self._update_from_pixel(event.x)

    def _on_release(self, event):
        if self._dragging:
            self._update_from_pixel(event.x)
            self._dragging = False

    def _update_from_pixel(self, x):
        new_val = round(self._val(x))
        if new_val != round(self._value):
            self._value = float(new_val)
            self.set_label.config(text=f"{int(self._value):>3}\u00b0")
            self._draw()
            self._on_change(self.joint_index, self._value)

    def set_value(self, angle):
        self._value = float(angle)
        self.set_label.config(text=f"{int(angle):>3}\u00b0")
        self._draw()

    def set_feedback(self, angle):
        self._feedback = float(angle)
        self.fb_label.config(text=f"[{int(angle):>3}\u00b0]")
        self._draw()

    def get_value(self):
        return self._value


# ---------------------------------------------------------------------------
# Ung dung chinh
# ---------------------------------------------------------------------------

class SliderController:
    def __init__(self, root, port):
        self.root = root
        self.closed = False
        self.receive_buffer = ""
        self._pending = {}
        self.actual_angles = [None] * len(JOINTS)

        # A va B la hai diem lam viec. SAFE la tu the trung chuyen tren cao;
        # mac dinh dung tu the khoi dong va co the day lai tren giao dien.
        self.points = {
            "A": None,
            "B": None,
            "SAFE": {i: float(JOINTS[i][3]) for i in ARM_JOINTS},
        }
        self.grip_open_angle = None
        self.grip_close_angle = None
        self.auto_steps = []
        self.auto_step_index = -1
        self.auto_target = None
        self.auto_deadline = 0.0
        self.auto_wait_until = 0.0
        self.auto_stable_samples = 0

        self.serial = serial.Serial(port, BAUD_RATE, timeout=0, write_timeout=0.1)

        root.title(f"Tay May \u2014 Dieu Khien Slider  ({port})")
        root.configure(bg=BG_COLOR)
        root.resizable(False, False)

        tk.Label(
            root, text="\u2699  DIEU KHIEN TAY MAY \u2014 KEO GOC SERVO",
            font=("Segoe UI", 14, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR,
        ).pack(pady=(16, 2))

        tk.Label(
            root,
            text="Keo slider de dat goc.   \u25bc xanh la = vi tri hien tai cua servo.",
            font=("Segoe UI", 9),
            bg=BG_COLOR, fg=LABEL_COLOR,
        ).pack(pady=(0, 10))

        sf = tk.Frame(root, bg=BG_COLOR)
        sf.pack(padx=20, pady=2)

        self.sliders = []
        for i, (name, lo, hi, init) in enumerate(JOINTS):
            s = JointSlider(sf, i, name, lo, hi, init, self._slider_changed)
            s.pack(fill="x", pady=3)
            self.sliders.append(s)

        btn_frame = tk.Frame(root, bg=BG_COLOR)
        btn_frame.pack(pady=(14, 6))

        for text, cmd in [
            ("Ve 0\u00b0 (tat ca)",  lambda: self._go_preset(0)),
            ("Ve 90\u00b0 (tat ca)", lambda: self._go_preset(90)),
            ("Reset ban dau",        self._go_initial),
        ]:
            tk.Button(
                btn_frame, text=f"  {text}  ", command=cmd,
                font=("Segoe UI", 10), bg="#313244", fg=TEXT_COLOR,
                activebackground=ACCENT_COLOR, activeforeground="#ffffff",
                relief="flat", padx=10, pady=5, cursor="hand2",
            ).pack(side="left", padx=6)

        teach_frame = tk.LabelFrame(
            root, text="  DAY DIEM A/B VA KEP  ",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR, padx=10, pady=8,
        )
        teach_frame.pack(fill="x", padx=20, pady=(8, 4))

        point_buttons = tk.Frame(teach_frame, bg=BG_COLOR)
        point_buttons.pack()
        for text, point in [
            ("Luu diem A", "A"),
            ("Luu diem B", "B"),
            ("Luu diem SAFE", "SAFE"),
        ]:
            tk.Button(
                point_buttons, text=text,
                command=lambda p=point: self._capture_point(p),
                font=("Segoe UI", 9), bg="#313244", fg=TEXT_COLOR,
                activebackground=ACCENT_COLOR, activeforeground="#ffffff",
                relief="flat", padx=8, pady=4, cursor="hand2",
            ).pack(side="left", padx=4)

        grip_buttons = tk.Frame(teach_frame, bg=BG_COLOR)
        grip_buttons.pack(pady=(7, 0))
        tk.Button(
            grip_buttons, text="Luu goc MO kep",
            command=lambda: self._capture_grip(True),
            font=("Segoe UI", 9), bg="#313244", fg=TEXT_COLOR,
            activebackground=ACCENT_COLOR, activeforeground="#ffffff",
            relief="flat", padx=8, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)
        tk.Button(
            grip_buttons, text="Luu goc DONG kep",
            command=lambda: self._capture_grip(False),
            font=("Segoe UI", 9), bg="#313244", fg=TEXT_COLOR,
            activebackground=ACCENT_COLOR, activeforeground="#ffffff",
            relief="flat", padx=8, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)

        self.teach_status_label = tk.Label(
            teach_frame,
            text="A: chua luu | B: chua luu | SAFE: mac dinh | Mo/Đong kep: chua luu",
            font=("Segoe UI", 9), bg=BG_COLOR, fg=LABEL_COLOR,
        )
        self.teach_status_label.pack(pady=(8, 0))

        auto_frame = tk.Frame(root, bg=BG_COLOR)
        auto_frame.pack(pady=(7, 1))
        self.run_button = tk.Button(
            auto_frame, text="  CHAY A  ->  B  ", command=self._run_a_to_b,
            font=("Segoe UI", 10, "bold"), bg="#2f8f56", fg="#ffffff",
            activebackground="#40a96b", activeforeground="#ffffff",
            relief="flat", padx=12, pady=6, cursor="hand2",
        )
        self.run_button.pack(side="left", padx=6)
        tk.Button(
            auto_frame, text="  DUNG KHAN CAP  ", command=self._emergency_stop,
            font=("Segoe UI", 10, "bold"), bg="#b00020", fg="#ffffff",
            activebackground="#d02040", activeforeground="#ffffff",
            relief="flat", padx=12, pady=6, cursor="hand2",
        ).pack(side="left", padx=6)

        self.status_label = tk.Label(
            root,
            text=f"\u2714  Ket noi  {port}  @  {BAUD_RATE} baud",
            font=("Segoe UI", 9),
            bg=BG_COLOR, fg=STATUS_OK_COLOR,
        )
        self.status_label.pack(pady=(6, 12))

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(POLL_MS, self._tick)

    def _slider_changed(self, joint, angle):
        if self.auto_steps:
            self._stop_automation("Da dung tu dong de dieu khien thu cong.")
        self._pending[joint] = angle

    def _send_angle(self, joint, angle):
        if not self.closed:
            self.serial.write(f"G{joint},{angle:.1f}\n".encode("ascii"))

    def _go_preset(self, angle):
        if self.auto_steps:
            self._stop_automation("Da dung tu dong.")
        for i, s in enumerate(self.sliders):
            safe_angle = max(s.min_deg, min(s.max_deg, float(angle)))
            s.set_value(safe_angle)
            self._pending[i] = safe_angle

    def _go_initial(self):
        if self.auto_steps:
            self._stop_automation("Da dung tu dong.")
        for i, (_, _, _, init) in enumerate(JOINTS):
            self.sliders[i].set_value(float(init))
            self._pending[i] = float(init)

    def _capture_point(self, name):
        if self.auto_steps:
            messagebox.showwarning("Dang chay", "Hay dung chu trinh truoc khi day diem.")
            return
        self.points[name] = {i: self.sliders[i].get_value() for i in ARM_JOINTS}
        self._update_teach_status()
        self.status_label.config(text=f"Da luu diem {name}.", fg=STATUS_OK_COLOR)

    def _capture_grip(self, is_open):
        if self.auto_steps:
            messagebox.showwarning("Dang chay", "Hay dung chu trinh truoc khi day kep.")
            return
        angle = self.sliders[HAND_INDEX].get_value()
        if is_open:
            self.grip_open_angle = angle
            text = "MO"
        else:
            self.grip_close_angle = angle
            text = "DONG"
        self._update_teach_status()
        self.status_label.config(
            text=f"Da luu goc {text} kep: {angle:.0f} do.", fg=STATUS_OK_COLOR
        )

    def _update_teach_status(self):
        a = "da luu" if self.points["A"] else "chua luu"
        b = "da luu" if self.points["B"] else "chua luu"
        safe = "da luu" if self.points["SAFE"] else "chua luu"
        opened = ("chua luu" if self.grip_open_angle is None
                  else f"{self.grip_open_angle:.0f} deg")
        closed = ("chua luu" if self.grip_close_angle is None
                  else f"{self.grip_close_angle:.0f} deg")
        self.teach_status_label.config(
            text=f"A: {a} | B: {b} | SAFE: {safe} | Mo: {opened} | Dong: {closed}"
        )

    def _run_a_to_b(self):
        missing = []
        if self.points["A"] is None:
            missing.append("diem A")
        if self.points["B"] is None:
            missing.append("diem B")
        if self.grip_open_angle is None:
            missing.append("goc MO kep")
        if self.grip_close_angle is None:
            missing.append("goc DONG kep")
        if missing:
            messagebox.showwarning(
                "Chua day du",
                "Can luu: " + ", ".join(missing) + ".",
            )
            return
        if any(angle is None for angle in self.actual_angles):
            messagebox.showwarning(
                "Chua co phan hoi", "Chua nhan duoc trang thai goc tu Arduino."
            )
            return

        self._pending.clear()
        self._send_line("X")
        self.auto_steps = [
            ("Mo kep", {HAND_INDEX: self.grip_open_angle}, GRIP_SETTLE_S),
            ("Ve diem an toan", self.points["SAFE"], 0.0),
            ("Di den A", self.points["A"], 0.0),
            ("Kep vat tai A", {HAND_INDEX: self.grip_close_angle}, GRIP_SETTLE_S),
            ("Nang ve diem an toan", self.points["SAFE"], 0.0),
            ("Di den B", self.points["B"], 0.0),
            ("Tha vat tai B", {HAND_INDEX: self.grip_open_angle}, GRIP_SETTLE_S),
            ("Roi ve diem an toan", self.points["SAFE"], 0.0),
        ]
        self.auto_step_index = -1
        self.run_button.config(state="disabled")
        self._start_next_auto_step()

    def _send_line(self, message):
        if not self.closed:
            self.serial.write((message + "\n").encode("ascii"))

    def _start_next_auto_step(self):
        self.auto_step_index += 1
        if self.auto_step_index >= len(self.auto_steps):
            self.auto_steps = []
            self.auto_target = None
            self.run_button.config(state="normal")
            self.status_label.config(
                text="Hoan thanh chu trinh gap A -> B.", fg=STATUS_OK_COLOR
            )
            return

        name, target, _settle = self.auto_steps[self.auto_step_index]
        self.auto_target = dict(target)
        self.auto_deadline = time.monotonic() + MOVE_TIMEOUT_S
        self.auto_wait_until = 0.0
        self.auto_stable_samples = 0
        for joint, angle in self.auto_target.items():
            self.sliders[joint].set_value(angle)
            self._pending[joint] = angle
        self.status_label.config(
            text=f"Tu dong {self.auto_step_index + 1}/{len(self.auto_steps)}: {name}",
            fg=VALUE_COLOR,
        )

    def _update_automation(self):
        if not self.auto_steps:
            return
        now = time.monotonic()
        if self.auto_wait_until:
            if now >= self.auto_wait_until:
                self._start_next_auto_step()
            return
        if now > self.auto_deadline:
            name = self.auto_steps[self.auto_step_index][0]
            self._stop_automation(f"Timeout khi: {name}", emergency=True)
            messagebox.showerror(
                "Robot khong toi dich",
                f"Robot khong toi dich trong {MOVE_TIMEOUT_S:.0f} giay. Da dung khan cap.",
            )
            return
        arrived = all(
            self.actual_angles[joint] is not None
            and abs(self.actual_angles[joint] - angle) <= ARRIVAL_TOLERANCE_DEG
            for joint, angle in self.auto_target.items()
        )
        self.auto_stable_samples = self.auto_stable_samples + 1 if arrived else 0
        if self.auto_stable_samples >= ARRIVAL_STABLE_SAMPLES:
            _name, _target, settle = self.auto_steps[self.auto_step_index]
            if settle > 0:
                self.auto_target = None
                self.auto_wait_until = now + settle
            else:
                self._start_next_auto_step()

    def _stop_automation(self, reason, emergency=True):
        self.auto_steps = []
        self.auto_target = None
        self.auto_wait_until = 0.0
        self.auto_stable_samples = 0
        self._pending.clear()
        if emergency:
            self._send_line("X")
        self.run_button.config(state="normal")
        self.status_label.config(text=reason, fg=STATUS_ERR_COLOR)

    def _emergency_stop(self):
        self._stop_automation("DA DUNG KHAN CAP.", emergency=True)

    def _tick(self):
        if self.closed:
            return
        try:
            for joint, angle in list(self._pending.items()):
                self._send_angle(joint, angle)
                del self._pending[joint]
            self._read_status()
            self._update_automation()
        except (serial.SerialException, serial.SerialTimeoutException) as err:
            self.auto_steps = []
            self.auto_target = None
            self.run_button.config(state="normal")
            self.status_label.config(text=f"\u2716  Loi: {err}", fg=STATUS_ERR_COLOR)
        self.root.after(POLL_MS, self._tick)

    def _read_status(self):
        waiting = self.serial.in_waiting
        if waiting <= 0:
            return
        self.receive_buffer += self.serial.read(waiting).decode("ascii", errors="ignore")
        lines = self.receive_buffer.replace("\r", "").split("\n")
        self.receive_buffer = lines.pop()
        for line in lines:
            if not line.startswith("A,"):
                continue
            fields = line.split(",")[1:]
            if len(fields) == len(self.sliders):
                for slider, field in zip(self.sliders, fields):
                    try:
                        angle = float(field)
                        slider.set_feedback(angle)
                        self.actual_angles[slider.joint_index] = angle
                    except ValueError:
                        pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.serial.write(b"X\n")
            time.sleep(0.05)
            self.serial.close()
        finally:
            self.root.destroy()


# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Dieu khien tay may bang slider keo goc")
    p.add_argument("--port", help="Cong Arduino, vi du COM3")
    return p.parse_args()


def main():
    args = parse_args()
    try:
        port = choose_port(args.port)
        root = tk.Tk()
        SliderController(root, port)
        root.mainloop()
        return 0
    except (RuntimeError, serial.SerialException) as err:
        msg = str(err)
        print(f"Loi: {msg}", file=sys.stderr)
        try:
            messagebox.showerror("Khong the ket noi", msg)
        except tk.TclError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
