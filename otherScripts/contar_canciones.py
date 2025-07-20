import json
import time

# Nombre del archivo JSON
file_path = 'acousticbrainz_data_updated_clean.json'

print(f"Iniciando el conteo de canciones en '{file_path}'...")
print("Este proceso puede tardar un poco si el archivo es muy grande.")

# Iniciar cronómetro
start_time = time.time()

try:
    # Abrir el archivo en modo lectura ('r')
    # 'with' se asegura de que el archivo se cierre automáticamente
    with open(file_path, 'r', encoding='utf-8') as f:
        # Cargar todo el contenido del archivo JSON en una variable de Python (un diccionario)
        data = json.load(f)
        
        # El número de canciones es simplemente el número de claves en el diccionario principal
        song_count = len(data)
        
        # Detener cronómetro
        end_time = time.time()
        
        # Calcular duración
        duration = end_time - start_time
        
        print("\n--- ¡Conteo Finalizado! ---")
        print(f"Número total de canciones encontradas: {song_count}")
        print(f"El proceso tomó: {duration:.2f} segundos.")

except FileNotFoundError:
    print(f"Error: El archivo '{file_path}' no fue encontrado.")
    print("Por favor, asegúrate de que el script esté en la misma carpeta que el archivo JSON o proporciona la ruta correcta.")
except json.JSONDecodeError:
    print(f"Error: El archivo '{file_path}' no es un JSON válido o está corrupto.")
except MemoryError:
    print("Error: ¡El archivo es demasiado grande para cargarlo en la memoria RAM!")
    print("Por favor, intenta usar la 'Versión 2: Optimizada' del script.")
except Exception as e:
    print(f"Ocurrió un error inesperado: {e}")