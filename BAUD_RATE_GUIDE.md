# TGAM Baud Rate Troubleshooting

## Current Issue:
- ESP32 receives bytes from TGAM (190 bytes)
- But Valid Packets = 0 (wrong baud rate)

## Solution: Try Different Baud Rates

Edit line 30 in `esp32_tgam.ino`:

### Try in this order:

1. **9600** (most common)
   ```cpp
   Serial2.begin(9600, SERIAL_8N1, TGAM_RX, TGAM_TX);
   ```

2. **57600** (alternative common)
   ```cpp
   Serial2.begin(57600, SERIAL_8N1, TGAM_RX, TGAM_TX);
   ```

3. **1200** (older modules)
   ```cpp
   Serial2.begin(1200, SERIAL_8N1, TGAM_RX, TGAM_TX);
   ```

4. **115200** (high speed)
   ```cpp
   Serial2.begin(115200, SERIAL_8N1, TGAM_RX, TGAM_TX);
   ```

## How to Test:
1. Change the baud rate in the code
2. Upload to ESP32
3. Open Serial Monitor
4. Wait for status report
5. Check if "Valid Packets" > 0

## Success Indicators:
```
✓ Valid Packets: 3
✓ Python receives data
✓ Signal Quality shows 0-200
```

## Current Code Status:
- Set to 9600 baud (most likely to work)
- Upload this version first!
