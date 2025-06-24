### Ruta paso a paso para tu **pipeline de análisis, reglas de asociación y clustering**

> **Supuestos de hardware**
> • Laptop/PC con 8–12 GB RAM y 4–8 núcleos CPU
> • Sin GPU: los tiempos que doy son *orientativos* (±30 %).
> • Trabajarás dentro de un entorno `venv` con *pandas*, *numpy*, *scikit-learn*, *mlxtend*, *scipy*, *seaborn/plotly*.

---

## 1 · Ingesta y organización de datos

| Paso                                                | Qué haces                                                                              | Dónde queda el código      | Tiempo de **dev** | Tiempo **runtime** |
| --------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------- | ----------------- | ------------------ |
| 1.1 Cargar `challenge_set.json`                     | Iterar playlists, almacenar `pid`, `name`, `tracks` en listas y normalizar a DataFrame | `src/01_load_playlists.py` | 1 h               | < 5 min            |
| 1.2 Filtrar playlists vacías                        | `df_playlists = df_playlists[df_playlists.num_tracks>0]`                               | —                          | 10 min            | instante           |
| 1.3 Cargar `acousticbrainz_data_updated_clean.json` | Crear dict → DataFrame (una fila/track)                                                | `src/02_load_acoustic.py`  | 1 h               | < 10 min           |
| 1.4 “Expandir” playlists a nivel track              | `playlist_tracks = df_playlists.explode('tracks')` → normalizar columnas track         | `src/03_flatten.py`        | 1 h               | 3–5 min            |
| 1.5 Integrar metadata + audio features              | `pd.merge` por `track_uri`                                                             | —                          | 30 min            | < 5 min            |

> 🔑 **Resultado**:
> • `tracks_df.csv` (≈ 66 k filas × \~150 columnas)
> • `playlists_df.csv` (≈ 10 k playlists)
> • `playlist_track_df.csv` (≈ 650 k filas)

---

## 2 · Análisis exploratorio (EDA)

1. **Distribución de longitud de playlists**

   ```python
   playlist_track_df.groupby('pid').size().hist()
   ```

   * Media \~65, máx 100, min 1.

2. **Análisis de géneros / moods**

   * Contar `highlevel.genre_dortmund.value`, `mood_party.value`, etc.
   * *Pareto* de los 10 géneros más frecuentes.

3. **Correlaciones numéricas** (`bpm`, `energy`, `danceability_ll`, `loudness`, …).

   * Heatmap Pearson / Spearman.
   * Detectar pares muy colineales para PCA.

4. **Outliers numéricos**

   * Boxplots por variable.
   * Z-score > 3 o IQR × 1.5 → marcar.

5. **Valores faltantes**

   * Tabla `% missing` por columna.
   * Variables con > 20 % vacíos: eliminar o imputar con media/mediana (dependiendo).

> ⏱️ **Tiempos**: 4–6 h (explorar + graficar) · ejecución de celdas << 5 min.

---

## 3 · Preprocesamiento

| Tarea                         | Herramienta / técnica                                                   | Notas                               | Dev    | Run           |
| ----------------------------- | ----------------------------------------------------------------------- | ----------------------------------- | ------ | ------------- |
| Eliminar duplicados de tracks | `tracks_df.drop_duplicates('track_uri')`                                | —                                   | 5 min  | instante      |
| Normalizar numéricos          | `StandardScaler` o `MinMaxScaler`                                       | Guardar *scaler* con `joblib`       | 15 min | 1 min         |
| Tratamiento de NA             | `SimpleImputer` media/mediana; o drop columnas con > 30 % NA            | —                                   | 20 min | 1 min         |
| Outliers                      | Winsorizar o recortar                                                   | Opcional para clustering            | 30 min | 1 min         |
| Discretizar para asociación   | `KBinsDiscretizer` o percentiles para `bpm`, `energy` (alto/medio/bajo) | Genera columnas tipo `bpm_high`=1/0 | 45 min | 2 min         |
| Binarizar pista-playlist      | `MultiLabelBinarizer` sobre `track_uri` ó sobre *tags*                  | Sparse matrix 10 k × 66 k           | 45 min | \~10 min      |
| Reducción de dimensionalidad  | PCA (k=50) para numéricos; UMAP/t-SNE 2 D para visual                   | Para graficar clusters              | 1 h    | UMAP 5–10 min |

> ⏱️ **Bloque completo**: 4–6 h dev · 15–30 min runtime.

---

## 4 · Reglas de asociación

### 4.1 Preparar transacciones

* **Opción 1 (clásica):** cada playlist = conjunto de `track_uri`.
* **Opción 2 (semántica):** agrupa por `genre_highlevel` o `mood_party` → transacciones más cortas.

