"""
EEG Real-time Cursor Control Demo
Controls mouse cursor using trained model or threshold-based method
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

# Try to import sklearn for model-based control
try:
    from sklearn.ensemble import RandomForestClassifier
    import pickle
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    print("⚠️ scikit-learn not installed. Using threshold-based control only.")

# Configuration
ESP32_IP = "NeuroCursor-esp.local"  # ⚠️ CHANGE THIS
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

# Control settings
CONTROL_MODES = ["Threshold", "ML Model"]
MOVEMENT_SPEED = 15  # pixels per command
SMOOTHING_WINDOW = 5  # average last N predictions

# Current EEG data
current_data = {
    "sig": 200, "att": 0, "med": 0, "raw": 0,
    "delta": 0, "theta": 0, "la": 0, "ha": 0,
    "lb": 0, "hb": 0, "lg": 0, "mg": 0
}
data_lock = threading.Lock()
ws_connected = False

# Control state
control_active = False
control_mode = "Threshold"
loaded_model = None
prediction_buffer = deque(maxlen=SMOOTHING_WINDOW)

# Safety limits
pyautogui.FAILSAFE = True  # Move mouse to corner to abort

class CursorControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 EEG Cursor Control")
        self.root.geometry("700x650")
        self.root.configure(bg="#f0f0f0")
        
        # Main container
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Title
        title = tk.Label(main_frame, text="🧠 EEG Cursor Control", 
                        font=("Segoe UI", 24, "bold"), bg="#f0f0f0", fg="#2c3e50")
        title.pack(pady=10)
        
        # Connection status
        self.status_label = tk.Label(main_frame, text="⚫ Disconnected", 
                                     font=("Segoe UI", 12), bg="#f0f0f0", fg="#e74c3c")
        self.status_label.pack(pady=5)
        
        # Signal quality
        signal_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        signal_frame.pack(pady=10, fill="x")
        
        tk.Label(signal_frame, text="Signal Quality:", font=("Arial", 11), 
                bg="white").grid(row=0, column=0, padx=10, pady=5)
        
        self.signal_bar = ttk.Progressbar(signal_frame, length=250, mode='determinate')
        self.signal_bar.grid(row=0, column=1, padx=10, pady=5)
        
        self.signal_text = tk.Label(signal_frame, text="--", 
                                   font=("Arial", 11, "bold"), bg="white")
        self.signal_text.grid(row=0, column=2, padx=10, pady=5)
        
        # Current values
        values_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        values_frame.pack(pady=10, fill="x")
        
        tk.Label(values_frame, text="Brain Activity:", font=("Arial", 11, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=2, pady=5)
        
        self.att_label = tk.Label(values_frame, text="Attention: --", 
                                 font=("Arial", 10), bg="white")
        self.att_label.grid(row=1, column=0, padx=20, pady=3, sticky="w")
        
        self.med_label = tk.Label(values_frame, text="Meditation: --", 
                                 font=("Arial", 10), bg="white")
        self.med_label.grid(row=1, column=1, padx=20, pady=3, sticky="w")
        
        self.alpha_label = tk.Label(values_frame, text="Alpha Ratio: --", 
                                   font=("Arial", 10), bg="white")
        self.alpha_label.grid(row=2, column=0, padx=20, pady=3, sticky="w")
        
        self.beta_label = tk.Label(values_frame, text="Beta Ratio: --", 
                                  font=("Arial", 10), bg="white")
        self.beta_label.grid(row=2, column=1, padx=20, pady=3, sticky="w")
        
        # Control mode selection
        mode_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        mode_frame.pack(pady=10, fill="x")
        
        tk.Label(mode_frame, text="Control Mode:", font=("Arial", 11, "bold"), 
                bg="white").grid(row=0, column=0, padx=10, pady=10)
        
        self.mode_var = tk.StringVar(value="Threshold")
        for i, mode in enumerate(CONTROL_MODES):
            rb = tk.Radiobutton(mode_frame, text=mode, variable=self.mode_var, 
                               value=mode, font=("Arial", 10), bg="white",
                               command=self.change_mode)
            rb.grid(row=0, column=i+1, padx=10, pady=10)
        
        if MODEL_AVAILABLE:
            self.load_model_btn = tk.Button(mode_frame, text="📂 Load Model", 
                                           font=("Arial", 10), command=self.load_model)
            self.load_model_btn.grid(row=0, column=3, padx=10, pady=10)
        
        # Settings
        settings_frame = tk.Frame(main_frame, bg="white", relief="solid", bd=2)
        settings_frame.pack(pady=10, fill="x")
        
        tk.Label(settings_frame, text="Settings:", font=("Arial", 11, "bold"), 
                bg="white").grid(row=0, column=0, columnspan=2, pady=5)
        
        tk.Label(settings_frame, text="Movement Speed:", font=("Arial", 10), 
                bg="white").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        
        self.speed_var = tk.IntVar(value=MOVEMENT_SPEED)
        speed_slider = tk.Scale(settings_frame, from_=5, to=50, orient="horizontal",
                               variable=self.speed_var, bg="white", length=200)
        speed_slider.grid(row=1, column=1, padx=10, pady=5)
        

        
        # Prediction display
        self.prediction_frame = tk.Frame(main_frame, bg="#2c3e50", 
                                        relief="solid", bd=3, height=120)
        self.prediction_frame.pack(pady=15, fill="x")
        self.prediction_frame.pack_propagate(False)
        
        self.prediction_label = tk.Label(self.prediction_frame, text="Waiting...", 
                                        font=("Arial", 40, "bold"), 
                                        bg="#2c3e50", fg="white")
        self.prediction_label.pack(expand=True)
        
        # Control buttons
        button_frame = tk.Frame(main_frame, bg="#f0f0f0")
        button_frame.pack(pady=15)
        
        self.start_button = tk.Button(button_frame, text="▶ Start Control", 
                                      font=("Arial", 13, "bold"), bg="#27ae60", 
                                      fg="white", padx=25, pady=12,
                                      command=self.start_control)
        self.start_button.pack(side="left", padx=10)
        
        self.stop_button = tk.Button(button_frame, text="⏸ Stop Control", 
                                    font=("Arial", 13, "bold"), bg="#e74c3c", 
                                    fg="white", padx=25, pady=12,
                                    command=self.stop_control, state="disabled")
        self.stop_button.pack(side="left", padx=10)
        
        # Instructions
        instructions = tk.Label(main_frame, 
                              text="💡 Focus your attention to activate control. Think about direction to move cursor.",
                              font=("Arial", 9), bg="#f0f0f0", fg="#7f8c8d", 
                              wraplength=600)
        instructions.pack(pady=5)
        
        # Start update loop
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
            
            # Signal quality
            sig = current_data["sig"]
            quality_percent = max(0, 100 - (sig / 2))
            self.signal_bar['value'] = quality_percent
            
            if sig == 0:
                self.signal_text.config(text="Excellent", fg="#27ae60")
            elif sig < 50:
                self.signal_text.config(text="Good", fg="#f39c12")
            else:
                self.signal_text.config(text="Poor", fg="#e74c3c")
            
            # Values
            self.att_label.config(text=f"Attention: {current_data['att']}/100")
            self.med_label.config(text=f"Meditation: {current_data['med']}/100")
            
            # Calculate ratios
            alpha_sum = current_data['la'] + current_data['ha']
            beta_sum = current_data['lb'] + current_data['hb']
            theta = current_data['theta']
            
            alpha_ratio = alpha_sum / (theta + 1)
            beta_ratio = beta_sum / (alpha_sum + 1)
            
            self.alpha_label.config(text=f"Alpha Ratio: {alpha_ratio:.2f}")
            self.beta_label.config(text=f"Beta Ratio: {beta_ratio:.2f}")
        
        self.root.after(100, self.update_ui)
    
    def change_mode(self):
        """Change control mode"""
        global control_mode
        control_mode = self.mode_var.get()
        
        if control_mode == "ML Model" and loaded_model is None:
            messagebox.showwarning("Warning", "No model loaded! Using threshold mode.")
            self.mode_var.set("Threshold")
            control_mode = "Threshold"
    
    def load_model(self):
        """Load trained model and its configuration"""
        global loaded_model
        
        filename = filedialog.askopenfilename(
            title="Load Trained Model",
            filetypes=[("Pickle files", "*.pkl"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'rb') as f:
                    loaded_model = pickle.load(f)
                
                # Check if it's the new model format (a dict) or old (just a model)
                if isinstance(loaded_model, dict):
                    print(f"✅ Loaded enhanced model from {loaded_model.get('training_date')}")
                    print(f"Accuracy: {loaded_model.get('test_accuracy', 0)*100:.2f}%")
                
                messagebox.showinfo("Success", f"Model package loaded from {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load model: {e}")
    
    def start_control(self):
        """Start cursor control"""
        global control_active
        
        if not ws_connected:
            messagebox.showerror("Error", "Please wait for WebSocket connection!")
            return
        
        if control_mode == "ML Model" and loaded_model is None:
            messagebox.showerror("Error", "Please load a trained model first!")
            return
        
        control_active = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        
        # Start control loop
        threading.Thread(target=self.control_loop, daemon=True).start()
    
    def stop_control(self):
        """Stop cursor control"""
        global control_active
        control_active = False
        
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.prediction_label.config(text="Stopped", fg="yellow")
    
    def control_loop(self):
        """Main control loop"""
        while control_active:
            try:
                if control_mode == "Threshold":
                    direction = self.threshold_predict()
                else:
                    direction = self.model_predict()
                
                # Smooth predictions
                prediction_buffer.append(direction)
                if len(prediction_buffer) >= 3:
                    # Use most common prediction in buffer
                    from collections import Counter
                    most_common = Counter(prediction_buffer).most_common(1)[0][0]
                    direction = most_common
                
                # Update display
                self.root.after(0, self.update_prediction_display, direction)
                
                # Handle actions
                if direction == "CLICK":
                    self.perform_click()
                    # After clicking, clear buffer to prevent rapid double-clicks
                    prediction_buffer.clear()
                    time.sleep(0.5) # Wait after click
                elif direction != "IDLE":
                    self.move_cursor(direction)
                
                time.sleep(0.15)  # Slightly faster control rate
                
            except Exception as e:
                print(f"Control error: {e}")
                time.sleep(0.5)
    
    def threshold_predict(self):
        """Threshold-based prediction"""
        with data_lock:
            la = current_data['la']
            ha = current_data['ha']
            lb = current_data['lb']
            hb = current_data['hb']
        
        # Determine direction based on band dominance
        if lb > hb + 5000:  # Left beta dominant
            return "LEFT"
        elif hb > lb + 5000:  # High beta dominant
            return "RIGHT"
        elif la > ha + 3000:  # Low alpha dominant
            return "UP"
        elif ha > la + 3000:  # High alpha dominant
            return "DOWN"
        else:
            return "IDLE"
    
    def model_predict(self):
        """Aligned with revised trainer: uses focused TGAM features and causal smoothing."""
        if loaded_model is None:
            return "IDLE"
        
        # Extract components from model package
        if isinstance(loaded_model, dict):
            model = loaded_model['model']
            scaler = loaded_model['scaler']
            expected_features = loaded_model.get('feature_names', [])
        else:
            return "IDLE"
        
        with data_lock:
            # 1. Aligned Base Features
            base_data = {
                'attention': current_data['att'],
                'meditation': current_data['med'],
                'theta': current_data['theta'],
                'low_alpha': current_data['la'],
                'high_alpha': current_data['ha'],
                'low_beta': current_data['lb'],
                'high_beta': current_data['hb']
            }
            
            # 2. Aligned Ratio Engineering
            alpha_sum = base_data['low_alpha'] + base_data['high_alpha']
            beta_sum = base_data['low_beta'] + base_data['high_beta']
            theta = base_data['theta']
            
            derived_features = {
                'alpha_theta_ratio': alpha_sum / (theta + 1),
                'beta_alpha_ratio': beta_sum / (alpha_sum + 1),
                'beta_theta_ratio': beta_sum / (theta + 1),
                'engagement_ratio': base_data['attention'] / (base_data['meditation'] + 1)
            }
            
            input_dict = {**base_data, **derived_features}
            
            try:
                feature_values = [input_dict[name] for name in expected_features]
                features = np.array(feature_values).reshape(1, -1)
            except KeyError as e:
                print(f"❌ Feature mismatch: {e}")
                return "IDLE"
        
        try:
            features_scaled = scaler.transform(features)
            
            # Weighted probability prediction for stability
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(features_scaled)[0]
                max_prob = np.max(probs)
                prediction = model.classes_[np.argmax(probs)]
                
                # Dynamic threshold for noise rejection
                # If we're not very sure, default to IDLE
                if max_prob < 0.55:
                    return "IDLE"
            else:
                prediction = model.predict(features_scaled)[0]
                    
            return prediction
        except Exception as e:
            print(f"Prediction error: {e}")
            return "IDLE"

    def perform_click(self):
        """Perform a mouse click via brain command"""
        try:
            pyautogui.click()
            # Visual feedback on label
            original_color = self.prediction_label.cget("fg")
            self.prediction_label.config(fg="#ffffff")
            self.root.after(100, lambda: self.prediction_label.config(fg=original_color))
        except:
            pass
    
    def update_prediction_display(self, direction):
        """Update prediction display"""
        symbols = {
            "LEFT": "← LEFT",
            "RIGHT": "→ RIGHT",
            "UP": "↑ UP",
            "DOWN": "↓ DOWN",
            "CLICK": "🔘 CLICK!",
            "IDLE": "◯ IDLE"
        }
        
        colors = {
            "LEFT": "#3498db",
            "RIGHT": "#e74c3c",
            "UP": "#2ecc71",
            "DOWN": "#f39c12",
            "CLICK": "#8e44ad",
            "IDLE": "#95a5a6"
        }
        
        self.prediction_label.config(text=symbols.get(direction, "?"), 
                                    fg=colors.get(direction, "white"))
    
    def move_cursor(self, direction):
        """Move cursor in direction"""
        speed = self.speed_var.get()
        
        try:
            if direction == "LEFT":
                pyautogui.move(-speed, 0)
            elif direction == "RIGHT":
                pyautogui.move(speed, 0)
            elif direction == "UP":
                pyautogui.move(0, -speed)
            elif direction == "DOWN":
                pyautogui.move(0, speed)
        except pyautogui.FailSafeException:
            self.stop_control()
            messagebox.showwarning("Safety Stop", 
                "Cursor moved to corner - control stopped for safety!")

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
app = CursorControlApp(root)

print("\n" + "="*60)
print("🧠 EEG Cursor Control Started")
print("="*60)
print(f"📡 Connecting to: {WS_URL}")
print("\n💡 Instructions:")
print("1. Wait for 'Connected' status")
print("2. Choose control mode (Threshold or ML Model)")
print("3. Adjust settings as needed")
print("4. Click 'Start Control'")
print("5. Focus your attention to move cursor")
print("\n⚠️ SAFETY: Move mouse to screen corner to emergency stop!")
print("="*60 + "\n")

root.mainloop()