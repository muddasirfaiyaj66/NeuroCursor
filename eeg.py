"""
EEG Real-time Plotter with WebSocket - OPTIMIZED VERSION
Receives brainwave data from ESP32-S3 and displays live graphs
"""

import websocket
import json
import csv
import time
import threading
from datetime import datetime
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
import numpy as np

# Configuration
ESP32_IP = "10.131.191.211"  # ⚠️ CHANGE THIS TO YOUR ESP32 IP
WS_PORT = 81
WS_URL = f"ws://{ESP32_IP}:{WS_PORT}"

# Band configuration
BANDS = [
    {"key": "delta", "label": "Delta", "color": "#8e44ad"},
    {"key": "theta", "label": "Theta", "color": "#3498db"},
    {"key": "la", "label": "L-Alpha", "color": "#1abc9c"},
    {"key": "ha", "label": "H-Alpha", "color": "#2ecc71"},
    {"key": "lb", "label": "L-Beta", "color": "#f39c12"},
    {"key": "hb", "label": "H-Beta", "color": "#e74c3c"},
    {"key": "lg", "label": "L-Gamma", "color": "#c0392b"},
    {"key": "mg", "label": "M-Gamma", "color": "#e67e22"}
]

# Data storage - REDUCED MAX POINTS for performance
MAX_POINTS = 100  # Reduced from 200
band_data = {b["key"]: deque(maxlen=MAX_POINTS) for b in BANDS}
attention_data = deque(maxlen=MAX_POINTS)
meditation_data = deque(maxlen=MAX_POINTS)
signal_quality = deque(maxlen=MAX_POINTS)

# Statistics
packet_count = 0
start_time = time.time()
connection_status = "Disconnected"
last_update = time.time()

# CSV file setup
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"eeg_data_{timestamp}.csv"
csvfile = open(csv_filename, "w", newline="", buffering=8192)  # Buffer writes
csv_writer = csv.writer(csvfile)
csv_writer.writerow([
    "timestamp", "signal_quality", "attention", "meditation", "raw",
    "delta", "theta", "low_alpha", "high_alpha", 
    "low_beta", "high_beta", "low_gamma", "mid_gamma"
])

print(f"📝 CSV file created: {csv_filename}")

# Create simplified figure
fig = plt.figure(figsize=(14, 8))
fig.suptitle('🧠 EEG Real-time Monitor', fontsize=14, fontweight='bold')
gs = GridSpec(3, 4, figure=fig, hspace=0.35, wspace=0.3)

# Top row: Attention, Meditation, Signal Quality
ax_attention = fig.add_subplot(gs[0, 0])
ax_meditation = fig.add_subplot(gs[0, 1])
ax_signal = fig.add_subplot(gs[0, 2])

# Brainwave bands
axes = {}
for i, band in enumerate(BANDS):
    row = 1 + i // 4
    col = i % 4
    axes[band["key"]] = fig.add_subplot(gs[row, col])

# Initialize lines with reduced features for performance
lines = {}
for band in BANDS:
    ax = axes[band["key"]]
    line, = ax.plot([], [], color=band["color"], linewidth=1.5, antialiased=True)
    ax.set_title(band["label"], fontsize=9)
    ax.set_xlim(0, MAX_POINTS)
    ax.set_ylim(0, 100000)  # Fixed scale initially
    ax.grid(True, alpha=0.2, linewidth=0.5)
    ax.tick_params(labelsize=7)
    lines[band["key"]] = line

# Attention line
line_attention, = ax_attention.plot([], [], color='#e74c3c', linewidth=1.5)
ax_attention.set_title('Attention', fontsize=9)
ax_attention.set_ylim(0, 100)
ax_attention.set_xlim(0, MAX_POINTS)
ax_attention.grid(True, alpha=0.2, linewidth=0.5)
ax_attention.tick_params(labelsize=7)

# Meditation line
line_meditation, = ax_meditation.plot([], [], color='#3498db', linewidth=1.5)
ax_meditation.set_title('Meditation', fontsize=9)
ax_meditation.set_ylim(0, 100)
ax_meditation.set_xlim(0, MAX_POINTS)
ax_meditation.grid(True, alpha=0.2, linewidth=0.5)
ax_meditation.tick_params(labelsize=7)

# Signal Quality line
line_signal, = ax_signal.plot([], [], color='#2ecc71', linewidth=1.5)
ax_signal.set_title('Signal Quality', fontsize=9)
ax_signal.set_ylim(0, 200)
ax_signal.set_xlim(0, MAX_POINTS)
ax_signal.grid(True, alpha=0.2, linewidth=0.5)
ax_signal.tick_params(labelsize=7)

