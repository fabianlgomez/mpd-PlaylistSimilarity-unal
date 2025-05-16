#!/usr/bin/env python3
"""
update_musicbrainz_data_only.py

Modifica un archivo acousticbrainz_data.json existente para:
1. Completar datos de MusicBrainz (género, rating_value, rating_votes)
   para entradas donde estos campos sean nulos, utilizando los MBIDs existentes.
No modifica datos de AcousticBrainz.
Maneja rate limits de MusicBrainz y guarda el progreso.
"""

import os
import sys
import time
import json
# from math import ceil # No longer needed as AcousticBrainz part is removed
from dotenv import load_dotenv

import requests # Keep for fetch_mb_genre_and_rating in case of direct calls, though musicbrainzngs handles it.
import musicbrainzngs

# ------------------------------------------------------------
# 1) Credenciales y user-agent
# ------------------------------------------------------------
load_dotenv()
# Las credenciales de Spotify no son necesarias para este script.

# Configura el user-agent para musicbrainzngs.
# ¡IMPORTANTE! Sustituye "tu_app_nombre", "tu_version", "tu_email@dominio.com"
# con un nombre descriptivo para tu aplicación, su versión, y tu email real o un contacto.
# Esto es requerido por MusicBrainz.
try:
    musicbrainzngs.set_useragent(
        "MiAppDeEnriquecimientoMusical",
        "1.0",
        "micorreo@ejemplo.com"
    )
except TypeError as e:
    # Esto puede ocurrir si la librería no está instalada correctamente.
    sys.exit(f"Error crítico al configurar musicbrainzngs user-agent: {e}. Asegúrate de que la librería está instalada.")


# Habilitar el rate limiting incorporado de musicbrainzngs.
# Por defecto, esto limita las solicitudes a 1 por segundo,
# lo cual es la política recomendada por MusicBrainz para usuarios anónimos.
musicbrainzngs.set_rate_limit(True)


# ------------------------------------------------------------
# 2) Funciones para MusicBrainz
# ------------------------------------------------------------

def fetch_mb_genre_and_rating(mbid):
    """
    Obtiene el género (primer tag más popular) y el rating de MusicBrainz para un MBID dado.
    Retorna (genre, rating_value, rating_votes_count).
    Si un campo no se encuentra, su valor respectivo será None.
    """
    if not mbid:
        return None, None, None
    try:
        # Incluye 'tags' para el género y 'ratings' para la calificación.
        rec = musicbrainzngs.get_recording_by_id(
            mbid, includes=["tags", "ratings"]
        )["recording"]
        
        # Procesar tags para obtener el género
        genre = None
        raw_tags = rec.get("tag-list", [])
        tags_list = raw_tags if isinstance(raw_tags, list) else ([raw_tags] if raw_tags else [])
        
        # Filtrar tags que no son diccionarios o no tienen 'count' o 'name', y luego ordenar
        valid_tags = []
        for tag_item in tags_list:
            if isinstance(tag_item, dict) and "count" in tag_item and "name" in tag_item:
                try:
                    # Asegurarse de que 'count' sea convertible a int
                    tag_item["count"] = int(tag_item["count"])
                    valid_tags.append(tag_item)
                except ValueError:
                    print(f"  Advertencia: Tag con 'count' no numérico para MBID {mbid}: {tag_item.get('name')}")
                    pass # Ignorar tag con 'count' inválido

        if valid_tags:
            tags_sorted = sorted(
                valid_tags,
                key=lambda t: t["count"], # 'count' ya es int
                reverse=True
            )
            if tags_sorted:
                genre = tags_sorted[0].get("name")
        
        # Procesar rating
        rating_value = None
        rating_votes = None
        rating_data = rec.get("rating", {}) # 'rating' es la clave correcta en la respuesta de get_recording_by_id
        if isinstance(rating_data, dict): # Asegurar que rating_data sea un diccionario
            raw_rating_value = rating_data.get("value")
            if raw_rating_value is not None:
                try:
                    rating_value = float(raw_rating_value)
                except (ValueError, TypeError):
                    rating_value = None # Si no se puede convertir a float
            
            raw_rating_votes = rating_data.get("votes-count")
            if raw_rating_votes is not None:
                try:
                    rating_votes = int(raw_rating_votes)
                except (ValueError, TypeError):
                    rating_votes = None # Si no se puede convertir a int

        return genre, rating_value, rating_votes

    except musicbrainzngs.WebServiceError as e:
        # Manejar errores específicos de la API de MusicBrainz (ej. 404 Not Found, 503 Service Unavailable)
        error_message = str(e)
        print(f"  ⚠️ Error de MusicBrainz para MBID {mbid}: {error_message}")
        if "404" in error_message or "Not Found" in error_message:
             print(f"    MBID {mbid} no encontrado en MusicBrainz o es inválido.")
        elif "503" in error_message or "Service Unavailable" in error_message:
             print("    MusicBrainz no disponible temporalmente (503). La librería debería reintentar o esperar.")
             # musicbrainzngs con set_rate_limit(True) podría manejar reintentos para 503.
             # Si el error persiste, es un problema del servidor de MB.
             # Se podría añadir un sleep aquí si se quiere ser extra cauteloso tras un 503.
             # time.sleep(60) # Espera más larga para 503 persistentes
        return None, None, None # Retornar None para todos los campos en caso de error de API
    except Exception as e:
        # Capturar otros errores inesperados (ej. problemas de red, parsing de respuesta)
        print(f"  ❌ Error inesperado al obtener datos de MusicBrainz para MBID {mbid}: {e}")
        return None, None, None

