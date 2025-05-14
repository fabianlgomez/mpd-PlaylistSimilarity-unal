#!/usr/bin/env python3
"""
enrich_challenge_set.py

Fase 1: Extrae y guarda metadata de Spotify (popularity, duration_ms, explicit, etc.)
Fase 2: Lee ese JSON intermedio y recupera tags de Last.fm.
Finalmente construye enriched_challenge_set.json.

Añade logging por batches en Last.fm y guarda archivos parciales si hay fallo.
"""

import os
import sys
import time
import json
from math import ceil
from dotenv import load_dotenv

import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ------------------------------------------------------------
# 1) Carga de credenciales
# ------------------------------------------------------------
load_dotenv()
SPOTI_ID     = os.getenv("SPOTIPY_CLIENT_ID")
SPOTI_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
LASTFM_KEY   = os.getenv("LASTFM_API_KEY")

if not (SPOTI_ID and SPOTI_SECRET and LASTFM_KEY):
    sys.exit("❌ Define SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET y LASTFM_API_KEY en tu .env")

creds = SpotifyClientCredentials(client_id=SPOTI_ID,
                                 client_secret=SPOTI_SECRET)
sp    = spotipy.Spotify(client_credentials_manager=creds)

LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"

# ------------------------------------------------------------
# 2) Funciones Last.fm
# ------------------------------------------------------------
def lastfm_search(track_name, artist_name):
    params = {
        "method": "track.search",
        "track": track_name,
        "artist": artist_name,
        "api_key": LASTFM_KEY,
        "format": "json",
        "limit": 1
    }
    r = requests.get(LASTFM_URL, params=params)
    r.raise_for_status()
    matches = r.json()["results"]["trackmatches"].get("track", [])
    return matches[0] if isinstance(matches, list) and matches else None

def lastfm_get_tags(mbid=None, track_name=None, artist_name=None):
    params = {"method": "track.getInfo", "api_key": LASTFM_KEY, "format": "json"}
    if mbid:
        params["mbid"] = mbid
    else:
        params["track"]  = track_name
        params["artist"] = artist_name
    r = requests.get(LASTFM_URL, params=params)
    r.raise_for_status()
    tags = r.json().get("track", {}).get("toptags", {}).get("tag", [])
    return [t["name"] for t in tags if "name" in t]

# ------------------------------------------------------------
# 3) Cargar challenge_set y extraer track IDs únicos
# ------------------------------------------------------------
with open("challenge_set.json", "r") as f:
    challenge = json.load(f)

playlists = challenge["playlists"]
playlist_tracks = {
    pl["pid"]: [t["track_uri"].split(":")[-1] for t in pl["tracks"]]
    for pl in playlists if pl.get("num_samples", 0) > 0
}
all_ids = list({tid for tids in playlist_tracks.values() for tid in tids})
print(f"➡️  {len(all_ids)} pistas únicas encontradas.\n")

# ------------------------------------------------------------
# 4) Fase 1: Obtener y guardar metadata de Spotify
# ------------------------------------------------------------
sp_metadata = {}
batches = ceil(len(all_ids) / 50)
try:
    for idx in range(batches):
        start = idx * 50
        batch = all_ids[start : start + 50]
        resp = sp.tracks(batch)["tracks"]
        for tr in resp:
            if tr is None:
                continue
            sp_metadata[tr["id"]] = {
                "track_name":   tr["name"],
                "artist_name":  tr["artists"][0]["name"],
                "duration_ms":  tr["duration_ms"],
                "explicit":     tr["explicit"],
                "popularity":   tr["popularity"],
                "release_date": tr["album"]["release_date"]
            }
        print(f"[Spotify] Procesado batch {idx+1}/{batches}")
        time.sleep(0.3)
except Exception as e:
    print(f"\n❌ Error en fase Spotify: {e}")
finally:
    with open("spotify_metadata.json", "w", encoding="utf-8") as fout:
        json.dump(sp_metadata, fout, indent=2, ensure_ascii=False)
    print("📁 spotify_metadata.json guardado tras interrupción o finalización de fase 1.\n")
    if 'e' in locals():
        sys.exit(1)

print("✅ Fase 1 completada: 'spotify_metadata.json' generado.\n")

# ------------------------------------------------------------
# 5) Fase 2: Leer JSON y recuperar tags de Last.fm
# ------------------------------------------------------------
# Si ya está creado spotify_metadata.json desde ejecuciones previas:
# with open("spotify_metadata.json", "r") as fin:
#     sp_metadata = json.load(fin)

lfm_tags = {}
total = len(all_ids)
l_fm_batch_size = 500
batches_lfm = ceil(total / l_fm_batch_size)

try:
    for bidx in range(batches_lfm):
        start = bidx * l_fm_batch_size
        end   = min(start + l_fm_batch_size, total)
        batch_ids = all_ids[start:end]
        print(f"[Last.fm] Iniciando batch {bidx+1}/{batches_lfm} ({start+1}-{end})")
        for tid in batch_ids:
            meta = sp_metadata.get(tid, {})
            match = lastfm_search(meta.get("track_name",""), meta.get("artist_name",""))
            if match:
                mbid = match.get("mbid") or None
                tags = lastfm_get_tags(mbid, meta["track_name"], meta["artist_name"])
            else:
                tags = []
            lfm_tags[tid] = tags
            # opcional: logging cada 100
        print(f"[Last.fm] Completado batch {bidx+1}/{batches_lfm}")
        with open("lastfm_tags.json", "w", encoding="utf-8") as fout:
            json.dump(lfm_tags, fout, indent=2, ensure_ascii=False)
        print(f"📁 lastfm_tags.json guardado tras batch {bidx+1}.")
        time.sleep(0.2)
except Exception as e:
    print(f"\n❌ Error en fase Last.fm: {e}")
    with open("lastfm_tags.json", "w", encoding="utf-8") as fout:
        json.dump(lfm_tags, fout, indent=2, ensure_ascii=False)
    print("📁 lastfm_tags.json guardado tras interrupción en fase 2.\n")
    sys.exit(1)

print("✅ Fase 2 completada: 'lastfm_tags.json' generado.\n")

# ------------------------------------------------------------
# 6) Construir enriched_challenge_set.json
# ------------------------------------------------------------
enriched = {
    "version": challenge.get("version"),
    "date":    challenge.get("date"),
    "playlists": []
}
for pl in playlists:
    new_pl = pl.copy()
    new_tracks = []
    for tr in pl["tracks"]:
        tid = tr["track_uri"].split(":")[-1]
        new_tr = tr.copy()
        new_tr.update(sp_metadata.get(tid, {}))
        new_tr["lastfm_tags"] = lfm_tags.get(tid, [])
        new_tracks.append(new_tr)
    new_pl["tracks"] = new_tracks
    enriched["playlists"].append(new_pl)

with open("enriched_challenge_set.json", "w", encoding="utf-8") as fout:
    json.dump(enriched, fout, indent=2, ensure_ascii=False)
print("✅ enriched_challenge_set.json generado.\n")
