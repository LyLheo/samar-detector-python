# -*- coding: utf-8 -*-
# webapp.py - SAMAR ULTIMATE v5.2 (Corregido: Estabilidad + Integridad de Galería)

from flask import Flask, render_template, Response, jsonify, request
import cv2, time, os, sqlite3
from datetime import datetime
import threading
from dotenv import load_dotenv 
from ultralytics import YOLO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
app = Flask(__name__)

# Configuración de Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURAS_DIR = os.path.join(BASE_DIR, 'static', 'capturas')
DB_PATH = os.path.join(BASE_DIR, 'samar.db')

# Asegurar que exista el directorio de capturas
os.makedirs(CAPTURAS_DIR, exist_ok=True)

# Cargar IA
print("⚙️ Cargando sistema neural YOLOv8s...")
model = YOLO('yolov8s.pt')

# --- 2. GESTIÓN DE BASE DE DATOS (SQLite) ---
def init_db():
    """Inicializa la DB si no existe"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tabla de Eventos
    c.execute('''CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    tipo TEXT,
                    imagen_path TEXT
                )''')
    conn.commit()
    conn.close()

def registrar_evento_db(tipo, imagen_nombre=""):
    """Inserta un registro en la BD de forma segura"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Guardamos la ruta relativa para el HTML
        img_rel_path = f"capturas/{imagen_nombre}" if imagen_nombre else ""
        c.execute("INSERT INTO eventos (timestamp, tipo, imagen_path) VALUES (?, ?, ?)",
                  (timestamp, tipo, img_rel_path))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error DB: {e}")

# Inicializamos la DB al arrancar
init_db()

# --- 3. VARIABLES GLOBALES Y ESTADO ---
video = cv2.VideoCapture(1)
global_logs = []

# Variables de Estado del Sistema
SISTEMA_ARMADO = False  # El sistema empieza desarmado
alerta_enviada_en_este_evento = False
alert_trigger_time = None
last_person_seen_time = None

# Constantes de Configuración
REMITENTE_EMAIL = os.getenv("GMAIL_USER")
REMITENTE_PASS = os.getenv("GMAIL_PASS")
DESTINATARIO_EMAIL = os.getenv("GMAIL_DESTINO")
ALERT_DELAY_SECONDS = 1.0
ALERT_COOLDOWN_SECONDS = 10.0

# --- 4. LÓGICA DE NEGOCIO ---

def agregar_log(mensaje):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {mensaje}"
    global_logs.insert(0, log_entry)
    if len(global_logs) > 20: global_logs.pop()

def enviar_alerta_completa(frame_evidencia):
    """Guarda foto localmente, registra en DB y envía correo"""
    global alerta_enviada_en_este_evento
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evidencia_{timestamp_str}.jpg"
    filepath = os.path.join(CAPTURAS_DIR, filename)
    
    agregar_log("📸 Guardando evidencia forense local...")
    
    # 1. Guardar Evidencia Local
    cv2.imwrite(filepath, frame_evidencia)
    
    # 2. Registrar en Base de Datos
    registrar_evento_db("INTRUSION", filename)
    
    # 3. Enviar Correo
    agregar_log("🚀 Iniciando protocolo de notificación SMTP...")
    try:
        _, buffer = cv2.imencode('.jpg', frame_evidencia)
        imagen_bytes = buffer.tobytes()
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 ALERTA CRÍTICA - Intrusión Detectada {timestamp_str}"
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = DESTINATARIO_EMAIL
        msg.attach(MIMEText("El sistema SAMAR ha detectado una amenaza confirmada.\n\nSe ha generado un registro forense en el servidor local."))
        msg.attach(MIMEImage(imagen_bytes, name=filename))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(REMITENTE_EMAIL, REMITENTE_PASS) 
            server.sendmail(REMITENTE_EMAIL, DESTINATARIO_EMAIL, msg.as_string())
        agregar_log("✅ Notificación enviada correctamente.")
    except Exception as e:
        agregar_log(f"❌ Fallo en envío de correo: {e}")

