# SAMAR v3.0 (Sistema de Alerta y Monitoreo Activo con Reconocimiento)

Prototipo de sistema de vigilancia inteligente desarrollado como proyecto final para la carrera de Ingeniería de Sistemas (UNP).

Este sistema utiliza Python y una red neuronal **YOLOv8** para detectar movimiento, identificar intrusos (personas) en tiempo real, y enviar alertas inmediatas por correo electrónico con evidencia visual.

## 🚀 Características Principales

* **Detección de IA (YOLOv8s):** Utiliza un modelo de IA "small" (`yolov8s.pt`) para una detección de personas precisa, eliminando falsos positivos de sombras, mascotas u objetos.
* **Filtro de 2 Etapas:** Un filtro de movimiento (OpenCV) de bajo costo computacional activa el análisis de IA, optimizando el rendimiento.
* **Alertas No Bloqueantes:** El sistema de alertas por correo se ejecuta en un hilo (`threading`) separado, garantizando que el video en vivo nunca se congele ("lag").
* **Lógica de Alerta Avanzada:**
    * **Retraso de 1s:** Espera 1 segundo después de la detección inicial para tomar una foto clara del intruso (evitando fotos de "hombros").
    * **Cooldown de 10s:** El sistema se "resetea" 10 segundos después de que una persona abandona la escena, permitiendo múltiples alertas para eventos separados.
* **Registro y Visualización:** Guarda un log de todos los eventos en `Times.csv` y incluye un script (`visualizador.py`) para generar un reporte gráfico en HTML.
* **Configuración Segura:** Todas las credenciales se manejan de forma segura fuera del código usando un archivo `.env`.

---

## 🛠️ Instalación y Configuración

### 1. Prerrequisitos

* Python 3.8+
* Git

### 2. Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/LyLheo/samar-detector-python.git](https://github.com/LyLheo/samar-detector-python.git)
    cd samar-detector-python
    ```

2.  **Crear y activar un entorno virtual:**
    ```bash
    # En Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Instalar las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Configuración del Correo

1.  Crea un archivo llamado `.env` en la raíz del proyecto.
2.  Añade tus credenciales de Gmail. (**Importante:** Debes usar una "Contraseña de Aplicación" de 16 dígitos de Google, no tu contraseña normal).

    ```ini
    # Archivo .env
    GMAIL_USER="tu-correo@gmail.com"
    GMAIL_PASS="tu-contraseña-de-app-de-16-digitos"
    GMAIL_DESTINO="correo-que-recibe-la-alerta@ejemplo.com"
    ```

---

## 🏃‍♂️ Modo de Uso

### 1. Iniciar el Detector

Asegúrate de tener tu cámara web conectada y tu entorno virtual (`venv`) activado.

```bash
python detector.py

