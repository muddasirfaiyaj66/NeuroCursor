/*
 * ESP32-S3 Taurus TGM (TGAM Compatible) Brainwave Sensor Reader
 * With WebSocket Communication (FIXED VERSION)
 * 
 * Connections for ESP32-S3:
 * TGAM T (TX) -> ESP32-S3 GPIO18 (RX1)
 * TGAM - (GND) -> ESP32-S3 GND
 * TGAM + (VCC) -> ESP32-S3 3.3V
 */

#include <WiFi.h>
#include <WebSocketsServer.h>
#include <HardwareSerial.h>
#include <ESPmDNS.h>

/* ================= WIFI LIST ================= */
const char* wifiList[][2] = {
  {"Motorola edge", "1234@###"},
  {"Sagar", "9661"},
  {"UIU-Faculty-Staff", "UIU#9876"},
  {"UIU-STUDENT", "12345678"},
  {"SHAHED", "987654321"}
};
const char* MDNS_NAME = "NeuroCursor-esp";
const int WIFI_COUNT = sizeof(wifiList) / sizeof(wifiList[0]);

/* ================= WEBSOCKET ================= */
WebSocketsServer webSocket(81);
bool clientConnected = false;

/* ================= TGAM SERIAL ================= */
HardwareSerial TGAMSerial(1);
#define TGAM_RX_PIN 18  // ESP32-S3 RX <- TGAM TX
#define TGAM_TX_PIN 17  // Not used
#define TGAM_BAUD_RATE 9600  // Use 9600 for processed data

/* ================= PACKET CONSTANTS ================= */
#define SYNC_BYTE 0xAA
#define EXCODE 0x55
#define CODE_POOR_SIGNAL 0x02
#define CODE_ATTENTION 0x04
#define CODE_MEDITATION 0x05
#define CODE_RAW_WAVE 0x80
#define CODE_ASIC_EEG_POWER 0x83



/* ================= DATA VARIABLES ================= */
int poorSignalQuality = 200;
int attention = 0;
int meditation = 0;
int rawValue = 0;

unsigned long delta = 0;
unsigned long theta = 0;
unsigned long lowAlpha = 0;
unsigned long highAlpha = 0;
unsigned long lowBeta = 0;
unsigned long highBeta = 0;
unsigned long lowGamma = 0;
unsigned long midGamma = 0;

/* ================= PACKET BUFFER ================= */
#define PACKET_BUFFER_SIZE 256
byte packetBuffer[PACKET_BUFFER_SIZE];
int packetLength = 0;

/* ================= TIMING ================= */
unsigned long lastStatusTime = 0;
unsigned long lastDataTime = 0;
const int STATUS_INTERVAL = 2000;

/* ================= FUNCTION DECLARATIONS ================= */
void connectToWiFi();
bool readTGAMPacket();
void parseTGAMPayload();
unsigned long read3ByteValue(int index);
void sendDataToWebSocket();
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length);

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  
  Serial.println("\n=================================");
  Serial.println("ESP32-S3 TGAM WebSocket Reader");
  Serial.println("=================================");
  
  // Initialize TGAM Serial
  TGAMSerial.begin(TGAM_BAUD_RATE, SERIAL_8N1, TGAM_RX_PIN, TGAM_TX_PIN);
  Serial.print("TGAM Serial: ");
  Serial.print(TGAM_BAUD_RATE);
  Serial.println(" baud");
  Serial.println("\n=== WIRING ===");
  Serial.println("TGAM TX  -> ESP32-S3 GPIO18");
  Serial.println("TGAM GND -> ESP32-S3 GND");
  Serial.println("TGAM VCC -> ESP32-S3 3.3V");
  Serial.println("==============\n");
  
  // Connect WiFi
  connectToWiFi();
  
  // Start WebSocket Server
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  Serial.println("WebSocket server started on port 81");
  Serial.println("Connect using: ws://" + WiFi.localIP().toString() + ":81");
  Serial.println();
}

/* ================= MAIN LOOP ================= */
void loop() {
  webSocket.loop();
  
  // Status update
  if (millis() - lastStatusTime >= STATUS_INTERVAL) {
    lastStatusTime = millis();
    
    int bytesAvailable = TGAMSerial.available();
    Serial.print("📊 TGAM buffer: ");
    Serial.print(bytesAvailable);
    Serial.print(" bytes | WS Client: ");
    Serial.print(clientConnected ? "Connected ✓" : "Not connected ✗");
    Serial.print(" | Last data: ");
    if (lastDataTime > 0) {
      Serial.print((millis() - lastDataTime) / 1000);
      Serial.println("s ago");
    } else {
      Serial.println("Never");
    }
    
    if (bytesAvailable == 0) {
      Serial.println("   ⚠️ No data - Check wiring!");
    }
  }
  
  // Read and parse TGAM data
  if (readTGAMPacket()) {
    lastDataTime = millis();
    parseTGAMPayload();
    
    // Print to Serial
    Serial.print("[");
    Serial.print(millis() / 1000);
    Serial.print("s] ");
    
    if (poorSignalQuality == 0) Serial.print("🟢 ");
    else if (poorSignalQuality < 50) Serial.print("🟡 ");
    else Serial.print("🔴 ");
    
    Serial.print("SIG:");
    Serial.print(poorSignalQuality);
    Serial.print(" | ATT:");
    Serial.print(attention);
    Serial.print(" | MED:");
    Serial.print(meditation);
    Serial.print(" | RAW:");
    Serial.println(rawValue);
    
    // Send via WebSocket
    sendDataToWebSocket();
  }
  
  // WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    MDNS.end(); 
    Serial.println("WiFi lost! Reconnecting...");
    connectToWiFi();
  }
}

