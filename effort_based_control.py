"""
Effort-Based EEG Cursor Control (NO CLICK)
------------------------------------------
IDLE:
  - Meditation > 55
  - Attention < 40

MOVE MODE:
  - Attention > 60
  - Meditation < 45
  - Alpha drop (engagement confirmation)

Movement:
  - LEFT  : betaRatio < 0.9
  - RIGHT : betaRatio > 1.1
  - IDLE  : Meditation > 55, Attention < 40 (Stop)

Click: ❌ REMOVED (intentionally)
"""

import websocket
import json
import time
import threading
from collections import deque
import tkinter as tk
from tkinter import ttk
import pyautogui

# ================= CONFIG =================
ESP32_IP = "NeuroCursor-esp.local"
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

ATTENTION_ON = 45
ATTENTION_OFF = 35
MEDITATION_LOCK = 55
ALPHA_DROP_THRESHOLD = 0.85  # ~15% drop

BETA_RATIO_LEFT = 0.9
BETA_RATIO_RIGHT = 1.1

MOVEMENT_SPEED_BASE = 8
MOVEMENT_FACTOR = 0.5
POLLING_INTERVAL = 0.1  # Faster for smoother proportional move

MOVE_COOLDOWN = 0.05  # Lowered for proportional smoothness

# ================= EMA STATE =================
avg_att = 0.0
avg_med = 0.0
baseline_att = 50.0  
EMA_ALPHA = 0.2  

sens_left = 5.0   # Default Gain
sens_right = 5.0  # Default Gain

last_move_time = 0
fail_safe_paused = False

current_data = {
    "sig": 200,
    "att": 0,
    "med": 0,
    "la": 0,
    "ha": 0,
    "lb": 0,
    "hb": 0
}

data_lock = threading.Lock()
ws_connected = False

att_history = deque(maxlen=5)
alpha_history = deque(maxlen=5)

