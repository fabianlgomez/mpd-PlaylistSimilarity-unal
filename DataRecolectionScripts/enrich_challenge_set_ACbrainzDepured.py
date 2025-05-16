#!/usr/bin/env python3
"""
update_acousticbrainz_data.py

Lee un archivo acousticbrainz_data.json existente,
luego consulta MusicBrainz y AcousticBrainz para actualizarlo:
  - MusicBrainz: completa genre_mb, rating_value, rating_votes si son nulos.
  - AcousticBrainz:
    - Actualiza los campos de low-level (bpm, energy, danceability_ll, loudness).
    - Reemplaza los datos de high-level con el objeto completo devuelto por AcousticBrainz.
      Los campos antiguos derivados de high-level son eliminados del nivel superior.
Utiliza MBIDs existentes en acousticbrainz_data.json.
Maneja rate limits y guarda el JSON actualizado.
"""

import os
import sys
import time
import json
from math import ceil # Para dividir en batches/chunks
from dotenv import load_dotenv

import requests
import musicbrainzngs
# spotipy no es necesario para este script modificado que opera sobre acousticbrainz_data.json

# ------------------------------------------------------------
# 1) Credenciales y user-agent
# ------------------------------------------------------------
load_dotenv()
# Las credenciales de Spotify (SPOTI_ID, SPOTI_SECRET) ya no son necesarias.

# ¡IMPORTANTE! Configura un User-Agent descriptivo para MusicBrainz.
# Reemplaza "tu_app_nombre", "tu_version", "tu_email@ejemplo.com" con tus datos.
try:
    musicbrainzngs.set_useragent(
        "AcousticBrainzUpdater",
        "1.1",
        "micorreo@ejemplo.com" # Cambia esto a tu email real o de contacto
    )
    musicbrainzngs.set_rate_limit(True) # Respetar 1 req/seg para MusicBrainz
except Exception as e:
    sys.exit(f"❌ Error configurando MusicBrainz: {e}")

# ------------------------------------------------------------
# 2) Funciones para MusicBrainz
# ------------------------------------------------------------

def get_mbid_from_name(track_name, artist_name):
    """Intenta obtener un MBID si no está presente, buscando por nombre y artista."""
    if not track_name or not artist_name:
        return None
    try:
        res = musicbrainzngs.search_recordings(
            recording=track_name, artist=artist_name, limit=1
        )
        recs = res.get("recording-list", [])
        return recs[0]["id"] if recs else None
    except musicbrainzngs.WebServiceError as e:
        print(f"  ⚠️ Error de MusicBrainz (search_recordings) para '{track_name} - {artist_name}': {e}")
        return None
    except Exception as e:
        print(f"  ❌ Error inesperado en get_mbid_from_name para '{track_name} - {artist_name}': {e}")
        return None


def fetch_mb_genre_and_rating(mbid):
    """Obtiene género y rating de MusicBrainz para un MBID."""
    if not mbid:
        return None, None, None
    try:
        rec = musicbrainzngs.get_recording_by_id(
            mbid, includes=["tags", "ratings"] # 'ratings' es correcto para la inclusión
        )["recording"]
        
        genre = None
        raw_tags = rec.get("tag-list", [])
        # Asegurar que tags_list es una lista, incluso si solo hay un tag.
        tags_list = raw_tags if isinstance(raw_tags, list) else ([raw_tags] if raw_tags else [])
        
        valid_tags = []
        for tag_item in tags_list:
            if isinstance(tag_item, dict) and "count" in tag_item and "name" in tag_item:
                try:
                    tag_item["count"] = int(tag_item["count"]) # Asegurar que count sea int
                    valid_tags.append(tag_item)
                except ValueError:
                    pass # Ignorar tag con count inválido
        
        if valid_tags:
            tags_sorted = sorted(valid_tags, key=lambda t: t["count"], reverse=True)
            genre = tags_sorted[0].get("name") if tags_sorted else None
        
        rating_value = None
        rating_votes = None
        rating_data = rec.get("rating", {}) # La respuesta anida el rating bajo la clave "rating"
        if isinstance(rating_data, dict):
            raw_val = rating_data.get("value")
            if raw_val is not None:
                try: rating_value = float(raw_val)
                except (ValueError, TypeError): pass
            
            raw_votes = rating_data.get("votes-count")
            if raw_votes is not None:
                try: rating_votes = int(raw_votes)
                except (ValueError, TypeError): pass
                
        return genre, rating_value, rating_votes
    except musicbrainzngs.WebServiceError as e:
        print(f"  ⚠️ Error de MusicBrainz (get_recording_by_id) para MBID {mbid}: {e}")
        return None, None, None
    except Exception as e:
        print(f"  ❌ Error inesperado en fetch_mb_genre_and_rating para MBID {mbid}: {e}")
        return None, None, None

