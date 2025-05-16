#!/usr/bin/env python3
"""
enrich_challenge_set_acousticbrainz.py

Lee spotify_metadata.json (fase 1 ya ejecutada),
luego consulta MusicBrainz (solo por nombre+artista) y AcousticBrainz
para extraer únicamente los campos requeridos:
  - MusicBrainz: primer tag (genre) y rating (value + votes-count)
  - AcousticBrainz low-level: bpm, dynamic_complexity, danceability, average_loudness
  - AcousticBrainz high-level: top genre, danceability, mood_happy, acousticness
Logea progreso, guarda al detectar interrupción o fallo,
y reanuda desde el JSON parcial.
"""

import os
import sys
import time
import json
from math import ceil
from dotenv import load_dotenv

import requests
import musicbrainzngs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ------------------------------------------------------------
# 1) Credenciales y user-agent
# ------------------------------------------------------------
load_dotenv()
SPOTI_ID     = os.getenv("SPOTIPY_CLIENT_ID")
SPOTI_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
if not (SPOTI_ID and SPOTI_SECRET):
    sys.exit("❌ Define SPOTIPY_CLIENT_ID y SPOTIPY_CLIENT_SECRET en tu .env")

sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=SPOTI_ID, client_secret=SPOTI_SECRET
))

musicbrainzngs.set_useragent("enrichAB", "1.0", "tu_email@dominio.com")

# ------------------------------------------------------------
# 2) Funciones para MusicBrainz y AcousticBrainz
# ------------------------------------------------------------
def get_mbid_from_name(track_name, artist_name):
    try:
        res = musicbrainzngs.search_recordings(
            recording=track_name, artist=artist_name, limit=1
        )
        recs = res.get("recording-list", [])
        return recs[0]["id"] if recs else None
    except Exception:
        return None


def fetch_mb_genre_and_rating(mbid):
    try:
        rec = musicbrainzngs.get_recording_by_id(
            mbid, includes=["tags", "rating"]
        )["recording"]
        raw = rec.get("tag-list", [])
        tags_list = [raw] if isinstance(raw, dict) else raw
        tags_sorted = sorted(
            tags_list,
            key=lambda t: int(t.get("count", 0)),
            reverse=True
        )
        genre = tags_sorted[0].get("name") if tags_sorted else None
        rating = rec.get("rating", {})
        return genre, rating.get("value"), rating.get("votes-count")
    except Exception:
        return None, None, None


def fetch_acousticbrainz(mbid):
    base = "https://acousticbrainz.org"
    try:
        ll_resp = requests.get(f"{base}/{mbid}/low-level", timeout=10)
        ll_resp.raise_for_status()
        hl_resp = requests.get(f"{base}/{mbid}/high-level", timeout=10)
        hl_resp.raise_for_status()
        return ll_resp.json(), hl_resp.json()
    except Exception:
        return {}, {}


def select_top_genre(highlevel_data_dict): # Renombrado el parámetro para mayor claridad
    """
    Selecciona el género con la probabilidad más alta del diccionario high-level de AcousticBrainz.
    highlevel_data_dict es el diccionario que corresponde a la clave 'highlevel' de la respuesta de AB.
    Ejemplo de estructura esperada para una entrada de género en highlevel_data_dict:
    "genre_rock": { "value": "rock", "probability": 0.85, ... }
    """
    if not isinstance(highlevel_data_dict, dict): # Comprobación de seguridad
        return None

    # 1. Filtrar solo las entradas de género que son diccionarios y tienen una clave 'probability'
    #    y almacenar la probabilidad para cada una.
    genre_probabilities = {}
    for key, value_dict in highlevel_data_dict.items():
        if key.startswith("genre_") and isinstance(value_dict, dict) and "probability" in value_dict:
            try:
                probability = float(value_dict["probability"])
                genre_probabilities[key] = probability
            except (ValueError, TypeError):
                # Ignorar si la probabilidad no es un número válido
                print(f"Advertencia: Probabilidad no válida para {key}: {value_dict['probability']}")
                continue

    if not genre_probabilities:
        return None

    # 2. Encontrar la clave del género (e.g., "genre_rock") que tiene el valor de probabilidad máximo.
    #    max() itera sobre las claves de genre_probabilities.
    #    key=genre_probabilities.get le dice a max() que use los valores del diccionario
    #    (las probabilidades) para la comparación.
    top_genre_key = max(genre_probabilities, key=genre_probabilities.get)

    # Opcionalmente, podrías querer devolver solo la parte del nombre del género
    # return top_genre_key.replace("genre_", "")
    return top_genre_key # Devuelve la clave completa como "genre_rock"

