# -*- coding: utf-8 -*-
# detector.py (SAMAR v3.0 - Detección de Personas con IA)

# Importación de librerías principales
import cv2, time, pandas
from datetime import datetime
import threading
import os 
from dotenv import load_dotenv 
from ultralytics import YOLO

# Cargar variables de entorno (.env)
load_dotenv() 

# 1. Variables Globales
first_frame = None
status_list = [None, None]
times = []
df = pandas.DataFrame(columns=["Start", "End"])

# Librerías para la alerta por correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# 2. Cargar el modelo de IA (YOLOv8)
print("Cargando modelo de IA (YOLOv8s)...")
# 's' es el modelo "small", buen balance de precisión/velocidad.
model = YOLO('yolov8s.pt') 
print("Modelo YOLO cargado. Sistema listo.")

# 3. Configuración de Alerta por Correo
REMITENTE_EMAIL = os.getenv("GMAIL_USER")
REMITENTE_PASS = os.getenv("GMAIL_PASS")
DESTINATARIO_EMAIL = os.getenv("GMAIL_DESTINO")

# Verificación de variables de entorno
if not REMITENTE_EMAIL or not REMITENTE_PASS or not DESTINATARIO_EMAIL:
    print("ERROR: No se encontraron las variables de GMAIL en el archivo .env")
    exit() 

# 4. Variables de control para la lógica de alertas
alerta_enviada_en_este_evento = False
alert_trigger_time = None          # Hora en que se "arma" el sistema para la foto
last_person_seen_time = None       # Hora de la última vez que se vio a una persona
ALERT_DELAY_SECONDS = 1.0          # Esperar 1s antes de tomar la foto (evita "hombros")
ALERT_COOLDOWN_SECONDS = 10.0      # Esperar 10s para poder enviar una nueva alerta

