#!/usr/bin/env python3
"""
enrich_challenge_set_acousticbrainz.py

Lee spotify_metadata.json (fase 1 ya ejecutada),
luego consulta AcousticBrainz para extraer low-level y high-level,
logea progress por canción y batch, muestra tiempo transcurrido,
guarda progreso inmediato al detectar KeyboardInterrupt o cualquier fallo,
y reanuda ejecuciones posteriores desde el JSON parcial.
Ahora también guarda el ISRC y el MBID usados en cada entrada.
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
# 1) Carga de credenciales y user-agent
# ------------------------------------------------------------
load_dotenv()
SPOTI_ID     = os.getenv("SPOTIPY_CLIENT_ID")
SPOTI_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
if not (SPOTI_ID and SPOTI_SECRET):
    sys.exit("❌ Define SPOTIPY_CLIENT_ID y SPOTIPY_CLIENT_SECRET en tu .env")

# Spotify (solo para fallback de ISRC)
creds = SpotifyClientCredentials(client_id=SPOTI_ID,
                                 client_secret=SPOTI_SECRET)
sp    = spotipy.Spotify(client_credentials_manager=creds)

# MusicBrainz para resolver MBID vía ISRC
musicbrainzngs.set_useragent("enrichAB", "1.0", "tu_email@dominio.com")

# ------------------------------------------------------------
# 2) Funciones AcousticBrainz
# ------------------------------------------------------------
def get_mbid_from_isrc(isrc):
    try:
        recs = musicbrainzngs.get_recordings_by_isrc(isrc)["recording-list"]
        return recs[0]["id"] if recs else None
    except Exception:
        return None

def fetch_acousticbrainz(mbid):
    base = "https://acousticbrainz.org"
    try:
        ll_resp = requests.get(f"{base}/{mbid}/low-level")
        hl_resp = requests.get(f"{base}/{mbid}/high-level")
        ll_resp.raise_for_status()
        hl_resp.raise_for_status()
        return ll_resp.json(), hl_resp.json()
    except Exception:
        return None, None

# ------------------------------------------------------------
# 3) Carga challenge_set y spotify_metadata
# ------------------------------------------------------------
with open("challenge_set.json", "r", encoding="utf-8") as f:
    challenge = json.load(f)
playlists = challenge["playlists"]

# extrae IDs únicos en orden
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

# lee metadata de Spotify (fase 1)
with open("spotify_metadata.json", "r", encoding="utf-8") as f:
    sp_meta = json.load(f)

# ------------------------------------------------------------
# 4) Preparar reanudación desde archivo parcial
# ------------------------------------------------------------
data_file = "acousticbrainz_data.json"
if os.path.exists(data_file):
    with open(data_file, "r", encoding="utf-8") as fin:
        abz_data = json.load(fin)
    processed = set(abz_data.keys())
    print(f"🔄 Reanudando: {len(processed)}/{total} ya procesadas.")
else:
    abz_data = {}
    processed = set()
print(f"⏳ Quedan {total - len(processed)}/{total} por procesar.\n")

remaining = [tid for tid in all_ids if tid not in processed]
batch_size = 500
batches    = ceil(len(remaining) / batch_size)
start_time = time.time()

# ------------------------------------------------------------
# 5) Fase AcousticBrainz con logging y guardado inmediato
# ------------------------------------------------------------
try:
    for b in range(batches):
        b_start = b * batch_size
        batch   = remaining[b_start : b_start + batch_size]
        print(f"[AB] Batch {b+1}/{batches}: tracks {b_start+1}–{b_start+len(batch)}")

        for idx, tid in enumerate(batch, start=b_start+1):
            elapsed = time.time() - start_time
            print(f"    ▶ [{idx}/{total}] ID={tid} – {elapsed:.1f}s elapsed")

            # 1) ISRC (fallback si no existe en sp_meta)
            isrc = sp_meta.get(tid, {}).get("isrc")
            if not isrc:
                try:
                    rec = sp.track(tid)
                    isrc = rec.get("external_ids", {}).get("isrc")
                except Exception:
                    isrc = None

            # 2) MBID
            mbid = get_mbid_from_isrc(isrc) if isrc else None

            # 3) AcousticBrainz
            ll, hl = (None, None)
            if mbid:
                ll, hl = fetch_acousticbrainz(mbid)

            # Guardar también isrc y mbid
            abz_data[tid] = {
                "isrc":       isrc,
                "mbid":       mbid,
                "low_level":  ll,
                "high_level": hl
            }

        # guardado intermedio tras cada batch
        with open(data_file, "w", encoding="utf-8") as fout:
            json.dump(abz_data, fout, indent=2, ensure_ascii=False)
        print(f"[AB] Guardado '{data_file}' tras batch {b+1}\n")
        time.sleep(0.1)

except KeyboardInterrupt:
    print(f"\n⏸️  Interrumpido por usuario. Guardando progreso en '{data_file}'…")
    with open(data_file, "w", encoding="utf-8") as fout:
        json.dump(abz_data, fout, indent=2, ensure_ascii=False)
    print("✅ Progreso guardado. Reanuda ejecuciones posteriores.")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Error inesperado: {e}\nGuardando progreso en '{data_file}'…")
    with open(data_file, "w", encoding="utf-8") as fout:
        json.dump(abz_data, fout, indent=2, ensure_ascii=False)
    sys.exit(1)

total_elapsed = time.time() - start_time
print(f"\n✅ Fase AcousticBrainz completada en {total_elapsed/60:.1f} min.")
