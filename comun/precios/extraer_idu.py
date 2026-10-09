#!/usr/bin/env python3
"""Carga a la base central de precios el visor de precios de referencia del IDU (Bogotá).

El IDU publica dos tablas planas: insumos (precio por insumo) y APU (valor total
de cada APU, sin su desglose). No trae rendimientos ni cuadrillas.

Qué verifica antes de cargar:
1. Cada fila con contenido entre el encabezado y el pie de la tabla se pudo leer
   completa (código, nombre, unidad y precio numérico). Si una no, no carga nada.
2. No hay códigos repetidos dentro de cada tabla.
3. Los precios son positivos (los en cero se reportan como advertencia).
4. Deja anotados el conteo y la suma de precios de cada tabla, para comparar con
   futuras cargas del mismo archivo.

Uso (siempre con -I, porque el Excel es un archivo descargado):
    python3 -I extraer_idu.py --edicion 2026-I-Fase-II RUTA/1A_Visor_BPR_....xlsx
    python3 -I extraer_idu.py --edicion 2026-I-Fase-II --solo-verificar RUTA/...xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Con -I Python no mira la carpeta del script: la agregamos a mano (es de confianza)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extraer_invias import Verificador, insertar, num, texto, openpyxl  # noqa: E402
from base import conectar, huella, normalizar, TABLAS_REGION  # noqa: E402

URL_IDU = "https://www.idu.gov.co/page/siipviales/economico/portafolio"
REGION = "bogota"


def leer_tabla(hoja, columnas_esperadas):
    """Lee una tabla del visor: encuentra el encabezado y devuelve sus filas.

    Devuelve (filas leídas, filas con contenido que no se pudieron leer, fechas de
    publicación y de último ajuste que trae la hoja arriba de la tabla).
    """
    filas, ilegibles, mapa, fechas = [], [], None, {}
    for i, f in enumerate(hoja.iter_rows(values_only=True), start=1):
        nombres = [normalizar(c) for c in f]
        if mapa is None:
            # Aquí guardamos las fechas que el IDU escribe encima de la tabla
            for c in f:
                t = texto(c)
                if t.lower().startswith("fecha de publicación"):
                    fechas["publicacion"] = t.split(":", 1)[1].strip()
                elif t.lower().startswith("fecha del último ajuste"):
                    fechas["ajuste"] = t.split(":", 1)[1].strip()
            # Aquí ubicamos la fila de encabezados (la que tiene "codigo")
            if "codigo" in nombres:
                mapa = {n: j for j, n in enumerate(nombres) if n}
                faltan = [c for c in columnas_esperadas if c not in mapa]
                if faltan:
                    sys.exit(f"La hoja {hoja.title} no trae las columnas {faltan}: revisar el formato.")
            continue
        if not any(c not in (None, "") for c in f):
            continue
        # Aquí paramos en el pie de página del IDU (texto de la dependencia, sin código)
        codigo = texto(f[mapa["codigo"]]) if mapa["codigo"] < len(f) else ""
        if not codigo and any(texto(c).startswith(("Subdirección", "Dirección")) for c in f):
            break
        fila = {n: (f[j] if j < len(f) else None) for n, j in mapa.items()}
        precio = num(fila.get("precio", fila.get("valor")))
        if not re.match(r"^\d+$", codigo) or precio is None or not texto(fila.get("nombre")):
            ilegibles.append(f"fila {i}: {[texto(c)[:30] for c in f if c not in (None, '')]}")
            continue
        fila.update(_codigo=codigo, _precio=precio, _fila=i)
        filas.append(fila)
    return filas, ilegibles, fechas


def verificar(insumos, apus, ilegibles):
    """Corre los chequeos sobre las dos tablas leídas."""
    v = Verificador()
    for nombre, filas, malas in (("insumos", insumos, ilegibles["insumos"]), ("APU", apus, ilegibles["apu"])):
        v.chequear(f"{nombre}: todas las filas con contenido se leyeron completas", malas,
                   len(filas) + len(malas), f"{len(filas)} filas leídas")
        repetidos = [c for c, n in Counter(f["_codigo"] for f in filas).items() if n > 1]
        v.chequear(f"{nombre}: códigos sin repetir", repetidos, len(filas))
        v.advertir(f"{nombre}: precios en cero", [f["_codigo"] for f in filas if f["_precio"] <= 0], len(filas))
        suma = sum(f["_precio"] for f in filas)
        v.resultados.append((f"{nombre}: suma de control", "OK", f"{len(filas)} filas, suma de precios {suma:,.0f}"))
        fechas = Counter(texto(f.get("fecha de actualizacion")) for f in filas)
        v.resultados.append((f"{nombre}: antigüedad de los precios", "OK",
                             "; ".join(f"{n} con '{t}'" for t, n in fechas.most_common())))
    return v


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--edicion", required=True, help="edición IDU, ej. 2026-I-Fase-II")
    p.add_argument("--solo-verificar", action="store_true", help="verifica sin escribir en la base")
    p.add_argument("archivo", type=Path)
    args = p.parse_args()

    # Aquí abrimos el Excel en modo solo lectura y con los valores ya calculados
    wb = openpyxl.load_workbook(args.archivo, read_only=True, data_only=True)
    insumos, malos_ins, fechas = leer_tabla(wb["Inusmos"], ["codigo", "nombre", "um", "precio"])
    apus, malos_apu, _ = leer_tabla(wb["APU"], ["codigo", "nombre", "um", "valor"])
    wb.close()
    v = verificar(insumos, apus, {"insumos": malos_ins, "apu": malos_apu})

    print(f"\n== {args.archivo.name}")
    for nombre, resultado, detalle in v.resultados:
        print(f"  [{resultado}] {nombre}: {detalle}")
    if not v.todo_ok:
        sys.exit("  NO SE CARGÓ: hay chequeos fallidos.")
    if args.solo_verificar:
        return

    publicacion = f"publicado {fechas.get('publicacion')}, último ajuste {fechas.get('ajuste')}"
    con = conectar()
    with con:  # Aquí abrimos una transacción: si algo falla, no queda nada a medias
        con.execute("INSERT OR IGNORE INTO ediciones (fuente, edicion, url, uso) VALUES ('idu', ?, ?, 'precios')",
                    (args.edicion, URL_IDU))
        con.execute("UPDATE ediciones SET publicacion=?, notas=? WHERE fuente='idu' AND edicion=?",
                    (publicacion, "Visor BPR: precios de insumos y valor total de APU, sin desglose ni rendimientos. "
                     "Obra vial y espacio público de Bogotá.", args.edicion))
        eid = con.execute("SELECT id FROM ediciones WHERE fuente='idu' AND edicion=?", (args.edicion,)).fetchone()[0]
        # Aquí borramos lo que hubiera de esta edición antes de recargar
        for t in TABLAS_REGION:
            con.execute(f"DELETE FROM {t} WHERE edicion_id=? AND region=?", (eid, REGION))
        base = dict(edicion_id=eid, region=REGION)
        insertar(con, "archivos", [dict(base, archivo=args.archivo.name, sha256=huella(args.archivo),
                                        bytes=args.archivo.stat().st_size,
                                        cargado_en=datetime.now().isoformat(timespec="seconds"))])
        insertar(con, "regiones", [dict(base, departamento="BOGOTÁ D.C.", provincia="BOGOTÁ D.C.")])
        insertar(con, "insumos", [dict(base, tipo="insumo", codigo=f["_codigo"], descripcion=texto(f["nombre"]),
                                       unidad=texto(f["um"]), precio=f["_precio"],
                                       categoria=texto(f.get("grupo de base de datos")),
                                       actualizacion=texto(f.get("fecha de actualizacion")),
                                       hoja="Inusmos", fila=f["_fila"]) for f in insumos])
        insertar(con, "apu", [dict(base, item=f["_codigo"], capitulo=texto(f.get("capitulo")),
                                   articulo=texto(f.get("subcapitulo")), clasificacion=texto(f.get("origen")),
                                   descripcion=texto(f["nombre"]), unidad=texto(f["um"]),
                                   costo_directo=f["_precio"], costo_directo_corregido=f["_precio"],
                                   actualizacion=texto(f.get("fecha de actualizacion")), hoja="APU")
                              for f in apus])
        insertar(con, "verificaciones", [dict(base, chequeo=n, resultado=r, detalle=d) for n, r, d in v.resultados])
    print(f"  Cargado: IDU {args.edicion}, {len(insumos)} insumos y {len(apus)} APU.")


if __name__ == "__main__":
    main()