# ------------------------------------------------------------
# 3) Lógica Principal de Modificación
# ------------------------------------------------------------
def main():
    input_data_file = "acousticbrainz_data.json"
    output_data_file = "acousticbrainz_data_mb_updated.json" # Nuevo nombre para reflejar el cambio

    if not os.path.exists(input_data_file):
        sys.exit(f"❌ Archivo de entrada '{input_data_file}' no encontrado.")

    try:
        with open(input_data_file, "r", encoding="utf-8") as fin:
            abz_data = json.load(fin)
    except json.JSONDecodeError as e:
        sys.exit(f"❌ Error al decodificar el JSON del archivo de entrada '{input_data_file}': {e}")
    except Exception as e:
        sys.exit(f"❌ Error al leer el archivo de entrada '{input_data_file}': {e}")
    
    total_entries = len(abz_data)
    if total_entries == 0:
        print("➡️  El archivo de entrada está vacío. No hay nada que procesar.")
        return
        
    print(f"➡️  Cargadas {total_entries} entradas desde '{input_data_file}'.")

    # --- Actualizar datos de MusicBrainz ---
    print("\n🔄  Actualizando datos de MusicBrainz (género y rating)...")
    print("    (Respetando el límite de 1 solicitud/segundo a MusicBrainz)")
    
    entries_checked_for_update = 0
    fields_updated_count = 0 # Contará cuántos campos individuales fueron rellenados

    for i, (track_id, track_data) in enumerate(abz_data.items()):
        mbid = track_data.get("mbid")

        if not mbid:
            # print(f"  [{i+1}/{total_entries}] Saltando {track_id}: sin MBID.")
            continue

        # Verificar si alguno de los campos objetivo es None (o no existe)
        needs_mb_update = False
        if track_data.get("genre_mb") is None:
            needs_mb_update = True
        if track_data.get("rating_value") is None:
            needs_mb_update = True
        if track_data.get("rating_votes") is None: # También verificar rating_votes por si rating_value fuera 0.0
            needs_mb_update = True
        
        if needs_mb_update:
            entries_checked_for_update += 1
            print(f"  Procesando MusicBrainz para MBID: {mbid} (Track ID: {track_id}, Entrada {i+1}/{total_entries})")
            
            # fetch_mb_genre_and_rating respetará el límite de tasa de musicbrainzngs
            genre, rating_val, rating_cnt = fetch_mb_genre_and_rating(mbid)
            
            # Actualizar campos solo si eran None y se obtuvo un nuevo valor no-None
            if track_data.get("genre_mb") is None and genre is not None:
                track_data["genre_mb"] = genre
                fields_updated_count += 1
                print(f"    -> Género MB actualizado a: {genre}")

            if track_data.get("rating_value") is None and rating_val is not None:
                track_data["rating_value"] = rating_val
                fields_updated_count += 1
                print(f"    -> Rating Value MB actualizado a: {rating_val}")

            if track_data.get("rating_votes") is None and rating_cnt is not None:
                track_data["rating_votes"] = rating_cnt
                fields_updated_count += 1
                print(f"    -> Rating Votes MB actualizado a: {rating_cnt}")
        
        if (i + 1) % 50 == 0 and entries_checked_for_update > 0 : # Log de progreso
             print(f"  ... {i+1}/{total_entries} entradas procesadas ...")


    print(f"\n✅ Proceso de MusicBrainz completado.")
    print(f"   {entries_checked_for_update} entradas necesitaron revisión de datos en MusicBrainz.")
    print(f"   Se rellenaron un total de {fields_updated_count} campos (genre_mb, rating_value, rating_votes).")

    # --- Guardar datos ---
    print(f"\n💾 Guardando datos actualizados en '{output_data_file}'...")
    try:
        with open(output_data_file, "w", encoding="utf-8") as fout:
            json.dump(abz_data, fout, indent=2, ensure_ascii=False)
        print(f"🎉 ¡Proceso completado! Archivo guardado en '{output_data_file}'.")
    except Exception as e:
        print(f"❌ Error al guardar el archivo de salida: {e}")
        # Considerar guardar un backup de emergencia si esto falla
        # emergency_backup_file = f"{output_data_file}.emergency_backup_{int(time.time())}.json"
        # try:
        #     with open(emergency_backup_file, "w", encoding="utf-8") as fbackup:
        #         json.dump(abz_data, fbackup, indent=2, ensure_ascii=False)
        #     print(f"🚨 Backup de emergencia guardado en '{emergency_backup_file}'")
        # except Exception as be:
        #     print(f"❌ Falló también el guardado del backup de emergencia: {be}")


if __name__ == "__main__":
    print("Iniciando script para completar datos de MusicBrainz...")
    script_start_time = time.time()
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Proceso interrumpido por el usuario.")
        # Los datos no se guardan si se interrumpe antes del paso de guardado.
        # Si se quisiera guardar al interrumpir, la lógica de guardado tendría que estar en un bloque finally
        # o capturar KeyboardInterrupt dentro de main y llamar a una función de guardado.
    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado durante la ejecución del script: {e}")
        import traceback
        print("\n--- Traceback ---")
        traceback.print_exc()
        print("--- Fin Traceback ---")
    finally:
        script_end_time = time.time()
        print(f"\n⏱️  Tiempo total de ejecución del script: {script_end_time - script_start_time:.2f} segundos.")