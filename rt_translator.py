#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Traductor offline (casi tiempo real) por bloques
- ASR: Vosk (streaming 16 kHz mono)
- VAD: umbral de energía (sin dependencias nativas)
- MT : Argos Translate 1.9.x (usa idiomas instalados ES<->EN)
- TTS: condicional por plataforma
       * Windows → pyttsx3 con motor EFÍMERO por frase (estable)
       * Linux/RPi → py-espeak-ng (preferente); fallback pyttsx3; último recurso: print

Modelos:
  - Vosk: descomprime en models/vosk-es (ES) y/o models/vosk-en (EN)
  - Argos: instala pares ES->EN y EN->ES (usa install_argos.py)

Uso:
  python rt_translator.py --in_model models/vosk-es --src es --tgt en
  python rt_translator.py --in_model models/vosk-en --src en --tgt es
  python rt_translator.py --list
  python rt_translator.py --in_device 2 --out_device 5
  python rt_translator.py --partials   (activa traducciones parciales)
"""

import os
import sys
import json
import time
import queue
import threading
import argparse
import platform

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import argostranslate.translate as tr

# =============== Import condicional TTS ===============
IS_WINDOWS = platform.system().lower().startswith("win")
PYTTSX3 = None
ESPEAKNG = None

if IS_WINDOWS:
    try:
        import pyttsx3 as PYTTSX3
    except Exception as e:
        PYTTSX3 = None
        print(f"⚠️  pyttsx3 no disponible en Windows: {e}", file=sys.stderr)
else:
    # Linux/RPi: preferimos espeak-ng
    try:
        import espeakng as ESPEAKNG
    except Exception as e:
        ESPEAKNG = None
        # Intentamos pyttsx3 como fallback
        try:
            import pyttsx3 as PYTTSX3
        except Exception as e2:
            PYTTSX3 = None
            print("⚠️  Ni py-espeak-ng ni pyttsx3 disponibles; TTS hará print.", file=sys.stderr)
# ======================================================


# ================== Parámetros ajustables ==================
SAMPLE_RATE   = 16000   # 16 kHz mono
BLOCK_MS      = 30      # 10/20/30 ms. 30=estable
PAUSE_MS      = 800     # silencio para cerrar frase (ms). 600–1000 según gusto
RMS_THRESH    = 0.009   # umbral VAD. Baja a 0.007–0.008 si no detecta voz; sube si hay ruido
PARTIAL_EVERY = 1200    # ms entre parciales (si activas --partials)
MIN_PARTIAL_CHARS = 6   # mínimo de caracteres para emitir parcial
TTS_RATE      = 170     # velocidad TTS (un poco más baja = más estable)
TTS_VOLUME    = 1.0     # volumen TTS (0.0–1.0)
# ===========================================================


# ================== VAD por energía ==================
def rms_energy(frame_bytes: bytes) -> float:
    x = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x * x)))

def is_speech_energy(frame_bytes: bytes) -> bool:
    return rms_energy(frame_bytes) >= RMS_THRESH
# =====================================================


# ================== TTS multiplataforma ==================
class TTSWorker:
    """
    Clase única y robusta:
      - Windows: pyttsx3 efímero por frase (evita atascos tras la 1ª).
      - Linux/RPi: py-espeak-ng si está; si no, pyttsx3; si no, print.
    priority=1 limpia la cola antes de hablar (asegura que el final SIEMPRE suene).
    """
    def __init__(self, rate: int = TTS_RATE, volume: float = TTS_VOLUME):
        self.q = queue.Queue()
        self.rate = rate
        self.volume = volume
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def say(self, text: str, lang_code: str, priority: int = 0):
        text = (text or "").strip()
        if not text:
            return
        if priority == 1:
            self._drain_queue()
        self.q.put((text, lang_code))

    # ---------- Internos ----------
    def _drain_queue(self):
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    # --- PYTTSX3 helpers ---
    def _pick_voice_pyttsx3(self, engine, lang_code: str):
        want = 'en' if (lang_code or '').lower().startswith('en') else 'es'
        try:
            voices = engine.getProperty('voices')
        except Exception:
            return None
        for v in voices:
            name = (getattr(v, "name", "") or "").lower()
            vid  = (getattr(v, "id", "") or "").lower()
            langs = []
            try:
                langs = [l.decode('utf-8','ignore') if isinstance(l, bytes) else str(l)
                         for l in (getattr(v, "languages", []) or [])]
            except Exception:
                pass
            if (want in name) or (want in vid) or any(want in s.lower() for s in langs):
                return v.id
        return None

    def _speak_pyttsx3_ephemeral(self, text: str, lang_code: str) -> bool:
        if PYTTSX3 is None:
            return False
        try:
            eng = PYTTSX3.init()
            eng.setProperty('rate', self.rate)
            eng.setProperty('volume', self.volume)
            vid = self._pick_voice_pyttsx3(eng, lang_code)
            if vid:
                eng.setProperty('voice', vid)
            eng.say(text)
            eng.runAndWait()
            del eng
            return True
        except Exception as e:
            print(f"⚠️  Error TTS (pyttsx3): {e}", file=sys.stderr)
            return False

    # --- ESPEAK-NG helper ---
    def _speak_espeakng(self, text: str, lang_code: str) -> bool:
        if ESPEAKNG is None:
            return False
        try:
            spk = ESPEAKNG.Speaker()
            spk.voice = "en" if (lang_code or "").lower().startswith("en") else "es"
            spk.rate = max(80, min(250, int(self.rate)))  # 120 ~ normal
            spk.say(text)
            return True
        except Exception as e:
            print(f"⚠️  Error TTS (espeak-ng): {e}", file=sys.stderr)
            return False

    def _run(self):
        while True:
            text, lang_code = self.q.get()
            try:
                if IS_WINDOWS:
                    ok = self._speak_pyttsx3_ephemeral(text, lang_code)
                    if not ok:
                        print(f"[TTS fallback] {lang_code}: {text}")
                else:
                    # Linux/RPi: espeak-ng → pyttsx3 → print
                    if not self._speak_espeakng(text, lang_code):
                        if not self._speak_pyttsx3_ephemeral(text, lang_code):
                            print(f"[TTS fallback] {lang_code}: {text}")
            except Exception as e:
                print(f"⚠️  Error TTS: {e}", file=sys.stderr)
# =====================================================


# ================== Argos Translate ==================
def ensure_language_pair(src: str, tgt: str) -> bool:
    """Comprueba que existe el par src->tgt instalado en Argos."""
    try:
        langs = tr.get_installed_languages()
        from_lang = next((l for l in langs if getattr(l, "code", "") == src), None)
        to_lang   = next((l for l in langs if getattr(l, "code", "") == tgt), None)
        if not from_lang or not to_lang:
            return False
        _ = from_lang.get_translation(to_lang)
        return True
    except Exception:
        return False

def translate_text(src: str, tgt: str, text: str) -> str:
    """Traduce usando Argos instalado. Si falta el par, devuelve el original."""
    try:
        langs = tr.get_installed_languages()
        from_lang = next((l for l in langs if getattr(l, "code", "") == src), None)
        to_lang   = next((l for l in langs if getattr(l, "code", "") == tgt), None)
        if not from_lang or not to_lang:
            print(f"⚠️  Argos: faltan idiomas instalados para {src}->{tgt}.")
            return text or ""
        translation = from_lang.get_translation(to_lang)
        return translation.translate(text or "")
    except Exception as e:
        print(f"⚠️  Error Argos: {e}")
        return text or ""
# =====================================================


def list_devices():
    print("=== Dispositivos de audio (sounddevice) ===")
    print(sd.query_devices())


def main():
    parser = argparse.ArgumentParser(description="Traductor offline (Vosk + Argos + TTS)")
    parser.add_argument("--in_model",   default="models/vosk-es", help="Ruta modelo Vosk (idioma de entrada)")
    parser.add_argument("--src",        default="es",             help="Idioma entrada (es|en|...)")
    parser.add_argument("--tgt",        default="en",             help="Idioma salida (en|es|...)")
    parser.add_argument("--in_device",  default=None,             help="Índice/nombre micrófono")
    parser.add_argument("--out_device", default=None,             help="Índice/nombre altavoz")
    parser.add_argument("--list",       action="store_true",      help="Lista dispositivos y sale")
    parser.add_argument("--partials",   action="store_true",      help="Emitir traducciones parciales")
    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    # Audio (opcional: forzar dispositivos)
    sd.default.samplerate = SAMPLE_RATE
    sd.default.channels = 1
    if args.in_device is not None or args.out_device is not None:
        sd.default.device = (args.in_device, args.out_device)

    # Vosk
    in_model_path = os.path.expanduser(args.in_model)
    if not os.path.isdir(in_model_path):
        raise SystemExit(f"No encuentro el modelo Vosk en: {in_model_path}")
    SetLogLevel(-1)
    print(f"Cargando Vosk: {in_model_path}")
    model = Model(in_model_path)
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetWords(True)

    # Argos
    print(f"Cargando Argos Translate: {args.src} -> {args.tgt}")
    if not ensure_language_pair(args.src, args.tgt):
        print(f"⚠️  Falta el par {args.src}->{args.tgt} en Argos. Instálalo con install_argos.py.")

    # TTS
    tts = TTSWorker(rate=TTS_RATE, volume=TTS_VOLUME)

    # Captura audio
    frame_bytes = int(2 * SAMPLE_RATE * BLOCK_MS / 1000)
    audio_q = queue.Queue()
    done = threading.Event()

    def audio_callback(indata, frames, time_info, status):
        audio_q.put(bytes(indata))

    def read_stream():
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=int(SAMPLE_RATE * BLOCK_MS / 1000),
            dtype='int16',
            channels=1,
            callback=audio_callback,
        ):
            while not done.is_set():
                time.sleep(0.01)

    threading.Thread(target=read_stream, daemon=True).start()
    print("Listo. Habla cerca del micro. Ctrl+C para salir.")

    last_voice_time = 0.0
    got_voice = False
    partial_buf_text = ""
    partial_last_emit = 0.0

    try:
        while True:
            chunk = audio_q.get()
            for i in range(0, len(chunk), frame_bytes):
                frame = chunk[i:i+frame_bytes]
                if len(frame) < frame_bytes:
                    continue

                speaking = is_speech_energy(frame)
                now = time.time()

                # Alimenta Vosk
                rec.AcceptWaveform(frame)

                if speaking:
                    got_voice = True
                    last_voice_time = now

                    # Parciales (solo si --partials)
                    if args.partials and (now - partial_last_emit) * 1000.0 > PARTIAL_EVERY:
                        res = json.loads(rec.PartialResult())
                        partial = (res.get("partial") or "").strip()
                        if partial and partial != partial_buf_text and len(partial) >= MIN_PARTIAL_CHARS:
                            partial_buf_text = partial
                            out = translate_text(args.src, args.tgt, partial_buf_text)
                            tts.say(out, args.tgt, priority=0)  # no flush
                            partial_last_emit = now
                else:
                    # Cierre de frase por silencio
                    if got_voice and (now - last_voice_time) * 1000.0 >= PAUSE_MS:
                        final = (json.loads(rec.FinalResult()).get("text") or "").strip()
                        got_voice = False
                        partial_buf_text = ""
                        partial_last_emit = 0.0
                        if final:
                            print(f"[ASR {args.src}] {final}")
                            translated = translate_text(args.src, args.tgt, final)
                            print(f"[{args.src}->{args.tgt}] {translated}")
                            tts.say(translated, args.tgt, priority=1)  # flush y habla
                        # reinicia reconocedor
                        rec = KaldiRecognizer(model, SAMPLE_RATE)
                        rec.SetWords(True)

    except KeyboardInterrupt:
        done.set()
        print("\nSaliendo…")

if __name__ == "__main__":
    main()
