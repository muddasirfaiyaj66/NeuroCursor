/*
 * ESP32-S3 Taurus TGM (TGAM Compatible) Brainwave Sensor Reader
 * With WiFi TCP Communication to Python for Mouse Control
 * 
 * Connections for ESP32-S3:
 * TGAM T (TX) -> ESP32-S3 GPIO18 (RX1)
 * TGAM - (GND) -> ESP32-S3 GND
 * TGAM + (VCC) -> ESP32-S3 3.3V
 * 
 * Taurus TGM Baud Rates:
 * - 9600 baud: Attention, Meditation, Brainwave bands
 * - 115200 baud: Raw EEG data
 * 
 * Using 9600 baud for processed data (recommended)
 */

#include <HardwareSerial.h>
#include <WiFi.h>

// ============== WiFi Configuration ==============
const char* WIFI_SSID = "Motorola edge";      // Change to your WiFi name
const char* WIFI_PASSWORD = "1234@@@###";  // Change to your WiFi password
const int TCP_PORT = 3333;

WiFiServer server(TCP_PORT);
WiFiClient client;

// Use Serial1 for TGAM communication on ESP32-S3
HardwareSerial TGAMSerial(1);

// ESP32-S3 Pin Configuration (Different from regular ESP32!)
// You can use any available GPIO pins on ESP32-S3
#define TGAM_RX_PIN 18  // ESP32-S3 RX <- TGAM TX (connect sensor TX here)
#define TGAM_TX_PIN 17  // ESP32-S3 TX (not used, TGAM is TX only)

// Taurus TGM Baud Rate - Use 9600 for processed data
#define TGAM_BAUD_RATE 9600  // Change to 115200 for raw EEG only

// Packet parsing constants
#define SYNC_BYTE 0xAA
#define EXCODE 0x55

// Data codes
#define CODE_POOR_SIGNAL 0x02
#define CODE_ATTENTION 0x04
#define CODE_MEDITATION 0x05
#define CODE_RAW_WAVE 0x80
#define CODE_ASIC_EEG_POWER 0x83

// Global variables to store parsed data
int poorSignalQuality = 200;
int attention = 0;
int meditation = 0;
int rawValue = 0;

// EEG Power bands
unsigned long delta = 0;
unsigned long theta = 0;
unsigned long lowAlpha = 0;
unsigned long highAlpha = 0;
unsigned long lowBeta = 0;
unsigned long highBeta = 0;
unsigned long lowGamma = 0;
unsigned long midGamma = 0;

// Packet buffer
#define PACKET_BUFFER_SIZE 256
byte packetBuffer[PACKET_BUFFER_SIZE];
int packetLength = 0;

// Timing variables
unsigned long lastStatusTime = 0;
unsigned long lastDataTime = 0;
const int STATUS_INTERVAL = 2000;  // Print status every 2 seconds

void setup() {
  // Initialize Serial Monitor
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }
  
  Serial.println("=================================");
  Serial.println("ESP32-S3 Taurus TGM Brainwave Sensor");
  Serial.println("=================================");
  
  // Initialize TGAM Serial on ESP32-S3
  TGAMSerial.begin(TGAM_BAUD_RATE, SERIAL_8N1, TGAM_RX_PIN, TGAM_TX_PIN);
  Serial.print("TGAM Serial initialized at ");
  Serial.print(TGAM_BAUD_RATE);
  Serial.println(" baud");
  Serial.print("TGAM RX Pin (connect sensor TX here): GPIO");
  Serial.println(TGAM_RX_PIN);
  Serial.println();
  Serial.println("=== WIRING for ESP32-S3 ===");
  Serial.println("TGAM TX  -> ESP32-S3 GPIO18");
  Serial.println("TGAM GND -> ESP32-S3 GND");
  Serial.println("TGAM VCC -> ESP32-S3 3.3V");
  Serial.println("===========================");
  
  // Connect to WiFi
  connectToWiFi();
  
  // Start TCP Server
  server.begin();
  Serial.print("TCP Server started on port ");
  Serial.println(TCP_PORT);
  Serial.println();
  Serial.println("Waiting for Python client connection...");
  Serial.println();
}

void connectToWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✓ WiFi Connected!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println();
    Serial.println(">>> Use this IP in your Python code <<<");
    Serial.println();
  } else {
    Serial.println();
    Serial.println("✗ WiFi Connection Failed!");
    Serial.println("Check SSID and Password, then restart ESP32");
  }
}

void loop() {
  // Check for new client connection
  if (!client || !client.connected()) {
    WiFiClient newClient = server.available();
    if (newClient) {
      client = newClient;
      Serial.println("✓ Python client connected!");
      Serial.print("Client IP: ");
      Serial.println(client.remoteIP());
    }
  }
  
  // Check TGAM serial buffer status periodically
  if (millis() - lastStatusTime >= STATUS_INTERVAL) {
    lastStatusTime = millis();
    
    int bytesAvailable = TGAMSerial.available();
    Serial.print("📊 Status: TGAM buffer=");
    Serial.print(bytesAvailable);
    Serial.print(" bytes | Client=");
    Serial.print(client && client.connected() ? "Connected" : "Not connected");
    Serial.print(" | Last data: ");
    if (lastDataTime > 0) {
      Serial.print((millis() - lastDataTime) / 1000);
      Serial.println("s ago");
    } else {
      Serial.println("Never");
    }
    
    if (bytesAvailable == 0) {
      Serial.println("   ⚠️ No TGAM data - Check wiring:");
      Serial.println("      TGAM TX  -> ESP32-S3 GPIO18");
      Serial.println("      TGAM GND -> ESP32-S3 GND");
      Serial.println("      TGAM VCC -> ESP32-S3 3.3V");
      Serial.println("   Also check:");
      Serial.println("      - Electrode contact on forehead");
      Serial.println("      - Sensor power LED is ON");
    }
  }
  
  // Read and parse TGAM packets
  if (readTGAMPacket()) {
    lastDataTime = millis();
    parseTGAMPayload();
    printDataCompact();
    sendDataToPython();
  }
  
  // Reconnect WiFi if disconnected
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected! Reconnecting...");
    connectToWiFi();
  }
}

// Send brainwave data to Python via TCP
void sendDataToPython() {
  if (client && client.connected()) {
    // Format: attention,meditation,rawValue
    String dataPacket = String(attention) + "," + 
                        String(meditation) + "," + 
                        String(rawValue) + "\n";
    
    client.print(dataPacket);
    
    Serial.print("[SENT->Python] ");
    Serial.print(dataPacket);
  } else {
    Serial.println("[NOT SENT] No Python client connected");
  }
}

// Read a complete TGAM packet
bool readTGAMPacket() {
  // Wait for SYNC bytes (0xAA 0xAA)
  while (TGAMSerial.available() >= 2) {
    // Look for first SYNC byte
    if (TGAMSerial.read() != SYNC_BYTE) {
      continue;
    }
    
    // Look for second SYNC byte
    if (TGAMSerial.read() != SYNC_BYTE) {
      continue;
    }
    
    // Wait for PLENGTH byte
    while (!TGAMSerial.available()) {
      delay(1);
    }
    
    packetLength = TGAMSerial.read();
    
    // PLENGTH should be less than 170 (0xAA)
    if (packetLength >= SYNC_BYTE) {
      continue;
    }
    
    // Read payload
    int bytesRead = 0;
    unsigned long startTime = millis();
    
    while (bytesRead < packetLength) {
      if (TGAMSerial.available()) {
        packetBuffer[bytesRead++] = TGAMSerial.read();
      }
      
      // Timeout after 100ms
      if (millis() - startTime > 100) {
        return false;
      }
    }
    
    // Wait for checksum
    while (!TGAMSerial.available()) {
      if (millis() - startTime > 100) {
        return false;
      }
      delay(1);
    }
    
    byte receivedChecksum = TGAMSerial.read();
    
    // Calculate checksum
    byte calculatedChecksum = 0;
    for (int i = 0; i < packetLength; i++) {
      calculatedChecksum += packetBuffer[i];
    }
    calculatedChecksum = ~calculatedChecksum & 0xFF;
    
    // Verify checksum
    if (calculatedChecksum == receivedChecksum) {
      return true;
    } else {
      Serial.println("Checksum error!");
      return false;
    }
  }
  
  return false;
}

