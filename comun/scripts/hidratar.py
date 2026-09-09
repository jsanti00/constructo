#!/usr/bin/env python3
"""Fuerza la descarga local de los archivos de OneDrive que estén como placeholder.

Por qué existe: OneDrive en macOS deja archivos como placeholders sin contenido en
disco. El tamaño aparece en `ls`, pero la primera lectura se queda esperando la
descarga (dos planos DWG de una obra tardaron 2m30s en bajar 78 MB). Para un
agente que lee esos archivos, eso es indistinguible de estar colgado.

Leer el archivo completo obliga al File Provider a descargarlo. Este script recorre
solo las carpetas de `carpetas.conf` y lee una vez cada archivo que no haya leído
antes, guardando la huella (ruta, tamaño, mtime) en un manifiesto fuera de OneDrive.

No intenta detectar si un archivo es placeholder: el File Provider de macOS no lo
expone de forma confiable (`stat` reporta bloques como si estuviera local). En su
lugar usa el manifiesto, que da la misma garantía con lógica más simple.

Uso:
    ./hidratar.py              descarga lo que falte
    ./hidratar.py --dry-run    lista qué descargaría, sin descargar
    ./hidratar.py --force      reprocesa todo, ignorando el manifiesto
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import time
from datetime import datetime
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
CONF = DIR_SCRIPT / "carpetas.conf"

ESTADO = Path.home() / ".local" / "state" / "hidratar-obras"
MANIFIESTO = ESTADO / "manifiesto.tsv"
LOG = ESTADO / "hidratar.log"
LOCK = ESTADO / "hidratar.lock"

# Presupuesto de tiempo por corrida: si un archivo enorme se está bajando, lo que
# quede pendiente se toma en la corrida siguiente en vez de dejar el proceso vivo.
PRESUPUESTO_SEG = int(os.environ.get("PRESUPUESTO_SEG", "900"))
LOG_MAX_BYTES = 2 * 1024 * 1024
LOCK_ANTIGUO_SEG = 3600
MANIFIESTO_MAX_LINEAS = 20_000

# Ruido del sistema y locks temporales de Office: descargarlos no aporta nada.
PATRONES_IGNORADOS = (".DS_Store", ".localized", "Icon\r", "~$*", "*.tmp", "*.crdownload")

BLOQUE = 4 * 1024 * 1024


def log(mensaje: str) -> None:
    ESTADO.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {mensaje}\n")


def rotar_log() -> None:
    if LOG.exists() and LOG.stat().st_size > LOG_MAX_BYTES:
        LOG.replace(LOG.with_suffix(".log.1"))


def tomar_lock() -> bool:
    """Evita que dos corridas simultáneas peleen por el mismo ancho de banda."""
    ESTADO.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            edad = time.time() - LOCK.stat().st_mtime
        except OSError:
            return False
        # Un lock viejo casi siempre es de una corrida que murió sin limpiar.
        if edad > LOCK_ANTIGUO_SEG:
            log(f"lock huérfano de {edad / 60:.0f} min, lo retomo")
            LOCK.unlink(missing_ok=True)
            return tomar_lock()
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def leer_carpetas() -> list[Path]:
    if not CONF.exists():
        log(f"ERROR: no existe {CONF}")
        sys.exit(1)
    carpetas = []
    for linea in CONF.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if linea:
            carpetas.append(Path(linea))
    return carpetas


def cargar_manifiesto() -> set[str]:
    if not MANIFIESTO.exists():
        return set()
    huellas = set()
    with MANIFIESTO.open(encoding="utf-8") as fh:
        for linea in fh:
            partes = linea.rstrip("\n").split("\t", 1)
            if partes and partes[0]:
                huellas.add(partes[0])
    return huellas


def ignorado(nombre: str) -> bool:
    return any(fnmatch.fnmatch(nombre, p) for p in PATRONES_IGNORADOS)


def leer_completo(ruta: Path) -> None:
    with ruta.open("rb") as fh:
        while fh.read(BLOQUE):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="lista sin descargar")
    ap.add_argument("--force", action="store_true", help="ignora el manifiesto")
    args = ap.parse_args()

    ESTADO.mkdir(parents=True, exist_ok=True)
    rotar_log()

    if not args.dry_run and not tomar_lock():
        log("otra corrida en progreso, salgo")
        return 0

    try:
        conocidas = set() if args.force else cargar_manifiesto()
        inicio = time.time()
        revisados = pendientes = descargados = fallidos = diferidos = 0
        nuevas_huellas: list[str] = []

        for raiz in leer_carpetas():
            if not raiz.is_dir():
                log(f"AVISO: carpeta inexistente, la salto: {raiz}")
                continue

            for dirpath, dirnames, filenames in os.walk(raiz):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                for nombre in filenames:
                    if ignorado(nombre):
                        continue
                    ruta = Path(dirpath) / nombre
                    revisados += 1
                    try:
                        st = ruta.stat()
                    except OSError:
                        continue

                    huella = f"{st.st_size}:{int(st.st_mtime)}:{ruta}"
                    if huella in conocidas:
                        continue
                    pendientes += 1

                    if args.dry_run:
                        print(f"PENDIENTE  {st.st_size:>12,}  {ruta}")
                        continue

                    if time.time() - inicio > PRESUPUESTO_SEG:
                        diferidos += 1
                        continue

                    t0 = time.time()
                    try:
                        leer_completo(ruta)
                    except OSError as exc:
                        fallidos += 1
                        log(f"ERROR al leer {ruta}: {exc}")
                        continue
                    tardanza = time.time() - t0
                    nuevas_huellas.append(huella)
                    descargados += 1
                    # Solo registro lo que costó tiempo: si tardó, era un placeholder.
                    if tardanza >= 3:
                        log(f"descargado en {tardanza:.0f}s ({st.st_size:,} bytes): {ruta}")

        if args.dry_run:
            print("---")
            print(f"archivos revisados: {revisados}   pendientes de descarga: {pendientes}")
            return 0

        if nuevas_huellas:
            marca = f"{datetime.now():%Y-%m-%dT%H:%M:%S}"
            with MANIFIESTO.open("a", encoding="utf-8") as fh:
                for huella in nuevas_huellas:
                    fh.write(f"{huella}\t{marca}\n")

        # El log solo habla cuando hubo algo que hacer; si no, se llenaría de
        # corridas vacías cada cinco minutos y dejaría de servir para diagnosticar.
        if descargados or fallidos or diferidos:
            log(
                f"corrida: {revisados} revisados, {descargados} descargados, "
                f"{fallidos} fallidos, {diferidos} diferidos por tiempo"
            )

        if MANIFIESTO.exists():
            lineas = MANIFIESTO.read_text(encoding="utf-8").splitlines()
            if len(lineas) > MANIFIESTO_MAX_LINEAS:
                MANIFIESTO.write_text(
                    "\n".join(lineas[-MANIFIESTO_MAX_LINEAS // 2 :]) + "\n", encoding="utf-8"
                )
                log("manifiesto compactado")

        return 0
    finally:
        if not args.dry_run:
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
