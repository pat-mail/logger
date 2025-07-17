#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <Adafruit_BME280.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>

// OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Capteurs
Adafruit_BME280 bme1;
Adafruit_BME280 bme2;

// Réseau
const char* ssid = "Livebox-9CB0";
const char* password = "WXbNigTrSpQe96CreW";
const char* serverUrl = "http://192.168.1.18:5000/receive_batch";
const char* timeServerUrl = "http://192.168.1.18:5000/time";

// Bouton
#define BUTTON_PIN 0

// Fonctions de compression/décompression
uint8_t compress(float value, float minVal, float maxVal) {
  return constrain(round((value - minVal) * 255.0 / (maxVal - minVal)), 0, 255);
}

float decompress(uint8_t compressed, float minVal, float maxVal) {
  return compressed * (maxVal - minVal) / 255.0 + minVal;
}

// Stockage mesures compressées
struct MesureCompressee {
  uint8_t temperature1, humidity1, pressure1;
  uint8_t temperature2, humidity2, pressure2;
};
const int MAX_MESURES = 6*(2*3*24)*1;  // nb_mesure_par_jour*( )*nb_jours
MesureCompressee mesuresCompress[MAX_MESURES];
int nbMesures = 0;

// Temps
unsigned long dernierTempsMesure = 0;
const unsigned long intervalleMesure = 2 * 60000;  // nb_mesures_par_heure
unsigned long dernierInteraction = 0;
const unsigned long timeoutOled = 5 * 60000;

bool oledAllume = true;

// Date/heure
int annee, mois, jour, heure, minute;

void setup() {
  pinMode(BUTTON_PIN, INPUT);
  Wire.begin();
  Serial.begin(9600);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println(F("Erreur OLED"));
    while (true);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  afficherTexte("Initialisation...");

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    afficherTexte("Connexion WiFi...");
  }
  afficherTexte("WiFi OK");

  if (!bme1.begin(0x76)) afficherTexte("Erreur capteur BME1");
  if (!bme2.begin(0x77)) afficherTexte("Erreur capteur BME2");

  synchroniserHorloge();
  dernierTempsMesure = millis();
  dernierInteraction = millis();
}

void loop() {
  if (digitalRead(BUTTON_PIN) == LOW) {
    delay(10);
    if (digitalRead(BUTTON_PIN) == LOW) {
      if (!oledAllume) {
        display.ssd1306_command(SSD1306_DISPLAYON);
        oledAllume = true;
        display.clearDisplay();
        display.display();
      }
      afficherInfos();
      synchroniserHorloge();
      envoyerVersServeur();
      dernierInteraction = millis();
      while (digitalRead(BUTTON_PIN) == LOW) delay(10);
    }
  }

  if (millis() - dernierTempsMesure >= intervalleMesure) {
    prendreMesureEtStocker();
    dernierTempsMesure = millis();
  }

  gererExtinctionOled();
}