### 4.2 Algoritmos

| Algoritmo             | Librería                             | Soporte inicial         | Tiempo *(10 k tx)* |
| --------------------- | ------------------------------------ | ----------------------- | ------------------ |
| **Apriori** (Agrawal) | `mlxtend.frequent_patterns.apriori`  | `min_support` 0.01–0.02 | 2–8 min            |
| **FP-Growth**         | `mlxtend.frequent_patterns.fpgrowth` | `min_support` igual     | 1–5 min            |

> Conjuntos frecuentes → `association_rules()` (confianza, lift).
> Ordena por *lift* > 1 y muestra top 20.

### 4.3 Entregables

* Tabla CSV “reglas\_significativas.csv”.
* Gráfico red de reglas (source → target, grosor=lift).
* Discusión: *“Las playlists ‘Party’ presentan co-ocurrencia alta entre tracks con `genre_dortmund=electronic` y `mood_party=party` (lift = 3.2)…”*.

> ⏱️ **Dev** 2–3 h · **Ejecución** 5–15 min (dependiendo soporte).

---

## 5 · Clustering (agrupación)

### 5.1 Features de entrada

| Nivel        | Vector                                                                      | Dimensión típica |
| ------------ | --------------------------------------------------------------------------- | ---------------- |
| **Track**    | `[bpm, energy, danceability_ll, loudness, …]`                               | 10–30            |
| **Playlist** | Promedio/mediana de features de sus canciones + proporción de géneros/moods | 30–60            |

### 5.2 Algoritmos mínimos (3)

| Algoritmo         | `sklearn` clase           | Hiperparámetros                        | Ventajas                             |
| ----------------- | ------------------------- | -------------------------------------- | ------------------------------------ |
| **K-Means**       | `KMeans`                  | `k` = 8–15 (usar *elbow* + Silhouette) | Rápido, baseline                     |
| **DBSCAN**        | `DBSCAN`                  | `eps`, `min_samples` (tune con k-dist) | Detecta densidades; identifica ruido |
| **Agglomerative** | `AgglomerativeClustering` | `linkage='ward'`, `n_clusters` = k     | Visualizable con dendrograma         |

*(Opcional bonus: Gaussian Mixture o HDBSCAN).*

### 5.3 Evaluación

* **Internas:** Silhouette Score, Davies-Bouldin.
* **Externas:** si tuvieras etiqueta “género dominante” podrías usar *Adjusted Rand*.
* Tabla comparativa.

### 5.4 Visualización

* Reducir a 2 D con UMAP → color por cluster.
* Gráfica radar por cluster con medias de `energy`, `danceability_ll`, etc.

> ⏱️ **Dev** 3–4 h · **Train + métricas** 5–20 min (UMAP \~10 min).

---

## 6 · Informe final y discusión

1. **Introducción** (objetivo, dataset).
2. **EDA** (hallazgos clave, gráficas).
3. **Preprocesamiento** (qué hiciste y por qué).
4. **Reglas de asociación** (metodología, top reglas, aplicación práctica: recomendar canciones).
5. **Clustering** (métodos, parámetros, comparativa, interpretación de clusters).
6. **Conclusiones** (limitaciones, trabajo futuro).

> ⏱️ Redacción + figuras: 1 día.

---

## Cronograma sugerido (en días de trabajo intensivo)

| Día   | Horas estimadas | Entregable                                      |
| ----- | --------------- | ----------------------------------------------- |
| **1** | 6–8 h           | Carga de datos + EDA preliminar                 |
| **2** | 6–7 h           | Preprocesamiento completo                       |
| **3** | 5 h             | Reglas de asociación + discusión                |
| **4** | 6 h             | Feature playlist-level + clustering             |
| **5** | 6 h             | Comparativas, visualizaciones, pulir resultados |
| **6** | 8 h             | Redactar informe y preparar slides/notebook     |

Total ≈ **37–40 h** (una semana laboral). Ajusta según tu familiaridad con *pandas* y *scikit-learn*.

---

### Consejos prácticos

* **Trabaja en notebooks Jupyter** para EDA y prototipos; pasa lo estable a scripts en `src/`.
* **Guarda artefactos intermedios** (`.pkl` de DataFrames, scaler, modelos) para no recalcular.
* Usa **`pd.read_json(..., lines=True)`** si conviertes los JSON a *jsonl*; consume menos RAM.
* Para la **matriz playlist-track**, usa `scipy.sparse.csr_matrix` para que Apriori/FP-Growth no reviente memoria.
* Fija semillas (`random_state`) y documenta versiones (`pip freeze > requirements_locked.txt`).

¡Con esto tienes un plan claro, tiempos estimados y el mapa de código que necesitas para completar tu proyecto de minería de datos de principio a fin!
