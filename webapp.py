# -*- coding: utf-8 -*-
# webapp.py - SAMAR v7.0 (VMS Command Center / SSE Architecture)

from flask import Flask, render_template, Response, jsonify, request
import os, sqlite3, secrets, time
from datetime import datetime
import threading
import multiprocessing
import queue
import json
from dotenv import load_dotenv 

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from vision_engine import VisionEngine

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# --- SecOps: Global Security Headers ---
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com;"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURAS_DIR = os.path.join(BASE_DIR, 'static', 'capturas')
DB_PATH = os.path.join(BASE_DIR, 'samar.db')
os.makedirs(CAPTURAS_DIR, exist_ok=True)

# --- 2. BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    tipo TEXT,
                    imagen_path TEXT
                )''')
    conn.commit()
    conn.close()

def registrar_evento_db(tipo, imagen_nombre=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        img_rel_path = f"capturas/{imagen_nombre}" if imagen_nombre else ""
        c.execute("INSERT INTO eventos (timestamp, tipo, imagen_path) VALUES (?, ?, ?)",
                  (timestamp, tipo, img_rel_path))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error DB: {e}")

init_db()

# --- 3. ESTADO GLOBAL E IPC ---
global_logs = []
SISTEMA_ARMADO = False
latest_frame = b''
sse_clients = [] # Lista de colas para Server-Sent Events

REMITENTE_EMAIL = os.getenv("GMAIL_USER")
REMITENTE_PASS = os.getenv("GMAIL_PASS")
DESTINATARIO_EMAIL = os.getenv("GMAIL_DESTINO")

frame_queue = None
event_queue = None
command_queue = None
stop_event = None

# --- 4. SSE Y CONSUMIDORES ---
def notify_sse_clients(data_dict):
    """Envía un payload JSON a todos los clientes web conectados vía SSE"""
    data_str = json.dumps(data_dict)
    for q in sse_clients:
        try:
            q.put_nowait(data_str)
        except queue.Full:
            pass

def agregar_log(mensaje):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {mensaje}"
    global_logs.insert(0, log_entry)
    if len(global_logs) > 50: global_logs.pop()
    notify_sse_clients({"type": "log", "message": log_entry})

def procesar_intrusion(imagen_bytes):
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evidencia_{timestamp_str}.jpg"
    filepath = os.path.join(CAPTURAS_DIR, filename)
    
    with open(filepath, 'wb') as f:
        f.write(imagen_bytes)
        
    registrar_evento_db("INTRUSION", filename)
    agregar_log("📸 Amenaza archivada localmente.")
    
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 ALERTA - SAMAR SOC {timestamp_str}"
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = DESTINATARIO_EMAIL
        msg.attach(MIMEText("SAMAR ha detectado una anomalía crítica.\nSe adjunta telemetría óptica."))
        msg.attach(MIMEImage(imagen_bytes, name=filename))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(REMITENTE_EMAIL, REMITENTE_PASS) 
            server.sendmail(REMITENTE_EMAIL, DESTINATARIO_EMAIL, msg.as_string())
        agregar_log("✅ Notificación SMTP despachada.")
    except Exception as e:
        agregar_log(f"❌ Fallo SMTP: {e}")

def get_db_metrics():
    """Calcula las detecciones del día y de la última hora"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Totales del día
        today_str = datetime.now().strftime("%Y-%m-%d") + "%"
        c.execute("SELECT COUNT(*) FROM eventos WHERE timestamp LIKE ?", (today_str,))
        day_total = c.fetchone()[0]
        
        # Última hora
        one_hour_ago = (time.time() - 3600)
        c.execute("SELECT COUNT(*) FROM eventos WHERE strftime('%s', timestamp) >= ?", (str(one_hour_ago),))
        hour_total = c.fetchone()[0]
        
        conn.close()
        return day_total, hour_total
    except Exception:
        return 0, 0

def ipc_event_consumer():
    """Hilo principal de eventos. Procesa IPC y emite Telemetría SSE"""
    last_metrics_time = time.time()
    
    while not stop_event.is_set():
        try:
            evento = event_queue.get(timeout=0.5)
            tipo = evento.get("type")
            
            if tipo == "LOG":
                agregar_log(evento["message"])
            elif tipo == "INTRUSION":
                notify_sse_clients({"type": "alert"})
                threading.Thread(target=procesar_intrusion, args=(evento["frame_bytes"],), daemon=True).start()
                
        except queue.Empty:
            # Heartbeat & Telemetry emitido cada segundo
            current_time = time.time()
            if current_time - last_metrics_time >= 1.0:
                last_metrics_time = current_time
                
                cpu_usage = psutil.cpu_percent() if HAS_PSUTIL else 45.2
                ram_usage = psutil.virtual_memory().percent if HAS_PSUTIL else 60.1
                day_total, hour_total = get_db_metrics()
                
                metrics_payload = {
                    "type": "telemetry",
                    "cpu": cpu_usage,
                    "ram": ram_usage,
                    "armed": SISTEMA_ARMADO,
                    "day_total": day_total,
                    "hour_total": hour_total
                }
                notify_sse_clients(metrics_payload)
        except Exception as e:
            print(f"Error IPC Consumer: {e}")

def ipc_frame_consumer():
    global latest_frame
    while not stop_event.is_set():
        try:
            latest_frame = frame_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error Frame Consumer: {e}")

def generar_frames_web():
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.04)

# --- 5. ENDPOINTS DE LA API ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generar_frames_web(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/stream')
def sse_stream():
    """Generador Server-Sent Events para telemetría en tiempo real"""
    def event_stream():
        q = queue.Queue(maxsize=10)
        sse_clients.append(q)
        try:
            # Enviar estado inicial
            initial_logs = [{"type": "log", "message": log} for log in reversed(global_logs)]
            for log in initial_logs:
                yield f"data: {json.dumps(log)}\n\n"
                
            while True:
                data = q.get()
                yield f"data: {data}\n\n"
        except GeneratorExit:
            sse_clients.remove(q)
    
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/toggle_arm', methods=['POST'])
def toggle_arm():
    global SISTEMA_ARMADO
    SISTEMA_ARMADO = not SISTEMA_ARMADO
    status = "ARMED" if SISTEMA_ARMADO else "STANDBY"
    agregar_log(f"🕹️ CMD: Override a estado {status}")
    
    if command_queue:
        command_queue.put({"cmd": "ARM", "value": SISTEMA_ARMADO})
        
    return jsonify({"success": True, "armed": SISTEMA_ARMADO})

@app.route('/api/gallery/more')
def get_gallery_more():
    """API REST para paginación de la Forensic Grid (Lazy Loading)"""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        c.execute("SELECT * FROM eventos WHERE imagen_path != '' ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = c.fetchall()
        conn.close()
        
        events = []
        for row in rows:
            events.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "image": row["imagen_path"]
            })
        return jsonify(events)
    except Exception as e:
        print(f"Error galería: {e}")
        return jsonify([])

# --- 6. ARRANQUE DEL SISTEMA ---
if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("🚀 Inicializando SAMAR SOC Architecture...")
        
        frame_queue = multiprocessing.Queue(maxsize=2)
        event_queue = multiprocessing.Queue()
        command_queue = multiprocessing.Queue()
        stop_event = multiprocessing.Event()

        motor_vision = VisionEngine(frame_queue, event_queue, command_queue, stop_event, camera_index=0)
        motor_vision.start()
        
        threading.Thread(target=ipc_event_consumer, daemon=True).start()
        threading.Thread(target=ipc_frame_consumer, daemon=True).start()

    try:
        flask_debug = os.getenv('FLASK_DEBUG', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
        app.run(debug=flask_debug, host='0.0.0.0', port=5000, use_reloader=False)
    finally:
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            print("🛑 Recibida señal de apagado. Cierre de conexiones y colas...")
            stop_event.set()
            motor_vision.join(timeout=5)
            if motor_vision.is_alive():
                motor_vision.terminate()
            print("✅ SOC Apagado exitosamente.")