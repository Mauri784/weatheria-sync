from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import requests
import json
import csv
import os
from datetime import datetime
import threading

app = Flask(__name__)
# Configurar CORS para permitir peticiones desde Vercel
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://weatheria1-topaz.vercel.app"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Variables de entorno
API_KEY = os.environ.get("WEATHER_COM_API_KEY", "c64e8a47b0f348298e8a47b0f3f829cd")
STATION_ID = os.environ.get("STATION_ID", "ISANTI245")
FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://weatheriadx-default-rtdb.firebaseio.com")

# Asegurar que Firebase URL no tenga / al final
FIREBASE_URL = FIREBASE_URL.rstrip('/')

# Directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_TS_FILE = os.path.join(BASE_DIR, "last_timestamp.txt")
JSON_FILE = os.path.join(BASE_DIR, "registros.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "history")

# Variable global para almacenar el último estado
ultimo_estado = {
    "ultimo_registro": None,
    "total_registros": 0,
    "ultima_actualizacion": None
}

# Variable global para almacenar reportes de inundaciones
reportes_inundacion = []


# --- FUNCIONES FIREBASE CON REQUESTS ---

def firebase_post(path, data):
    """POST a Firebase usando requests"""
    try:
        url = f"{FIREBASE_URL}{path}.json"
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error en firebase_post: {e}")
        return None


def firebase_put(path, data):
    """PUT a Firebase usando requests"""
    try:
        url = f"{FIREBASE_URL}{path}.json"
        response = requests.put(url, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error en firebase_put: {e}")
        return None


def firebase_get(path):
    """GET de Firebase usando requests"""
    try:
        url = f"{FIREBASE_URL}{path}.json"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error en firebase_get: {e}")
        return None


# --- FUNCIONES PRINCIPALES ---

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

        firebase_post("/registros", registro)
        print(f"[{registro['timestamp']}] Datos subidos a Firebase:", registro)
        return registro
    except Exception as e:
        print(f"[Error al subir datos a Firebase: {e}]")
        return None


def save_to_csv(registros):
    """Guarda los datos en CSV separados por día"""
    if not registros:
        return

    registros_por_dia = {}
    for reg in registros:
        try:
            fecha = datetime.fromisoformat(reg["timestamp"]).strftime("%Y-%m-%d")
        except Exception:
            fecha = datetime.now().strftime("%Y-%m-%d")

        registros_por_dia.setdefault(fecha, []).append(reg)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for fecha, registros_dia in registros_por_dia.items():
        filename = os.path.join(OUTPUT_DIR, f"{fecha}.csv")
        file_exists = os.path.exists(filename)

        fieldnames = sorted(list({k for r in registros_dia for k in r.keys()}))

        with open(filename, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(registros_dia)

        print(f"[{datetime.now()}] Guardados {len(registros_dia)} registros en {filename}")


def save_to_json(registros):
    """Guarda todos los datos en un JSON y lo sube a Firebase"""
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as jsonfile:
            json.dump(registros, jsonfile, indent=4, ensure_ascii=False)
        print(f"[{datetime.now()}] Guardados {len(registros)} registros en {JSON_FILE}")

        firebase_put("/json_data", registros)
        print(f"[{datetime.now()}] Datos JSON subidos a Firebase (/json_data)")
    except Exception as e:
        print(f"Error al guardar/subir JSON: {e}")


def load_existing_data():
    """Carga el JSON existente para no perder registros previos"""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def actualizar_datos_interno():
    """Función interna para actualizar los datos meteorológicos"""
    global ultimo_estado
    
    all_records = load_existing_data()
    datos = get_data()
    
    if datos:
        registro = process_and_upload(datos)
        if registro:
            all_records.append(registro)
            save_to_csv([registro])
            save_to_json(all_records)
            
            ultimo_estado = {
                "ultimo_registro": registro,
                "total_registros": len(all_records),
                "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return True, registro
    
    return False, None


# --- ENDPOINTS DE LA API ---

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'API de sincronización meteorológica funcionando',
        'ultima_actualizacion': ultimo_estado.get('ultima_actualizacion'),
        'total_registros': ultimo_estado.get('total_registros', 0)
    })


@app.route('/actualizar', methods=['GET', 'POST'])
def actualizar_datos():
    """Endpoint para forzar una actualización de datos"""
    try:
        exito, registro = actualizar_datos_interno()
        
        if exito:
            return jsonify({
                'status': 'success',
                'message': 'Datos actualizados correctamente',
                'data': registro
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No se pudieron obtener datos válidos'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/registros', methods=['GET'])
def obtener_registros():
    """Obtener todos los registros guardados"""
    try:
        registros = load_existing_data()
        return jsonify({
            'status': 'success',
            'total': len(registros),
            'data': registros
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/ultimo', methods=['GET'])
def obtener_ultimo():
    """Obtener el último registro"""
    try:
        if ultimo_estado.get('ultimo_registro'):
            return jsonify({
                'status': 'success',
                'data': ultimo_estado['ultimo_registro']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No hay registros disponibles'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/descargar-json', methods=['GET'])
def descargar_json():
    """Descargar el archivo JSON completo"""
    try:
        if os.path.exists(JSON_FILE):
            return send_file(JSON_FILE, as_attachment=True, download_name='registros.json')
        else:
            return jsonify({
                'status': 'error',
                'message': 'No hay archivo JSON disponible'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/flood_history', methods=['GET'])
def obtener_historial_inundaciones():
    """Obtener el historial de reportes de inundaciones"""
    try:
        return jsonify({
            'status': 'success',
            'total': len(reportes_inundacion),
            'data': reportes_inundacion
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/report_flood', methods=['POST'])
def reportar_inundacion():
    """Endpoint para reportar una inundación"""
    try:
        from flask import request
        data = request.get_json()
        
        # Agregar timestamp al reporte
        reporte = {
            **data,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'id': len(reportes_inundacion) + 1
        }
        
        reportes_inundacion.append(reporte)
        
        # Opcional: guardar en Firebase
        try:
            firebase_post("/reportes_inundacion", reporte)
        except Exception as fb_error:
            print(f"Error guardando en Firebase: {fb_error}")
        
        return jsonify({
            'status': 'success',
            'message': 'Reporte de inundación registrado correctamente',
            'data': reporte
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def inicializar():
    """Se ejecuta una vez al iniciar el servidor"""
    print("🌦️ Iniciando servidor de sincronización meteorológica...")
    try:
        actualizar_datos_interno()
        print("✅ Primera actualización completada")
    except Exception as e:
        print(f"❌ Error en inicialización: {e}")


if __name__ == '__main__':
    # Ejecutar inicialización en un hilo separado
    threading.Thread(target=inicializar, daemon=True).start()
    
    # Iniciar el servidor Flask
    app.run(host='0.0.0.0', port=5000, debug=False)