/* ================= WIFI CONNECTION ================= */
void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(200);

  Serial.println("Scanning WiFi networks...");
  int n = WiFi.scanNetworks();

  if (n == 0) {
    Serial.println("❌ No WiFi networks found");
    return;
  }

  for (int i = 0; i < WIFI_COUNT; i++) {
    for (int j = 0; j < n; j++) {
      if (WiFi.SSID(j) == wifiList[i][0]) {
        Serial.print("Connecting to ");
        Serial.println(wifiList[i][0]);

        WiFi.begin(wifiList[i][0], wifiList[i][1]);

        int attempts = 0;
        while (WiFi.status() != WL_CONNECTED && attempts < 20) {
          delay(500);
          Serial.print(".");
          attempts++;
        }

        if (WiFi.status() == WL_CONNECTED) {
          Serial.println("\n✅ Connected!");
          Serial.print("IP: ");
          Serial.println(WiFi.localIP());

         // -------- mDNS START --------
          if (!MDNS.begin(MDNS_NAME)) {
           Serial.println("❌ mDNS failed to start");
          } else {
            MDNS.addService("ws", "tcp", 81);
            Serial.print("🌐 mDNS active: ");
            Serial.print(MDNS_NAME);
            Serial.println(".local");
          }
  // ----------------------------

          Serial.println();
          return;
        } else {
          Serial.println("\n❌ Failed, trying next...");
        }
      }
    }
  }

  Serial.println("⚠️ Could not connect to any WiFi");
}


/* ================= READ TGAM PACKET ================= */
bool readTGAMPacket() {
  while (TGAMSerial.available() >= 2) {
    // Look for SYNC bytes (0xAA 0xAA)
    if (TGAMSerial.read() != SYNC_BYTE) continue;
    if (TGAMSerial.read() != SYNC_BYTE) continue;
    
    // Wait for packet length
    while (!TGAMSerial.available()) delay(1);
    
    packetLength = TGAMSerial.read();
    if (packetLength >= SYNC_BYTE) continue;
    
    // Read payload
    int bytesRead = 0;
    unsigned long startTime = millis();
    
    while (bytesRead < packetLength) {
      if (TGAMSerial.available()) {
        packetBuffer[bytesRead++] = TGAMSerial.read();
      }
      if (millis() - startTime > 100) return false;
    }
    
    // Wait for checksum
    while (!TGAMSerial.available()) {
      if (millis() - startTime > 100) return false;
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

/* ================= PARSE PAYLOAD ================= */
void parseTGAMPayload() {
  int i = 0;
  
  while (i < packetLength) {
    // Skip extended code bytes
    while (packetBuffer[i] == EXCODE && i < packetLength) {
      i++;
    }
    
    if (i >= packetLength) break;
    
    byte code = packetBuffer[i++];
    
    // Single-byte codes
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
    // Multi-byte codes
    else {
      if (i >= packetLength) break;
      byte vlength = packetBuffer[i++];
      
      if (i + vlength > packetLength) break;
      
      switch (code) {
        case CODE_RAW_WAVE:
          if (vlength == 2) {
            rawValue = ((int)packetBuffer[i] << 8) | packetBuffer[i + 1];
            if (rawValue >= 32768) rawValue -= 65536;
          }
          break;
          
        case CODE_ASIC_EEG_POWER:
          if (vlength == 24) {
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

/* ================= READ 3-BYTE VALUE ================= */
unsigned long read3ByteValue(int index) {
  return ((unsigned long)packetBuffer[index] << 16) |
         ((unsigned long)packetBuffer[index + 1] << 8) |
         (unsigned long)packetBuffer[index + 2];
}

/* ================= SEND VIA WEBSOCKET ================= */
void sendDataToWebSocket() {
  if (!clientConnected) return;
  
  // Build JSON string
  String json = "{";
  json += "\"sig\":" + String(poorSignalQuality) + ",";
  json += "\"att\":" + String(attention) + ",";
  json += "\"med\":" + String(meditation) + ",";
  json += "\"raw\":" + String(rawValue) + ",";
  json += "\"delta\":" + String(delta) + ",";
  json += "\"theta\":" + String(theta) + ",";
  json += "\"la\":" + String(lowAlpha) + ",";
  json += "\"ha\":" + String(highAlpha) + ",";
  json += "\"lb\":" + String(lowBeta) + ",";
  json += "\"hb\":" + String(highBeta) + ",";
  json += "\"lg\":" + String(lowGamma) + ",";
  json += "\"mg\":" + String(midGamma);
  json += "}";
  
  webSocket.broadcastTXT(json);
}

/* ================= WEBSOCKET EVENT HANDLER ================= */
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.printf("[%u] Client disconnected\n", num);
      clientConnected = false;
      break;
      
    case WStype_CONNECTED:
      {
        IPAddress ip = webSocket.remoteIP(num);
        Serial.printf("[%u] Client connected from %d.%d.%d.%d\n", 
                      num, ip[0], ip[1], ip[2], ip[3]);
        clientConnected = true;
      }
      break;
      
    case WStype_TEXT:
      Serial.printf("[%u] Received text: %s\n", num, payload);
      break;
  }
}