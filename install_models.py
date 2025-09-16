#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instalador automático de modelos Vosk
Descarga y descomprime los modelos necesarios en la carpeta ./models/

Modelos soportados (ejemplo inicial):
- Español (vosk-model-small-es-0.42)
- Inglés  (vosk-model-small-en-us-0.15)

Uso:
  python install_models.py --lang es
  python install_models.py --lang en
  python install_models.py --all
"""

import os
import sys
import zipfile
import argparse
import urllib.request

MODELS = {
    "es": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
        "folder": "vosk-es",
    },
    "en": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "folder": "vosk-en",
    },
}

def download_and_extract(lang: str, dest_dir="models"):
    if lang not in MODELS:
        print(f"✗ Idioma {lang} no soportado. Usa: {list(MODELS.keys())}")
        return

    url = MODELS[lang]["url"]
    folder = MODELS[lang]["folder"]
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, f"{folder}.zip")
    target_folder = os.path.join(dest_dir, folder)

    # Si ya existe, no descargamos de nuevo
    if os.path.isdir(target_folder):
        print(f"✓ Modelo {lang} ya está instalado en {target_folder}")
        return

    print(f"\nDescargando modelo {lang} desde:\n {url}")
    urllib.request.urlretrieve(url, zip_path)

    print("Descomprimiendo…")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(dest_dir)

    # Busca la carpeta real dentro del ZIP
    extracted_folder = None
    for name in os.listdir(dest_dir):
        if name.startswith("vosk-model-") and os.path.isdir(os.path.join(dest_dir, name)):
            extracted_folder = os.path.join(dest_dir, name)
            break

    if not extracted_folder:
        print("✗ No se pudo encontrar la carpeta del modelo extraído.")
        return

    os.rename(extracted_folder, target_folder)
    os.remove(zip_path)
    print(f"✓ Instalado modelo {lang} en {target_folder}")

def main():
    parser = argparse.ArgumentParser(description="Instalador de modelos Vosk")
    parser.add_argument("--lang", choices=["es", "en"], help="Idioma a instalar (es|en)")
    parser.add_argument("--all", action="store_true", help="Instalar todos los modelos disponibles")
    args = parser.parse_args()

    if args.all:
        for lang in MODELS.keys():
            download_and_extract(lang)
    elif args.lang:
        download_and_extract(args.lang)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
