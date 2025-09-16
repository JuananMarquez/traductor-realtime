# install_argos.py  (versión corregida para Argos 1.9.x)
import argostranslate.package as pkg
import argostranslate.translate as tr

def install_pair(src, tgt):
    print(f"\nBuscando paquete {src}->{tgt}…")
    avail = pkg.get_available_packages()
    cand = [p for p in avail if p.from_code == src and p.to_code == tgt]
    if not cand:
        print(f"  ✗ No hay paquete disponible {src}->{tgt} en el índice.")
        return
    p = cand[0]
    print(f"  Descargando {src}->{tgt} (versión {p.package_version})…")
    path = p.download()
    print(f"  Instalando desde {path} …")
    pkg.install_from_path(path)
    print(f"  ✓ OK {src}->{tgt}")

def main():
    print("Actualizando índice de paquetes de Argos…")
    pkg.update_package_index()

    # Instala ambos sentidos ES <-> EN (si ya estaban, no pasa nada)
    install_pair("es", "en")
    install_pair("en", "es")

    print("\nIdiomas instalados:")
    langs = tr.get_installed_languages()
    for L in langs:
        code = getattr(L, "code", "?")
        # Argos 1.9.x: 'translations_to' es la lista de traducciones disponibles desde este idioma
        for T in getattr(L, "translations_to", []):
            to_code = getattr(T, "to_lang", "?")
            print(f"  {code} -> {to_code}")

    # Prueba rápida
    sample = "hola mundo"
    out = tr.translate(sample, "es", "en")
    print(f'\nPrueba rápida: "{sample}" (es->en) -> "{out}"')

if __name__ == "__main__":
    main()
