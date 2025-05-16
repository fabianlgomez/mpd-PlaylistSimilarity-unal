#!/usr/bin/env python3
import json
import sys

def remove_versions_from_highlevel(input_path: str, output_path: str):
    """
    Carga el JSON de AcousticBrainz, elimina todas las claves "version"
    dentro de cada subobjeto de "highlevel" para cada pista, y guarda el resultado.
    """
    # 1) Leer el JSON existente
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2) Iterar por cada pista
    for track_id, track_data in data.items():
        hl = track_data.get("highlevel")
        if isinstance(hl, dict):
            # 3) Para cada característica en highlevel, borrar la clave "version"
            for feature_name, feature_data in hl.items():
                if isinstance(feature_data, dict) and "version" in feature_data:
                    del feature_data["version"]

    # 4) Volcar el JSON modificado
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # if len(sys.argv) != 3:
    #     # print("Uso: python clean_highlevel_versions.py <input_json> <output_json>")
    #     sys.exit(1)
    # inp, outp = sys.argv[1], sys.argv[2]
    inp = "acousticbrainz_data_updated.json"
    outp = "acousticbrainz_data_updated_clean.json"
    remove_versions_from_highlevel(inp, outp)
    print(f"Procesado '{inp}', generado '{outp}' sin claves 'version' en highlevel.")
