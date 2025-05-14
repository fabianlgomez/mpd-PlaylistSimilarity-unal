import json
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# 1) Configuración de credenciales (asegúrate de exportar tus variables de entorno)
client_credentials_manager = SpotifyClientCredentials()
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# 2) Cargar el challenge set
with open('challenge_set.json', 'r') as f:
    data = json.load(f)
playlists = data['playlists']

# 3) Extraer track IDs por playlist
playlist_tracks = {
    pl['pid']: [track['track_uri'].split(':')[-1] for track in pl['tracks']]
    for pl in playlists if pl['num_samples'] > 0
}

# 4) Obtener la lista única de track IDs
unique_track_ids = list({tid for tracks in playlist_tracks.values() for tid in tracks})

# 5) Recuperar metadata y audio features en lotes de 50
records = []
for i in range(0, len(unique_track_ids), 50):
    batch = unique_track_ids[i:i+50]
    metas = sp.tracks(batch)['tracks']
    feats = sp.audio_features(batch)
    
    # Para cada track, además recuperamos géneros del primer artista
    artist_ids = [m['artists'][0]['id'] for m in metas]
    artists = sp.artists(artist_ids)['artists']
    
    for m, f, artist in zip(metas, feats, artists):
        records.append({
            'track_id': m['id'],
            'track_name': m['name'],
            'artist_id': artist['id'],
            'artist_name': artist['name'],
            'album_id': m['album']['id'],
            'album_name': m['album']['name'],
            'genres': artist.get('genres', []),
            'popularity': m['popularity'],
            'danceability': f['danceability'],
            'energy': f['energy'],
            'valence': f['valence'],
            'tempo': f['tempo'],
            'loudness': f['loudness']
        })

# 6) Crear DataFrame con toda la metadata
df_tracks = pd.DataFrame(records)

# 7) Agregar métricas por playlist
playlist_stats = []
for pid, tids in playlist_tracks.items():
    df_pl = df_tracks[df_tracks['track_id'].isin(tids)]
    all_genres = sum(df_pl['genres'].tolist(), [])
    predominant_genre = max(set(all_genres), key=all_genres.count) if all_genres else None
    
    playlist_stats.append({
        'pid': pid,
        'n_tracks': len(df_pl),
        'predominant_genre': predominant_genre,
        'avg_popularity': df_pl['popularity'].mean(),
        'avg_valence': df_pl['valence'].mean(),
        'avg_energy': df_pl['energy'].mean()
    })

df_playlist_stats = pd.DataFrame(playlist_stats)

# Mostrar resultados
import ace_tools as tools; tools.display_dataframe_to_user(name="Resumen por Playlist", dataframe=df_playlist_stats)