def enviar_alerta_correo(frame_con_movimiento):
    """
    Toma un fotograma, lo codifica y lo envía por correo en un hilo separado.
    """
    
    print(f"[{datetime.now()}] (Hilo): Iniciando envío de correo de ALERTA DE PERSONA...")
    
    try:
        _, buffer = cv2.imencode('.jpg', frame_con_movimiento)
        imagen_bytes = buffer.tobytes()

        msg = MIMEMultipart()
        msg['Subject'] = "¡ALERTA DE INTRUSIÓN! - Persona Detectada (SAMAR)"
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = DESTINATARIO_EMAIL
        
        texto = MIMEText("¡Se ha detectado una PERSONA en el área monitoreada (SAMAR)!\n\nSe adjunta captura de evidencia.")
        msg.attach(texto)
        
        imagen_adjunta = MIMEImage(imagen_bytes, name="captura_persona.jpg")
        msg.attach(imagen_adjunta)

        print(f"[{datetime.now()}] (Hilo): Conectando al servidor SMTP de Gmail...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(REMITENTE_EMAIL, REMITENTE_PASS) 
            server.sendmail(REMITENTE_EMAIL, DESTINATARIO_EMAIL, msg.as_string())
        
        print(f"[{datetime.now()}] (Hilo): ¡Alerta de correo enviada exitosamente a {DESTINATARIO_EMAIL}!")

    except Exception as e:
        print(f"ERROR (Hilo): No se pudo enviar el correo: {e}")
        # Si falla, reseteamos el flag para un reintento
        global alerta_enviada_en_este_evento
        alerta_enviada_en_este_evento = False


# 5. Inicialización de la Cámara
video = cv2.VideoCapture(0)

print("Iniciando sistema de detección... Presiona 'q' para salir.")
print("--- Esperando a que la cámara se estabilice...")
time.sleep(2) 
print("--- Sistema activo.")

# 6. Bucle Principal de Procesamiento
while True:
    check, frame = video.read()
    if not check:
        print("Error: No se pudo leer el fotograma.")
        break
        
    status = 0
    person_detected = False 
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if first_frame is None:
        first_frame = gray
        continue

    # ETAPA 1: Detección de Movimiento (Filtro rápido)
    delta_frame = cv2.absdiff(first_frame, gray)
    thresh_frame = cv2.threshold(delta_frame, 30, 255, cv2.THRESH_BINARY)[1]
    thresh_frame = cv2.dilate(thresh_frame, None, iterations=2)
    (cnts, _) = cv2.findContours(thresh_frame.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in cnts:
        if cv2.contourArea(contour) < 2000: # Ignorar ruido pequeño
            continue 
        status = 1 
        (x, y, w, h) = cv2.boundingRect(contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2) # Caja verde: Movimiento

    # ETAPA 2: Detección de Personas (Filtro IA)
    if status == 1:
        # Si hay movimiento, correr la IA (YOLO)
        results = model(frame, conf=0.5, verbose=False) 
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls = int(box.cls[0])
                if cls == 0: # Clase 0 es "persona" en el modelo YOLO
                    person_detected = True # Flag positivo
                    x1, y1, x2, y2 = box.xyxy[0]
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3) # Caja roja: Persona
                    conf = float(box.conf[0])
                    cv2.putText(frame, f'Persona {conf:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # ETAPA 3: Lógica de Alerta y Estado
        
        # 3.1. Lógica de Alerta (Ajustes 1 y 2)
        if person_detected:
            # Actualizar la última vez que vimos a alguien
            last_person_seen_time = time.time()
            
            # Si no hemos enviado una alerta para este evento...
            if not alerta_enviada_en_este_evento:
                # Si el sistema no estaba "armado", lo armamos.
                if alert_trigger_time is None:
                    print(f"[{datetime.now()}] (Principal): Persona detectada. Armado y esperando {ALERT_DELAY_SECONDS}s para la foto...")
                    alert_trigger_time = time.time()
                
                # Si ya estaba armado, chequear si pasó el delay de 1.0s
                elif (time.time() - alert_trigger_time) >= ALERT_DELAY_SECONDS:
                    print(f"[{datetime.now()}] (Principal): ¡¡¡PERSONA CONFIRMADA!!! Disparando alerta...")
                    
                    # Marcar alerta como enviada INMEDIATAMENTE
                    alerta_enviada_en_este_evento = True 
                    
                    # Registrar 'Start' time si es el inicio del evento
                    if status_list[-1] == 0: 
                        times.append(datetime.now())
                        
                    # Lanzar el hilo de correo
                    hilo_alerta = threading.Thread(target=enviar_alerta_correo, args=(frame.copy(),), daemon=True)
                    hilo_alerta.start()
                    alert_trigger_time = None # Resetear gatillo
        
        # Si NO hay persona detectada en este frame...
        else:
            # Si estábamos "armados" (persona se vio < 1s) pero se fue, desarmar.
            if alert_trigger_time is not None:
                print(f"[{datetime.now()}] (Principal): Persona perdida (pre-alerta). Desarmando.")
                alert_trigger_time = None
                
            # Lógica de Cooldown: Si ya enviamos una alerta y no vemos a nadie...
            if alerta_enviada_en_este_evento and last_person_seen_time is not None:
                # Chequear si pasaron los 10s de enfriamiento
                if (time.time() - last_person_seen_time) >= ALERT_COOLDOWN_SECONDS:
                    print(f"[{datetime.now()}] (Principal): Cooldown finalizado. El sistema está listo para una nueva alerta.")
                    alerta_enviada_en_este_evento = False
                    last_person_seen_time = None
                    
    # 3.2. Lógica de Estado (para CSV y reseteo)
    status_list.append(status)
    status_list = status_list[-2:]
    
    # Si el movimiento INICIA (0->1) y NO es persona
    if status_list[-1] == 1 and status_list[-2] == 0 and not person_detected:
         times.append(datetime.now())
         print(f"[{datetime.now()}] (Principal): Movimiento detectado (no-persona), registrando.")
            
    # Si el movimiento TERMINA (1->0)
    if status_list[-1] == 0 and status_list[-2] == 1:
        times.append(datetime.now())
        print(f"[{datetime.now()}] (Principal): El movimiento ha terminado. Sistema en espera.")
        
        # Reseteo general de todos los flags al fin del evento
        alerta_enviada_en_este_evento = False
        alert_trigger_time = None
        last_person_seen_time = None
        
    # 7. Visualización en Pantalla
    
    estado_texto = "ALERTA: PERSONA DETECTADA" if person_detected else "Movimiento Detectado" if status == 1 else "Sistema en Espera"
    color_texto = (0, 0, 255) if person_detected else (0, 255, 0) if status == 1 else (255, 255, 255)
    
    # Texto especial si el sistema está "armado"
    if alert_trigger_time is not None:
        estado_texto = "ARMADO... (Confirmando persona)"
        color_texto = (0, 255, 255) # Amarillo

    # Dibujar textos en el frame
    cv2.putText(frame, f"Estado: {estado_texto}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_texto, 2)
    cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    cv2.imshow("Sistema SAMAR (v3.0 IA) - En Vivo", frame)
    
    # Salir con la tecla 'q'
    key = cv2.waitKey(1)
    if key == ord('q'):
        if status == 1:
            times.append(datetime.now())
        break

# 8. Limpieza y Guardado de CSV
print("Cerrando sistema...")

# Procesar la lista de tiempos para el CSV
for i in range(0, len(times), 2):
    if (i+1) < len(times):
        df.loc[len(df)] = [times[i], times[i+1]]

# Guardar el CSV si no está vacío
if not df.empty:
    df.to_csv("Times.csv", index=False)
    print(f"Registros de movimiento guardados en 'Times.csv'")
else:
    print("No se detectó ningún evento de movimiento para guardar.")

video.release()
cv2.destroyAllWindows()