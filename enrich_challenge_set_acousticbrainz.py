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
    client_id=SPOTI_ID, client_secret=SPOTI_SECRET))

musicbrainzngs.set_useragent("enrichAB", "1.0", "tu_email@dominio.com")

# ------------------------------------------------------------
# 2) Funciones para MBID, MusicBrainz y AcousticBrainz
# ------------------------------------------------------------
def get_mbid_from_name(track_name, artist_name):
    try:
        res = musicbrainzngs.search_recordings(recording=track_name,
                                               artist=artist_name,
                                               limit=1)
        recs = res.get("recording-list", [])
        return recs[0]["id"] if recs else None
    except:
        return None

def fetch_mb_genre_and_rating(mbid):
    try:
        rec = musicbrainzngs.get_recording_by_id(mbid,
            includes=["tags","rating"])
        r = rec["recording"]
        tags = sorted(r.get("tag-list", []),
                      key=lambda t: int(t.get("count",0)),
                      reverse=True)
        genre = tags[0]["name"] if tags else None
        rating = r.get("rating", {})
        return genre, rating.get("value"), rating.get("votes-count")
    except:
        return None, None, None

def fetch_acousticbrainz(mbid):
    base = "https://acousticbrainz.org"
    try:
        ll = requests.get(f"{base}/{mbid}/low-level"); ll.raise_for_status(); ll=ll.json()
        hl = requests.get(f"{base}/{mbid}/high-level"); hl.raise_for_status(); hl=hl.json()
        return ll, hl
    except:
        return {}, {}

def select_top_genre(highlevel):
    genres = {k:v for k,v in highlevel.items() if k.startswith("genre_")}
    return max(genres, key=genres.get) if genres else None

# ------------------------------------------------------------
# 3) Carga challenge_set y spotify_metadata
# ------------------------------------------------------------
with open("challenge_set.json","r",encoding="utf-8") as f:
    challenge = json.load(f)
playlists = challenge["playlists"]

all_ids, seen = [], set()
for pl in playlists:
    for tr in pl["tracks"]:
        tid = tr["track_uri"].split(":")[-1]
        if tid not in seen:
            seen.add(tid); all_ids.append(tid)
total = len(all_ids)
print(f"➡️  {total} pistas únicas encontradas.\n")

with open("spotify_metadata.json","r",encoding="utf-8") as f:
    sp_meta = json.load(f)

# ------------------------------------------------------------
# 4) Reanudación desde archivo parcial
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
# 5) Procesar cada batch
# ------------------------------------------------------------
try:
    for b in range(batches):
        start = b * batch_size
        batch = remaining[start:start+batch_size]
        print(f"[Batch {b+1}/{batches}] pistas {start+1}-{start+len(batch)}")

        for i, tid in enumerate(batch, start=start+1):
            elapsed = time.time() - start_time
            print(f" ▶ [{i}/{total}] {tid} – {elapsed:.1f}s")

            meta = sp_meta.get(tid,{})
            name   = meta.get("track_name","")
            artist = meta.get("artist_name","")

            mbid = get_mbid_from_name(name, artist)

            genre_mb, rating_val, rating_cnt = (None,None,None)
            bpm = energy = dance_ll = loudness = None
            dance_hl = mood_happy = acousticness = None
            top_genre_hl = None

            if mbid:
                # MusicBrainz
                genre_mb, rating_val, rating_cnt = fetch_mb_genre_and_rating(mbid)
                # AcousticBrainz
                ll, hl = fetch_acousticbrainz(mbid)
                # low-level
                bpm            = ll.get("rhythm",{}).get("bpm")
                energy         = ll.get("lowlevel",{}).get("dynamic_complexity")
                dance_ll       = ll.get("rhythm",{}).get("danceability")
                loudness       = ll.get("lowlevel",{}).get("average_loudness")
                # high-level
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
        time.sleep(0.1)

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
