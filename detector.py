# librerías necesarias
import cv2, time, pandas
from datetime import datetime
import threading
import os                     
from dotenv import load_dotenv 

# Cargar variables de entorno 
load_dotenv() # lee archivo .env y carga las variables

# Librerías para enviar correo electrónico
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# --- 1. Inicialización de Variables ---

first_frame = None
status_list = [None, None]
times = []
df = pandas.DataFrame(columns=["Start", "End"])

# --- 1.5 Configuración de Alerta por Correo (Desde .env) ---

# Leemos las variables seguras del archivo .env
REMITENTE_EMAIL = os.getenv("GMAIL_USER")
REMITENTE_PASS = os.getenv("GMAIL_PASS")
DESTINATARIO_EMAIL = os.getenv("GMAIL_DESTINO")

# Comprobación de seguridad
if not REMITENTE_EMAIL or not REMITENTE_PASS or not DESTINATARIO_EMAIL:
    print("ERROR: No se encontraron las variables de GMAIL en el archivo .env")
    print("Por favor, asegúrate de que el archivo .env exista y tenga:")
    print("GMAIL_USER='tu_correo'")
    print("GMAIL_PASS='tu_pass'")
    print("GMAIL_DESTINO='tu_destino'")
    exit() # Detiene el script si no hay contraseñas

# ------------------------------------------------------

# Variable para evitar enviar spam. Solo enviará una alerta por evento.
alerta_enviada_en_este_evento = False

def enviar_alerta_correo(frame_con_movimiento):
    """
    Toma un fotograma de CV2, lo codifica y lo envía por correo.
    ESTA FUNCIÓN SE EJECUTA EN UN HILO SEPARADO.
    """
    global alerta_enviada_en_este_evento 
    
    print(f"[{datetime.now()}] (Hilo): Iniciando envío de correo de alerta...")
    
    try:
        _, buffer = cv2.imencode('.jpg', frame_con_movimiento)
        imagen_bytes = buffer.tobytes()

        msg = MIMEMultipart()
        msg['Subject'] = "¡ALERTA DE SEGURIDAD! - Movimiento Detectado (SAMAR)"
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = DESTINATARIO_EMAIL

        texto = MIMEText("Se ha detectado movimiento en el área monitoreada (SAMAR).\n\nSe adjunta captura de evidencia.")
        msg.attach(texto)

        imagen_adjunta = MIMEImage(imagen_bytes, name="captura_movimiento.jpg")
        msg.attach(imagen_adjunta)

        print(f"[{datetime.now()}] (Hilo): Conectando al servidor SMTP de Gmail...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(REMITENTE_EMAIL, REMITENTE_PASS) # <--- Usa las variables seguras
            server.sendmail(REMITENTE_EMAIL, DESTINATARIO_EMAIL, msg.as_string())
        
        print(f"[{datetime.now()}] (Hilo): ¡Alerta de correo enviada exitosamente a {DESTINATARIO_EMAIL}!")
        alerta_enviada_en_este_evento = True 

    except Exception as e:
        print(f"ERROR (Hilo): No se pudo enviar el correo: {e}")
        alerta_enviada_en_este_evento = False

# Se inicia la captura de video
video = cv2.VideoCapture(0)

print("Iniciando sistema de detección... Presiona 'q' para salir.")
print("--- Esperando a que la cámara se estabilice...")
time.sleep(2) 
print("--- Sistema activo.")

# --- Bucle Principal de Procesamiento ---
while True:
    check, frame = video.read()
    if not check:
        print("Error: No se pudo leer el fotograma.")
        break
        
    status = 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if first_frame is None:
        first_frame = gray
        continue

    # --- Detección de Diferencias y Contornos ---
    delta_frame = cv2.absdiff(first_frame, gray)
    thresh_frame = cv2.threshold(delta_frame, 30, 255, cv2.THRESH_BINARY)[1]
    thresh_frame = cv2.dilate(thresh_frame, None, iterations=2)
    (cnts, _) = cv2.findContours(thresh_frame.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in cnts:
        area_detectada = cv2.contourArea(contour)

        if area_detectada < 2000:
            # print(f"DEBUG: Contorno detectado (área={area_detectada}) ... ignorado por ser pequeño.")
            continue 

        print(f"DEBUG: ¡¡OBJETO GRANDE DETECTADO!! (área={area_detectada})")
        status = 1
        (x, y, w, h) = cv2.boundingRect(contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)


    # --- Lógica de Registro y ALERTA ---
    status_list.append(status)
    status_list = status_list[-2:]

    if status_list[-1] == 1 and status_list[-2] == 0:
        times.append(datetime.now())
        
        if not alerta_enviada_en_este_evento:
            print(f"[{datetime.now()}] (Principal): ¡Movimiento detectado! Disparando alerta en 2do plano...")

            hilo_alerta = threading.Thread(target=enviar_alerta_correo, args=(frame.copy(),), daemon=True)
            hilo_alerta.start()
            
    if status_list[-1] == 0 and status_list[-2] == 1:
        times.append(datetime.now())
        
        print(f"[{datetime.now()}] (Principal): El movimiento ha terminado. Sistema en espera.")
        alerta_enviada_en_este_evento = False
        
    # --- Visualización y Salida ---
    cv2.imshow("Sistema SAMAR - En Vivo", frame)
    
    key = cv2.waitKey(1)
    if key == ord('q'):
        if status == 1:
            times.append(datetime.now())
        break

print("Cerrando sistema...")

# --- Guardado de Datos y Limpieza ---
for i in range(0, len(times), 2):
    if (i+1) < len(times):
        df.loc[len(df)] = [times[i], times[i+1]]

if not df.empty:
    df.to_csv("Times.csv", index=False)
    print(f"Registros de movimiento guardados en 'Times.csv'")
else:
    print("No se detectó ningún evento de movimiento para guardar.")

video.release()
cv2.destroyAllWindows()