# ------------------------------------------------------------
# 3) Carga challenge_set y spotify_metadata
# ------------------------------------------------------------
with open("challenge_set.json", "r", encoding="utf-8") as f:
    challenge = json.load(f)
playlists = challenge["playlists"]

all_ids, seen = [], set()
for pl in playlists:
    for tr in pl["tracks"]:
        tid = tr["track_uri"].split(":")[-1]
        if tid not in seen:
            seen.add(tid)
            all_ids.append(tid)
total = len(all_ids)
print(f"➡️  {total} pistas únicas encontradas.\n")

with open("spotify_metadata.json", "r", encoding="utf-8") as f:
    sp_meta = json.load(f)

# ------------------------------------------------------------
# 4) Reanudación desde archivo parcial
# ------------------------------------------------------------
data_file = "acousticbrainz_data.json"
if os.path.exists(data_file):
    with open(data_file, "r", encoding="utf-8") as fin:
        abz_data = json.load(fin)
    processed = set(abz_data.keys())
    print(f"🔄 Reanudando: {len(processed)}/{total} procesadas.")
else:
    abz_data = {}
    processed = set()
print(f"⏳ Quedan {total - len(processed)}/{total} por procesar.\n")

remaining = [tid for tid in all_ids if tid not in processed]
batch_size = 100
batches    = ceil(len(remaining) / batch_size)
start_time = time.time()

# ------------------------------------------------------------
# 5) Procesar cada batch
# ------------------------------------------------------------
try:
    for b in range(batches):
        start = b * batch_size
        batch = remaining[start : start + batch_size]
        print(f"[Batch {b+1}/{batches}] pistas {start+1}-{start+len(batch)}")

        for i, tid in enumerate(batch, start=start+1):
            elapsed = time.time() - start_time
            print(f" ▶ [{i}/{total}] {tid} – {elapsed:.1f}s")

            meta    = sp_meta.get(tid, {})
            name    = meta.get("track_name", "")
            artist  = meta.get("artist_name", "")

            mbid = get_mbid_from_name(name, artist)

            genre_mb = rating_val = rating_cnt = None
            bpm = energy = dance_ll = loudness = None
            dance_hl = mood_happy = acousticness = None
            top_genre_hl = None

            if mbid:
                # MusicBrainz
                genre_mb, rating_val, rating_cnt = fetch_mb_genre_and_rating(mbid)
                # AcousticBrainz
                ll, hl = fetch_acousticbrainz(mbid)
                # low-level
                bpm      = ll.get("rhythm", {}).get("bpm")
                energy   = ll.get("lowlevel", {}).get("dynamic_complexity")
                dance_ll = ll.get("rhythm", {}).get("danceability")
                loudness = ll.get("lowlevel", {}).get("average_loudness")
                # high-level
                dance_hl     = hl.get("highlevel", {}).get("danceability", {}).get("value") # Asumiendo que quieres el 'value'
                mood_happy   = hl.get("highlevel", {}).get("mood_happy", {}).get("value")   # Asumiendo que quieres el 'value'
                acousticness = hl.get("highlevel", {}).get("acousticness", {}).get("value") # Asumiendo que quieres el 'value'
                top_genre_hl = select_top_genre(hl.get("highlevel", {}))

            abz_data[tid] = {
                "mbid":            mbid,
                "genre_mb":        genre_mb,
                "top_genre_hl":    top_genre_hl,
                "bpm":             bpm,
                "energy":          energy,
                "danceability_ll": dance_ll,
                "danceability_hl": dance_hl,
                "loudness":        loudness,
                "mood_happy":      mood_happy,
                "acousticness":    acousticness,
                "rating_value":    rating_val,
                "rating_votes":    rating_cnt
            }

        with open(data_file, "w", encoding="utf-8") as fout:
            json.dump(abz_data, fout, indent=2, ensure_ascii=False)
        print(f"✅ Guardado '{data_file}' tras batch {b+1}\n")
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n⏸️ Interrumpido. Guardando…")
    with open(data_file, "w", encoding="utf-8") as fout:
        json.dump(abz_data, fout, indent=2, ensure_ascii=False)
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Error inesperado: {e}\nGuardando…")
    with open(data_file, "w", encoding="utf-8") as fout:
        json.dump(abz_data, fout, indent=2, ensure_ascii=False)
    sys.exit(1)

print(f"\n✅ Completado en {(time.time()-start_time)/60:.1f} min.")
