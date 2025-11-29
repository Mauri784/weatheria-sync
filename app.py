import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
import re
import sqlite3
from flask_cors import CORS
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import datetime
import googlemaps
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuración JWT
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'tu_clave_secreta_super_fuerte')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(minutes=30)
jwt = JWTManager(app)

# Google Maps
API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
if not API_KEY:
    raise ValueError("Clave de API de Google Maps no encontrada")
gmaps = googlemaps.Client(key=API_KEY)

# Base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            status INTEGER NOT NULL
        )
    ''')
    initial_users = [
        ("username1", generate_password_hash("Hola.123"), 1),
        ("username2", generate_password_hash("Hola.123"), 1),
        ("username3", generate_password_hash("Hola.123"), 1),
        ("username4", generate_password_hash("Hola.123"), 1)
    ]
    for username, hashed_password, status in initial_users:
        cursor.execute(
            "INSERT OR IGNORE INTO users (username, password, status) VALUES (?, ?, ?)",
            (username, hashed_password, status)
        )
    conn.commit()
    conn.close()

def validate_username(username: str) -> bool:
    return bool(username and 3 <= len(username) <= 50 and re.match(r'^[a-zA-Z0-9_]+$', username))

# === RUTAS ===

@app.route('/')
def health_check():
    return jsonify({'message': 'Backend funcionando correctamente'})

# RUTA LOGIN - AHORA DEVUELVE "token" (lo que espera tu frontend)
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"message": "Faltan username o password"}), 400

    username = data['username'].strip()
    password = data['password']

    if not validate_username(username):
        return jsonify({"message": "Username inválido"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password, status FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({"message": "Usuario no encontrado"}), 404

    hashed_password, status = user

    if status != 1:
        return jsonify({"message": "Usuario inactivo"}), 403

    if check_password_hash(hashed_password, password):
        access_token = create_access_token(identity=username)
        return jsonify({
            "token": access_token,        # ← ¡¡ESTO ES LO QUE ESPERA TU FRONTEND!!
            "username": username,
            "message": "Login exitoso"
        }), 200
    else:
        return jsonify({"message": "Contraseña incorrecta"}), 401

# Ruta protegida para reportar inundación
@app.route('/report_flood', methods=['POST'])
@jwt_required()
def report_flood():
    current_user = get_jwt_identity()
    data = request.get_json()
    required_fields = ['ubicacion', 'fecha', 'temperatura', 'descripcion_clima', 'mensaje']
    
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Todos los campos son requeridos"}), 400

    ubicacion = data['ubicacion']
    fecha = data['fecha']
    temperatura = data['temperatura']
    descripcion_clima = data['descripcion_clima']
    mensaje = data['mensaje']

    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
    COMPANY_EMAIL = os.environ.get("COMPANY_EMAIL")

    if not all([SENDGRID_API_KEY, SENDER_EMAIL, COMPANY_EMAIL]):
        return jsonify({"message": "Faltan variables de entorno de SendGrid"}), 500

    body = f"""
Se ha recibido un reporte de inundación desde la app Weatheria.

Usuario: {current_user}
Ubicación: {ubicacion}
Fecha: {fecha}
Temperatura: {temperatura}
Descripción del clima: {descripcion_clima}
Mensaje: {mensaje}

Verificar inmediatamente la zona reportada.
    """

    email = Mail(
        from_email=SENDER_EMAIL,
        to_emails=COMPANY_EMAIL,
        subject="Reporte de Inundación - Weatheria App",
        plain_text_content=body
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(email)
        print("EMAIL ENVIADO - STATUS:", response.status_code)
        return jsonify({"message": "Reporte enviado exitosamente"}), 200
    except Exception as e:
        print("ERROR SENDGRID:", str(e))
        return jsonify({"message": f"Error al enviar correo: {str(e)}"}), 500

# Inicializar base de datos
init_db()

# === ARRANQUE DEL SERVIDOR (compatible con Render) ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
