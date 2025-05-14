#!/usr/bin/env python3
"""
enrich_challenge_set_acousticbrainz.py

Lee spotify_metadata.json (fase 1 ya ejecutada),
luego consulta MusicBrainz (solo por nombre+artista) y AcousticBrainz
para extraer únicamente los campos requeridos:
  - MusicBrainz: primer tag (genre) y rating (value + votes-count)
  - AcousticBrainz low-level: bpm, dynamic_complexity, danceability, average_loudness
  - AcousticBrainz high-level: top genre, danceability, mood_happy, acousticness
Respetando el rate limit de MusicBrainz (1 req/s por IP),
paraleliza llamadas a AcousticBrainz (8 hilos),
logea progreso, guarda al detectar interrupción o fallo,
y reanuda desde el JSON parcial.
"""

import os
import sys
import time
import json
from math import ceil
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

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
    client_id=SPOTI_ID, client_secret=SPOTI_SECRET))

musicbrainzngs.set_useragent("enrichAB", "1.0", "tu_email@dominio.com")

# ------------------------------------------------------------
# 2) Throttling para MusicBrainz (1 req/s)
# ------------------------------------------------------------
_mb_last_request = 0.0
def _throttle_mb():
    global _mb_last_request
    now = time.time()
    elapsed = now - _mb_last_request
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _mb_last_request = time.time()

# ------------------------------------------------------------
# 3) Sesión y executor para AcousticBrainz
# ------------------------------------------------------------
AB_SESSION = requests.Session()
acoustic_executor = ThreadPoolExecutor(max_workers=8)

# ------------------------------------------------------------
# 4) Funciones para MusicBrainz y AcousticBrainz
# ------------------------------------------------------------
def get_mb_info(track_name, artist_name):
    """
    Busca recording por nombre+artista e incluye tags y rating en una sola llamada.
    Devuelve (mbid, genre, rating_value, rating_votes) o (None,None,None,None).
    """
    try:
        _throttle_mb()
        res = musicbrainzngs.search_recordings(
            recording=track_name,
            artist=artist_name,
            limit=1,
            includes=["tags","rating"]
        )
        recs = res.get("recording-list", [])
        if not recs:
            return None, None, None, None
        rec = recs[0]
        mbid = rec.get("id")
        raw_tags = rec.get("tag-list", [])
        tags_list = [raw_tags] if isinstance(raw_tags, dict) else raw_tags
        tags_sorted = sorted(
            tags_list,
            key=lambda t: int(t.get("count",0)),
            reverse=True
        )
        genre = tags_sorted[0].get("name") if tags_sorted else None
        rating = rec.get("rating", {})
        return mbid, genre, rating.get("value"), rating.get("votes-count")
    except:
        return None, None, None, None

def fetch_acousticbrainz(mbid):
    """
    Obtiene low-level y high-level de AcousticBrainz para un MBID dado.
    """
    base = "https://acousticbrainz.org"
    try:
        ll = AB_SESSION.get(f"{base}/{mbid}/low-level", timeout=10)
        ll.raise_for_status()
        hl = AB_SESSION.get(f"{base}/{mbid}/high-level", timeout=10)
        hl.raise_for_status()
        return ll.json(), hl.json()
    except:
        return {}, {}

def select_top_genre(highlevel):
    """
    De highlevel dict, selecciona la clave genre_* con mayor probability.
    """
    if not isinstance(highlevel, dict):
        return None
    probs = {}
    for k, v in highlevel.items():
        if k.startswith("genre_") and isinstance(v, dict) and "probability" in v:
            try:
                probs[k] = float(v["probability"])
            except:
                continue
    return max(probs, key=probs.get) if probs else None

# ------------------------------------------------------------
# 5) Carga challenge_set y spotify_metadata
# ------------------------------------------------------------
with open("challenge_set.json","r",encoding="utf-8") as f:
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

with open("spotify_metadata.json","r",encoding="utf-8") as f:
    sp_meta = json.load(f)

# ------------------------------------------------------------
# 6) Reanudación desde archivo parcial
# ------------------------------------------------------------
data_file = "acousticbrainz_data.json"
if os.path.exists(data_file):
    with open(data_file,"r",encoding="utf-8") as fin:
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
        batch = remaining[start:start+batch_size]
        print(f"[Batch {b+1}/{batches}] pistas {start+1}-{start+len(batch)}")

        for i, tid in enumerate(batch, start=start+1):
            elapsed = time.time() - start_time
            print(f" ▶ [{i}/{total}] {tid} – {elapsed:.1f}s")

            meta   = sp_meta.get(tid, {})
            name   = meta.get("track_name","")
            artist = meta.get("artist_name","")

            mbid, genre_mb, rating_val, rating_cnt = get_mb_info(name, artist)

            bpm = energy = dance_ll = loudness = None
            dance_hl = mood_happy = acousticness = None
            top_genre_hl = None

            if mbid:
                future = acoustic_executor.submit(fetch_acousticbrainz, mbid)
                ll, hl = future.result()
                bpm            = ll.get("rhythm",{}).get("bpm")
                energy         = ll.get("lowlevel",{}).get("dynamic_complexity")
                dance_ll       = ll.get("rhythm",{}).get("danceability")
                loudness       = ll.get("lowlevel",{}).get("average_loudness")
                dance_hl       = hl.get("highlevel",{}).get("danceability")
                mood_happy     = hl.get("highlevel",{}).get("mood_happy")
                acousticness   = hl.get("highlevel",{}).get("acousticness")
                top_genre_hl   = select_top_genre(hl.get("highlevel",{}))

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

        with open(data_file,"w",encoding="utf-8") as fout:
            json.dump(abz_data,fout,indent=2,ensure_ascii=False)
        print(f"✅ Guardado '{data_file}' tras batch {b+1}\n")
        time.sleep(0.1)  # descansa entre batches

except KeyboardInterrupt:
    print("\n⏸️ Interrumpido. Guardando…")
    with open(data_file,"w",encoding="utf-8") as fout:
        json.dump(abz_data,fout,indent=2,ensure_ascii=False)
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Error inesperado: {e}\nGuardando…")
    with open(data_file,"w",encoding="utf-8") as fout:
        json.dump(abz_data,fout,indent=2,ensure_ascii=False)
    sys.exit(1)

print(f"\n✅ Completado en {(time.time()-start_time)/60:.1f} min.")
