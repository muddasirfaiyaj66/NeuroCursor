/*
 * ESP32-S3 TGAM EEG Dashboard (WebSocket Real-Time)
 */

#include <WiFi.h>
#include <WebSocketsServer.h>
#include <HardwareSerial.h>

// ================= WIFI =================
const char* ssid = "Motorola edge";
const char* password = "1234@@@###";

// ================= TGAM =================
HardwareSerial TGAMSerial(1);
#define TGAM_RX_PIN 18
#define TGAM_TX_PIN 17
#define TGAM_BAUD_RATE 9600

#define SYNC_BYTE 0xAA
#define EXCODE 0x55
#define CODE_POOR_SIGNAL 0x02
#define CODE_ATTENTION 0x04
#define CODE_MEDITATION 0x05
#define CODE_BLINK 0x16
#define CODE_RAW_WAVE 0x80

// ================= SERVERS =================
WiFiServer httpServer(80);
WebSocketsServer webSocket(81);

// ================= EEG DATA =================
int poorSignalQuality = 200;
int attention = 0;
int meditation = 0;
int blinkStrength = 0;
int rawValue = 0;

// ================= CSV =================
#define MAX_CSV_ROWS 500
String csv[MAX_CSV_ROWS];
int csvRows = 0;
bool recording = false;
unsigned long recordStart = 0;

// ================= TGAM BUFFER =================
byte packetBuffer[256];
int packetLength = 0;

