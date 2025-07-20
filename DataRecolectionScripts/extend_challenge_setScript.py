import json

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def enrich_challenge_with_acoustic(challenge_path, acoustic_path, output_path):
    # 1. Carga de los JSON
    challenge = load_json(challenge_path)
    acoustic = load_json(acoustic_path)

    # 2. Recorre cada playlist y cada pista
    for playlist in challenge.get('playlists', []):
        for track in playlist.get('tracks', []):
            # Extrae el código que coincide con la clave de acoustic
            # Si el campo track_uri viene como 'spotify:track:XYZ', toma solo 'XYZ'.
            uri = track.get('track_uri', '')
            track_id = uri.split(':')[-1] if ':' in uri else uri

            # Busca en acoustic; si no existe, deja None o maneja como prefieras
            features = acoustic.get(track_id)
            track['acoustic_features'] = features  # puede ser un dict o None

    # 3. Escribe el JSON enriquecido a disco
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(challenge, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    enrich_challenge_with_acoustic(
        'challenge_set.json',
        'acousticbrainz_data_updated_clean.json',
        'challenge_set_enriched.json'
    )
    print("¡Listo! Se ha generado challenge_set_enriched.json con los datos acústicos.")
