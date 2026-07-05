# SAMAR (Sistema de Alerta y Monitoreo Activo con Reconocimiento)
## AI Agent Context & Vibe Coding Guidelines

### 1. [PROJECT IDENTITY]
**Mission:** SAMAR is a production-ready, AI-Powered Edge Computing Security System designed to eliminate "alarm fatigue" in high-traffic enterprise environments.
**Core Philosophy:** 
- Zero cloud dependency (100% local processing and sandboxing).
- Absolute data privacy.
- High performance on edge hardware (minimizing CPU/Memory footprint).
**Current Status:** Capstone Engineering Project (Grade: 96/100). Successfully deployed in a commercial environment with a 0% false-positive rate.

### 2. [TECH STACK]
- **AI & Computer Vision:** Python 3.x, OpenCV (lightweight background subtraction), YOLOv8s (Ultralytics) for semantic classification.
- **Backend & Web:** Flask, Flask-Routing.
- **Database:** Serverless SQLite (local forensic logs).
- **Concurrency:** Native Python `threading` (Daemon threads).
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (Responsive Dashboard).

### 3. [CORE ARCHITECTURE & FLOW]
- **Hybrid Detection Motor:** The system MUST NOT run YOLOv8 on every frame. It uses OpenCV to detect pixel variations (motion). Only when physical movement is detected, YOLOv8 is triggered to classify human morphology. This saves ~80% CPU usage.
- **Asynchronous Alerts:** When an intrusion is confirmed, the SMTP email alert (with photographic evidence) is dispatched via a background Daemon thread. This is critical to prevent the main video feed from dropping frames or lagging.
- **Local Dashboard:** The Flask app serves as an administrative portal to view live feeds, arm/disarm the system, and audit forensic logs via SQLite.

### 4. [VIBE & CODING STANDARDS]
- **Role:** You are acting as a Principal Staff Engineer assisting the Lead Orchestrator.
- **Code Quality:** Write clean, modular, and PEP-8 compliant Python code. Use type hints (`def process_frame(frame: np.ndarray) -> bool:`).
- **Performance First:** Any new feature must be evaluated for its impact on video latency (FPS).
- **Language:** Code logic, variables, and comments should preferably be in English. However, the User Interface (HTML/Frontend) MUST remain in Spanish for the end-user.

### 5. [STRICT GUARDRAILS (DO NOT VIOLATE)]
1. **NO Cloud Services:** Do not suggest AWS, Azure, Firebase, or external APIs for core functionality. SAMAR is an Edge Computing system.
2. **NO Hardcoded Secrets:** Never hardcode credentials. Always read from environment variables (e.g., `os.getenv('GMAIL_PASS')`). 
3. **NO Destructive DB Operations:** Never drop SQLite tables or alter the database schema without providing a rollback/migration strategy and asking for explicit permission.
4. **NO Blocking the Main Thread:** Any network request, heavy I/O operation, or long-running task must be handled asynchronously or via threads to protect the video stream's FPS.
5. **Security Baseline:** Flask must always run with `debug=False` in production. 

### 6. [CURRENT FOCUS AREAS]
- Enhancing UI/UX real-time capabilities (e.g., WebSockets for audit logs).
- Implementing automated local data retention (Log rotation).
- System containerization (Docker) for seamless deployments.