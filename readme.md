# Traductor Offline en Tiempo Real (Windows / Raspberry Pi)

Este proyecto implementa un traductor de voz offline y casi en tiempo real que:

* Escucha desde un micrófono USB
* Reconoce la voz con Vosk (ASR)
* Traduce con Argos Translate (MT)
* Reproduce la traducción con TTS (pyttsx3 en Windows, espeak-ng en Linux/RPi)

Funciona con la misma clase `rt_translator.py` tanto en Windows como en Raspberry Pi/Linux.

---

## Instalación

1. Crea un entorno virtual:

```bash
python -m venv traductor_env
source traductor_env/bin/activate     # Linux / Raspberry Pi
traductor_env\Scripts\activate        # Windows
```

2. Instala dependencias:

```bash
pip install -r requirements.txt
```

---

## requirements.txt

```txt
vosk
sounddevice
numpy
argostranslate==1.*
pyttsx3; platform_system == "Windows"
py-espeak-ng; platform_system != "Windows"
```

Esto asegura compatibilidad multiplataforma.

---

## Modelos Vosk

Descarga modelos con `install_models.py`:

```bash
# Español
python install_models.py --lang es

# Inglés
python install_models.py --lang en

# Todos los modelos
python install_models.py --all
```

Se crearán automáticamente las carpetas:

```
models/vosk-es
models/vosk-en
```

---

## Modelos de Traducción (Argos)

Instala paquetes de traducción con `install_argos.py`:

```bash
python install_argos.py
```

Esto instala los pares:

* es → en
* en → es

Prueba rápida incluida:

```
"hola mundo" (es->en) → "hello world"
```

---

## Uso

Ejecuta el traductor:

```bash
# Español → Inglés
python rt_translator.py --in_model models/vosk-es --src es --tgt en

# Inglés → Español
python rt_translator.py --in_model models/vosk-en --src en --tgt es
```

### Opciones adicionales

```bash
--list          Lista dispositivos de audio
--in_device N   Forzar micrófono (ID)
--out_device N  Forzar altavoz (ID)
--partials      Traducciones parciales en vivo
```

Ejemplo:

```bash
python rt_translator.py --in_model models/vosk-es --src es --tgt en --partials
```

---

## Archivos principales

* `rt_translator.py` → Traductor en tiempo real (misma clase Win/RPi)
* `install_argos.py` → Instala paquetes de traducción Argos
* `install_models.py` → Instala modelos Vosk
* `requirements.txt` → Dependencias multiplataforma
* `models/` → Carpeta de modelos Vosk

---

## Estado actual

* Reconocimiento de voz offline (Vosk)
* Traducción offline (Argos)
* TTS estable (pyttsx3 Windows, espeak-ng RPi)
* Misma clase para ambos sistemas
* Instaladores automáticos (`install_models.py`, `install_argos.py`)

---

## Próximos pasos

* Añadir soporte para más idiomas (fr, de, it...)
* Optimizar rendimiento en Raspberry Pi 3B
* Integrar hotword (activar solo al decir una palabra clave)