// =================================================
// HTML + JS (WebSocket)
const char webpage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>EEG WebSocket Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body{margin:0;font-family:Arial;background:#0b1020;color:#fff}
.container{padding:20px;max-width:1300px;margin:auto}
h1{text-align:center}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px}
.card{background:#161f3d;padding:20px;border-radius:14px}
.value{font-size:2.5rem;font-weight:bold}
.good{color:#2ce59b}
.mid{color:#f6c177}
.bad{color:#ff6b6b}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-top:20px}
canvas{max-height:260px}
button{padding:14px 24px;border:none;border-radius:10px;font-weight:bold;margin:10px;cursor:pointer}
.rec{background:#ff6b6b}
</style>
</head>

<body>
<div class="container">
<h1>🧠 EEG Real-Time Dashboard</h1>

<div class="cards">
  <div class="card"><div>Signal</div><div id="sig" class="value">---</div></div>
  <div class="card"><div>Attention</div><div id="att" class="value">0</div></div>
  <div class="card"><div>Meditation</div><div id="med" class="value">0</div></div>
  <div class="card"><div>Blink</div><div id="blink" class="value">0</div></div>
</div>

<div class="charts">
  <canvas id="attMed"></canvas>
  <canvas id="signal"></canvas>
  <canvas id="blinkChart"></canvas>
  <canvas id="raw"></canvas>
</div>

<div style="text-align:center">
<button id="recBtn" onclick="toggleRec()">Start Recording</button>
<button onclick="location.href='/download'">Download CSV</button>
</div>

</div>

<script>
const ws = new WebSocket(`ws://${location.hostname}:81`);
const maxPoints = 80;

const base = {
  responsive:true,
  animation:false,
  scales:{x:{display:false},y:{grid:{color:'rgba(255,255,255,.1)'}}}
};

const attMed = new Chart(attMed.getContext('2d'),{
 type:'line',
 data:{labels:[],datasets:[
  {label:'Attention',data:[],borderColor:'#2ce59b'},
  {label:'Meditation',data[],borderColor:'#4fd1c5'}
 ]},
 options:{...base,scales:{...base.scales,y:{min:0,max:100}}}
});

const signal = new Chart(signal.getContext('2d'),{
 type:'line',
 data:{labels:[],datasets:[{label:'Signal',data:[],borderColor:'#f6c177'}]},
 options:{...base,scales:{...base.scales,y:{min:0,max:200}}}
});

const blinkChart = new Chart(blinkChart.getContext('2d'),{
 type:'bar',
 data:{labels:[],datasets:[{label:'Blink',data:[],backgroundColor:'#ff6b6b'}]},
 options:{...base,scales:{...base.scales,y:{min:0,max:100}}}
});

const raw = new Chart(raw.getContext('2d'),{
 type:'line',
 data:{labels:[],datasets:[{label:'RAW',data:[],borderColor:'#00f5ff',pointRadius:0}]},
 options:base
});

function push(chart, vals){
 chart.data.labels.push('');
 vals.forEach((v,i)=>chart.data.datasets[i].data.push(v));
 if(chart.data.labels.length>maxPoints){
  chart.data.labels.shift();
  chart.data.datasets.forEach(d=>d.data.shift());
 }
 chart.update();
}

ws.onmessage = e =>{
 const d = JSON.parse(e.data);

 att.textContent = d.att;
 med.textContent = d.med;
 blink.textContent = d.blink;

 sig.textContent = d.sig==0?'Good':d.sig<50?'Medium':'Poor';
 sig.className = 'value '+(d.sig==0?'good':d.sig<50?'mid':'bad');

 push(attMed,[d.att,d.med]);
 push(signal,[d.sig]);
 push(blinkChart,[d.blink]);
 push(raw,[d.raw]);
};

function toggleRec(){
 fetch(recBtn.classList.toggle('rec')?'/start':'/stop');
 recBtn.textContent = recBtn.classList.contains('rec')?'Stop Recording':'Start Recording';
}
</script>
</body>
</html>
)rawliteral";

// =================================================
// TGAM PARSER

bool readTGAMPacket() {
  while (TGAMSerial.available() >= 2) {
    if (TGAMSerial.read() != SYNC_BYTE) continue;
    if (TGAMSerial.read() != SYNC_BYTE) continue;

    packetLength = TGAMSerial.read();
    if (packetLength >= 170) continue;

    for (int i = 0; i < packetLength; i++) {
      while (!TGAMSerial.available());
      packetBuffer[i] = TGAMSerial.read();
    }

    byte checksum = TGAMSerial.read();
    byte sum = 0;
    for (int i = 0; i < packetLength; i++) sum += packetBuffer[i];
    sum = ~sum;

    return sum == checksum;
  }
  return false;
}

void parseTGAM() {
  int i = 0;
  while (i < packetLength) {
    byte code = packetBuffer[i++];
    if (code < 0x80) {
      byte val = packetBuffer[i++];
      if (code == CODE_POOR_SIGNAL) poorSignalQuality = val;
      if (code == CODE_ATTENTION) attention = val;
      if (code == CODE_MEDITATION) meditation = val;
      if (code == CODE_BLINK) blinkStrength = val;
    } else {
      byte len = packetBuffer[i++];
      if (code == CODE_RAW_WAVE && len == 2) {
        rawValue = (packetBuffer[i]<<8)|packetBuffer[i+1];
        if (rawValue > 32767) rawValue -= 65536;
      }
      i += len;
    }
  }

  if (recording && csvRows < MAX_CSV_ROWS) {
    csv[csvRows++] = String(millis()-recordStart)+","+attention+","+meditation+","+blinkStrength+","+poorSignalQuality+","+rawValue+"\n";
  }
}

// =================================================
// WEBSOCKET EVENT

void webSocketEvent(uint8_t, WStype_t type, uint8_t*, size_t) {
  if (type == WStype_CONNECTED) Serial.println("🌐 WebSocket Client Connected");
}

// =================================================
// HTTP HANDLER

void handleHttp(WiFiClient c){
  String r = c.readStringUntil('\r');
  c.flush();

  if (r.indexOf("GET / ")>=0){
    c.println("HTTP/1.1 200 OK\r\nContent-Type:text/html\r\n\r\n");
    c.print(webpage);
  }
  else if (r.indexOf("GET /start")>=0){
    recording=true; csvRows=0; recordStart=millis();
    c.println("HTTP/1.1 200 OK\r\n\r\n");
  }
  else if (r.indexOf("GET /stop")>=0){
    recording=false;
    c.println("HTTP/1.1 200 OK\r\n\r\n");
  }
  else if (r.indexOf("GET /download")>=0){
    c.println("HTTP/1.1 200 OK\r\nContent-Type:text/csv\r\n\r\n");
    c.print("t,att,med,blink,sig,raw\n");
    for(int i=0;i<csvRows;i++) c.print(csv[i]);
  }
  c.stop();
}

// =================================================
// SETUP

void setup() {
  Serial.begin(115200);
  TGAMSerial.begin(TGAM_BAUD_RATE, SERIAL_8N1, TGAM_RX_PIN, TGAM_TX_PIN);

  WiFi.begin(ssid,password);
  while(WiFi.status()!=WL_CONNECTED) delay(500);

  httpServer.begin();
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);

  Serial.print("Dashboard: http://");
  Serial.println(WiFi.localIP());
}

// =================================================
// LOOP

void loop() {
  webSocket.loop();

  WiFiClient c = httpServer.available();
  if (c) handleHttp(c);

  if (readTGAMPacket()) {
    parseTGAM();
    String json = "{\"att\":"+String(attention)+
                  ",\"med\":"+String(meditation)+
                  ",\"blink\":"+String(blinkStrength)+
                  ",\"sig\":"+String(poorSignalQuality)+
                  ",\"raw\":"+String(rawValue)+"}";
    webSocket.broadcastTXT(json);
  }
}
