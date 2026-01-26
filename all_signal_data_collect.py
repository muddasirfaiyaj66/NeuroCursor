"""
EEG Training Data Collector
Shows directional arrows and records labeled EEG data for model training
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

# Configuration
ESP32_IP = "NeuroCursor-esp.local"  # ⚠️ CHANGE THIS
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

# Training configuration
DIRECTIONS = ["LEFT", "RIGHT", "UP", "DOWN", "CLICK", "IDLE"]
SAMPLES_PER_DIRECTION = 60 # Increased samples for better distinct values
DISPLAY_TIME = 5  # Increased seconds to show each arrow (more precise collection)
REST_TIME = 2     # Increased seconds rest between trials

# Current EEG data (latest)
current_data = {
    "sig": 200, "att": 0, "med": 0, "raw": 0,
    "delta": 0, "theta": 0, "la": 0, "ha": 0,
    "lb": 0, "hb": 0, "lg": 0, "mg": 0
}
data_lock = threading.Lock()
ws_connected = False

# Training session data
training_data = []
current_trial = 0
total_trials = 100 * len(DIRECTIONS) # Default for UI initialization
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
        self.root.geometry("850x850") # Increased height to ensure all buttons are visible
        self.root.configure(bg="#f0f0f0")
        self.root.resizable(True, True) # Allow resizing if needed
        
        # Main container
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Title
        title = tk.Label(main_frame, text="🧠 EEG Cursor Training", 
                        font=("Arial", 24, "bold"), bg="#f0f0f0", fg="#2c3e50")
        title.pack(pady=10)
        
        # Connection status
        self.status_label = tk.Label(main_frame, text="⚫ Disconnected", 
                                     font=("Arial", 14), bg="#f0f0f0", fg="#e74c3c")
        self.status_label.pack(pady=5)
        
        # Signal quality indicator
        self.signal_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        self.signal_frame.pack(pady=10, fill="x")
        
        quality_label = tk.Label(self.signal_frame, text="Signal Quality:", 
                                font=("Arial", 12), bg="white")
        quality_label.grid(row=0, column=0, padx=10, pady=5)
        
        self.signal_bar = ttk.Progressbar(self.signal_frame, length=300, mode='determinate')
        self.signal_bar.grid(row=0, column=1, padx=20, pady=10)
        
        self.signal_text = tk.Label(self.signal_frame, text="--", 
                                   font=("Segoe UI", 12, "bold"), bg="white")
        self.signal_text.grid(row=0, column=2, padx=10, pady=5)
        
        # Current values display
        values_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        values_frame.pack(pady=10, fill="x")
        
        tk.Label(values_frame, text="Current Values:", font=("Arial", 12, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=4, pady=5)
        
        self.att_label = tk.Label(values_frame, text="Attention: --", 
                                 font=("Arial", 11), bg="white")
        self.att_label.grid(row=1, column=0, padx=15, pady=5)
        
        self.med_label = tk.Label(values_frame, text="Meditation: --", 
                                 font=("Arial", 11), bg="white")
        self.med_label.grid(row=1, column=1, padx=15, pady=5)
        
        self.alpha_label = tk.Label(values_frame, text="Alpha: --", 
                                   font=("Arial", 11), bg="white")
        self.alpha_label.grid(row=1, column=2, padx=15, pady=5)
        
        self.beta_label = tk.Label(values_frame, text="Beta: --", 
                                  font=("Arial", 11), bg="white")
        self.beta_label.grid(row=1, column=3, padx=15, pady=5)
        
        # Arrow display (main training area) - Reduced height slightly to save space
        self.arrow_frame = tk.Frame(main_frame, bg="#2c3e50", relief="solid", bd=3, height=200)
        self.arrow_frame.pack(pady=10, fill="both", expand=True)
        self.arrow_frame.pack_propagate(False)
        
        self.arrow_label = tk.Label(self.arrow_frame, text="Ready", 
                                   font=("Arial", 80, "bold"), 
                                   bg="#2c3e50", fg="white")
        self.arrow_label.pack(expand=True)
        
        # Progress
        progress_frame = tk.Frame(main_frame, bg="#f0f0f0")
        progress_frame.pack(pady=10, fill="x")
        
        self.progress_label = tk.Label(progress_frame, 
                                       text=f"Progress: 0/{total_trials}", 
                                       font=("Arial", 12), bg="#f0f0f0")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, length=600, mode='determinate')
        self.progress_bar.pack(pady=5)
        
        # Training Settings
        settings_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        settings_frame.pack(pady=10, fill="x")
        
        tk.Label(settings_frame, text="Session Settings:", font=("Segoe UI", 11, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=4, pady=5)
        
        tk.Label(settings_frame, text="Samples per Dir:", font=("Segoe UI", 10), bg="white").grid(row=1, column=0, padx=10, pady=5)
        self.samples_var = tk.IntVar(value=100) # Increased default
        tk.Scale(settings_frame, from_=10, to=200, orient="horizontal", variable=self.samples_var, bg="white", length=150).grid(row=1, column=1, padx=10, pady=5)
        
        tk.Label(settings_frame, text="Focus Time (s):", font=("Segoe UI", 10), bg="white").grid(row=1, column=2, padx=10, pady=5)
        self.time_var = tk.IntVar(value=5)
        tk.Scale(settings_frame, from_=2, to=10, orient="horizontal", variable=self.time_var, bg="white", length=150).grid(row=1, column=3, padx=10, pady=5)

        # Instructions
        instructions = tk.Label(main_frame, 
                              text="Instructions: Focus on the arrow and imagine the movement. Use PAUSE if you need a break.",
                              font=("Segoe UI", 9), bg="#f0f0f0", fg="#7f8c8d", wraplength=600)
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

        # Action buttons
        action_frame = tk.Frame(main_frame, bg="#f0f0f0")
        action_frame.pack(pady=5)

        self.click_button = tk.Button(action_frame, text="🖱️ MANUAL CLICK", 
                                    font=("Segoe UI", 11, "bold"), bg="#8e44ad", 
                                    fg="white", width=20, height=1,
                                    command=self.manual_click)
        self.click_button.pack(pady=5)
        
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
            
            # Current values
            self.att_label.config(text=f"Attention: {current_data['att']}")
            self.med_label.config(text=f"Meditation: {current_data['med']}")
            
            alpha_sum = current_data['la'] + current_data['ha']
            beta_sum = current_data['lb'] + current_data['hb']
            self.alpha_label.config(text=f"Alpha: {alpha_sum}")
            self.beta_label.config(text=f"Beta: {beta_sum}")
        
        # Schedule next update
        self.root.after(100, self.update_ui)
    
    def start_training(self):
        """Start training session"""
        global is_training, current_trial, training_data, total_trials, DISPLAY_TIME
        
        if not ws_connected:
            messagebox.showerror("Error", "Please wait for WebSocket connection!")
            return
        
        # Update settings from UI
        DISPLAY_TIME = self.time_var.get()
        samples_per_dir = self.samples_var.get()
        total_trials = samples_per_dir * len(DIRECTIONS)
        
        if current_data["sig"] > 100:
            response = messagebox.askwarning("Warning", 
                "Signal quality is poor. Continue anyway?")
            if not response:
                return
        
        is_training = True
        current_trial = 0
        training_data = []
        
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal")
        self.stop_button.config(state="normal")
        
        # Start training sequence
        threading.Thread(target=self.training_loop, args=(samples_per_dir,), daemon=True).start()
    
    def stop_training(self):
        """Stop training session"""
        global is_training, is_paused
        is_training = False
        is_paused = False
        
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled", text="⏸ PAUSE", bg="#f39c12")
        self.stop_button.config(state="disabled")
        self.arrow_label.config(text="Session Ended", fg="#95a5a6", font=("Segoe UI", 40, "bold"))
        
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

    def manual_click(self):
        """Manually record a 'CLICK' sample"""
        if not ws_connected:
            messagebox.showwarning("Connection", "Not connected to sensor!")
            return
        
        self.collect_sample("CLICK")
        # Visual feedback for manual click
        original_bg = self.click_button.cget("bg")
        self.click_button.config(bg="#d35400")
        self.root.after(200, lambda: self.click_button.config(bg=original_bg))
    
    def training_loop(self, samples_per_dir):
        """Main training loop"""
        global current_trial, current_direction, training_data
        
        # Create randomized sequence
        sequence = []
        for direction in DIRECTIONS:
            sequence.extend([direction] * samples_per_dir)
        random.shuffle(sequence)
        
        for i, direction in enumerate(sequence):
            # Check for stop
            if not is_training:
                break
            
            # Check for pause
            while is_paused and is_training:
                time.sleep(0.5)
            
            if not is_training:
                break

            current_trial = i + 1
            current_direction = direction
            
            # Update UI
            self.root.after(0, self.update_training_ui, direction)
            
            # Wait and collect (check pause during wait)
            start_time = time.time()
            while time.time() - start_time < DISPLAY_TIME:
                if not is_training: break
                while is_paused and is_training:
                    time.sleep(0.5)
                    start_time += 0.5 # Offset start time to compensate for pause
                time.sleep(0.1)

            # Collect data sample
            if is_training:
                self.collect_sample(direction)
            
            # Rest period
            self.root.after(0, lambda: self.arrow_label.config(text="Rest", fg="#7f8c8d"))
            
            rest_start = time.time()
            while time.time() - rest_start < REST_TIME:
                if not is_training: break
                while is_paused and is_training:
                    time.sleep(0.5)
                    rest_start += 0.5
                time.sleep(0.1)
        
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
            "CLICK": "🔘",
            "IDLE": "◯"
        }
        
        colors = {
            "LEFT": "#3498db",
            "RIGHT": "#e74c3c",
            "UP": "#2ecc71",
            "DOWN": "#f39c12",
            "CLICK": "#8e44ad",
            "IDLE": "#95a5a6"
        }
        
        self.arrow_label.config(text=arrow_symbols[direction], 
                               fg=colors[direction])
        self.progress_label.config(text=f"Progress: {current_trial}/{total_trials} - Focusing: {direction}")
        self.progress_bar['value'] = (current_trial / total_trials) * 100
    
    def collect_sample(self, direction):
        """Collect one training sample"""
        global training_data
        
        with data_lock:
            sample = {
                "timestamp": time.time(),
                "direction": direction,
                "signal_quality": current_data["sig"],
                "attention": current_data["att"],
                "meditation": current_data["med"],
                "raw": current_data["raw"],
                "delta": current_data["delta"],
                "theta": current_data["theta"],
                "low_alpha": current_data["la"],
                "high_alpha": current_data["ha"],
                "low_beta": current_data["lb"],
                "high_beta": current_data["hb"],
                "low_gamma": current_data["lg"],
                "mid_gamma": current_data["mg"],
            }
            training_data.append(sample)
    
    def training_complete(self):
        """Handle training completion"""
        global is_training
        
        is_training = False
        is_paused = False
        self.arrow_label.config(text="✓ Session Complete", fg="#27ae60", font=("Segoe UI", 40, "bold"))
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled", text="⏸ PAUSE", bg="#f39c12")
        self.stop_button.config(state="disabled")
        
        self.save_data()
        messagebox.showinfo("Complete", 
                          f"Training complete! {len(training_data)} samples collected.\n"
                          f"Data saved to: {csv_filename}")
    
    def save_data(self):
        """Save training data to CSV"""
        if len(training_data) == 0:
            return
        
        with open(csv_filename, 'w', newline='') as f:
            fieldnames = training_data[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(training_data)
        
        print(f"✅ Saved {len(training_data)} samples to {csv_filename}")

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
print("🧠 EEG Training Data Collector Started")
print("="*60)
print(f"📡 Connecting to: {WS_URL}")
print(f"📝 Data will be saved to: {csv_filename}")
print(f"🎯 Total trials: {total_trials}")
print("\n💡 Instructions:")
print("1. Wait for 'Connected' status")
print("2. Ensure signal quality is good (green)")
print("3. Click 'Start Training'")
print("4. Focus on each arrow and imagine moving cursor that way")
print("="*60 + "\n")

root.mainloop()