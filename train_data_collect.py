"""
EEG Training Data Collector & Calibration Tool
Shows directional arrows and records labeled EEG data for model training
Also provides baseline calibration for threshold-based control

Signal Mapping:
- Attention high  → Cursor UP
- Meditation high → Cursor DOWN  
- Alpha high      → Cursor LEFT
- Beta high       → Cursor RIGHT
"""

import websocket
import json
import csv
import time
import threading
import random
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import glob
import os

# Configuration
ESP32_IP = "NeuroCursor-esp.local"  # ⚠️ CHANGE THIS
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

# Training configuration - Updated for signal-specific collection
DIRECTIONS = ["LEFT", "RIGHT", "UP", "DOWN", "IDLE"]
SIGNAL_MAPPING = {
    "UP": "Attention",
    "DOWN": "Meditation", 
    "LEFT": "Alpha",
    "RIGHT": "Beta",
    "IDLE": "Baseline"
}
SAMPLES_PER_DIRECTION = 60
DISPLAY_TIME = 5  # seconds to show each arrow
REST_TIME = 0     # Removed rest between trials per user request

# Current EEG data (latest)
current_data = {
    "sig": 200, "att": 0, "med": 0, "raw": 0,
    "delta": 0, "theta": 0, "la": 0, "ha": 0,
    "lb": 0, "hb": 0, "lg": 0, "mg": 0
}
baseline_data = {
    "att": 50, "med": 50, "raw": 0,
    "delta": 0, "theta": 0, "la": 0, "ha": 0,
    "lb": 0, "hb": 0, "lg": 0, "mg": 0
}
data_lock = threading.Lock()
ws_connected = False

# Training session data
training_data = []
current_trial = 0
total_trials = 100 * len(DIRECTIONS)
is_training = False
is_paused = False
current_direction = None

# CSV file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"eeg_training_{timestamp}.csv"

class TrainingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 EEG Training Data Collector")
        self.root.geometry("900x920")
        self.current_filename = csv_filename
        self.root.configure(bg="#f0f0f0")
        self.root.resizable(True, True)
        
        # Main container
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(expand=True, fill="both", padx=20, pady=15)
        
        # Title
        title = tk.Label(main_frame, text="🧠 EEG Signal Training", 
                        font=("Arial", 24, "bold"), bg="#f0f0f0", fg="#2c3e50")
        title.pack(pady=5)
        
        # Subtitle with signal mapping
        subtitle = tk.Label(main_frame, 
                          text="Attention→UP | Meditation→DOWN | Alpha→LEFT | Beta→RIGHT",
                          font=("Arial", 10), bg="#f0f0f0", fg="#7f8c8d")
        subtitle.pack(pady=2)
        
        # Connection status
        self.status_label = tk.Label(main_frame, text="⚫ Disconnected", 
                                     font=("Arial", 14), bg="#f0f0f0", fg="#e74c3c")
        self.status_label.pack(pady=5)
        
        # Signal quality indicator
        self.signal_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        self.signal_frame.pack(pady=8, fill="x")
        
        quality_label = tk.Label(self.signal_frame, text="Signal Quality:", 
                                font=("Arial", 12), bg="white")
        quality_label.grid(row=0, column=0, padx=10, pady=5)
        
        self.signal_bar = ttk.Progressbar(self.signal_frame, length=300, mode='determinate')
        self.signal_bar.grid(row=0, column=1, padx=20, pady=10)
        
        self.signal_text = tk.Label(self.signal_frame, text="--", 
                                   font=("Segoe UI", 12, "bold"), bg="white")
        self.signal_text.grid(row=0, column=2, padx=10, pady=5)
        
        # Current values display with signal mapping
        values_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        values_frame.pack(pady=8, fill="x")
        
        tk.Label(values_frame, text="Current Signal Values:", font=("Arial", 12, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=4, pady=5)
        
        # Signal labels with direction hints
        self.att_label = tk.Label(values_frame, text="↑ Attention: --", 
                                 font=("Arial", 11), bg="white", fg="#2ecc71")
        self.att_label.grid(row=1, column=0, padx=15, pady=5)
        
        self.med_label = tk.Label(values_frame, text="↓ Meditation: --", 
                                 font=("Arial", 11), bg="white", fg="#f39c12")
        self.med_label.grid(row=1, column=1, padx=15, pady=5)
        
        self.alpha_label = tk.Label(values_frame, text="← Alpha: --", 
                                   font=("Arial", 11), bg="white", fg="#3498db")
        self.alpha_label.grid(row=1, column=2, padx=15, pady=5)
        
        self.beta_label = tk.Label(values_frame, text="→ Beta: --", 
                                  font=("Arial", 11), bg="white", fg="#e74c3c")
        self.beta_label.grid(row=1, column=3, padx=15, pady=5)
        
        # Arrow display (main training area)
        self.arrow_frame = tk.Frame(main_frame, bg="#2c3e50", relief="solid", bd=3, height=150)
        self.arrow_frame.pack(pady=8, fill="x")
        self.arrow_frame.pack_propagate(False)
        
        self.arrow_label = tk.Label(self.arrow_frame, text="Ready", 
                                   font=("Arial", 50, "bold"), 
                                   bg="#2c3e50", fg="white")
        self.arrow_label.pack(expand=True)
        
        # Signal instruction label
        self.signal_instruction = tk.Label(main_frame, text="", 
                                          font=("Arial", 14, "italic"), 
                                          bg="#f0f0f0", fg="#2c3e50")
        self.signal_instruction.pack(pady=5)
        
        # Progress
        progress_frame = tk.Frame(main_frame, bg="#f0f0f0")
        progress_frame.pack(pady=5, fill="x")
        
        self.progress_label = tk.Label(progress_frame, 
                                       text=f"Progress: 0/{total_trials}", 
                                       font=("Arial", 11), bg="#f0f0f0")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, length=600, mode='determinate')
        self.progress_bar.pack(pady=2)
        
        # Training Settings
        settings_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        settings_frame.pack(pady=5, fill="x")
        
        tk.Label(settings_frame, text="Session Settings:", font=("Segoe UI", 11, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=4, pady=5)
        
        tk.Label(settings_frame, text="Samples per Dir:", font=("Segoe UI", 10), bg="white").grid(row=1, column=0, padx=10, pady=5)
        self.samples_var = tk.IntVar(value=100)
        tk.Scale(settings_frame, from_=10, to=200, orient="horizontal", variable=self.samples_var, bg="white", length=150).grid(row=1, column=1, padx=10, pady=5)
        
        self.calibrate_btn = tk.Button(settings_frame, text="⚖️ CALIBRATE", 
                                     font=("Segoe UI", 9, "bold"), bg="#34495e", fg="white",
                                     command=self.calibrate_baseline)
        self.calibrate_btn.grid(row=0, column=3, padx=5, pady=5)

        tk.Label(settings_frame, text="Focus Time (s):", font=("Segoe UI", 10), bg="white").grid(row=1, column=2, padx=10, pady=5)
        self.time_var = tk.IntVar(value=5)
        tk.Scale(settings_frame, from_=2, to=10, orient="horizontal", variable=self.time_var, bg="white", length=150).grid(row=1, column=3, padx=10, pady=5)

        instructions = tk.Label(main_frame, 
                              text="Focus on the arrow and produce the corresponding mental state for each direction.",
                              font=("Segoe UI", 9), bg="#f0f0f0", fg="#7f8c8d", wraplength=700)
        instructions.pack(pady=2)
        
        # Control buttons
        button_container = tk.Frame(main_frame, bg="#f0f0f0")
        button_container.pack(pady=10)

        # Primary controls
        self.start_button = tk.Button(button_container, text="▶ START", 
                                      font=("Segoe UI", 12, "bold"), bg="#27ae60", 
                                      fg="white", width=12, height=2,
                                      command=self.start_training)
        self.start_button.pack(side="left", padx=5)
        
        self.pause_button = tk.Button(button_container, text="⏸ PAUSE", 
                                     font=("Segoe UI", 12, "bold"), bg="#f39c12", 
                                     fg="white", width=12, height=2,
                                     command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=5)

        self.stop_button = tk.Button(button_container, text="⏹ STOP", 
                                    font=("Segoe UI", 12, "bold"), bg="#e74c3c", 
                                    fg="white", width=12, height=2,
                                    command=self.stop_training, state="disabled")
        self.stop_button.pack(side="left", padx=5)

        # Collection Dashboard (Manual + Step-by-Step)
        collect_frame = tk.LabelFrame(main_frame, text="🧠 Signal-Specific Collection", font=("Segoe UI", 10, "bold"), 
                                     bg="white", relief="solid", bd=2, fg="#2c3e50")
        collect_frame.pack(pady=5, fill="x")

        # Row 1: Manual recording buttons with signal hints
        manual_row = tk.Frame(collect_frame, bg="white")
        manual_row.pack(pady=5, fill="x")
        tk.Label(manual_row, text="Manual Capture:", font=("Segoe UI", 9, "bold"), bg="white").pack(side="left", padx=10)
        
        btn_config = [
            ("← Alpha", "LEFT", "#3498db"), 
            ("→ Beta", "RIGHT", "#e74c3c"), 
            ("↑ Attn", "UP", "#2ecc71"), 
            ("↓ Med", "DOWN", "#f39c12"),
            ("○ Idle", "IDLE", "#95a5a6")
        ]
        
        for text, direct, color in btn_config:
            btn = tk.Button(manual_row, text=text, font=("Segoe UI", 9, "bold"), 
                           bg=color, fg="white", width=8, 
                           command=lambda d=direct: self.collect_sample(d))
            btn.pack(side="left", padx=2)

        # Row 2: Step-by-Step + Merge
        step_row = tk.Frame(collect_frame, bg="white")
        step_row.pack(pady=5, fill="x")
        
        tk.Label(step_row, text="Step Control:", font=("Segoe UI", 9, "bold"), bg="white").pack(side="left", padx=10)
        self.step_dir_var = tk.StringVar(value="LEFT")
        self.step_dir_menu = ttk.Combobox(step_row, textvariable=self.step_dir_var, 
                                        values=DIRECTIONS, state="readonly", width=8)
        self.step_dir_menu.pack(side="left", padx=5)
        
        self.step_start_btn = tk.Button(step_row, text="Record Step", font=("Segoe UI", 9, "bold"), 
                                       bg="#3498db", fg="white", command=self.start_step_training)
        self.step_start_btn.pack(side="left", padx=5)
        
        self.merge_btn = tk.Button(step_row, text="Merge All CSVs", font=("Segoe UI", 9, "bold"), 
                                 bg="#9b59b6", fg="white", command=self.merge_data)
        self.merge_btn.pack(side="left", padx=5)
        
        # Start WebSocket and update loop
        self.update_ui()
        
    def update_ui(self):
        """Update UI with current data"""
        global ws_connected, current_data
        
        with data_lock:
            # Connection status
            if ws_connected:
                self.status_label.config(text="🟢 Connected", fg="#27ae60")
            else:
                self.status_label.config(text="🔴 Disconnected", fg="#e74c3c")
            
            # Signal quality (0=good, 200=bad, invert for display)
            sig = current_data["sig"]
            quality_percent = max(0, 100 - (sig / 2))
            self.signal_bar['value'] = quality_percent
            
            if sig == 0:
                self.signal_text.config(text="Excellent", fg="#27ae60")
            elif sig < 50:
                self.signal_text.config(text="Good", fg="#f39c12")
            elif sig < 100:
                self.signal_text.config(text="Fair", fg="#e67e22")
            else:
                self.signal_text.config(text="Poor", fg="#e74c3c")
            
            # Current values with color indicating strength
            att = current_data['att']
            med = current_data['med']
            alpha_sum = current_data['la'] + current_data['ha']
            beta_sum = current_data['lb'] + current_data['hb']
            
            self.att_label.config(text=f"↑ Attention: {att}")
            self.med_label.config(text=f"↓ Meditation: {med}")
            self.alpha_label.config(text=f"← Alpha: {alpha_sum}")
            self.beta_label.config(text=f"→ Beta: {beta_sum}")
        
        # Schedule next update
        self.root.after(100, self.update_ui)
    
    def start_training(self):
        """Start full training session"""
        global is_training, current_trial, training_data, total_trials, DISPLAY_TIME
        
        if not ws_connected:
            messagebox.showerror("Error", "Please wait for WebSocket connection!")
            return
        
        # Update settings from UI
        DISPLAY_TIME = self.time_var.get()
        samples_per_dir = self.samples_var.get()
        
        if current_data["sig"] > 100:
            response = messagebox.askwarning("Warning", 
                "Signal quality is poor. Continue anyway?")
            if not response:
                return
        
        # Create sequence - each direction in order
        sequence = []
        for direction in DIRECTIONS:
            sequence.extend([direction] * samples_per_dir)
            
        total_trials = len(sequence)
        self.current_filename = csv_filename
        
        is_training = True
        current_trial = 0
        training_data = []
        
        self.start_button.config(state="disabled")
        self.step_start_btn.config(state="disabled")
        self.merge_btn.config(state="disabled")
        self.pause_button.config(state="normal")
        self.stop_button.config(state="normal")
        
        # Start training sequence
        threading.Thread(target=self.training_loop, args=(sequence,), daemon=True).start()

    def start_step_training(self):
        """Start single step training session for specific signal"""
        global is_training, current_trial, training_data, total_trials, DISPLAY_TIME
        
        if not ws_connected:
            messagebox.showerror("Error", "Please wait for WebSocket connection!")
            return
            
        direction = self.step_dir_var.get()
        samples_per_dir = self.samples_var.get()
        DISPLAY_TIME = self.time_var.get()
        
        # Create sequence: Only selected direction
        sequence = [direction] * samples_per_dir
        total_trials = len(sequence)
        
        # Set specific filename for this step
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        signal_name = SIGNAL_MAPPING.get(direction, direction)
        self.current_filename = f"step_data_{direction}_{signal_name}_{timestamp}.csv"
        
        is_training = True
        current_trial = 0
        training_data = []
        
        self.start_button.config(state="disabled")
        self.step_start_btn.config(state="disabled")
        self.merge_btn.config(state="disabled")
        self.pause_button.config(state="normal")
        self.stop_button.config(state="normal")
        
        # Start training sequence
        threading.Thread(target=self.training_loop, args=(sequence,), daemon=True).start()
    
    def stop_training(self):
        """Stop training session"""
        global is_training, is_paused
        is_training = False
        is_paused = False
        
        self.start_button.config(state="normal")
        self.step_start_btn.config(state="normal")
        self.merge_btn.config(state="normal")
        self.pause_button.config(state="disabled", text="⏸ PAUSE", bg="#f39c12")
        self.stop_button.config(state="disabled")
        self.arrow_label.config(text="Session Ended", fg="#95a5a6", font=("Segoe UI", 40, "bold"))
        self.signal_instruction.config(text="")
        
        if len(training_data) > 0:
            self.save_data()

    def toggle_pause(self):
        """Toggle pause state"""
        global is_paused
        is_paused = not is_paused
        
        if is_paused:
            self.pause_button.config(text="▶ RESUME", bg="#2980b9")
            self.arrow_label.config(text="PAUSED", fg="#f1c40f")
        else:
            self.pause_button.config(text="⏸ PAUSE", bg="#f39c12")
    
    def calibrate_baseline(self):
        """Record baseline for 10 seconds"""
        if not ws_connected:
            messagebox.showerror("Error", "Connect to sensor first!")
            return
            
        self.calibrate_btn.config(text="⏳ Calibrating...", state="disabled")
        threading.Thread(target=self._run_calibration, daemon=True).start()

    def _run_calibration(self):
        """Background calibration loop"""
        global baseline_data
        temp_data = []
        start_time = time.time()
        
        while time.time() - start_time < 10:
            if current_data["sig"] < 50: # Only good data
                with data_lock:
                    temp_data.append(current_data.copy())
            time.sleep(0.1)
        
        if len(temp_data) > 0:
            # Calculate averages
            keys = ["att", "med", "delta", "theta", "la", "ha", "lb", "hb", "lg", "mg"]
            for k in keys:
                values = [d[k] for d in temp_data]
                baseline_data[k] = sum(values) / len(values)
            
            self.root.after(0, lambda: messagebox.showinfo("Calibration", 
                f"Baseline set!\n\n"
                f"Attention: {baseline_data['att']:.0f}\n"
                f"Meditation: {baseline_data['med']:.0f}\n"
                f"Alpha: {baseline_data['la'] + baseline_data['ha']:.0f}\n"
                f"Beta: {baseline_data['lb'] + baseline_data['hb']:.0f}"))
        else:
            self.root.after(0, lambda: messagebox.showwarning("Calibration", "Failed - check signal quality"))
            
        self.root.after(0, lambda: self.calibrate_btn.config(text="⚖️ CALIBRATE", state="normal"))
    
    def training_loop(self, sequence):
        """Main training loop with auto-pause between blocks"""
        global current_trial, current_direction, training_data, is_paused
        
        last_direction = None
        
        for i, direction in enumerate(sequence):
            # Check for stop
            if not is_training:
                break
            
            # Auto-pause on direction change
            if last_direction is not None and direction != last_direction:
                is_paused = True
                self.root.after(0, lambda: self.pause_button.config(text="▶ RESUME", bg="#2980b9"))
                signal_hint = SIGNAL_MAPPING.get(direction, "")
                self.root.after(0, lambda d=direction, s=signal_hint: (
                    self.arrow_label.config(text=f"Next: {d}", fg="#f39c12", font=("Arial", 40, "bold")),
                    self.signal_instruction.config(text=f"Get ready to focus on: {s}")
                ))
                
            last_direction = direction

            # Check for pause
            while is_paused and is_training:
                time.sleep(0.5)
            
            if not is_training:
                break

            current_trial = i + 1
            current_direction = direction

            # Update UI for direction
            self.root.after(0, self.update_training_ui, direction)

            # Wait and collect multiple samples per direction
            start_time = time.time()
            collection_interval = 0.2  # 200ms
            last_collection = 0
            
            while time.time() - start_time < DISPLAY_TIME:
                if not is_training: break
                
                while is_paused and is_training:
                    time.sleep(0.5)
                    start_time += 0.5
                
                # Continuous collection logic
                current_now = time.time()
                if current_now - last_collection >= collection_interval:
                    self.collect_sample(direction)
                    last_collection = current_now
                    
                time.sleep(0.05)
        
        # Training complete
        if is_training:
            self.root.after(0, self.training_complete)
    
    def update_training_ui(self, direction):
        """Update UI for current training direction"""
        arrow_symbols = {
            "LEFT": "←",
            "RIGHT": "→",
            "UP": "↑",
            "DOWN": "↓",
            "IDLE": "◯"
        }
        
        colors = {
            "LEFT": "#3498db",
            "RIGHT": "#e74c3c",
            "UP": "#2ecc71",
            "DOWN": "#f39c12",
            "IDLE": "#95a5a6"
        }
        
        signal_hints = {
            "LEFT": "Increase ALPHA: Close eyes, relax, think calm thoughts",
            "RIGHT": "Increase BETA: Stay alert, think actively, problem solve",
            "UP": "Increase ATTENTION: Focus hard, concentrate intensely",
            "DOWN": "Increase MEDITATION: Relax deeply, calm your mind",
            "IDLE": "Stay neutral, baseline state"
        }
        
        self.arrow_label.config(text=arrow_symbols[direction], fg=colors[direction])
        self.signal_instruction.config(text=signal_hints.get(direction, ""))
        self.progress_label.config(text=f"Progress: {current_trial}/{total_trials} - {direction} ({SIGNAL_MAPPING.get(direction, '')})")
        self.progress_bar['value'] = (current_trial / total_trials) * 100
    
    def collect_sample(self, direction):
        """Collect one training sample with signal-specific focus"""
        global training_data
        
        # Artifact Rejection
        if current_data["sig"] > 50:
            return

        with data_lock:
            # Calculate combined values
            alpha = current_data["la"] + current_data["ha"]
            beta = current_data["lb"] + current_data["hb"]
            
            # Focused data collection as per user instruction:
            # "ignore others" when collecting for a specific direction
            
            # Default everything to 0
            att = 0
            med = 0
            l_alpha = 0
            h_alpha = 0
            l_beta = 0
            h_beta = 0
            theta = 0
            delta = 0
            lg = 0
            mg = 0
            
            if direction == "UP":
                att = current_data["att"]
            elif direction == "DOWN":
                med = current_data["med"]
            elif direction == "LEFT":
                l_alpha = current_data["la"]
                h_alpha = current_data["ha"]
                alpha = l_alpha + h_alpha
            elif direction == "RIGHT":
                l_beta = current_data["lb"]
                h_beta = current_data["hb"]
                beta = l_beta + h_beta
            elif direction == "IDLE":
                # For idle, we might want to keep the true baseline or specific signals
                # Let's keep a small window of real noise
                att = current_data["att"]
                med = current_data["med"]
                l_alpha = current_data["la"]
                h_alpha = current_data["ha"]
                l_beta = current_data["lb"]
                h_beta = current_data["hb"]
            
            sample = {
                "timestamp": time.time(),
                "direction": direction,
                "signal_quality": current_data["sig"],
                "attention": att,
                "meditation": med,
                "raw": current_data["raw"],
                "delta": delta,
                "theta": theta,
                "low_alpha": l_alpha,
                "high_alpha": h_alpha,
                "low_beta": l_beta,
                "high_beta": h_beta,
                "low_gamma": lg,
                "mid_gamma": mg,
                # Normalized values (against baseline)
                "norm_att": att - baseline_data["att"] if direction in ["UP", "IDLE"] else 0,
                "norm_med": med - baseline_data["med"] if direction in ["DOWN", "IDLE"] else 0,
                "norm_alpha": (l_alpha + h_alpha) - (baseline_data["la"] + baseline_data["ha"]) if direction in ["LEFT", "IDLE"] else 0,
                "norm_beta": (l_beta + h_beta) - (baseline_data["lb"] + baseline_data["hb"]) if direction in ["RIGHT", "IDLE"] else 0
            }
            training_data.append(sample)
    
    def training_complete(self):
        """Handle training completion"""
        global is_training
        
        is_training = False
        self.arrow_label.config(text="✓ Complete", fg="#27ae60", font=("Segoe UI", 40, "bold"))
        self.signal_instruction.config(text="Training session finished!")
        self.start_button.config(state="normal")
        self.step_start_btn.config(state="normal")
        self.merge_btn.config(state="normal")
        self.pause_button.config(state="disabled", text="⏸ PAUSE", bg="#f39c12")
        self.stop_button.config(state="disabled")
        
        self.save_data()
        messagebox.showinfo("Complete", 
                          f"Training complete! {len(training_data)} samples collected.\n"
                          f"Data saved to: {self.current_filename}")
    
    def save_data(self):
        """Save training data to CSV"""
        if len(training_data) == 0:
            return
        
        with open(self.current_filename, 'w', newline='') as f:
            fieldnames = training_data[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(training_data)
        
        print(f"✅ Saved {len(training_data)} samples to {self.current_filename}")

    def merge_data(self):
        """Merge all step data files into one"""
        step_files = glob.glob("step_data_*.csv")
        if not step_files:
            messagebox.showinfo("Merge", "No step data files found to merge.")
            return

        response = messagebox.askyesno("Merge Files", f"Found {len(step_files)} files. Merge them into a single training file?")
        if not response:
            return
            
        merged_data = []
        try:
            for file in step_files:
                with open(file, 'r') as f:
                    reader = csv.DictReader(f)
                    merged_data.extend(list(reader))
            
            # Save to main file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            merged_filename = f"merged_training_{timestamp}.csv"
            
            if merged_data:
                with open(merged_filename, 'w', newline='') as f:
                    fieldnames = merged_data[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(merged_data)
                
                messagebox.showinfo("Success", f"Merged {len(merged_data)} samples into {merged_filename}")
                
                if messagebox.askyesno("Cleanup", "Delete individual step files?"):
                    for file in step_files:
                        os.remove(file)
            else:
                messagebox.showwarning("Error", "No data found in files.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to merge: {str(e)}")

# WebSocket handlers
def on_open(ws):
    global ws_connected
    ws_connected = True
    print("✅ Connected to ESP32")

def on_close(ws, close_status_code, close_msg):
    global ws_connected
    ws_connected = False
    print("❌ Disconnected from ESP32")

def on_error(ws, error):
    print(f"⚠️ WebSocket error: {error}")

def on_message(ws, message):
    global current_data
    
    try:
        data = json.loads(message)
        with data_lock:
            current_data.update(data)
    except:
        pass

def run_websocket():
    """Run WebSocket in background"""
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever()
        except:
            pass
        time.sleep(3)

# Start WebSocket thread
ws_thread = threading.Thread(target=run_websocket, daemon=True)
ws_thread.start()

# Create and run GUI
root = tk.Tk()
app = TrainingApp(root)

print("\n" + "="*60)
print("🧠 EEG Signal Training Data Collector")
print("="*60)
print(f"📡 Connecting to: {WS_URL}")
print(f"📝 Data will be saved to: {csv_filename}")
print("\n🎯 Signal-to-Direction Mapping:")
print("   Attention high  → Cursor UP")
print("   Meditation high → Cursor DOWN")
print("   Alpha high      → Cursor LEFT")
print("   Beta high       → Cursor RIGHT")
print("\n💡 Instructions:")
print("1. Wait for 'Connected' status")
print("2. Ensure signal quality is good (green)")
print("3. Use Step Control to collect one direction at a time")
print("4. Focus on producing the correct mental state for each direction")
print("="*60 + "\n")

root.mainloop()