# ------------------------------------------------------------
# 3) Funciones para AcousticBrainz en lote (bulk)
# ------------------------------------------------------------

def chunk_list(lst, n):
    """Divide una lista en trozos de tamaño máximo n."""
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def fetch_acousticbrainz_bulk(mbids):
    """
    Obtiene low-level y high-level para hasta 25 MBIDs en una sola petición.
    Maneja 429 y headers de rate limit. Retorna (ll_json, hl_json).
    AcousticBrainz rate limit: ej. 10 queries / 10 segundos.
    Esta función hace 2 queries (1 para low-level, 1 para high-level).
    """
    base = "https://acousticbrainz.org/api/v1"
    ids_param = ";".join(mbids)
    results = {}

    for level_type in ["low-level", "high-level"]:
        url = f"{base}/{level_type}?recording_ids={ids_param}"
        current_json = {}
        retries = 0
        max_retries = 3 # Intentar hasta 3 veces por petición (low o high)

        while retries < max_retries:
            try:
                resp = requests.get(url, timeout=20) # Timeout un poco más largo para bulk
                if resp.status_code == 429: # Too Many Requests
                    reset_in = int(resp.headers.get("X-RateLimit-Reset-In", 10))
                    retry_after = int(resp.headers.get("Retry-After", reset_in)) + 1 # Usar Retry-After si está, sino X-RateLimit-Reset-In
                    print(f"  ⏳ Rate limit en AcousticBrainz ({level_type}). Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    # No incrementar retries aquí, es un rate limit esperado
                    continue # Reintentar la misma petición
                
                resp.raise_for_status() # Lanza HTTPError para otros errores 4xx/5xx
                current_json = resp.json()
                
                # Chequeo opcional de remaining requests, aunque ya manejamos 429
                remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
                if remaining < 1: # Si queda menos de 1, esperar un poco preventivamente
                    wait_time = int(resp.headers.get("X-RateLimit-Reset-In", 2)) + 1
                    print(f"   proactively sleeping {wait_time}s due to low remaining AB requests")
                    time.sleep(wait_time)
                break # Petición exitosa para este nivel

            except requests.exceptions.Timeout:
                retries += 1
                print(f"  ⌛ Timeout en AcousticBrainz ({level_type}) para chunk. Intento {retries}/{max_retries}.")
                if retries >= max_retries:
                    print(f"  ❌ Fallaron todos los intentos por Timeout para {level_type} del chunk: {mbids[:3]}...") # Mostrar algunos MBIDs
                else:
                    time.sleep(5 * retries) # Backoff simple
            except requests.exceptions.RequestException as e:
                retries += 1
                print(f"  ❌ Error en petición a AcousticBrainz ({level_type}): {e}. Intento {retries}/{max_retries}.")
                if retries >= max_retries:
                     print(f"  ❌ Fallaron todos los intentos por RequestException para {level_type} del chunk: {mbids[:3]}...")
                else:
                    time.sleep(10 * retries) # Backoff más largo
            
        results[level_type] = current_json # Guardar {} si fallaron todos los reintentos
        
    return results.get("low-level", {}), results.get("high-level", {})


# ------------------------------------------------------------
# 4) Lógica Principal de Actualización
# ------------------------------------------------------------
def main():
    start_time_script = time.time()
    data_file = "acousticbrainz_data.json"
    output_file = "acousticbrainz_data_updated.json" # Guardar en un nuevo archivo

    if not os.path.exists(data_file):
        sys.exit(f"❌ Archivo de entrada '{data_file}' no encontrado. Este script actualiza un archivo existente.")

    print(f"🔄 Cargando '{data_file}'...")
    try:
        with open(data_file, "r", encoding="utf-8") as fin:
            abz_data = json.load(fin)
    except json.JSONDecodeError as e:
        sys.exit(f"❌ Error decodificando JSON de '{data_file}': {e}")
    except Exception as e:
        sys.exit(f"❌ Error leyendo '{data_file}': {e}")
        
    total_tracks_in_file = len(abz_data)
    print(f"➡️  {total_tracks_in_file} pistas cargadas desde '{data_file}'.")

    # --- 4.1 (Opcional pero mantenido) Actualizar datos de MusicBrainz ---
    print("\n🎵 Procesando MusicBrainz para completar género/ratings faltantes...")
    mb_updated_tracks = 0
    for i, (track_id, track_entry) in enumerate(abz_data.items()):
        # print(f"  Verificando MusicBrainz para track {i+1}/{total_tracks_in_file}: {track_id}")
        mbid = track_entry.get("mbid")
        
        # Intentar obtener MBID si falta (esto es opcional, si se asume que todos tienen MBID)
        # if not mbid and "track_name" in track_entry and "artist_name" in track_entry:
        #     print(f"    MBID faltante para {track_entry['track_name']}, intentando buscar...")
        #     mbid = get_mbid_from_name(track_entry["track_name"], track_entry["artist_name"])
        #     if mbid:
        #         track_entry["mbid"] = mbid # Guardar el MBID encontrado
        #         print(f"    MBID encontrado y añadido: {mbid}")

    #     if mbid:
    #         needs_mb_update = (
    #             track_entry.get("genre_mb") is None or
    #             track_entry.get("rating_value") is None or
    #             track_entry.get("rating_votes") is None
    #         )
    #         if needs_mb_update:
    #             if (mb_updated_tracks % 20 == 0 and mb_updated_tracks > 0) or needs_mb_update : # Log más frecuente si hay update
    #                  print(f"    Track {i+1}/{total_tracks_in_file}: Consultando MusicBrainz para MBID {mbid}...")
    #             genre, rating_val, rating_cnt = fetch_mb_genre_and_rating(mbid)
    #             updated = False
    #             if track_entry.get("genre_mb") is None and genre is not None:
    #                 track_entry["genre_mb"] = genre
    #                 updated = True
    #             if track_entry.get("rating_value") is None and rating_val is not None:
    #                 track_entry["rating_value"] = rating_val
    #                 updated = True
    #             if track_entry.get("rating_votes") is None and rating_cnt is not None:
    #                 track_entry["rating_votes"] = rating_cnt
    #                 updated = True
    #             if updated:
    #                 mb_updated_tracks += 1
    #     elif (i+1)%100 == 0: # Log de progreso general de MusicBrainz
    #         print(f"  ... {i+1}/{total_tracks_in_file} pistas revisadas para MusicBrainz.")


    # print(f"✅ MusicBrainz: {mb_updated_tracks} pistas tuvieron campos de género/rating actualizados.")

    # --- 4.2 Actualizar datos de AcousticBrainz (low-level y high-level) ---
    print("\n🎧 Procesando AcousticBrainz para actualizar datos low-level y high-level...")
    
    mbid_to_spotify_ids_map = {}
    for spotify_id, track_data_val in abz_data.items():
        mbid_val = track_data_val.get("mbid")
        if mbid_val:
            mbid_to_spotify_ids_map.setdefault(mbid_val, []).append(spotify_id)
    
    unique_mbids_to_fetch = list(mbid_to_spotify_ids_map.keys())
    total_unique_mbids = len(unique_mbids_to_fetch)
    print(f"  Se encontraron {total_unique_mbids} MBIDs únicos para consultar en AcousticBrainz.")

    acousticbrainz_data_cache = {} # Para almacenar temporalmente datos de AB por MBID

    if total_unique_mbids > 0:
        num_chunks = ceil(total_unique_mbids / 25)
        for chunk_idx, mbid_chunk in enumerate(chunk_list(unique_mbids_to_fetch, 25)):
            print(f"  Procesando chunk de AcousticBrainz {chunk_idx + 1}/{num_chunks} (MBIDs: {len(mbid_chunk)})...")
            # Medir tiempo de procesamiento por chunk
            chunk_start = time.time()
            ll_bulk, hl_bulk = fetch_acousticbrainz_bulk(mbid_chunk)

            # Cachear los resultados por mbid
            for mbid_in_chunk in mbid_chunk:
                raw_ll_data = ll_bulk.get(mbid_in_chunk, {})
                doc_ll = next(iter(raw_ll_data.values()), {}) if isinstance(raw_ll_data, dict) else {}
                
                raw_hl_data = hl_bulk.get(mbid_in_chunk, {})
                doc_hl_wrapper = next(iter(raw_hl_data.values()), {}) if isinstance(raw_hl_data, dict) else {}
                
                # El highlevel object está anidado dentro de la primera submission
                actual_highlevel_payload = doc_hl_wrapper.get("highlevel", {}) if isinstance(doc_hl_wrapper, dict) else {}

                acousticbrainz_data_cache[mbid_in_chunk] = {
                    "lowlevel_payload": doc_ll,
                    "highlevel_payload": actual_highlevel_payload
                }
            
            # Pausa proactiva para respetar el rate limit de AcousticBrainz (10 queries / 10s)
            # fetch_acousticbrainz_bulk hace 2 queries. Esperar 1 segundo aquí mantiene ~2 queries/segundo.
            if chunk_idx < num_chunks -1 : # No dormir después del último chunk
                 time.sleep(1) 
            
            # Mostrar tiempo transcurrido para este chunk
            elapsed = time.time() - chunk_start
            print(f"  ⏱️ Tiempo de procesamiento del chunk {chunk_idx + 1}/{num_chunks}: {elapsed:.2f} segundos.")


        # Aplicar los datos cacheados a abz_data
        ab_updated_tracks = 0
        for mbid_processed, ab_payloads in acousticbrainz_data_cache.items():
            spotify_ids_for_mbid = mbid_to_spotify_ids_map.get(mbid_processed, [])
            if not spotify_ids_for_mbid: # Debería existir si construimos el map correctamente
                continue

            updated_for_this_mbid = False
            for spotify_id_to_update in spotify_ids_for_mbid:
                track_entry = abz_data[spotify_id_to_update]

                # Actualizar highlevel
                track_entry["highlevel"] = ab_payloads["highlevel_payload"]

                # Actualizar low-level fields
                ll_payload = ab_payloads["lowlevel_payload"]
                track_entry["bpm"] = ll_payload.get("rhythm", {}).get("bpm")
                track_entry["energy"] = ll_payload.get("lowlevel", {}).get("dynamic_complexity") # Asumiendo que esto es 'energy'
                track_entry["danceability_ll"] = ll_payload.get("rhythm", {}).get("danceability")
                track_entry["loudness"] = ll_payload.get("lowlevel", {}).get("average_loudness")

                # Eliminar campos antiguos derivados de highlevel
                track_entry.pop("top_genre_hl", None)
                track_entry.pop("danceability_hl", None)
                track_entry.pop("mood_happy", None)
                track_entry.pop("acousticness", None) # Este era un campo de ejemplo en el JSON original.
                                                    # La información de 'acoustic' estará en highlevel.mood_acoustic.value
                updated_for_this_mbid = True
            
            if updated_for_this_mbid:
                ab_updated_tracks += len(spotify_ids_for_mbid) # Contar por track_id actualizado
        
        print(f"✅ AcousticBrainz: {ab_updated_tracks} pistas (entradas en JSON) actualizadas con datos de AcousticBrainz.")
    else:
        print("✅ AcousticBrainz: No hay MBIDs para procesar.")


    # --- 4.3 Guardar archivo actualizado ---
    print(f"\n💾 Guardando datos actualizados en '{output_file}'...")
    try:
        with open(output_file, "w", encoding="utf-8") as fout:
            json.dump(abz_data, fout, indent=2, ensure_ascii=False)
        print(f"🎉 ¡Proceso completado! Archivo guardado en '{output_file}'.")
    except Exception as e:
        print(f"❌ Error al guardar el archivo de salida: {e}")

    print(f"\n⏱️  Tiempo total de ejecución del script: {(time.time() - start_time_script)/60:.2f} minutos.")

if __name__ == "__main__":
    main()