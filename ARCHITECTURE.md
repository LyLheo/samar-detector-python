# SAMAR: System Architecture & Technical Overview

## 1. System Definition
SAMAR (Sistema de Alerta y Monitoreo Activo con Reconocimiento) is a production-ready, zero-cloud Edge Computing security solution. Designed to eliminate "alarm fatigue" in high-traffic enterprise environments, SAMAR operates entirely on-premise, guaranteeing absolute data privacy and ultra-low latency without reliance on external cloud APIs. It serves as an intelligent, autonomous VMS (Video Management System) capable of real-time threat detection, node telemetry, and forensic archiving.

## 2. Architecture Breakdown
The core engineering achievement of SAMAR is its high-concurrency **Multi-Process Architecture**, explicitly designed to bypass the Python Global Interpreter Lock (GIL).

Pivoting from a monolithic, single-threaded paradigm, the system employs a robust **Producer-Consumer pattern** utilizing Inter-Process Communication (IPC) Queues:
- **VisionEngine (Producer)**: An isolated, dedicated process that handles all hardware-accelerated computer vision tasks, frame matrix processing, and AI inference. It pushes encoded frames and distinct event types to shared memory queues.
- **Flask Web Core (Consumer)**: A separate process running lightweight background daemon threads that consume the IPC queues. It serves the web interface, broadcasts real-time data via Server-Sent Events (SSE), and handles I/O tasks like SQLite writes and asynchronous SMTP dispatching.

This architectural schism ensures that heavy neural network calculations never block or degrade the performance of the web server or I/O operations, guaranteeing real-time FPS fluidity.

## 3. Key Technological Pillars
SAMAR is built upon a highly optimized, modern technology stack:
- **YOLOv8s & CUDA**: State-of-the-art semantic classification for human morphology, hardware-accelerated via NVIDIA CUDA for rapid edge inference.
- **OpenCV**: Powers the hybrid detection motor (background subtraction). It ensures the heavy neural network is only triggered during physical pixel alteration (motion), drastically reducing baseline CPU/GPU cycles.
- **Flask & Python Multiprocessing**: Orchestrates the backend REST APIs, web serving, and the rigorous multi-process boundaries.
- **Server-Sent Events (SSE)**: Replaces traditional HTTP polling with a persistent, unidirectional TCP tunnel for zero-latency telemetry and system log broadcasting.
- **SQLite3**: A serverless, lightweight SQL database for fast, local forensic data archiving.
- **Native CSS3 Rendering**: Pure CSS conic-gradients (`conic-gradient`) replace heavy JavaScript charting libraries, ensuring 60 FPS hardware-accelerated UI rendering with zero DOM-recalculation flicker.

## 4. Enterprise Capabilities (VMS-Grade Features)
- **Real-Time Telemetry**: Live node monitoring (CPU load, detection ratios, and hourly threat metrics) is streamed directly to the SOC dashboard via SSE.
- **Hardware-Accelerated Native HUD**: Dynamic tactical overlays (Threat Level, FPS, System Status) are rendered natively onto the pixel matrix via OpenCV *before* network transmission, eliminating browser-side flickering and guaranteeing frame-perfect synchronization.
- **Automated Forensic Data Management**: Autonomous background routines handle high-quality JPEG evidence extraction, asynchronous SMTP email dispatching, and SQLite logging.
- **Tactical Command Center UI**: A sophisticated Enterprise Light dashboard featuring a Lazy-Loaded Forensic DataGrid, a local System Audit Console, and native CSS radial charts for an intuitive, professional operator experience.

## 5. Technical Standards
SAMAR strictly adheres to enterprise security and engineering standards:
- **Security-First Configuration**: Flask runs strictly with `debug=False` in production to prevent arbitrary code execution vulnerabilities. All sensitive credentials (SMTP passwords, user emails, secret keys) are securely abstracted via environment variables (`.env`).
- **Non-Blocking I/O**: Heavy operations, such as network requests for email attachments, are isolated into daemon threads to prevent execution bottlenecks.
- **Memory Safety & IPC Integrity**: Strict process instantiations behind `if __name__ == '__main__':` boundary guards prevent recursive process spawning in Windows environments, ensuring a stable, leak-free shared memory pool.
