# Lee el archivo Times.csv y genera una gráfica
# interactiva de los eventos de movimiento.

import pandas as pd
from bokeh.plotting import figure, show, output_file
from bokeh.models import HoverTool, ColumnDataSource

# --- Cargar y Preparar los Datos ---

try:
    # Cargar el CSV
    df = pd.read_csv("Times.csv")
    
    # Convertir las columnas de texto a objetos de fecha y hora (datetime)
    # Esto es esencial para que Bokeh entienda el eje X
    df["Start"] = pd.to_datetime(df["Start"])
    df["End"] = pd.to_datetime(df["End"])
    
    # Calcular la duración en segundos (opcional, pero útil)
    df["Duration_sec"] = (df["End"] - df["Start"]).dt.total_seconds()
    
    # Crear una columna con un string bonito para el HoverTool
    df["Start_str"] = df["Start"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["End_str"] = df["End"].dt.strftime("%Y-%m-%d %H:%M:%S")

    print(f"Archivo 'Times.csv' cargado exitosamente.")
    print(f"Se encontraron {len(df)} eventos de movimiento.")
    print("\nResumen de eventos:")
    print(df[['Start_str', 'End_str', 'Duration_sec']])
    
except FileNotFoundError:
    print("Error: No se encontró el archivo 'Times.csv'.")
    print("Asegúrate de ejecutar primero 'detector.py' para generar datos.")
    exit()
except pd.errors.EmptyDataError:
    print("Error: El archivo 'Times.csv' está vacío.")
    print("No hay eventos de movimiento para graficar.")
    exit()
except Exception as e:
    print(f"Ocurrió un error inesperado al leer el archivo: {e}")
    exit()


# --- Configurar la Gráfica (Bokeh) ---

# Convertir nuestro DataFrame de pandas a un ColumnDataSource
source = ColumnDataSource(df)

# Configurar las "Tooltips" 
hover = HoverTool(tooltips=[
    ("Evento", "#$index"),
    ("Inicio", "@Start_str"),
    ("Fin", "@End_str"),
    ("Duración", "@Duration_sec segundos")
])

# Crear la figura principal
# x_axis_type="datetime" le dice a Bokeh que el eje X es tiempo
p = figure(
    height=300,
    width=800,
    title="Cronología de Eventos de Movimiento (SAMAR)",
    x_axis_label="Fecha y Hora",
    y_axis_label="Eventos",
    x_axis_type="datetime",
    tools=[hover, "pan,wheel_zoom,box_zoom,reset,save"] # Añadimos herramientas de navegación
)

# --- Dibujar los Eventos ---

# uso de 'quad' (cuadrilátero/rectángulo) para dibujar las barras de eventos.
# 'top' y 'bottom' definen la altura de la barra.
# 'left' y 'right' definen el inicio (Start) y fin (End) en el eje de tiempo.
p.quad(
    left="Start",
    right="End",
    bottom=0,
    top=1,
    color="#009933", # Un color verde
    source=source,
    legend_label="Periodo de Movimiento"
)

# Ocultar los números del eje Y (0 y 1) porque no significan nada
p.yaxis.minor_tick_line_color = None
p.yaxis.major_tick_line_color = None
p.yaxis.major_label_text_font_size = '0pt' # para ocultar etiquetas

# Configurar el archivo de salida
output_file(
    "visualizacion_eventos.html",
    title="Reporte de Movimiento SAMAR"
)

# --- Mostrar la Gráfica ---
print("\nGenerando gráfica 'visualizacion_eventos.html'...")
show(p) # Esto guardará el archivo y lo abrirá en el navegador
print("¡Gráfica generada! Abriendo en el navegador...")