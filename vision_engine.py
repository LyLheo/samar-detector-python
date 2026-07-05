# -*- coding: utf-8 -*-
# vision_engine.py - Core IA unificado y aislado

import multiprocessing
import queue
import cv2
import time
from datetime import datetime

class VisionEngine(multiprocessing.Process):
    """
    Motor de Visión por Computadora y Deep Learning (YOLO).
    Totalmente aislado del servidor web para evitar bloqueos por el GIL de Python.
    """
    
    def __init__(self, frame_queue, event_queue, command_queue, stop_event, camera_index=0):
        super().__init__()
        self.frame_queue = frame_queue
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.stop_event = stop_event
        self.camera_index = camera_index
        
        # IMPORTANTE: NO cargamos YOLO aquí en el __init__ (proceso principal).
        # Lo haremos en el método run() para que se cargue exclusivamente en el proceso hijo,
        # evitando problemas de Pickling/serialización de memoria CUDA en Windows.

    def run(self):
        """
        Punto de entrada del proceso aislado (Safeguard 1: Process Boundary).
        Todo lo que ocurra aquí vive en su propio espacio de memoria.
        """
        # Importaciones locales al proceso para optimizar la carga inicial
        from ultralytics import YOLO
        
        self._emit_log("⚙️ Cargando sistema neural YOLOv8s (Proceso aislado)...")
        # Load the model directly within the spawned process
        model = YOLO('yolov8s.pt')
        
        self._emit_log(f"📷 Iniciando hardware de video (Index: {self.camera_index})...")
        video = cv2.VideoCapture(self.camera_index)
        
        # Variables de estado del núcleo de visión
        avg_bg = None
        sistema_armado = False
        
        # Estados para la lógica anti-falsos positivos
        alerta_enviada = False
        alert_trigger_time = None
        last_person_time = None
        was_moving = False
        
        # Constantes de configuración operativa
        ALERT_DELAY = 1.0       # Segundos para confirmar amenaza
        ALERT_COOLDOWN = 10.0   # Segundos de enfriamiento tras alerta

        try:
            # Loop infinito hasta que el proceso padre envíe la señal de stop
            while not self.stop_event.is_set():
                loop_start = time.time()
                
                # 1. Chequear comandos del orquestador (Flask / Consola) de forma No-Bloqueante
                try:
                    cmd = self.command_queue.get_nowait()
                    if cmd.get("cmd") == "ARM":
                        sistema_armado = cmd.get("value")
                        estado = "ARMADO" if sistema_armado else "DESARMADO"
                        self._emit_log(f"🕹️ Motor de visión ajustado a: {estado}")
                        
                        # Reseteamos fondos y estados de alerta para evitar arrastre térmico o visual
                        avg_bg = None
                        alerta_enviada = False
                        alert_trigger_time = None
                except queue.Empty:
                    pass

                # 2. Captura de Frame
                ret, frame = video.read()
                if not ret:
                    time.sleep(0.01) # Evitar consumo 100% CPU si la cámara tartamudea
                    continue
                
                # Preprocesamiento económico
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if avg_bg is None:
                    avg_bg = gray.copy().astype("float")
                    continue

                movimiento = False
                person_detected = False

                if sistema_armado:
                    # --- LÓGICA DE DETECCIÓN HÍBRIDA ---
                    
                    # 1. Filtro Económico: Sustracción de Fondo Suave (Evita falsos por iluminación)
                    cv2.accumulateWeighted(gray, avg_bg, 0.01)
                    delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg_bg))
                    thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
                    # Morfología más agresiva para fusionar masas fragmentadas
                    thresh = cv2.dilate(thresh, None, iterations=4)
                    cnts, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    min_x, min_y = float('inf'), float('inf')
                    max_x, max_y = 0, 0

                    for c in cnts:
                        if cv2.contourArea(c) > 2000:
                            movimiento = True
                            (x, y, w, h) = cv2.boundingRect(c)
                            min_x = min(min_x, x)
                            min_y = min(min_y, y)
                            max_x = max(max_x, x + w)
                            max_y = max(max_y, y + h)

                    if movimiento:
                        # Bounding Box Unificada (Una sola caja verde envolvente)
                        cv2.rectangle(frame, (min_x, min_y), (max_x, max_y), (0, 255, 0), 2)

                    # Eventos para logs crudos (Útil para detector.py y Times.csv)
                    if movimiento and not was_moving:
                        self._emit_event("MOTION_START")
                    elif not movimiento and was_moving:
                        self._emit_event("MOTION_END")
                    was_moving = movimiento

                    # 2. Inferencia IA: Solo corremos YOLO si hubo alteración de píxeles
                    if movimiento:
                        # Calibración Estricta: conf=0.65, iou=0.45 para NMS severo, classes=[0] para personas
                        results = model(frame, conf=0.65, iou=0.45, classes=[0], verbose=False)
                        for r in results:
                            for box in r.boxes:
                                if int(box.cls[0]) == 0: # 0 = Persona
                                    person_detected = True
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                                    cv2.putText(frame, 'AMENAZA DETECTADA', (x1, y1 - 10), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    
                    # 3. Lógica Temporal de Alertas
                    if person_detected:
                        last_person_time = time.time()
                        
                        if not alerta_enviada:
                            if alert_trigger_time is None:
                                alert_trigger_time = time.time()
                                self._emit_log("⚠️ Posible amenaza. Analizando...")
                            
                            # Validar que no sea un reflejo de 1 frame
                            elif (time.time() - alert_trigger_time) >= ALERT_DELAY:
                                alerta_enviada = True
                                self._emit_log("🚨 AMENAZA CONFIRMADA. Notificando al core principal.")
                                
                                # Empaquetar y enviar evidencia ALTA CALIDAD al proceso padre
                                _, full_buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                                self._emit_event("INTRUSION", {"frame_bytes": full_buffer.tobytes()})
                                
                                alert_trigger_time = None
                    else:
                        # Si perdimos a la persona en la pre-alerta
                        if alert_trigger_time is not None:
                            if (time.time() - alert_trigger_time) > 2.0:
                                alert_trigger_time = None
                                self._emit_log("🔄 Falsa alarma. Objeto perdido.")
                        
                        # Lógica de Cooldown post-alerta
                        if alerta_enviada and last_person_time:
                            if (time.time() - last_person_time) >= ALERT_COOLDOWN:
                                alerta_enviada = False
                                last_person_time = None
                                self._emit_log("✅ Zona despejada. Sistema de alerta rearmado.")
                                
                    # Calcular FPS
                    fps = 1.0 / (time.time() - loop_start) if (time.time() - loop_start) > 0 else 30.0
                    
                    # UX: Indicador visual de estado (HUD Dinámico Táctico)
                    cv2.rectangle(frame, (0,0), (640, 40), (26, 23, 15), -1) # Deep Navy en BGR (15, 23, 26) pero BGR es al revés
                    
                    status_text = "SYS.ARMED | VIGILANCE: ACTIVE"
                    cv2.putText(frame, status_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 0), 2)
                    
                    # Threat Level y FPS
                    cv2.putText(frame, f"FPS: {fps:.1f}", (540, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
                    
                    if person_detected:
                        cv2.rectangle(frame, (0, 440), (640, 480), (0, 0, 150), -1)
                        cv2.putText(frame, "THREAT LEVEL: CRITICAL", (10, 465), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                else:
                    # En reposo
                    avg_bg = gray.copy().astype("float")
                    cv2.rectangle(frame, (0,0), (640, 40), (26, 23, 15), -1)
                    cv2.putText(frame, "SYS.STANDBY | VIGILANCE: PAUSED", (10, 25), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2) # Naranja en BGR

                    alert_trigger_time = None
                    alerta_enviada = False

                # [Safeguard 2: Real-Time Frame Queue Management]
                # Redimensionar para reducir carga en el bus IPC (memoria)
                frame_resized = cv2.resize(frame, (640, 480))
                _, buffer = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                frame_bytes = buffer.tobytes()
                
                # Patrón LIFO Estricto para asegurar latencia 0 en la web
                try:
                    # Si la cola está llena, descartamos activamente el frame más viejo (Stale Frame)
                    if self.frame_queue.full():
                        self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
                
                try:
                    # Insertamos el frame más fresco
                    self.frame_queue.put_nowait(frame_bytes)
                except queue.Full:
                    pass # Seguridad extra por si la cola se llenó concurrentemente

        except Exception as e:
            self._emit_log(f"❌ Error crítico en VisionEngine: {str(e)}")
            
        finally:
            # [Safeguard 3: Graceful Termination & Hardware Release]
            self._emit_log("🛑 Secuencia de apagado iniciada en VisionEngine...")
            if video and video.isOpened():
                video.release()
            cv2.destroyAllWindows()
            self._emit_log("✅ Hardware de cámara liberado exitosamente.")

    def _emit_log(self, message):
        """Helper para enviar logs limpios al proceso de orquestación."""
        self._emit_event("LOG", {"message": message})
        
    def _emit_event(self, event_type, data=None):
        """Helper para enviar eventos IPC estructurados."""
        payload = {
            "type": event_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if data:
            payload.update(data)
            
        try:
            self.event_queue.put_nowait(payload)
        except queue.Full:
            pass # Si el buffer de eventos colapsa, es preferible perder un log a frenar el motor