# ================= GUI APP (NeuroGlide) =================
class EffortControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 NeuroGlide – Pure Intent Control")
        self.root.geometry("600x680")
        self.root.configure(bg="#0b0f19") # Deep space dark

        pyautogui.FAILSAFE = True

        # Custom Style Overrides
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", thickness=15, troughcolor="#1a202c", bordercolor="#1a202c", relief="flat")
        style.configure("Horizontal.TProgressbar", background="#4fd1c5") # Teal for Gauges

        main = tk.Frame(root, bg="#0b0f19")
        main.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(
            main, text="NEUROGLIDE",
            font=("fixedsys", 32, "bold"),
            bg="#0b0f19", fg="#4fd1c5"
        ).pack(pady=(0, 5))

        tk.Label(
            main, text="PURE INTENT CONTROL SYSTEM",
            font=("Segoe UI", 8, "bold"),
            bg="#0b0f19", fg="#718096"
        ).pack(pady=(0, 20))

        self.status_label = tk.Label(
            main, text="🔴 OFFLINE",
            font=("Segoe UI", 10),
            bg="#0b0f19", fg="#e53e3e"
        )
        self.status_label.pack()

        # State Display (Modern Header)
        self.state_frame = tk.Frame(main, bg="#1a202c", bd=0, highlightthickness=1, highlightbackground="#2d3748")
        self.state_frame.pack(fill="x", pady=20)
        self.state_frame.pack_propagate(False)
        self.state_frame.config(height=80)

        self.state_label = tk.Label(
            self.state_frame, text="CALIBRATING...",
            font=("Consolas", 28, "bold"),
            bg="#1a202c", fg="#a0aec0"
        )
        self.state_label.pack(expand=True)

        # Data Gauges Container
        gauge = tk.Frame(main, bg="#1a202c", padx=15, pady=15, bd=0, highlightthickness=1, highlightbackground="#2d3748")
        gauge.pack(fill="x", pady=10)

        self.att_bar = self.make_gauge(gauge, "ATTENTION", 0, "#4fd1c5")
        self.med_bar = self.make_gauge(gauge, "MEDITATION", 1, "#63b3ed")

        self.beta_label = tk.Label(
            gauge, text="SIGNAL STABILITY: SCANNING...",
            font=("Consolas", 8), bg="#1a202c", fg="#718096"
        )
        self.beta_label.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        # Sensitivity Control Panel
        sens_panel = tk.Frame(main, bg="#0b0f19")
        sens_panel.pack(fill="x", pady=10)
        
        # Left Slider
        l_f = tk.Frame(sens_panel, bg="#0b0f19")
        l_f.pack(side="left", expand=True)
        tk.Label(l_f, text="LEFT SENS", font=("Segoe UI", 8, "bold"), bg="#0b0f19", fg="#a0aec0").pack()
        self.s_left = tk.Scale(l_f, from_=1, to=15, orient="horizontal", bg="#0b0f19", fg="white", 
                               troughcolor="#2d3748", highlightthickness=0, bd=0)
        self.s_left.set(5)
        self.s_left.pack(fill="x", padx=10)

        # Right Slider
        r_f = tk.Frame(sens_panel, bg="#0b0f19")
        r_f.pack(side="left", expand=True)
        tk.Label(r_f, text="RIGHT SENS", font=("Segoe UI", 8, "bold"), bg="#0b0f19", fg="#a0aec0").pack()
        self.s_right = tk.Scale(r_f, from_=1, to=15, orient="horizontal", bg="#0b0f19", fg="white", 
                                troughcolor="#2d3748", highlightthickness=0, bd=0)
        self.s_right.set(10)
        self.s_right.pack(fill="x", padx=10)

        self.active = False
        ctrl = tk.Frame(main, bg="#0b0f19")
        ctrl.pack(pady=15)

        self.toggle_btn = tk.Button(
            ctrl, text="ACTIVATE SYSTEM",
            font=("Segoe UI", 10, "bold"),
            bg="#38a169", fg="white",
            relief="flat", width=18, height=2,
            command=self.toggle_active
        )
        self.toggle_btn.pack(side="left", padx=10)

        self.zero_btn = tk.Button(
            ctrl, text="CALIBRATE BASELINE",
            font=("Segoe UI", 10, "bold"),
            bg="#3182ce", fg="white",
            relief="flat", width=18, height=2,
            command=self.set_baseline
        )
        self.zero_btn.pack(side="left", padx=10)

        # Energy Bars Container (The "Push/Pull" visuals)
        e_container = tk.Frame(main, bg="#1a202c", padx=15, pady=15, bd=0, highlightthickness=1, highlightbackground="#2d3748")
        e_container.pack(fill="x", pady=10)
        
        self.l_energy = self.make_energy_bar(e_container, "INTENT: LEFT", "#3182ce")
        self.r_energy = self.make_energy_bar(e_container, "INTENT: RIGHT", "#e53e3e")

        # Compact Log
        self.log_box = tk.Text(
            main, height=3,
            bg="#000000", fg="#4fd1c5",
            font=("Consolas", 8), bd=0, padx=10, pady=5
        )
        self.log_box.pack(fill="x")

        self.log("NEURAL LINK: STANDBY. Press [SPACE] to Center.")
        self.root.bind("<space>", lambda e: self.center_mouse())
        self.update_loop()

    def make_gauge(self, parent, name, row, color):
        tk.Label(parent, text=name, font=("Segoe UI", 8, "bold"), bg="#1a202c", fg="#a0aec0").grid(row=row, column=0, padx=10, sticky="w")
        bar = ttk.Progressbar(parent, length=380, maximum=100, style="Horizontal.TProgressbar")
        bar.grid(row=row, column=1, padx=10, pady=5)
        return bar

    def make_energy_bar(self, parent, name, color):
        f = tk.Frame(parent, bg="#1a202c")
        f.pack(fill="x", pady=2)
        tk.Label(f, text=name, font=("Segoe UI", 7, "bold"), bg="#1a202c", fg="#718096").pack(side="left", padx=5)
        bar = ttk.Progressbar(f, length=380, maximum=100)
        bar.pack(side="right", padx=5)
        return bar

    def set_baseline(self):
        global baseline_att
        baseline_att = avg_att
        self.log(f"Baseline set to {int(baseline_att)}")

    def center_mouse(self):
        sw, sh = pyautogui.size()
        pyautogui.moveTo(sw//2, sh//2)
        self.log("🎯 Mouse Centered")

    def log(self, msg):
        self.log_box.insert(tk.END, f"> {msg}\n")
        self.log_box.see(tk.END)

    def toggle_active(self):
        self.active = not self.active
        if self.active:
            self.toggle_btn.config(text="STOP SYSTEM", bg="#e53e3e")
            self.log("NEURAL LINK: ACTIVE")
        else:
            self.toggle_btn.config(text="ACTIVATE SYSTEM", bg="#38a169")
            self.log("NEURAL LINK: STANDBY")

    def update_loop(self):
        global last_move_time, fail_safe_paused, avg_att, avg_med, baseline_att

        if fail_safe_paused:
            self.state_label.config(text="SYSTEM LOCK", fg="#e53e3e")
            self.status_label.config(text="⚠️ SAFETY TRIGGER: MOUSE HIT CORNER", fg="#ecc94b")
            # Wait for user to move mouse away from corner
            mx, my = pyautogui.position()
            sw, sh = pyautogui.size()
            if mx > 10 and my > 10 and mx < sw-10 and my < sh-10:
                fail_safe_paused = False
                self.log("✅ Fail-safe cleared.")
            self.root.after(500, self.update_loop)
            return

        with data_lock:
            att = current_data["att"]
            med = current_data["med"]
            la, ha = current_data["la"], current_data["ha"]
            lb, hb = current_data["lb"], current_data["hb"]
            sig = current_data["sig"]

        alpha = la + ha
        beta_ratio = hb / (lb + 1)

        att_history.append(att)
        alpha_history.append(alpha)

        if len(alpha_history) >= 2 and alpha_history[-2] > 0:
            alpha_change_pct = alpha / alpha_history[-2]
        else:
            alpha_change_pct = 1.0

        self.att_bar["value"] = att
        self.med_bar["value"] = med
        self.beta_label.config(text=f"Beta Ratio: {beta_ratio:.2f}")

        self.status_label.config(
            text="🟢 Connected" if ws_connected else "🔴 Disconnected",
            fg="#27ae60" if ws_connected else "#e74c3c"
        )

        # --- EMA SMOOTHING ---
        avg_att = (EMA_ALPHA * att) + ((1 - EMA_ALPHA) * avg_att)
        avg_med = (EMA_ALPHA * med) + ((1 - EMA_ALPHA) * avg_med)

        self.att_bar["value"] = avg_att
        self.med_bar["value"] = avg_med
        self.beta_label.config(text=f"Raw Att: {att} | Avg Att: {int(avg_att)}")

        # ===== CONTROL LOGIC (ULTRA-SENSITIVE DYNAMIC PIVOT) =====
        if self.active and ws_connected and sig <= 50:
            
            # --- GET SLIDER VALUES ---
            l_sens = self.s_left.get()
            r_sens = self.s_right.get()

            # Movement Threshold (Deadzone = 5)
            diff = avg_att - baseline_att
            
            # PUSH LEFT (Focus higher)
            l_drive = max(0, min(100, (diff - 5) * l_sens)) 
            
            # PULL RIGHT (Focus lower)
            # We use r_sens to make the "Relaxation" trigger much easier
            r_drive = max(0, min(100, ((-diff) - 5) * r_sens))
            
            self.l_energy['value'] = l_drive
            self.r_energy['value'] = r_drive

            now = time.time()
            if now - last_move_time > MOVE_COOLDOWN:
                try:
                    # LEFT
                    if l_drive > 5:
                        speed = MOVEMENT_SPEED_BASE + (l_drive / 8)
                        pyautogui.move(int(-speed), 0)
                        last_move_time = now
                        self.state_label.config(text="PUSH LEFT", fg="#3498db")
                    
                    # RIGHT
                    elif r_drive > 5:
                        speed = MOVEMENT_SPEED_BASE + (r_drive / 8)
                        pyautogui.move(int(speed), 0)
                        last_move_time = now
                        self.state_label.config(text="PULL RIGHT", fg="#e74c3c")
                    
                    else:
                        self.state_label.config(text=f"NEUTRAL (Center: {int(baseline_att)})", fg="#bdc3c7")
                        
                except pyautogui.FailSafeException:
                    fail_safe_paused = True
                    self.log("⚠️ SAFETY LOCK ENGAGED")
                    self.active = False
                    self.toggle_btn.config(text="ACTIVATE SYSTEM", bg="#38a169")

        self.root.after(int(POLLING_INTERVAL * 1000), self.update_loop)


# ================= WEBSOCKET =================
def on_message(ws, message):
    try:
        data = json.loads(message)
        with data_lock:
            current_data.update(data)
    except:
        pass

def on_open(ws):
    global ws_connected
    ws_connected = True

def on_close(ws, *_):
    global ws_connected
    ws_connected = False

def run_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_message=on_message,
                on_open=on_open,
                on_close=on_close
            )
            ws.run_forever()
        except:
            pass
        time.sleep(2)

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_ws, daemon=True).start()
    root = tk.Tk()
    EffortControlApp(root)
    root.mainloop()
