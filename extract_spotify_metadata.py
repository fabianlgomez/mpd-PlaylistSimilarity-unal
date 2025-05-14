#!/usr/bin/env python3
"""
extract_spotify_metadata.py

Fase 1: Extrae y guarda metadata de Spotify para cada track:
  - track_id, track_name, artist_name, duration_ms, explicit,
    popularity, release_date, isrc

Genera spotify_metadata.json listo para la Fase 2.
"""

import os
import sys
import time
import json
from math import ceil
from dotenv import load_dotenv

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ------------------------------------------------------------
# 1) Carga de credenciales
# ------------------------------------------------------------
load_dotenv()
SPOTI_ID     = os.getenv("SPOTIPY_CLIENT_ID")
SPOTI_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

if not (SPOTI_ID and SPOTI_SECRET):
    sys.exit("❌ Define SPOTIPY_CLIENT_ID y SPOTIPY_CLIENT_SECRET en tu .env")

creds = SpotifyClientCredentials(client_id=SPOTI_ID,
                                 client_secret=SPOTI_SECRET)
sp    = spotipy.Spotify(client_credentials_manager=creds)

# ------------------------------------------------------------
# 2) Carga challenge_set y construye lista de track IDs
# ------------------------------------------------------------
with open("challenge_set.json", "r", encoding="utf-8") as f:
    challenge = json.load(f)

playlists = challenge["playlists"]

# IDs únicos de todas las pistas
all_ids = []
seen = set()
for pl in playlists:
    for tr in pl["tracks"]:
        tid = tr["track_uri"].split(":")[-1]
        if tid not in seen:
            seen.add(tid)
            all_ids.append(tid)

total = len(all_ids)
print(f"➡️  {total} pistas únicas encontradas.\n")

# ------------------------------------------------------------
# 3) Fase 1: Extraer metadata de Spotify en batches de 50
# ------------------------------------------------------------
sp_metadata = {}
batch_size = 50
batches    = ceil(total / batch_size)
start_time = time.time()

for i in range(batches):
    start = i * batch_size
    batch = all_ids[start : start + batch_size]
    resp  = sp.tracks(batch)["tracks"]
    for tr in resp:
        if tr is None:
            continue
        sp_metadata[tr["id"]] = {
            "track_name":    tr["name"],
            "artist_name":   tr["artists"][0]["name"],
            "duration_ms":   tr["duration_ms"],
            "explicit":      tr["explicit"],
            "popularity":    tr["popularity"],
            "release_date":  tr["album"]["release_date"],
            "isrc":          tr.get("external_ids", {}).get("isrc")
        }
    elapsed = time.time() - start_time
    print(f"[Spotify] Batch {i+1}/{batches} procesado — {len(sp_metadata)}/{total} tracks "
          f"in {elapsed:.1f}s")
    time.sleep(0.3)

# ------------------------------------------------------------
# 4) Guardar JSON intermedio
# ------------------------------------------------------------
with open("spotify_metadata.json", "w", encoding="utf-8") as fout:
    json.dump(sp_metadata, fout, indent=2, ensure_ascii=False)

total_elapsed = time.time() - start_time
print(f"\n✅ spotify_metadata.json generado con {len(sp_metadata)} records "
      f"en {total_elapsed/60:.1f} min.")