# Status text
status_text = fig.text(0.7, 0.97, '', fontsize=8, verticalalignment='top')

def update_status_text():
    """Update status information"""
    global packet_count, start_time, connection_status
    
    elapsed = time.time() - start_time
    rate = packet_count / elapsed if elapsed > 0 else 0
    
    status = f"{connection_status} | Pkts: {packet_count} | {rate:.1f}/s | {elapsed:.0f}s"
    status_text.set_text(status)

def on_open(ws):
    """WebSocket connection opened"""
    global connection_status
    connection_status = "Connected ✓"
    print(f"✅ Connected to {WS_URL}")

def on_close(ws, close_status_code, close_msg):
    """WebSocket connection closed"""
    global connection_status
    connection_status = "Disconnected ✗"
    print(f"❌ Disconnected")

def on_error(ws, error):
    """WebSocket error occurred"""
    print(f"⚠️ Error: {error}")

def on_message(ws, message):
    """Process incoming WebSocket message"""
    global packet_count, last_update
    
    try:
        data = json.loads(message)
        current_time = time.time()
        packet_count += 1
        
        # Extract values
        sig = data.get("sig", 200)
        att = data.get("att", 0)
        med = data.get("med", 0)
        raw = data.get("raw", 0)
        
        # Update data
        attention_data.append(att)
        meditation_data.append(med)
        signal_quality.append(sig)
        
        # Update band data
        band_values = []
        for band in BANDS:
            value = data.get(band["key"], 0)
            band_data[band["key"]].append(value)
            band_values.append(value)
        
        # Write to CSV every 5 packets to reduce I/O
        if packet_count % 5 == 0:
            csv_writer.writerow([
                current_time, sig, att, med, raw,
                band_values[0], band_values[1], band_values[2], band_values[3],
                band_values[4], band_values[5], band_values[6], band_values[7]
            ])
        
        last_update = current_time
        
    except Exception as e:
        if packet_count % 100 == 0:  # Only print errors occasionally
            print(f"⚠️ Error: {e}")

# Pre-allocate x-axis data
x_data = np.arange(MAX_POINTS)

def animate(frame):
    """Animation function - OPTIMIZED"""
    
    # Only update if we have recent data (within last 2 seconds)
    if time.time() - last_update > 2:
        return []
    
    updated_lines = []
    
    # Update attention
    if len(attention_data) > 0:
        x = np.arange(len(attention_data))
        line_attention.set_data(x, list(attention_data))
        updated_lines.append(line_attention)
    
    # Update meditation
    if len(meditation_data) > 0:
        x = np.arange(len(meditation_data))
        line_meditation.set_data(x, list(meditation_data))
        updated_lines.append(line_meditation)
    
    # Update signal quality
    if len(signal_quality) > 0:
        x = np.arange(len(signal_quality))
        line_signal.set_data(x, list(signal_quality))
        updated_lines.append(line_signal)
    
    # Update band data - only rescale every 50 frames
    for band in BANDS:
        key = band["key"]
        if len(band_data[key]) > 0:
            x = np.arange(len(band_data[key]))
            lines[key].set_data(x, list(band_data[key]))
            updated_lines.append(lines[key])
            
            # Auto-scale only occasionally
            if frame % 50 == 0 and len(band_data[key]) > 10:
                max_val = max(band_data[key])
                if max_val > 0:
                    axes[key].set_ylim(0, max_val * 1.2)
    
    # Update status text only every 10 frames
    if frame % 10 == 0:
        update_status_text()
    
    return updated_lines

def run_websocket():
    """Run WebSocket client in separate thread"""
    while True:
        try:
            print(f"🔌 Connecting to {WS_URL}...")
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever()
        except Exception as e:
            print(f"⚠️ Exception: {e}")
        
        print("🔄 Reconnecting in 3s...")
        time.sleep(3)

# Start WebSocket in background thread
ws_thread = threading.Thread(target=run_websocket, daemon=True)
ws_thread.start()

print("\n" + "="*60)
print("🧠 EEG Real-time Plotter - OPTIMIZED")
print("="*60)
print(f"📡 Connecting to: {WS_URL}")
print(f"📝 Logging to: {csv_filename}")
print("\n💡 Close the plot window to stop\n")

# Start animation with optimized interval
try:
    ani = animation.FuncAnimation(
        fig, animate, 
        interval=100,  # Update every 100ms (10 FPS) instead of 50ms
        blit=True,     # Use blitting for faster rendering
        cache_frame_data=False
    )
    plt.tight_layout()
    plt.show()
except KeyboardInterrupt:
    print("\n⏹ Stopped by user")
finally:
    csvfile.close()
    print(f"\n✅ Data saved to: {csv_filename}")
    print(f"📊 Total packets: {packet_count}")