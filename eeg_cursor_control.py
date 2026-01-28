"""
EEG Real-time Cursor Control - Debug Version
Controls mouse cursor using Signal-Focused ML Model
"""

import websocket
import json
import time
import threading
from collections import deque
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyautogui
import numpy as np
import pickle

# Configuration
ESP32_IP = "NeuroCursor-esp.local"
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

# Control settings
MOVEMENT_SPEED = 15
SMOOTHING_WINDOW = 3 # Slightly faster response

# Current EEG data
current_data = {
    "sig": 200, "att": 0, "med": 0, "raw": 0,
    "delta": 0, "theta": 0, "la": 0, "ha": 0,
    "lb": 0, "hb": 0, "lg": 0, "mg": 0
}
# Baseline data for normalization (updated via calibrate)
baseline_data = {"att": 30, "med": 30, "la": 5000, "ha": 5000, "lb": 3000, "hb": 3000}
data_lock = threading.Lock()
ws_connected = False

# Control state
control_active = False
loaded_model = None
prediction_buffer = deque(maxlen=SMOOTHING_WINDOW)

# Feature smoothing
FEATURE_SMOOTH_WINDOW = 3
feature_buffers = {
    'att': deque(maxlen=FEATURE_SMOOTH_WINDOW),
    'med': deque(maxlen=FEATURE_SMOOTH_WINDOW),
    'la': deque(maxlen=FEATURE_SMOOTH_WINDOW),
    'ha': deque(maxlen=FEATURE_SMOOTH_WINDOW),
    'lb': deque(maxlen=FEATURE_SMOOTH_WINDOW),
    'hb': deque(maxlen=FEATURE_SMOOTH_WINDOW),
}

def update_feature_buffers():
    with data_lock:
        feature_buffers['att'].append(current_data['att'])
        feature_buffers['med'].append(current_data['med'])
        feature_buffers['la'].append(current_data['la'])
        feature_buffers['ha'].append(current_data['ha'])
        feature_buffers['lb'].append(current_data['lb'])
        feature_buffers['hb'].append(current_data['hb'])

def get_smoothed_data():
    smoothed = {}
    for key, buffer in feature_buffers.items():
        smoothed[key] = sum(buffer) / len(buffer) if buffer else 0
    return smoothed

pyautogui.FAILSAFE = True

class CursorControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 NeuroCursor ML (Debug Mode)")
        self.root.geometry("750x850")
        self.root.configure(bg="#f0f0f0")
        
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(expand=True, fill="both", padx=20, pady=10)
        
        tk.Label(main_frame, text="🧠 NeuroCursor ML", font=("Segoe UI", 24, "bold"), bg="#f0f0f0").pack(pady=5)
        
        self.status_label = tk.Label(main_frame, text="⚫ Disconnected", font=("Segoe UI", 12), bg="#f0f0f0", fg="#e74c3c")
        self.status_label.pack(pady=2)
        
        # Signal Quality
        q_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=1)
        q_frame.pack(fill="x", pady=5)
        tk.Label(q_frame, text="Signal Quality:", bg="white").pack(side="left", padx=10, pady=5)
        self.q_bar = ttk.Progressbar(q_frame, length=300, mode='determinate')
        self.q_bar.pack(side="left", padx=10, pady=5)
        self.q_text = tk.Label(q_frame, text="--", bg="white", font=("Segoe UI", 10, "bold"))
        self.q_text.pack(side="left", padx=10)
        
        # Values
        v_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=1)
        v_frame.pack(fill="x", pady=5)
        self.val_label = tk.Label(v_frame, text="Att: -- | Med: -- | Alpha: -- | Beta: --", font=("Consolas", 11), bg="white")
        self.val_label.pack(pady=5)
        
        # Calibration & Model
        c_frame = tk.Frame(main_frame, bg="#f0f0f0")
        c_frame.pack(pady=5)
        self.cal_btn = tk.Button(c_frame, text="⚖️ Calibrate Baseline", command=self.calibrate, bg="#34495e", fg="white", width=18)
        self.cal_btn.grid(row=0, column=0, padx=5)
        tk.Button(c_frame, text="📂 Load Model", command=self.load_model, bg="#34495e", fg="white", width=18, font=("Arial", 9, "bold")).grid(row=0, column=1, padx=5)
        
        # Speed
        s_frame = tk.Frame(main_frame, bg="#f0f0f0")
        s_frame.pack(pady=5)
        tk.Label(s_frame, text="Movement Speed:", bg="#f0f0f0").pack(side="left")
        self.speed_var = tk.IntVar(value=20)
        tk.Scale(s_frame, from_=5, to=80, orient="horizontal", variable=self.speed_var, bg="#f0f0f0", length=200).pack(side="left", padx=10)
        
        # Prediction
        self.p_frame = tk.Frame(main_frame, bg="#2c3e50", height=130)
        self.p_frame.pack(fill="x", pady=10)
        self.p_frame.pack_propagate(False)
        self.p_label = tk.Label(self.p_frame, text="READY", font=("Arial", 45, "bold"), bg="#2c3e50", fg="white")
        self.p_label.pack(expand=True)
        
        # Probabilities Display (Debug)
        self.prob_label = tk.Label(main_frame, text="Probabilities: IDLE: -- | UP: -- | DOWN: -- | LEFT: -- | RIGHT: --", 
                                  font=("Consolas", 9), bg="#f0f0f0", fg="#34495e")
        self.prob_label.pack(pady=5)
        
        # Controls
        b_frame = tk.Frame(main_frame, bg="#f0f0f0")
        b_frame.pack(pady=10)
        self.start_btn = tk.Button(b_frame, text="▶ START CONTROL", font=("Arial", 14, "bold"), bg="#27ae60", fg="white", width=16, height=2, command=self.start_control)
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = tk.Button(b_frame, text="⏹ STOP", font=("Arial", 14, "bold"), bg="#e74c3c", fg="white", width=12, height=2, command=self.stop_control, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        
        # Bottom Console
        self.console = tk.Text(main_frame, height=4, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.console.pack(fill="x", pady=5)
        self.log("System initialized. Calibrate and Load Model to start.")
        
        self.update_ui()

    def log(self, msg):
        self.console.insert(tk.END, f"> {msg}\n")
        self.console.see(tk.END)
        print(f"DEBUG: {msg}")

    def load_model(self):
        global loaded_model
        path = filedialog.askopenfilename(filetypes=[("Model files", "*.pkl")])
        if path:
            try:
                with open(path, 'rb') as f: loaded_model = pickle.load(f)
                self.log(f"Model loaded: {path.split('/')[-1]}")
                messagebox.showinfo("Success", "Model loaded successfully!")
            except Exception as e: 
                self.log(f"Error loading model: {e}")
                messagebox.showerror("Error", f"Failed: {e}")

    def calibrate(self):
        if not ws_connected: return messagebox.showerror("Error", "Connect first!")
        self.cal_btn.config(text="⏳ Calibrating...", state="disabled")
        self.log("Calibration started... stay relaxed.")
        
        def run():
            tmp = {'att':[], 'med':[], 'la':[], 'ha':[], 'lb':[], 'hb':[]}
            start = time.time()
            while time.time() - start < 5:
                if current_data['sig'] < 100:
                    with data_lock:
                        for k in tmp: tmp[k].append(current_data.get(k, 0))
                time.sleep(0.1)
            
            if tmp['att']:
                with data_lock:
                    for k in tmp:
                        if tmp[k]: baseline_data[k] = sum(tmp[k]) / len(tmp[k])
                self.log(f"Calibration done! Baseline: Att={baseline_data['att']:.1f}, Med={baseline_data['med']:.1f}")
                self.root.after(0, lambda: messagebox.showinfo("Done", "Baseline Calibrated!"))
            else:
                self.log("Calibration failed: Poor signal.")
            
            self.root.after(0, lambda: self.cal_btn.config(text="⚖️ Calibrate Baseline", state="normal"))
            
        threading.Thread(target=run, daemon=True).start()

    def update_ui(self):
        with data_lock:
            status = "🟢 Connected" if ws_connected else "🔴 Disconnected"
            color = "#27ae60" if ws_connected else "#e74c3c"
            self.status_label.config(text=status, fg=color)
            
            sig = current_data['sig']
            self.q_bar['value'] = max(0, 100 - (sig / 2))
            self.q_text.config(text=f"{sig}", fg="#27ae60" if sig < 50 else "#e67e22" if sig < 100 else "#e74c3c")
            
            alpha = current_data['la'] + current_data['ha']
            beta = current_data['lb'] + current_data['hb']
            self.val_label.config(text=f"Att: {current_data['att']} | Med: {current_data['med']} | Alpha: {alpha} | Beta: {beta}")
            
        self.root.after(100, self.update_ui)

    def start_control(self):
        global control_active
        if not loaded_model: return messagebox.showerror("Error", "Please load a model first!")
        control_active = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log("Cursor control STARTED.")
        threading.Thread(target=self.control_loop, daemon=True).start()

    def stop_control(self):
        global control_active
        control_active = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.p_label.config(text="STOPPED", fg="#95a5a6")
        self.log("Cursor control STOPPED.")

    def control_loop(self):
        while control_active:
            if current_data['sig'] > 120:
                self.root.after(0, lambda: self.p_label.config(text="POOR SIGNAL", fg="#e74c3c"))
                time.sleep(0.5); continue
            
            direction = self.predict()
            prediction_buffer.append(direction)
            
            # Simple voting for smoothing
            if len(prediction_buffer) >= SMOOTHING_WINDOW:
                from collections import Counter
                final_dir = Counter(prediction_buffer).most_common(1)[0][0]
            else:
                final_dir = direction
            
            self.root.after(0, self.update_prediction_display, final_dir)
            if final_dir != "IDLE": 
                self.move_cursor(final_dir)
            
            time.sleep(0.15) # Faster polling

    def predict(self):
        if not loaded_model: return "IDLE"
        update_feature_buffers()
        s = get_smoothed_data()
        
        # 1. SOFT PURIFICATION (Match training set expectation of "ignore others")
        # During training, we zeroed out irrelevant signals. 
        # We find which one is the most dominant relative to baseline.
        
        att = s['att']
        med = s['med']
        la, ha = s['la'], s['ha']
        lb, hb = s['lb'], s['hb']
        alpha = la + ha
        beta = lb + hb
        
        n_att = att - baseline_data['att']
        n_med = med - baseline_data['med']
        n_alpha = alpha - (baseline_data['la'] + baseline_data['ha'])
        n_beta = beta - (baseline_data['lb'] + baseline_data['hb'])
        
        signals = {'UP': n_att, 'DOWN': n_med, 'LEFT': n_alpha, 'RIGHT': n_beta}
        best_candidate = max(signals, key=signals.get)
        
        # Safety: If nothing is really elevated, it's likely IDLE
        if signals[best_candidate] < 5: 
            best_candidate = "IDLE"

        # Apply purification: Zero out what the model thinks should be 0
        p_att = att if best_candidate == "UP" else 0
        p_med = med if best_candidate == "DOWN" else 0
        p_la = la if best_candidate == "LEFT" else 0
        p_ha = ha if best_candidate == "LEFT" else 0
        p_lb = lb if best_candidate == "RIGHT" else 0
        p_hb = hb if best_candidate == "RIGHT" else 0
        
        # If IDLE, keep some baseline signal
        if best_candidate == "IDLE":
            p_att, p_med, p_la, p_ha, p_lb, p_hb = att, med, la, ha, lb, hb

        input_data = {
            'attention': p_att, 'meditation': p_med,
            'low_alpha': p_la, 'high_alpha': p_ha,
            'low_beta': p_lb, 'high_beta': p_hb,
            'norm_att': p_att - baseline_data['att'] if best_candidate in ["UP", "IDLE"] else 0,
            'norm_med': p_med - baseline_data['med'] if best_candidate in ["DOWN", "IDLE"] else 0,
            'norm_alpha': (p_la + p_ha) - (baseline_data['la'] + baseline_data['ha']) if best_candidate in ["LEFT", "IDLE"] else 0,
            'norm_beta': (p_lb + p_hb) - (baseline_data['lb'] + baseline_data['hb']) if best_candidate in ["RIGHT", "IDLE"] else 0,
            'beta_alpha_ratio': (p_lb + p_hb) / (p_la + p_ha + 1),
            'engagement_ratio': p_att / (p_med + 1)
        }
        
        m = loaded_model['model']
        scaler = loaded_model['scaler']
        f_names = loaded_model['feature_names']
        
        try:
            vec = np.array([input_data.get(f, 0) for f in f_names]).reshape(1, -1)
            vec_s = scaler.transform(vec)
            probs = m.predict_proba(vec_s)[0]
            
            # Update Debug Probabilities UI
            prob_text = "Probabilities: " + " | ".join([f"{c}: {p*100:.0f}%" for c, p in zip(m.classes_, probs)])
            self.root.after(0, lambda t=prob_text: self.prob_label.config(text=t))
            
            # Lower confidence threshold for smoother movement
            if np.max(probs) < 0.35: 
                return "IDLE"
            
            return m.classes_[np.argmax(probs)]
        except Exception as e:
            # print(f"Prediction error: {e}")
            return "IDLE"

    def update_prediction_display(self, direction):
        colors = {"UP": "#2ecc71", "DOWN": "#f39c12", "LEFT": "#3498db", "RIGHT": "#e74c3c", "IDLE": "#95a5a6"}
        self.p_label.config(text=direction, fg=colors.get(direction, "white"))

    def move_cursor(self, direction):
        speed = self.speed_var.get()
        try:
            if direction == "LEFT": pyautogui.move(-speed, 0)
            elif direction == "RIGHT": pyautogui.move(speed, 0)
            elif direction == "UP": pyautogui.move(0, -speed)
            elif direction == "DOWN": pyautogui.move(0, speed)
            self.log(f"MOVED {direction}")
        except Exception as e:
            self.log(f"Move Error: {e}")
            self.stop_control()

def on_message(ws, msg):
    try:
        data = json.loads(msg)
        with data_lock: current_data.update(data)
    except: pass

def on_open(ws): global ws_connected; ws_connected = True
def on_close(ws, c1, c2): global ws_connected; ws_connected = False

def run_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_open=on_open, on_close=on_close)
            ws.run_forever()
        except: pass
        time.sleep(2)

threading.Thread(target=run_ws, daemon=True).start()
root = tk.Tk()
app = CursorControlApp(root)
root.mainloop()