# mpd-PlaylistSimilarity-unal

Este repositorio contiene un pipeline de minería de datos el cuál se desarrolló como proyecto para la materia Minería de Datos de la UNAL-Sede Bogotá , enfocado en analizar el **challenge set** (10.000 playlists parciales) del Million Playlist Dataset (MPD) de Spotify y medir la **similitud** entre playlists. Utiliza atributos musicales (géneros, popularidad, danceability, energy, valence, tempo, etc.) y técnicas de clustering y similitud para descubrir patrones y agrupar playlists con gustos afines.

---  

---



---

## 🛠️ Requisitos previos

- Python **>= 3.8**
- **pip**
- **virtualenv** (incluido en la librería estándar `venv`)
- Claves de API de Spotify (Client ID y Client Secret)
- Claves de API de AcousticBrainz

---

## 🚀 Instalación (venv + pip)

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/mpd-challenge-analysis.git
   cd mpd-challenge-analysis
   ```

2. **Crear y activar el entorno virtual**
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # macOS/Linux
   # .\venv\Scripts\Activate.ps1  # Windows PowerShell
   ```

3. **Actualizar pip e instalar dependencias**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   Crea un archivo `.env` en la raíz del proyecto con:
   ```env
   SPOTIPY_CLIENT_ID=tu_client_id
   SPOTIPY_CLIENT_SECRET=tu_client_secret
   LASTFM_API_KEY=tu_lastfm_api_key         # si usas Last.fm
   ```

---

## 📊 Uso

1. **Descargar metadata y audio features**
   ```bash
   python src/extract_metadata.py --input challenge_set.json --output tracks_metadata.csv
   ```
ON PROGRESS...

---

## 🔗 Recursos

- [Million Playlist Dataset (MPD) ](https://www.kaggle.com/datasets/himanshuwagh/spotify-million)
- [RecSys Challenge 2018 en AIcrowd](https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge)
- [Spotipy – Python library for Spotify Web API](https://spotipy.readthedocs.io/)
- [AcousticBrainz API](https://acousticbrainz.org/data)
- [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API)
- [Last.FM API](https://www.last.fm/api)
---
## 📌 API de Spotify y de terceros

**Deprecación de Audio Features & Audio Analysis (27 Nov 2024):**  
Spotify anunció el 27 de noviembre de 2024 que los endpoints **Get Several Tracks' Audio Features** y **Get Track's Audio Analysis** han sido **deprecados para nuevas aplicaciones**. Solo las aplicaciones que contaban con **acceso extendido** antes de esa fecha pueden seguir utilizándolos.  
*Más info: [https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api)*

**Por ello el pipeline también integra:**

- **Last.fm API**: para obtener géneros y etiquetas comunitarias (tags).
- **AcousticBrainz API**: para extraer atributos **low-level** (danceability, energy, loudness, tempo…) y **high-level** (moods: happy, sad, party, acoustic…) de forma gratuita y abierta.


## ⚖️ Licencia

Este proyecto está bajo la licencia MIT. Revisa el archivo `LICENSE` para más detalles.