// Parse the payload data
void parseTGAMPayload() {
  int i = 0;
  
  while (i < packetLength) {
    // Skip extended code bytes
    while (packetBuffer[i] == EXCODE && i < packetLength) {
      i++;
    }
    
    if (i >= packetLength) break;
    
    byte code = packetBuffer[i++];
    
    // Single-byte value codes (0x00 - 0x7F)
    if (code < 0x80) {
      if (i >= packetLength) break;
      byte value = packetBuffer[i++];
      
      switch (code) {
        case CODE_POOR_SIGNAL:
          poorSignalQuality = value;
          break;
        case CODE_ATTENTION:
          attention = value;
          break;
        case CODE_MEDITATION:
          meditation = value;
          break;
      }
    }
    // Multi-byte value codes (0x80 - 0xFF)
    else {
      if (i >= packetLength) break;
      byte vlength = packetBuffer[i++];
      
      if (i + vlength > packetLength) break;
      
      switch (code) {
        case CODE_RAW_WAVE:
          if (vlength == 2) {
            rawValue = ((int)packetBuffer[i] << 8) | packetBuffer[i + 1];
            // Convert to signed 16-bit
            if (rawValue >= 32768) {
              rawValue -= 65536;
            }
          }
          break;
          
        case CODE_ASIC_EEG_POWER:
          if (vlength == 24) {
            // Each power value is 3 bytes (24-bit unsigned)
            delta = read3ByteValue(i);
            theta = read3ByteValue(i + 3);
            lowAlpha = read3ByteValue(i + 6);
            highAlpha = read3ByteValue(i + 9);
            lowBeta = read3ByteValue(i + 12);
            highBeta = read3ByteValue(i + 15);
            lowGamma = read3ByteValue(i + 18);
            midGamma = read3ByteValue(i + 21);
          }
          break;
      }
      
      i += vlength;
    }
  }
}

// Read 3-byte unsigned value (big-endian)
unsigned long read3ByteValue(int index) {
  return ((unsigned long)packetBuffer[index] << 16) |
         ((unsigned long)packetBuffer[index + 1] << 8) |
         (unsigned long)packetBuffer[index + 2];
}

// Print parsed data to Serial Monitor (compact version)
void printDataCompact() {
  // Print timestamp (millis)
  Serial.print("[");
  Serial.print(millis() / 1000);
  Serial.print("s] ");
  
  // Signal quality indicator
  if (poorSignalQuality == 0) {
    Serial.print("🟢 ");
  } else if (poorSignalQuality < 50) {
    Serial.print("🟡 ");
  } else {
    Serial.print("🔴 ");
  }
  
  Serial.print("SIG:");
  Serial.print(poorSignalQuality);
  Serial.print(" | ATT:");
  Serial.print(attention);
  Serial.print(" | MED:");
  Serial.print(meditation);
  Serial.print(" | RAW:");
  Serial.println(rawValue);
}

// Print parsed data to Serial Monitor (full version)
void printData() {
  Serial.println("--- TGAM Data ---");
  
  // Signal Quality (0 = good, 200 = no contact)
  Serial.print("Signal Quality: ");
  if (poorSignalQuality == 0) {
    Serial.println("Good (Electrode contact OK)");
  } else if (poorSignalQuality == 200) {
    Serial.println("No Contact (Check electrode)");
  } else {
    Serial.print("Noise level: ");
    Serial.println(poorSignalQuality);
  }
  
  // Attention and Meditation (0-100)
  Serial.print("Attention: ");
  Serial.print(attention);
  Serial.print(" | Meditation: ");
  Serial.println(meditation);
  
  // Raw EEG value
  Serial.print("Raw Value: ");
  Serial.println(rawValue);
  
  // EEG Power Bands
  Serial.println("EEG Power Bands:");
  Serial.print("  Delta: "); Serial.println(delta);
  Serial.print("  Theta: "); Serial.println(theta);
  Serial.print("  Low Alpha: "); Serial.println(lowAlpha);
  Serial.print("  High Alpha: "); Serial.println(highAlpha);
  Serial.print("  Low Beta: "); Serial.println(lowBeta);
  Serial.print("  High Beta: "); Serial.println(highBeta);
  Serial.print("  Low Gamma: "); Serial.println(lowGamma);
  Serial.print("  Mid Gamma: "); Serial.println(midGamma);
  
  Serial.println();
}

