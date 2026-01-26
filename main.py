import socket
import pyautogui
import time

# ============== Configuration ==============
ESP_IP = "http://10.131.191.211"  # Update this with your ESP32 IP from Serial Monitor
PORT = 3333
STEP = 20  # Pixels to move per action

# Thresholds for mouse control
ATTENTION_HIGH = 70    # Move UP when attention > this
ATTENTION_LOW = 30     # Move LEFT when attention < this
MEDITATION_HIGH = 70   # Move DOWN when meditation > this
MEDITATION_LOW = 30    # Move RIGHT when meditation < this
BLINK_THRESHOLD = 1500 # Click when |raw| > this

# Safety: prevent mouse from moving to corners (PyAutoGUI failsafe)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01  # Small delay between actions

def connect_to_esp32():
    """Connect to ESP32 TCP server"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)
    
    print("=" * 50)
    print("🧠 TGAM Brainwave Mouse Control")
    print("=" * 50)
    print(f"Connecting to ESP32 at {ESP_IP}:{PORT}...")
    
    try:
        sock.connect((ESP_IP, PORT))
        print("✅ Connected to ESP32!")
        print()
        print("Controls:")
        print(f"  • Attention > {ATTENTION_HIGH}  → Move UP")
        print(f"  • Meditation > {MEDITATION_HIGH} → Move DOWN")
        print(f"  • Attention < {ATTENTION_LOW}  → Move LEFT")
        print(f"  • Meditation < {MEDITATION_LOW} → Move RIGHT")
        print(f"  • Blink (raw > {BLINK_THRESHOLD}) → CLICK")
        print()
        print("Press Ctrl+C to stop")
        print("-" * 50)
        return sock
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("   Make sure:")
        print("   1. ESP32 is powered on and connected to WiFi")
        print("   2. ESP_IP matches the IP shown in ESP32 Serial Monitor")
        print("   3. Both devices are on the same network")
        return None

def process_brainwave_data(attention, meditation, raw):
    """Process brainwave data and control mouse"""
    moved = False
    action = ""
    
    # Vertical movement (UP/DOWN)
    if attention > ATTENTION_HIGH:
        pyautogui.move(0, -STEP)
        action = "⬆️ UP"
        moved = True
    elif meditation > MEDITATION_HIGH:
        pyautogui.move(0, STEP)
        action = "⬇️ DOWN"
        moved = True
    
    # Horizontal movement (LEFT/RIGHT)
    if attention < ATTENTION_LOW:
        pyautogui.move(-STEP, 0)
        action = "⬅️ LEFT" if not action else action + " + ⬅️ LEFT"
        moved = True
    elif meditation < MEDITATION_LOW:
        pyautogui.move(STEP, 0)
        action = "➡️ RIGHT" if not action else action + " + ➡️ RIGHT"
        moved = True
    
    # Click on blink/spike
    if abs(raw) > BLINK_THRESHOLD:
        pyautogui.click()
        action = "🖱️ CLICK" if not action else action + " + 🖱️ CLICK"
        moved = True
    
    return action if moved else None

def main():
    sock = connect_to_esp32()
    if not sock:
        return
    
    sock.settimeout(2.0)
    buffer = ""
    last_data_time = time.time()
    
    print("\n🔴 LIVE DATA STREAM:")
    print("=" * 60)
    
    try:
        while True:
            try:
                data = sock.recv(256).decode(errors="ignore")
                if not data:
                    print("❌ Connection lost!")
                    break
                
            except socket.timeout:
                # Show waiting message if no data for 5 seconds
                if time.time() - last_data_time > 5:
                    print(f"⏳ Waiting for TGAM data... (check ESP32 Serial Monitor)")
                    last_data_time = time.time()
                continue
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Receive error: {e}")
                break
            
            buffer += data
            
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                
                try:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        attention = int(parts[0])
                        meditation = int(parts[1])
                        raw = int(parts[2])
                        
                        # Process and move mouse
                        action = process_brainwave_data(attention, meditation, raw)
                        
                        # Update last data time
                        last_data_time = time.time()
                        
                        # Display ALL real-time data
                        timestamp = time.strftime("%H:%M:%S")
                        status = f"ATT: {attention:3d} | MED: {meditation:3d} | RAW: {raw:6d}"
                        
                        if action:
                            print(f"[{timestamp}] 📡 {status} → {action}")
                        else:
                            print(f"[{timestamp}] 📡 {status}")
                                
                except ValueError as e:
                    print(f"⚠️ Parse error: {line} - {e}")
                    continue
                    
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
    finally:
        sock.close()
        print("Connection closed.")

if __name__ == "__main__":
    main()

