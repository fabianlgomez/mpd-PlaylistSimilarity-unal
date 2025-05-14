#!/usr/bin/env python3
"""
enrich_challenge_set_acousticbrainz.py

Lee spotify_metadata.json (fase 1 ya ejecutada),
luego consulta MusicBrainz (solo por nombre+artista) y AcousticBrainz
para extraer únicamente los campos requeridos:
  - MusicBrainz: primer tag (genre) y rating (value + votes-count)
  - AcousticBrainz low-level y high-level en lote (bulk) para hasta 25 recordings por petición
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
# 2) Funciones para MusicBrainz
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
    Maneja 429 y headers de rate limit.
    """
    base = "https://acousticbrainz.org/api/v1"
    ids = ";".join(mbids)

    # Bulk low-level
    ll_url = f"{base}/low-level?recording_ids={ids}"
    while True:
        resp = requests.get(ll_url, timeout=10)
        if resp.status_code == 429:
            reset = int(resp.headers.get("X-RateLimit-Reset-In", 10))
            time.sleep(reset)
            continue
        resp.raise_for_status()
        ll_json = resp.json()
        headers = resp.headers
        remaining = int(headers.get("X-RateLimit-Remaining", 0))
        if remaining < 1:
            reset = int(headers.get("X-RateLimit-Reset-In", 1))
            time.sleep(reset)
        break

    # Bulk high-level
    hl_url = f"{base}/high-level?recording_ids={ids}"
    while True:
        resp = requests.get(hl_url, timeout=10)
        if resp.status_code == 429:
            reset = int(resp.headers.get("X-RateLimit-Reset-In", 10))
            time.sleep(reset)
            continue
        resp.raise_for_status()
        hl_json = resp.json()
        headers = resp.headers
        remaining = int(headers.get("X-RateLimit-Remaining", 0))
        if remaining < 1:
            reset = int(headers.get("X-RateLimit-Reset-In", 1))
            time.sleep(reset)
        break

    return ll_json, hl_json

# ------------------------------------------------------------
# 4) Función para seleccionar género top de high-level
# ------------------------------------------------------------
def select_top_genre(highlevel_data_dict):
    if not isinstance(highlevel_data_dict, dict):
        return None

    genre_probabilities = {}
    for key, value_dict in highlevel_data_dict.items():
        if key.startswith("genre_") and isinstance(value_dict, dict) and "probability" in value_dict:
            try:
                probability = float(value_dict["probability"])
                genre_probabilities[key] = probability
            except (ValueError, TypeError):
                continue

    if not genre_probabilities:
        return None

    return max(genre_probabilities, key=genre_probabilities.get)

# ------------------------------------------------------------
# 5) Carga challenge_set y spotify_metadata
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
# 6) Reanudación desde archivo parcial
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
# 7) Procesar cada batch
# ------------------------------------------------------------
try:
    for b in range(batches):
        start = b * batch_size
        batch = remaining[start : start + batch_size]
        print(f"[Batch {b+1}/{batches}] pistas {start+1}-{start+len(batch)}")

        # 7.1 MusicBrainz: obtener mbid, género y rating
        mbid_map = {}
        meta_map = {}
        for i, tid in enumerate(batch, start=start+1):
            elapsed = time.time() - start_time
            print(f" ▶ MB [{i}/{total}] {tid} – {elapsed:.1f}s")

            meta = sp_meta.get(tid, {})
            name = meta.get("track_name", "")
            artist = meta.get("artist_name", "")

            mbid = get_mbid_from_name(name, artist)
            mbid_map[tid] = mbid

            if mbid:
                genre_mb, rating_val, rating_cnt = fetch_mb_genre_and_rating(mbid)
            else:
                genre_mb = rating_val = rating_cnt = None

            meta_map[tid] = (genre_mb, rating_val, rating_cnt)

        # 7.2 AcousticBrainz en lote (chunks de 25)
        ll_data_map = {}
        hl_data_map = {}
        acoustic_tids = [tid for tid, m in mbid_map.items() if m]
        for chunk in chunk_list(acoustic_tids, 25):
            mbids = [mbid_map[tid] for tid in chunk]
            ll_json, hl_json = fetch_acousticbrainz_bulk(mbids)
            for tid in chunk:
                m = mbid_map[tid]
                raw_ll = ll_json.get(m, {})
                doc_ll = next(iter(raw_ll.values()), {}) if isinstance(raw_ll, dict) else {}
                raw_hl = hl_json.get(m, {})
                doc_hl = next(iter(raw_hl.values()), {}) if isinstance(raw_hl, dict) else {}
                ll_data_map[tid] = doc_ll
                hl_data_map[tid] = doc_hl

        # 7.3 Combinar y guardar
        for tid in batch:
            genre_mb, rating_val, rating_cnt = meta_map[tid]
            ll = ll_data_map.get(tid, {})
            hl = hl_data_map.get(tid, {})

            abz_data[tid] = {
                "mbid":            mbid_map.get(tid),
                "genre_mb":        genre_mb,
                "top_genre_hl":    select_top_genre(hl.get("highlevel", {})),
                "bpm":             ll.get("rhythm", {}).get("bpm"),
                "energy":          ll.get("lowlevel", {}).get("dynamic_complexity"),
                "danceability_ll": ll.get("rhythm", {}).get("danceability"),
                "danceability_hl": hl.get("highlevel", {}).get("danceability", {}).get("value"),
                "loudness":        ll.get("lowlevel", {}).get("average_loudness"),
                "mood_happy":      hl.get("highlevel", {}).get("mood_happy", {}).get("value"),
                "acousticness":    hl.get("highlevel", {}).get("acousticness", {}).get("value"),
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