def generar_frames():
    """
    Lógica principal de visión por computador.
    CORREGIDA: Usa acumulador de peso para evitar que objetos estáticos desaparezcan.
    """
    global alerta_enviada_en_este_evento, alert_trigger_time, last_person_seen_time, SISTEMA_ARMADO
    
    # Variable estática para el fondo promedio (más estable que first_frame)
    avg_bg = None

    while True:
        success, frame = video.read()
        if not success: break
        
        # Preprocesamiento
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # Inicializar fondo si es necesario
        if avg_bg is None:
            avg_bg = gray.copy().astype("float")
            continue

        if SISTEMA_ARMADO:
            # --- LÓGICA DE DETECCIÓN MEJORADA ---
            
            # 1. Actualización SUAVE del fondo
            # El 0.01 significa que el fondo cambia MUY lento. 
            # Si te quedas quieto, NO te absorbe el fondo inmediatamente.
            cv2.accumulateWeighted(gray, avg_bg, 0.01)
            
            # Diferencia absoluta entre el fondo promedio y el frame actual
            delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg_bg))
            
            thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            cnts, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            movimiento = False
            for c in cnts:
                if cv2.contourArea(c) > 2000: # Filtro de ruido
                    movimiento = True
                    (x, y, w, h) = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 1) # Caja Verde

            # 2. Detección de IA (Si hay movimiento)
            person_detected = False
            if movimiento:
                results = model(frame, conf=0.5, verbose=False) # Confianza 50%
                for r in results:
                    for box in r.boxes:
                        if int(box.cls[0]) == 0: # Persona
                            person_detected = True
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3) # Caja Roja
                            cv2.putText(frame, 'AMENAZA DETECTADA', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)

            # 3. Lógica de Alerta (Resetear trigger solo si se pierde por completo)
            if person_detected:
                last_person_seen_time = time.time()
                
                if not alerta_enviada_en_este_evento:
                    # Si es la primera vez que lo vemos en este evento
                    if alert_trigger_time is None:
                        alert_trigger_time = time.time()
                        agregar_log("⚠️ Posible amenaza. Verificando...")
                    
                    # Chequear si pasó el segundo de seguridad
                    elif (time.time() - alert_trigger_time) >= ALERT_DELAY_SECONDS:
                        alerta_enviada_en_este_evento = True
                        agregar_log("🚨 AMENAZA CONFIRMADA. Ejecutando protocolos.")
                        threading.Thread(target=enviar_alerta_completa, args=(frame.copy(),), daemon=True).start()
                        alert_trigger_time = None
            else:
                # Si dejamos de ver a la persona...
                
                # Si estábamos "armando" la alerta pero la persona desapareció rápido (falso positivo)
                if alert_trigger_time is not None: 
                    # Pequeña tolerancia: No resetear inmediatamente si parpadea la detección
                    if (time.time() - alert_trigger_time) > 2.0: 
                        alert_trigger_time = None

                # Si YA enviamos alerta, esperamos el cooldown
                if alerta_enviada_en_este_evento and last_person_seen_time:
                    if (time.time() - last_person_seen_time) >= ALERT_COOLDOWN_SECONDS:
                        alerta_enviada_en_este_evento = False
                        last_person_seen_time = None
                        agregar_log("🔄 Zona despejada. Sistema rearmado.")
            
            # Estado visual
            cv2.rectangle(frame, (0,0), (640, 40), (0,0,0), -1)
            cv2.putText(frame, "SISTEMA ARMADO - VIGILANCIA ACTIVA", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        else:
            # SISTEMA DESARMADO
            # Reiniciamos el fondo para que cuando se arme no detecte cambios viejos
            avg_bg = gray.copy().astype("float")
            
            cv2.rectangle(frame, (0,0), (640, 40), (0,0,0), -1)
            cv2.putText(frame, "SISTEMA DESARMADO - STANDBY", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # Resetear variables de alerta
            alert_trigger_time = None
            alerta_enviada_en_este_evento = False
            
        # Codificar para web
        frame_resized = cv2.resize(frame, (640, 480))
        _, buffer = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- 5. RUTAS DE LA API (Endpoints) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generar_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def get_status():
    """Devuelve estado y logs para el JS"""
    return jsonify({
        "armed": SISTEMA_ARMADO,
        "logs": global_logs
    })

@app.route('/api/toggle_arm', methods=['POST'])
def toggle_arm():
    """Interruptor para Armar/Desarmar"""
    global SISTEMA_ARMADO
    SISTEMA_ARMADO = not SISTEMA_ARMADO
    status = "ARMADO" if SISTEMA_ARMADO else "DESARMADO"
    agregar_log(f"🕹️ Comando recibido: Sistema {status} manualmente.")
    return jsonify({"success": True, "armed": SISTEMA_ARMADO})

@app.route('/api/gallery')
def get_gallery():
    """Consulta la Base de Datos y devuelve SOLO las imágenes que existen físicamente"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        # Traemos un poco más por si hay archivos borrados
        c.execute("SELECT * FROM eventos WHERE imagen_path != '' ORDER BY id DESC LIMIT 20")
        rows = c.fetchall()
        conn.close()
        
        events = []
        for row in rows:
            # --- MEJORA DE SEGURIDAD ---
            # Verificamos si el archivo existe realmente en el disco
            full_path = os.path.join(BASE_DIR, 'static', row["imagen_path"])
            
            if os.path.exists(full_path):
                events.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "image": row["imagen_path"]
                })
                
                # Limitamos a 6 fotos para el diseño
                if len(events) >= 6:
                    break
            # ---------------------------
            
        return jsonify(events)
    except Exception as e:
        print(f"Error galería: {e}")
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)