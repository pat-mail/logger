#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <Adafruit_BME280.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>

void afficherTexte(String txt);
void synchroniserHorloge();
void afficherInfos();
void prendreMesureEtStocker();
void gererExtinctionOled();
void afficherErreurTransfert();


#define DEVICE_NAME "carambole"

// OLED config
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Capteurs BME280
Adafruit_BME280 bme1; // Adresse I2C 0x76
Adafruit_BME280 bme2; // Adresse I2C 0x77

// Réseau
const char* ssid = ".......";
const char* password = ".......";
const char* serverUrl = "http://192.168.1.18:5000/receive_batch";
const char* timeServerUrl = "http://192.168.1.18:5000/time";

// Bouton
#define BUTTON_PIN 0

// Données mesures
struct Mesure {
  float temperature1, humidity1, pressure1;
  float temperature2, humidity2, pressure2;
};
const int MAX_MESURES = 4.5*432;   //  3x24x6  =432/jour
Mesure mesures[MAX_MESURES];
int nbMesures = 0;

// Temps
unsigned long dernierTempsMesure = 0;
const unsigned long intervalleMesure = 10 * 60000; // 60s

unsigned long dernierInteraction = 0;
const unsigned long timeoutOled = 5 * 60000; // 5 min

bool oledAllume = true;

// Heure
int annee, mois, jour, heure, minute;

// Anti-rebond bouton
bool boutonEtatPrecedent = HIGH;
unsigned long dernierDebounce = 0;
const unsigned long debounceDelay = 50; // 50 ms

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

  if (!bme1.begin(0x76)) Serial.println("Erreur BME1");
  if (!bme2.begin(0x77)) Serial.println("Erreur BME2");

  synchroniserHorloge();
  dernierTempsMesure = millis();
  dernierInteraction = millis();
}

void loop() {
  int lectureBouton = digitalRead(BUTTON_PIN);

  if (lectureBouton == LOW) {
    delay(10); // anti-rebond simple
    if (digitalRead(BUTTON_PIN) == LOW) {
      Serial.println("Bouton appuyé");
      if (!oledAllume) {
        display.ssd1306_command(SSD1306_DISPLAYON);
        oledAllume = true;
        display.clearDisplay();
        display.display();
      }
      afficherInfos();
      synchroniserHorloge();
      envoyerVersServeur();
      dernierInteraction = millis();  // mettre à jour interaction après envoi
      while(digitalRead(BUTTON_PIN) == LOW) delay(10); // attente relâchement
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
    Serial.println("WiFi non connecté, pas d'envoi");
    return;
  }
  if (nbMesures == 0) {
    Serial.println("Aucune mesure à envoyer");
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray data = doc.to<JsonArray>();

  for (int i = 0; i < nbMesures; i++) {
    JsonObject m1 = data.createNestedObject();
    m1["device"] = String(DEVICE_NAME) + "_BME1";
    m1["temperature"] = mesures[i].temperature1;
    m1["humidity"] = mesures[i].humidity1;
    m1["pressure"] = mesures[i].pressure1;
    m1["timestamp"] = String(annee) + "-" + (mois < 10 ? "0" : "") + String(mois) + "-" + (jour < 10 ? "0" : "") + String(jour)
                      + " " + (heure < 10 ? "0" : "") + String(heure) + ":" + (minute < 10 ? "0" : "") + String(minute) + ":00";

    JsonObject m2 = data.createNestedObject();
    m2["device"] = String(DEVICE_NAME) + "_BME2";
    m2["temperature"] = mesures[i].temperature2;
    m2["humidity"] = mesures[i].humidity2;
    m2["pressure"] = mesures[i].pressure2;
    m2["timestamp"] = String(annee) + "-" + (mois < 10 ? "0" : "") + String(mois) + "-" + (jour < 10 ? "0" : "") + String(jour)
                      + " " + (heure < 10 ? "0" : "") + String(heure) + ":" + (minute < 10 ? "0" : "") + String(minute) + ":00";
  }

  String jsonStr;
  serializeJson(doc, jsonStr);

  HTTPClient http;
  WiFiClient client;
  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(jsonStr);
  if (code > 0 && code < 300) {
    Serial.printf("[HTTP] Réponse serveur : %d\n", code);
  } else {
    Serial.printf("[HTTP] Échec : %s\n", http.errorToString(code).c_str());
    afficherErreurTransfert();
  }
  http.end();

  nbMesures = 0;
  dernierInteraction = millis(); // mettre à jour interaction ici aussi
}

// Affiche un texte simple sur l'écran OLED
void afficherTexte(String txt) {
  if (!oledAllume) {
    display.ssd1306_command(SSD1306_DISPLAYON);
    oledAllume = true;
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(txt);
  display.display();
  Serial.println(txt);
}

// Synchronise l'heure avec le serveur HTTP
void synchroniserHorloge() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi non connecté, impossible de synchroniser l'heure.");
    return;
  }

  HTTPClient http;
  WiFiClient client;
  http.begin(client, timeServerUrl);

  int httpCode = http.GET();
  if (httpCode == 200) {
    String payload = http.getString();

    DynamicJsonDocument doc(256);
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
      Serial.println("Erreur JSON horloge : " + String(err.c_str()));
    } else {
      annee  = doc["year"];
      mois   = doc["month"];
      jour   = doc["day"];
      heure  = doc["hour"];
      minute = doc["minute"];
      Serial.printf("Horloge synchronisée : %04d-%02d-%02d %02d:%02d\n", annee, mois, jour, heure, minute);
    }
  } else {
    Serial.printf("Erreur HTTP horloge : %d\n", httpCode);
  }
  http.end();
}


