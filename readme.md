# Million Playlist Dataset Challenge Analysis

Este repositorio contiene el pipeline para analizar el **challenge set** (10.000 playlists parciales) del Million Playlist Dataset (MPD) de Spotify, con el fin de extraer atributos musicales (géneros, popularidad, mood, etc.) y generar estadísticas por playlist.

---



---

## 🛠️ Requisitos previos

- Python **>= 3.8**
- **pip**
- **virtualenv** (incluido en la librería estándar `venv`)
- Claves de API de Spotify (Client ID y Client Secret)

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
   ```

---

## 📊 Uso

1. **Descargar metadata y audio features**
   ```bash
   python src/extract_metadata.py --input challenge_set.json --output tracks_metadata.csv
   ```

2. **Abrir el Jupyter Notebook**
   ```bash
   jupyter lab
   ```
   - Abre `notebooks/analysis.ipynb` y ejecuta todas las celdas.

3. **Generar estadísticas por playlist**
   - El notebook produce `playlist_stats.csv` con columnas:
     - `pid`: ID de la playlist
     - `predominant_genre`
     - `avg_popularity`, `avg_valence`, `avg_energy`, etc.

---

## 🔗 Recursos

- [Million Playlist Dataset (MPD) ](https://www.kaggle.com/datasets/himanshuwagh/spotify-million)
- (https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge)
- [Spotipy – Python library for Spotify Web API](https://spotipy.readthedocs.io/)

---

## ⚖️ Licencia

Este proyecto está bajo la licencia MIT. Revisa el archivo `LICENSE` para más detalles.
