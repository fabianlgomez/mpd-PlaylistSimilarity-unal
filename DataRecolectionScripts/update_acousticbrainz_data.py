#!/usr/bin/env python3
"""
update_acousticbrainz_data.py

Lee un archivo acousticbrainz_data.json existente,
actualiza MusicBrainz (opcional) y AcousticBrainz en bulk,
mostrando tiempo por chunk, reutilizando conexiones,
paralelizando solicitudes low/high-level y permitiendo
reanudar tras interrupción guardando checkpoints.
"""

import os
import sys
import time
import json
from math import ceil
from dotenv import load_dotenv

import requests
import musicbrainzngs
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------------------------------------------
# 1) Configuración inicial y sesión HTTP
# ------------------------------------------------------------
load_dotenv()
try:
    musicbrainzngs.set_useragent(
        "AcousticBrainzUpdater", "1.1", "micorreo@ejemplo.com"
    )
    musicbrainzngs.set_rate_limit(True)
except Exception as e:
    sys.exit(f"❌ Error configurando MusicBrainz: {e}")

session = requests.Session()  # Keep-alive para acelerar peticiones HTTP

# ------------------------------------------------------------
# 2) Helpers para bulk y concurrencia
# ------------------------------------------------------------
def chunk_list(lst, n):
    """Divide una lista en trozos de tamaño máximo n."""
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def fetch_chunk_level(level_type, ids_param, max_retries=3, timeout=20):
    """Petición individual para low-level o high-level con reintentos."""
    base = "https://acousticbrainz.org/api/v1"
    url = f"{base}/{level_type}?recording_ids={ids_param}"
    retries = 0
    while retries < max_retries:
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After",
                                  resp.headers.get("X-RateLimit-Reset-In", 10))) + 1
                print(f"  ⏳ Rate limit {level_type}. Esperando {retry_after}s...")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            data = resp.json()
            # Control proactivo de rate-limit
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
            if remaining < 1:
                wait = int(resp.headers.get("X-RateLimit-Reset-In", 2)) + 1
                time.sleep(wait)
            return data
        except requests.exceptions.Timeout:
            retries += 1
            time.sleep(5 * retries)
        except requests.exceptions.RequestException:
            retries += 1
            time.sleep(10 * retries)
    print(f"  ❌ Fallaron todos los intentos para {level_type}")
    return {}


def fetch_acousticbrainz_bulk(mbids):
    """
    Obtiene low-level y high-level en paralelo para hasta 25 MBIDs.
    Retorna tuple (low_json, high_json).
    """
    ids_param = ";".join(mbids)
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            executor.submit(fetch_chunk_level, level, ids_param): level
            for level in ("low-level", "high-level")
        }
        for future in as_completed(future_map):
            level = future_map[future]
            results[level] = future.result() or {}
    return results.get("low-level", {}), results.get("high-level", {})

# ------------------------------------------------------------
# 3) Función principal con checkpoint/reanudación
# ------------------------------------------------------------
def main():
    start_script = time.time()
    data_file = "acousticbrainz_data.json"
    output_file = "acousticbrainz_data_updated.json"
    checkpoint_file = "acousticbrainz_checkpoint.json"

    # Cargar datos previos o del original
    if os.path.exists(output_file):
        print(f"🔄 Reanudando desde '{output_file}'...")
        with open(output_file, "r", encoding="utf-8") as fin:
            abz_data = json.load(fin)
    elif os.path.exists(data_file):
        print(f"🔄 Cargando '{data_file}'...")
        with open(data_file, "r", encoding="utf-8") as fin:
            abz_data = json.load(fin)
    else:
        sys.exit(f"❌ No se encontró ni '{output_file}' ni '{data_file}'")

    # Cargar MBIDs ya procesados
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as ckp:
            processed_mbids = set(json.load(ckp))
        print(f"✅ Se retomarán {len(processed_mbids)} MBIDs ya procesados.")
    else:
        processed_mbids = set()

    # Mapear MBID -> lista de Spotify IDs
    mbid_map = {}
    for sid, entry in abz_data.items():
        mbid = entry.get("mbid")
        if mbid:
            mbid_map.setdefault(mbid, []).append(sid)
    all_mbids = list(mbid_map.keys())
    # Filtrar solo MBIDs pendientes
    pending_mbids = [m for m in all_mbids if m not in processed_mbids]
    print(f"🎧 Total MBIDs: {len(all_mbids)}, pendientes: {len(pending_mbids)}.")

    # Procesar en chunks
    if pending_mbids:
        num_chunks = ceil(len(pending_mbids) / 25)
        for idx, chunk in enumerate(chunk_list(pending_mbids, 25), start=1):
            print(f"  Procesando chunk {idx}/{num_chunks} ({len(chunk)} MBIDs)...")
            t0 = time.time()
            ll_bulk, hl_bulk = fetch_acousticbrainz_bulk(chunk)

            # Asignar resultados al JSON en memoria
            for m in chunk:
                ll_raw = ll_bulk.get(m, {})
                ll = next(iter(ll_raw.values()), {}) if isinstance(ll_raw, dict) else {}
                hl_raw = hl_bulk.get(m, {})
                hl = next(iter(hl_raw.values()), {}).get("highlevel", {})
                for sid in mbid_map.get(m, []):
                    e = abz_data[sid]
                    e["highlevel"] = hl
                    e["bpm"] = ll.get("rhythm", {}).get("bpm")
                    e["energy"] = ll.get("lowlevel", {}).get("dynamic_complexity")
                    e["danceability_ll"] = ll.get("rhythm", {}).get("danceability")
                    e["loudness"] = ll.get("lowlevel", {}).get("average_loudness")
                    for old in ("top_genre_hl","danceability_hl","mood_happy","acousticness"):
                        e.pop(old, None)

            elapsed = time.time() - t0
            print(f"  ⏱️ Chunk {idx}/{num_chunks} procesado en {elapsed:.2f}s.")

            # Guardar checkpoint: actualizar lista de procesados
            processed_mbids.update(chunk)
            with open(checkpoint_file, "w", encoding="utf-8") as ckp:
                json.dump(list(processed_mbids), ckp)
            # Guardar progreso parcial
            with open(output_file, "w", encoding="utf-8") as fout:
                json.dump(abz_data, fout, indent=2, ensure_ascii=False)

            # Pausa mínima de seguridad
            # if idx < num_chunks:
            #     time.sleep(1)
    else:
        print("✅ No hay MBIDs pendientes.")

    # Final: eliminar checkpoint y reporte
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
    total_min = (time.time() - start_script) / 60
    print(f"\n🎉 Proceso completado en {total_min:.2f} minutos. Datos en '{output_file}'.")

if __name__ == "__main__":
    main()