// Affiche le nombre de mesures et l'heure sur OLED
void afficherInfos() {
  dernierInteraction = millis();

  if (!oledAllume) {
    display.ssd1306_command(SSD1306_DISPLAYON);
    oledAllume = true;
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(0, 0);
  display.println("Mesures stockees: " + String(nbMesures));

  display.setCursor(0, 12);
  display.printf("%02d:%02d - %02d/%02d/%04d\n", heure, minute, jour, mois, annee);

  display.setCursor(0, 24);
  if (nbMesures > 0) {
    display.println("Derniere mesure:");
    display.printf("T1: %.1fC H1: %.1f%%\n", mesures[nbMesures - 1].temperature1, mesures[nbMesures - 1].humidity1);
    display.printf("T2: %.1fC H2: %.1f%%\n", mesures[nbMesures - 1].temperature2, mesures[nbMesures - 1].humidity2);
  } else {
    display.println("Aucune mesure.");
  }

  display.display();
}

// Prend une mesure sur les deux capteurs BME280 et stocke dans le tableau
void prendreMesureEtStocker() {
  if (nbMesures >= MAX_MESURES) {
    Serial.println("Capacité de stockage atteinte.");
    return;
  }

  Mesure m;
  m.temperature1 = bme1.readTemperature();
  m.humidity1 = bme1.readHumidity();
  m.pressure1 = bme1.readPressure() / 100.0F;

  m.temperature2 = bme2.readTemperature();
  m.humidity2 = bme2.readHumidity();
  m.pressure2 = bme2.readPressure() / 100.0F;

  // Vérification simple capteur (valeurs plausibles)
  if (isnan(m.temperature1) || isnan(m.humidity1) || isnan(m.pressure1)) {
    Serial.println("Erreur lecture BME1");
  }
  if (isnan(m.temperature2) || isnan(m.humidity2) || isnan(m.pressure2)) {
    Serial.println("Erreur lecture BME2");
  }

  mesures[nbMesures++] = m;
  Serial.println("Mesure prise et stockée.");
}

// Gère l'extinction automatique de l'écran OLED après timeout
void gererExtinctionOled() {
  if (oledAllume && (millis() - dernierInteraction > timeoutOled)) {
    display.ssd1306_command(SSD1306_DISPLAYOFF);
    oledAllume = false;
    Serial.println("OLED éteint par timeout.");
  }
}

// Affiche un message d'erreur transfert sur OLED et sur série
void afficherErreurTransfert() {
  Serial.println("Erreur lors du transfert des données.");

  if (!oledAllume) {
    display.ssd1306_command(SSD1306_DISPLAYON);
    oledAllume = true;
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Erreur transfert !");
  display.display();
}
