import requests
import json
import time
import csv
import os
from datetime import datetime
from firebase import firebase

API_KEY = "c64e8a47b0f348298e8a47b0f3f829cd"
STATION_ID = "ISANTI245"
FIREBASE_URL = "https://weatheriadx-default-rtdb.firebaseio.com/"

db = firebase.FirebaseApplication(FIREBASE_URL, None)

# 🔧 BASE_DIR siempre apunta al directorio real donde está este archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LAST_TS_FILE = os.path.join(BASE_DIR, "last_timestamp.txt")
JSON_FILE = os.path.join(BASE_DIR, "registros.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "history")


def get_data():
    """Obtiene datos meteorológicos actuales desde Weather.com"""
    url = (
        f"https://api.weather.com/v2/pws/observations/current?"
        f"stationId={STATION_ID}&format=json&units=m&apiKey={API_KEY}"
    )

    try:
        response = requests.get(url)
        response.raise_for_status()
        datos = response.json()
        datos["local_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return datos
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Error al obtener datos: {e}")
        return None


def process_and_upload(datos):
    """Procesa los datos y los sube a Firebase"""
    try:
        obs = datos["observations"][0]
        metric = obs["metric"]

        registro = {
            "temp": metric.get("temp"),
            "heatIndex": metric.get("heatIndex"),
            "dewpt": metric.get("dewpt"),
            "windChill": metric.get("windChill"),
            "windSpeed": metric.get("windSpeed"),
            "windGust": metric.get("windGust"),
            "humidity": obs.get("humidity"),
            "pressure": metric.get("pressure"),
            "precipRate": metric.get("precipRate"),
            "precipTotal": metric.get("precipTotal"),
            "timestamp": datos["local_timestamp"]
        }

        db.post("/registros", registro)
        print(f"[{registro['timestamp']}] Datos subidos a Firebase:", registro)
        return registro
    except Exception as e:
        print(f"[Error al subir datos a Firebase: {e}]")
        return None


def save_to_csv_firebase(registro):
    fecha = datetime.now().strftime("%Y-%m-%d")

    try:
        existing = db.get("/csv_history", fecha)

        if isinstance(existing, str):
            existing = []

        if not existing:
            existing = []

        existing.append(registro)

        db.put("/csv_history", fecha, existing)

        print(f"Registro agregado al historial del día {fecha}")

    except Exception as e:
        print("Error guardando historial:", e)


def save_to_json(registros):
    try:
        db.put("/", "json_data", registros)
        print(f"[{datetime.now()}] Datos JSON subidos a Firebase (/json_data)")
    except Exception as e:
        print(f"Error JSON Firebase: {e}")



def load_existing_data():
    try:
        data = db.get("/json_data", None)
        return data if data else []
    except:
        return []



def main_loop():
    print("🌦️ Sistema Weatheria iniciado (sincronización cada 15 minutos).")
    all_records = load_existing_data()

    while True:
        datos = get_data()
        if datos:
            registro = process_and_upload(datos)
            if registro:
                all_records.append(registro)
                save_to_csv_firebase(registro)
                save_to_json(all_records)
        else:
            print(f"[{datetime.now()}] No se obtuvieron datos válidos, reintentando...")

        print("⏳ Esperando 15 minutos para la siguiente actualización...\n")
        time.sleep(900)  # 900 segundos = 15 minutos


if __name__ == "__main__":
    main_loop()
