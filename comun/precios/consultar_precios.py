#!/usr/bin/env python3
"""Consulta la base central de precios de referencia, limitada a las regiones de una obra.

Es la herramienta que usa el agente de cada obra. Solo lee: nunca escribe en la base.
Las regiones permitidas vienen de la variable PRECIOS_REGIONES, que define el
arranque del agente (no el prompt). Ejemplo: PRECIOS_REGIONES="invias:2510".
Sin esa variable, no responde nada: igual que una allowlist vacía.

Uso:
    consultar_precios.py fuentes                    qué fuentes, ediciones y regiones ve esta obra
    consultar_precios.py buscar "concreto 3000"     busca insumos, APU y cargos por texto
    consultar_precios.py buscar "pañete" --tipo apu
    consultar_precios.py apu 630,4                  desglose completo de un APU
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Con -I Python no mira la carpeta del script: la agregamos a mano (es de confianza)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from base import BASE, normalizar  # noqa: E402

import sqlite3  # noqa: E402

AVISO = ("Referencia pública, no es el precio de la obra. El precio oficial de la obra "
         "es el de su presupuesto.")


def regiones_permitidas():
    """Lee de PRECIOS_REGIONES las parejas (fuente, región) que puede ver esta obra."""
    valor = os.environ.get("PRECIOS_REGIONES", "").strip()
    if not valor:
        sys.exit("Sin regiones autorizadas (PRECIOS_REGIONES vacía): no hay precios que mostrar.")
    # Aquí convertimos "invias:2510,idu:bogota" en [("invias","2510"), ("idu","bogota")]
    return [tuple(p.strip().split(":", 1)) for p in valor.split(",") if ":" in p]


def abrir():
    """Abre la base en modo solo lectura (no se puede modificar desde aquí)."""
    if not BASE.exists():
        sys.exit(f"No existe la base de precios en {BASE}.")
    con = sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
    con.create_function("norm", 1, normalizar)
    return con


def ediciones_vigentes(con, permitidas, edicion=None):
    """Para cada región permitida, elige la edición más reciente (o la pedida)."""
    salida = []
    for fuente, region in permitidas:
        fila = con.execute(
            """SELECT e.id, e.fuente, e.edicion, e.publicacion, e.uso, r.departamento, r.provincia,
                      substr(a.cargado_en, 1, 10)
               FROM ediciones e JOIN regiones r ON r.edicion_id = e.id
               JOIN archivos a ON a.edicion_id = e.id AND a.region = r.region
               WHERE e.fuente = ? AND r.region = ? AND (? IS NULL OR e.edicion = ?)
               ORDER BY e.edicion DESC LIMIT 1""",
            (fuente, region, edicion, edicion)).fetchone()
        if fila:
            salida.append(dict(id=fila[0], fuente=fila[1], edicion=fila[2], publicacion=fila[3],
                               uso=fila[4], region=region, lugar=f"{fila[5]} / {fila[6]}", cargada=fila[7]))
    if not salida:
        sys.exit("Ninguna de las regiones autorizadas tiene datos cargados en la base.")
    return salida


def procedencia(e):
    """Arma la línea que dice de dónde sale cada dato."""
    return (f"Fuente: {e['fuente'].upper()} {e['edicion']} ({e['publicacion']}), "
            f"región {e['region']} {e['lugar']}. Cargada a la base el {e['cargada']}.")


def pesos(x):
    """Formatea un número como pesos colombianos, ej. 1.234.567,89."""
    if x is None:
        return "sin precio"
    return f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cmd_fuentes(con, eds, args):
    """Muestra las fuentes, ediciones y regiones que ve esta obra, con su verificación."""
    print(AVISO)
    for e in eds:
        print("\n" + procedencia(e) + f" Uso permitido: {e['uso']}.")
        for chequeo, resultado, detalle in con.execute(
                "SELECT chequeo, resultado, detalle FROM verificaciones WHERE edicion_id=? AND region=?",
                (e["id"], e["region"])):
            print(f"  [{resultado}] {chequeo}: {detalle}")


def cmd_buscar(con, eds, args):
    """Busca por texto en insumos, APU y cargos, sin importar tildes ni mayúsculas."""
    # Aquí partimos la búsqueda en palabras: cada palabra debe aparecer en la descripción
    palabras = normalizar(args.texto).split()
    filtro = " AND ".join(["norm(descripcion) LIKE ?"] * len(palabras))
    valores = [f"%{p}%" for p in palabras]
    print(AVISO)
    for e in eds:
        print("\n" + procedencia(e))
        if args.tipo in (None, "insumo"):
            filas = con.execute(
                f"""SELECT tipo, codigo, descripcion, unidad, precio, actualizacion FROM insumos
                    WHERE edicion_id=? AND region=? AND {filtro} ORDER BY tipo, descripcion LIMIT ?""",
                (e["id"], e["region"], *valores, args.limite)).fetchall()
            for t, c, d, u, p, act in filas:
                print(f"  insumo {t:10s} {c:10s} {d[:70]:70s} {u:8s} {pesos(p)}" + (f"  ({act})" if act else ""))
        if args.tipo in (None, "apu"):
            filas = con.execute(
                f"""SELECT item, descripcion, unidad, costo_directo, costo_directo_corregido FROM apu
                    WHERE edicion_id=? AND region=? AND {filtro} ORDER BY item LIMIT ?""",
                (e["id"], e["region"], *valores, args.limite)).fetchall()
            for i, d, u, p, pc in filas:
                # Aquí avisamos si corregimos un error de la fuente en este APU
                extra = (f" -> corregido por Constructo: {pesos(pc)}" if pc is not None and abs(pc - p) > 0.01 else "")
                print(f"  APU {i:12s} {d[:75]:75s} {u:8s} {pesos(p)} (costo directo){extra}")
        if args.tipo in (None, "mano_obra"):
            filas = con.execute(
                f"""SELECT codigo, cargo, salario_mensual, factor_jornal, factor_prestacional
                    FROM mano_obra WHERE edicion_id=? AND region=?
                    AND {filtro.replace('descripcion', 'cargo')} LIMIT ?""",
                (e["id"], e["region"], *valores, args.limite)).fetchall()
            for c, d, s, fj, fp in filas:
                print(f"  cargo {c:10s} {d[:50]:50s} salario {pesos(s)}/mes, factor jornal {fj}, "
                      f"factor prestacional {fp:.4f}")


def cmd_apu(con, eds, args):
    """Muestra el desglose completo de un APU: cada insumo con su rendimiento y valor."""
    print(AVISO)
    for e in eds:
        apu = con.execute("SELECT item, descripcion, unidad, costo_directo, costo_directo_corregido, nota FROM apu "
                          "WHERE edicion_id=? AND region=? AND item=?",
                          (e["id"], e["region"], args.item)).fetchone()
        if not apu:
            print(f"\n{procedencia(e)}\n  No existe el APU {args.item}.")
            continue
        print(f"\n{procedencia(e)}\nAPU {apu[0]}: {apu[1]} ({apu[2]})")
        titulos = {"equipo": "I. Equipo (tarifa/hora x horas por unidad)",
                   "materiales": "II. Materiales (cantidad x precio)",
                   "transporte": "III. Transporte (cantidad x distancia x tarifa)",
                   "mano_obra": "IV. Mano de obra (jornal x prestaciones / unidades por jornal)"}
        for comp, titulo in titulos.items():
            lineas = con.execute(
                """SELECT codigo, descripcion, unidad, cantidad, distancia, precio, prestaciones,
                          rendimiento, valor, valor_corregido, nota FROM apu_detalle
                   WHERE edicion_id=? AND region=? AND item=? AND componente=? ORDER BY fila""",
                (e["id"], e["region"], args.item, comp)).fetchall()
            if not lineas:
                continue
            print(f"  {titulo}")
            for c, d, u, q, dist, p, pr, r, v, vc, nota in lineas:
                if c == "HERMENINV":
                    detalle = f"{r:.0%} de la mano de obra"
                elif comp in ("equipo", "mano_obra"):
                    detalle = f"precio {pesos(p)}, rendimiento {r:.4f}" + (f", prestaciones {pr:.4f}" if pr else "")
                elif comp == "transporte":
                    detalle = f"cantidad {q}, distancia {dist}, tarifa {pesos(p)}"
                else:
                    detalle = f"cantidad {q}, precio {pesos(p)}"
                if nota:
                    # Línea que la fuente dejó en $0 por un error suyo: mostramos la corrección
                    print(f"    {c:10s} {d[:55]:55s} cantidad {q}  = $0 según la fuente; {pesos(vc)} corregido")
                    print(f"               ({nota})")
                else:
                    print(f"    {c:10s} {(d or '(la fuente no trae descripción)')[:55]:55s} {detalle}  = {pesos(v)}")
        tiene_detalle = con.execute("SELECT 1 FROM apu_detalle WHERE edicion_id=? AND region=? AND item=? LIMIT 1",
                                    (e["id"], e["region"], args.item)).fetchone()
        if not tiene_detalle:
            print("  Esta fuente publica solo el valor total del APU, sin desglose ni rendimientos.")
        print(f"  Costo directo publicado por la fuente: {pesos(apu[3])}")
        if apu[4] is not None and abs(apu[4] - apu[3]) > 0.01:
            print(f"  Costo directo corregido por Constructo: {pesos(apu[4])}. {apu[5]}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--edicion", help="edición a consultar; por defecto la más reciente")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("fuentes")
    b = sub.add_parser("buscar")
    b.add_argument("texto")
    b.add_argument("--tipo", choices=["insumo", "apu", "mano_obra"])
    b.add_argument("--limite", type=int, default=20)
    a = sub.add_parser("apu")
    a.add_argument("item")
    args = p.parse_args()

    permitidas = regiones_permitidas()
    con = abrir()
    eds = ediciones_vigentes(con, permitidas, args.edicion)
    {"fuentes": cmd_fuentes, "buscar": cmd_buscar, "apu": cmd_apu}[args.comando](con, eds, args)


if __name__ == "__main__":
    main()
