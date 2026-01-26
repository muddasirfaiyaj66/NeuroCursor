# 🧠 EEG Brain-Computer Interface (BCI) Cursor Control

A professional, end-to-end EEG signal processing and machine learning pipeline for real-time mouse cursor control and brain-triggered clicking using an ESP32 and EEG sensors.

## 🚀 Overview

This project enables users to control their computer cursor using brainwaves. It employs a **Random Forest Classifier** trained on high-frequency EEG band ratios (Alpha, Beta, Theta, and Gamma) to detect directional intent and "click" actions.

### Key Features:
- **Real-time Signal Processing**: Advanced feature engineering including 8+ neuroscience-standard EEG ratios.
- **Signal Smoothing**: 3-point rolling average to eliminate environmental noise.
- **Dynamic Training UI**: Professional data collector with Pause/Resume, adjustable sample rates, and visual feedback.
- **Precise Control**: Optimized cursor movement loop with confidence-thresholding for stability.

---

## 🛠️ Project Structure

1.  **`train_data_collect.py`**: The UI for gathering labeled EEG data. Features adjustable focus times and randomized trials.
2.  **`eeg_model_trainer.py`**: The "Brain" of the project. Processes CSV data, filters signal noise, and exports a high-precision ML model package (`.pkl`).
3.  **`eeg_cursor_control.py`**: The live application that translates your brainwaves into real-world mouse movements and clicks.

---

## 📋 Prerequisites

- **Python 3.8+**
- **Hardware**: ESP32, EEG Sensor (e.g., ThinkGear based), and necessary electrodes.
- **Virtual Environment**: Recommended for dependency management.

### Installation:
```bash
# Create and activate venv
python -m venv venv
./venv/Scripts/activate

# Install dependencies
pip install websocket-client pandas numpy scikit-learn pyautogui matplotlib seaborn
```

---

## 🚦 How to Use

### 1. Data Collection
Run the collector to gather your personal brainwave signatures:
```powershell
python train_data_collect.py
```
*   **Tip**: Use the "Samples per Dir" slider to set at least 100 samples for better accuracy.
*   **Tip**: Ensure signal quality is "Excellent" (Green) before starting.

### 2. Model Training
Once you have collected data, train your personalized model:
```powershell
python eeg_model_trainer.py
```
*   Review the **Confusion Matrix** and **Feature Importance** charts to see how well the model distinguishes your thoughts.

### 3. Real-time Control
Launch the cursor control interface:
```powershell
python eeg_cursor_control.py
```
1. Click **Load Model** and select your latest `.pkl` file.
2. Set your preferred **Movement Speed**.
3. Click **▶ Start Control**.
4. **Emergency Stop**: Move your physical mouse to any corner of the screen to abort.

---

## 🧠 Brainwave Guide
| Direction | Mental Strategy (Suggested) |
| :--- | :--- |
| **UP / DOWN** | Focus on moving an object vertically in your mind. |
| **LEFT / RIGHT** | Focus on lateral movement or specific motor imagery. |
| **CLICK** | A sudden burst of attention or a quick jaw clench (as a physical trigger). |
| **IDLE** | Relaxed state, clear mind, no specific intent. |

---

## ⚠️ Safety & Troubleshooting
*   **FailSafe**: The app uses `pyautogui.FAILSAFE`. If the cursor goes out of control, slam your mouse into any corner of the monitor.
*   **Connection**: Ensure your ESP32 is on the same Wi-Fi as your PC and the IP address in the scripts matches your ESP32 IP.
*   **Accuracy**: For better results, increase training samples and use consistent electrode placement.

---
*Developed by **Muddasir Faiyaj** for Advanced IOT & Electronics Research.*