void envoyerVersServeur() {
  if (WiFi.status() != WL_CONNECTED) {
    afficherTexte("WiFi absent\nPas d'envoi.");
    return;
  }

  if (nbMesures == 0) {
    afficherTexte("Aucune mesure\na envoyer");
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray data = doc.to<JsonArray>();

  for (int i = 0; i < nbMesures; i++) {
    JsonObject m1 = data.createNestedObject();
    m1["device"] = String("lecthi") + "_BME1";
    m1["temperature"] = decompress(mesuresCompress[i].temperature1, 10, 50);
    m1["humidity"] = decompress(mesuresCompress[i].humidity1, 0, 100);
    m1["pressure"] = decompress(mesuresCompress[i].pressure1, 800, 1100);
    m1["timestamp"] = String(annee) + "-" + (mois < 10 ? "0" : "") + String(mois) + "-" + (jour < 10 ? "0" : "") + String(jour)
                      + " " + (heure < 10 ? "0" : "") + String(heure) + ":" + (minute < 10 ? "0" : "") + String(minute) + ":00";

    JsonObject m2 = data.createNestedObject();
    m2["device"] = String("lecthi") + "_BME2";
    m2["temperature"] = decompress(mesuresCompress[i].temperature2, 10, 50);
    m2["humidity"] = decompress(mesuresCompress[i].humidity2, 0, 100);
    m2["pressure"] = decompress(mesuresCompress[i].pressure2, 800, 1100);
    m2["timestamp"] = m1["timestamp"];
  }

  String jsonStr;
  serializeJson(doc, jsonStr);

  HTTPClient http;
  WiFiClient client;
  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(jsonStr);

  if (code > 0 && code < 300) {
    afficherTexte("Envoi OK\n" + String(nbMesures) + " mesures");
  } else {
    afficherErreurTransfert();
  }

  http.end();
  nbMesures = 0;
  dernierInteraction = millis();
}

void afficherTexte(String txt) {
  if (!oledAllume) {
    display.ssd1306_command(SSD1306_DISPLAYON);
    oledAllume = true;
  }
  display.clearDisplay();
  display.setCursor(0, 0);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.println(txt);
  display.display();
}

void synchroniserHorloge() {
  if (WiFi.status() != WL_CONNECTED) {
    afficherTexte("WiFi absent\nSync horloge ratee");
    return;
  }

  HTTPClient http;
  WiFiClient client;
  http.begin(client, timeServerUrl);
  int code = http.GET();

  if (code == 200) {
    String payload = http.getString();
    DynamicJsonDocument doc(256);
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      annee = doc["year"];
      mois = doc["month"];
      jour = doc["day"];
      heure = doc["hour"];
      minute = doc["minute"];
      afficherTexte("Heure sync:\n" + String(heure) + ":" + String(minute));
    } else {
      afficherTexte("Erreur JSON horloge");
    }
  } else {
    afficherTexte("Sync horloge échouée");
  }

  http.end();
}

void afficherInfos() {
  dernierInteraction = millis();
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Mesures: " + String(nbMesures));
  display.printf("%02d:%02d - %02d/%02d/%04d\n", heure, minute, jour, mois, annee);

  if (nbMesures > 0) {
    display.println("T1:" + String(decompress(mesuresCompress[nbMesures - 1].temperature1, 10, 50), 1) +
                    " H1:" + String(decompress(mesuresCompress[nbMesures - 1].humidity1, 0, 100), 1));
    display.println("T2:" + String(decompress(mesuresCompress[nbMesures - 1].temperature2, 10, 50), 1) +
                    " H2:" + String(decompress(mesuresCompress[nbMesures - 1].humidity2, 0, 100), 1));
  } else {
    display.println("Aucune mesure.");
  }
  display.display();
}

void prendreMesureEtStocker() {
  if (nbMesures >= MAX_MESURES) {
    afficherTexte("Stockage plein!");
    return;
  }

  float t1 = bme1.readTemperature();
  float h1 = bme1.readHumidity();
  float p1 = bme1.readPressure() / 100.0F;

  float t2 = bme2.readTemperature();
  float h2 = bme2.readHumidity();
  float p2 = bme2.readPressure() / 100.0F;

  if (isnan(t1) || isnan(h1) || isnan(p1)) {
    afficherTexte("Erreur BME1");
    return;
  }
  if (isnan(t2) || isnan(h2) || isnan(p2)) {
    afficherTexte("Erreur BME2");
    return;
  }

  mesuresCompress[nbMesures++] = {
    compress(t1, 10, 50), compress(h1, 0, 100), compress(p1, 800, 1100),
    compress(t2, 10, 50), compress(h2, 0, 100), compress(p2, 800, 1100)
  };

  afficherTexte("Mesure OK\nT1:" + String(t1, 1) + " T2:" + String(t2, 1));
}

void gererExtinctionOled() {
  if (oledAllume && (millis() - dernierInteraction > timeoutOled)) {
    display.ssd1306_command(SSD1306_DISPLAYOFF);
    oledAllume = false;
  }
}

void afficherErreurTransfert() {
  afficherTexte("Erreur transfert !");
}
