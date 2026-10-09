#!/usr/bin/env python3
"""Carga a la base central de precios un Excel provincial de APU de INVIAS.

Qué hace, en orden:
1. Lee del Excel de una provincia los listados de materiales, equipos, transporte y
   mano de obra, el índice de APU y la hoja de cada APU con su desglose.
2. Verifica la integridad: conteos, que cada línea del APU dé su valor, que cada
   capítulo sume su subtotal, que cada APU cuadre con el índice, que los precios
   usados en los APU sean los del listado y que el listado coincida con la matriz
   nacional que trae el mismo archivo.
3. Solo si todo cuadra, reemplaza en la base los datos de esa edición y provincia.
   Si algo falla, no escribe nada y muestra qué falló.

Uso (siempre con -I, porque el Excel es un archivo descargado):
    python3 -I extraer_invias.py --edicion 2026-1 RUTA/APU_2510_..._2026_1.xlsx [...]
    python3 -I extraer_invias.py --edicion 2026-1 --solo-verificar RUTA/...xlsx
"""

from __future__ import annotations

import argparse
import re
import site
import sys
from datetime import datetime
from pathlib import Path

# Con -I Python no mira la carpeta del script ni las librerías del usuario.
# Aquí agregamos a mano solo esas dos rutas, que son de confianza.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(site.getusersitepackages())

import openpyxl  # noqa: E402  (librería para leer Excel)

from base import conectar, huella, normalizar, TABLAS_REGION  # noqa: E402

URL_INVIAS = ("https://www.invias.gov.co/publicaciones/4149/"
              "analisis-de-precios-unitarios-apu-regionalizados-de-referencia/")

# Aquí fijamos el margen de error aceptado: medio peso por redondeo a 2 decimales
TOLERANCIA = 0.5

# Aquí nombramos los cuatro capítulos de un APU tal como aparecen en la hoja
CAPITULOS = {"i. equipo": "equipo", "ii. materiales": "materiales",
             "iii. transportes": "transporte", "iv. mano de obra": "mano_obra"}

# Hojas de un Excel provincial que no son APU individuales
HOJAS_FIJAS = {"PORTADA", "ÍNDICE", "MENÚ", "APU´S", "INSUMO_EQUIPO",
               "INSUMO MATERIALES", "INSUMO_TRANSPORTE", "INSUMO_MANO DE OBRA",
               "IMAGENES_PROVINCIAS", "CLASIFICACIÓN_APU", "HOJA DE CALCULOS ",
               "LISTADO DE PROVINCIAS", "MATERIALES", "EQUIPO", "MANO DE OBRA",
               "TRANSPORTE", "APU BASE"}

# Un código de insumo de INVIAS: letras y números (B0013791, C0010052, A0030040),
# o HERMENINV, la herramienta menor
PATRON_CODIGO = re.compile(r"^([A-Z]+\d+|HERMENINV)$")


def num(valor):
    """Convierte una celda a número; devuelve None si está vacía o no es número."""
    try:
        return float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        return None


def texto(valor) -> str:
    """Convierte una celda a texto limpio (sin espacios sobrantes)."""
    return " ".join(str(valor).split()) if valor is not None else ""


def filas(hoja):
    """Recorre una hoja y entrega (número de fila, valores) de cada fila."""
    for i, f in enumerate(hoja.iter_rows(values_only=True), start=1):
        yield i, f


def celda(f, j):
    """Devuelve la celda j de una fila, o None si la fila es más corta."""
    return f[j] if j < len(f) else None


# ---------------------------------------------------------------------------
# Lectura de los listados de la provincia
# ---------------------------------------------------------------------------

def leer_listado(hoja, tipo):
    """Lee un listado de insumos (materiales, equipo o transporte) de la provincia."""
    insumos, columnas = [], None
    for i, f in filas(hoja):
        nombres = [normalizar(c) for c in f]
        # Aquí ubicamos la fila de encabezados buscando la palabra "codigo"
        if columnas is None:
            if "codigo" in nombres:
                columnas = {n: j for j, n in enumerate(nombres) if n}
            continue
        codigo = texto(celda(f, columnas["codigo"]))
        precio = num(celda(f, columnas.get("precio ($ cop)", -1)))
        # Aquí saltamos filas sin código válido o sin precio (ej. herramienta menor)
        if not PATRON_CODIGO.match(codigo) or precio is None:
            continue
        categoria = celda(f, columnas.get("categoria", columnas.get("clasificacion", -1)))
        insumos.append(dict(tipo=tipo, codigo=codigo,
                            descripcion=texto(celda(f, columnas["insumo"])),
                            unidad=texto(celda(f, columnas["unidad"])),
                            precio=precio, categoria=texto(categoria),
                            hoja=hoja.title, fila=i))
    return insumos


def leer_mano_obra(hoja):
    """Lee el listado de cargos de mano de obra: salario, factor de jornal y prestaciones."""
    cargos, columnas, col_prestacional, smmlv = [], None, None, None
    for i, f in filas(hoja):
        nombres = [normalizar(c) for c in f]
        # Aquí guardamos el salario mínimo que declara la hoja: es el primer número
        # que aparece después del texto "Salario mínimo legal mensual"
        if smmlv is None:
            for j, n in enumerate(nombres):
                if n.startswith("salario minimo legal mensual"):
                    smmlv = next((num(c) for c in f[j + 1:] if num(c) is not None), None)
                    break
        if columnas is None:
            if "codigo" in nombres:
                columnas = {n: j for j, n in enumerate(nombres) if n}
            continue
        # Aquí ubicamos la columna del factor prestacional (su título va una fila abajo)
        if col_prestacional is None and "factor prestacional" in nombres:
            col_prestacional = nombres.index("factor prestacional")
            continue
        codigo = texto(celda(f, columnas["codigo"]))
        if not PATRON_CODIGO.match(codigo):
            continue
        col_multiplo = next(j for n, j in columnas.items() if n.startswith("factor jornal"))
        col_salario = next(j for n, j in columnas.items() if n.startswith("precio base"))
        cargos.append(dict(codigo=codigo, cargo=texto(celda(f, columnas["insumo"])),
                           salario_mensual=num(celda(f, col_salario)),
                           factor_jornal=num(celda(f, col_multiplo)),
                           factor_prestacional=num(celda(f, col_prestacional)),
                           hoja=hoja.title, fila=i))
    return cargos, smmlv


def leer_indice(hoja):
    """Lee el índice de APU de la provincia: un renglón por APU con sus subtotales."""
    apus, departamento, provincia = [], None, None
    for i, f in filas(hoja):
        # Aquí leemos el departamento y la provincia del encabezado (la etiqueta puede
        # estar en cualquier columna; el valor va en la celda siguiente)
        for j, c in enumerate(f):
            if normalizar(c) == "departamento:":
                departamento = texto(celda(f, j + 1))
            elif normalizar(c) == "provincia:":
                provincia = texto(celda(f, j + 1))
        # Aquí tomamos solo los renglones numerados que tienen ítem y costo directo
        if num(celda(f, 0)) is None or num(celda(f, 11)) is None:
            continue
        apus.append(dict(item=texto(celda(f, 4)), capitulo=texto(celda(f, 1)),
                         articulo=texto(celda(f, 2)), clasificacion=texto(celda(f, 3)),
                         descripcion=texto(celda(f, 5)), unidad=texto(celda(f, 6)),
                         sub_equipo=num(celda(f, 7)), sub_materiales=num(celda(f, 8)),
                         sub_transporte=num(celda(f, 9)), sub_mano_obra=num(celda(f, 10)),
                         costo_directo=num(celda(f, 11))))
    return apus, departamento, provincia


def leer_matriz(hoja, departamento, provincia):
    """Lee de la matriz nacional (140 provincias en columnas) la columna de la provincia."""
    clave = normalizar(f"{departamento}{provincia}").replace(" ", "")
    columna, valores = None, {}
    for i, f in filas(hoja):
        # Aquí buscamos la columna cuyo encabezado es "DepartamentoProvincia"
        if columna is None:
            for j, c in enumerate(f):
                if normalizar(c).replace(" ", "") == clave:
                    columna = j
            continue
        codigo = texto(celda(f, 0))
        if PATRON_CODIGO.match(codigo):
            valores[codigo] = num(celda(f, columna))
    return valores


# ---------------------------------------------------------------------------
# Lectura de la hoja de un APU
# ---------------------------------------------------------------------------

def leer_apu(hoja):
    """Lee el desglose de un APU: sus líneas por capítulo, subtotales y total."""
    apu = dict(item=None, unidad=None, provincia=None, publicacion=None,
               lineas=[], subtotales={}, total=None)
    capitulo = None
    for i, f in filas(hoja):
        etiqueta = normalizar(celda(f, 1))
        if etiqueta.startswith("item base de apu"):
            apu["publicacion"] = texto(celda(f, 7))
        elif etiqueta.startswith("unidad ejecutora"):
            apu["provincia"] = texto(celda(f, 11))
        elif i == 33:
            # Aquí leemos el ítem y la unidad del APU (fila fija del formato INVIAS)
            apu["item"], apu["unidad"] = texto(celda(f, 1)), texto(celda(f, 11))
        elif etiqueta in CAPITULOS:
            capitulo = CAPITULOS[etiqueta]
        elif etiqueta.startswith("subtotal") and capitulo:
            apu["subtotales"][capitulo] = num(celda(f, 13)) or 0.0
        elif etiqueta.startswith("total costo directo"):
            apu["total"] = num(celda(f, 13))
        elif etiqueta.startswith("v. costos indirectos"):
            break
        elif capitulo and (PATRON_CODIGO.match(texto(celda(f, 1)))):
            apu["lineas"].append(linea_apu(capitulo, f, hoja.title, i))
    return apu


def linea_apu(capitulo, f, hoja, fila):
    """Convierte una fila del APU en un registro, según las columnas de su capítulo."""
    l = dict(componente=capitulo, codigo=texto(celda(f, 1)), descripcion=texto(celda(f, 2)),
             unidad=None, cantidad=None, distancia=None, precio=None, prestaciones=None,
             rendimiento=None, valor=num(celda(f, 13)), hoja=hoja, fila=fila)
    if capitulo == "equipo":
        # Equipo: tarifa por hora por rendimiento (horas por unidad)
        l.update(unidad=texto(celda(f, 9)), precio=num(celda(f, 10)), rendimiento=num(celda(f, 11)))
    elif capitulo == "materiales":
        l.update(unidad=texto(celda(f, 9)), cantidad=num(celda(f, 10)), precio=num(celda(f, 11)))
    elif capitulo == "transporte":
        l.update(unidad=texto(celda(f, 8)), cantidad=num(celda(f, 9)),
                 distancia=num(celda(f, 10)), precio=num(celda(f, 12)))
    elif capitulo == "mano_obra":
        # Mano de obra: jornal por prestaciones, dividido por el rendimiento (unidades por día)
        l.update(unidad="jornal", precio=num(celda(f, 8)), prestaciones=num(celda(f, 9)),
                 rendimiento=num(celda(f, 11)))
    return l


def valor_esperado(l):
    """Recalcula el valor de una línea del APU con su propia fórmula."""
    if l["codigo"] == "HERMENINV":
        # Herramienta menor: un porcentaje de la mano de obra del APU
        return (l["precio"] or 0) * (l["rendimiento"] or 0)
    if l["componente"] == "equipo":
        return (l["precio"] or 0) * (l["rendimiento"] or 0)
    if l["componente"] == "materiales":
        return (l["cantidad"] or 0) * (l["precio"] or 0)
    if l["componente"] == "transporte":
        return (l["cantidad"] or 0) * (l["distancia"] or 0) * (l["precio"] or 0)
    if l["componente"] == "mano_obra":
        return (l["precio"] or 0) * (l["prestaciones"] or 0) / l["rendimiento"] if l["rendimiento"] else 0
    return None


# ---------------------------------------------------------------------------
# Verificación de integridad
# ---------------------------------------------------------------------------

class Verificador:
    """Acumula los chequeos de integridad y sus resultados."""

    def __init__(self):
        self.resultados = []

    def advertir(self, nombre, casos, total):
        """Registra un defecto de la fuente que no impide cargar, pero que se informa."""
        if casos:
            self.resultados.append((nombre, "ADVERTENCIA",
                                    f"{len(casos)} de {total}: " + "; ".join(str(x) for x in casos)))

    def chequear(self, nombre, fallas, total, detalle_ok=""):
        """Registra un chequeo: OK si no hubo fallas, FALLA con ejemplos si las hubo."""
        if fallas:
            ejemplos = "; ".join(str(x) for x in fallas[:5])
            self.resultados.append((nombre, "FALLA", f"{len(fallas)} de {total}. Ej.: {ejemplos}"))
        else:
            self.resultados.append((nombre, "OK", detalle_ok or f"{total} revisados"))

    @property
    def todo_ok(self):
        return all(r[1] != "FALLA" for r in self.resultados)


def verificar(datos):
    """Corre todos los chequeos sobre lo leído de un Excel provincial."""
    v = Verificador()
    indice = {a["item"]: a for a in datos["indice"]}
    apus = datos["apus"]

    # 1. Cada APU del índice tiene su hoja, y no sobran hojas
    faltan = sorted(set(indice) - set(apus))
    sobran = sorted(set(apus) - set(indice))
    v.chequear("conteo: APU del índice vs hojas de APU", faltan + sobran, len(indice),
               f"{len(indice)} APU en el índice, {len(apus)} hojas")

    # 2. Cada hoja de APU es de la provincia del archivo
    ajenas = [k for k, a in apus.items() if normalizar(a["provincia"]) != normalizar(datos["provincia"])]
    v.chequear("provincia de cada hoja de APU", ajenas, len(apus))

    # 3. Cada línea vale lo que dice su fórmula. Las líneas que la fuente dejó sin
    # descripción, precio ni valor (su fórmula no encontró el insumo) se reportan aparte
    malas, sin_precio, n = [], [], 0
    for k, a in apus.items():
        for l in a["lineas"]:
            n += 1
            if l["valor"] is None and l["precio"] is None and not l["descripcion"]:
                sin_precio.append(f"{k} {l['codigo']}")
                continue
            esperado = valor_esperado(l)
            if l["valor"] is None or abs(esperado - l["valor"]) > TOLERANCIA:
                malas.append(f"{k} {l['codigo']}: hoja {l['valor']} vs calculado {round(esperado, 2)}")
    v.chequear("cada línea = cantidad x precio (o tarifa x rendimiento)", malas, n,
               f"{n} líneas revisadas")
    v.advertir("insumos sin precio en la fuente (valen 0 dentro del APU de INVIAS)", sin_precio, n)

    # 4. Cada capítulo suma su subtotal, y los subtotales suman el costo directo
    malos = []
    for k, a in apus.items():
        for cap in CAPITULOS.values():
            suma = sum(l["valor"] or 0 for l in a["lineas"] if l["componente"] == cap)
            if abs(suma - a["subtotales"].get(cap, 0.0)) > TOLERANCIA:
                malos.append(f"{k} {cap}: líneas {round(suma, 2)} vs subtotal {a['subtotales'].get(cap)}")
        if a["total"] is None or abs(sum(a["subtotales"].values()) - a["total"]) > TOLERANCIA:
            malos.append(f"{k}: subtotales {round(sum(a['subtotales'].values()), 2)} vs total {a['total']}")
    v.chequear("líneas = subtotal por capítulo, subtotales = costo directo", malos, len(apus))

    # 5. Cada APU cuadra con su renglón del índice
    campos = {"equipo": "sub_equipo", "materiales": "sub_materiales",
              "transporte": "sub_transporte", "mano_obra": "sub_mano_obra"}
    malos = []
    for k, a in apus.items():
        if k not in indice:
            continue
        for cap, campo in campos.items():
            if abs(a["subtotales"].get(cap, 0.0) - (indice[k][campo] or 0)) > TOLERANCIA:
                malos.append(f"{k} {cap}: hoja {a['subtotales'].get(cap)} vs índice {indice[k][campo]}")
        if abs((a["total"] or 0) - indice[k]["costo_directo"]) > TOLERANCIA:
            malos.append(f"{k}: hoja {a['total']} vs índice {indice[k]['costo_directo']}")
    suma_hojas = sum(a["total"] or 0 for a in apus.values())
    suma_indice = sum(a["costo_directo"] for a in datos["indice"])
    v.chequear("APU = índice (subtotales y costo directo)", malos, len(apus),
               f"suma de costos directos: hojas {suma_hojas:,.2f} = índice {suma_indice:,.2f}")

    # 6. Los precios usados dentro de los APU son los del listado de la provincia
    listado = {(i["tipo"], i["codigo"]): i["precio"] for i in datos["insumos"]}
    cargos = {c["codigo"]: c for c in datos["mano_obra"]}
    tipo_de = {"equipo": "equipo", "materiales": "material", "transporte": "transporte"}
    malos, n = [], 0
    for k, a in apus.items():
        for l in a["lineas"]:
            if l["codigo"] == "HERMENINV" or f"{k} {l['codigo']}" in sin_precio:
                continue
            n += 1
            if l["componente"] == "mano_obra":
                c = cargos.get(l["codigo"])
                jornal = c["salario_mensual"] / 30 if c else None
                ok = (c and l["precio"] is not None and l["prestaciones"] is not None
                      and abs(jornal - l["precio"]) <= 0.01
                      and abs(c["factor_prestacional"] - l["prestaciones"]) <= 1e-6)
            else:
                p = listado.get((tipo_de[l["componente"]], l["codigo"]))
                ok = p is not None and l["precio"] is not None and abs(p - l["precio"]) <= 0.01
            if not ok:
                malos.append(f"{k} {l['codigo']}")
    v.chequear("precios de los APU = listado de la provincia", malos, n, f"{n} líneas revisadas")

    # 7. El listado de la provincia coincide con la matriz nacional del mismo archivo
    malos, n = [], 0
    for tipo, matriz in datos["matrices"].items():
        for i in (x for x in datos["insumos"] if x["tipo"] == tipo):
            n += 1
            m = matriz.get(i["codigo"])
            if m is None or abs(m - i["precio"]) > 0.01:
                malos.append(f"{tipo} {i['codigo']}: listado {i['precio']} vs matriz {m}")
    v.chequear("listado de la provincia = matriz nacional", malos, n, f"{n} insumos revisados")
    return v


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def leer_excel(ruta: Path):
    """Lee todo lo necesario de un Excel provincial de INVIAS."""
    region = re.match(r"APU_(\d{4})_", ruta.name)
    if not region:
        sys.exit(f"El nombre {ruta.name} no tiene el patrón APU_<código>_..._<edición>.xlsx")
    # Aquí abrimos el Excel en modo solo lectura y con los valores ya calculados
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    indice, departamento, provincia = leer_indice(wb["ÍNDICE"])
    insumos = (leer_listado(wb["MATERIALES"], "material") + leer_listado(wb["EQUIPO"], "equipo")
               + leer_listado(wb["TRANSPORTE"], "transporte"))
    mano_obra, smmlv = leer_mano_obra(wb["MANO DE OBRA"])
    matrices = {"material": leer_matriz(wb["INSUMO MATERIALES"], departamento, provincia),
                "equipo": leer_matriz(wb["INSUMO_EQUIPO"], departamento, provincia),
                "transporte": leer_matriz(wb["INSUMO_TRANSPORTE"], departamento, provincia)}
    # Aquí leemos cada hoja de APU individual (las que se llaman como un ítem, ej. "200,1,1")
    apus = {}
    for nombre in wb.sheetnames:
        if nombre not in HOJAS_FIJAS and nombre[:1].isdigit():
            a = leer_apu(wb[nombre])
            apus[a["item"]] = a
    wb.close()
    return dict(region=region.group(1), departamento=departamento, provincia=provincia,
                indice=indice, insumos=insumos, mano_obra=mano_obra, smmlv=smmlv,
                matrices=matrices, apus=apus)


def corregir(datos):
    """Corrige los insumos que la fuente dejó sin precio por un error de su fórmula.

    Caso conocido (2026-1): en algunos APU el código del material trae un salto de
    línea, la fórmula de INVIAS no lo encuentra en su listado y cuenta ese material
    en $0. Aquí tomamos el precio del listado de la misma provincia, recalculamos la
    línea y el costo directo, y dejamos la nota. Lo publicado por INVIAS no se toca:
    queda en 'valor' y 'costo_directo'; lo corregido va en columnas aparte.
    """
    listado = {(i["tipo"], i["codigo"]): i for i in datos["insumos"]}
    tipo_de = {"equipo": "equipo", "materiales": "material", "transporte": "transporte"}
    correcciones = []
    for k, a in datos["apus"].items():
        ajuste = 0.0
        for l in a["lineas"]:
            l["valor_corregido"], l["nota"] = l["valor"], None
            if l["valor"] is not None or l["precio"] is not None or l["descripcion"]:
                continue
            ref = listado.get((tipo_de.get(l["componente"]), l["codigo"]))
            if ref is None:
                continue
            # Aquí recalculamos la línea con el precio del listado de la provincia
            l["descripcion"] = l["descripcion"] or ref["descripcion"]
            l["unidad"] = l["unidad"] or ref["unidad"]
            if l["componente"] == "transporte":
                l["valor_corregido"] = round((l["cantidad"] or 0) * (l["distancia"] or 0) * ref["precio"], 2)
            else:
                l["valor_corregido"] = round((l["cantidad"] or 0) * ref["precio"], 2)
            l["nota"] = (f"Corregido por Constructo: INVIAS lo cuenta en $0 porque su fórmula no encontró "
                         f"el código; se usó el precio del listado de la provincia ({ref['precio']:.2f}).")
            ajuste += l["valor_corregido"]
        a["ajuste"] = ajuste
        if ajuste:
            correcciones.append(f"{k} +{ajuste:,.2f}")
    # Aquí trasladamos la corrección al renglón del índice de cada APU
    for fila in datos["indice"]:
        ajuste = datos["apus"].get(fila["item"], {}).get("ajuste", 0.0)
        fila["costo_directo_corregido"] = round(fila["costo_directo"] + ajuste, 2)
        fila["nota"] = (f"Corregido por Constructo: INVIAS publica {fila['costo_directo']:,.2f}, pero deja "
                        f"insumos en $0 por un error de su fórmula; con los precios de su listado da "
                        f"{fila['costo_directo_corregido']:,.2f}.") if ajuste else None
    if correcciones:
        datos["verificacion"].resultados.append(
            ("correcciones aplicadas (lo publicado se conserva aparte)", "CORREGIDO",
             f"{len(correcciones)} APU: " + "; ".join(correcciones)))


def insertar(con, tabla, filas):
    """Inserta una lista de diccionarios en una tabla, columna por columna por nombre."""
    if not filas:
        return
    columnas = list(filas[0])
    con.executemany(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
                    [tuple(f[c] for c in columnas) for f in filas])


def guardar(con, edicion, ruta, datos):
    """Reemplaza en la base los datos de esta edición y provincia, todo o nada."""
    publicacion = next((a["publicacion"] for a in datos["apus"].values() if a["publicacion"]), None)
    with con:  # Aquí abrimos una transacción: si algo falla, no queda nada a medias
        con.execute("INSERT OR IGNORE INTO ediciones (fuente, edicion, url, uso) VALUES "
                    "('invias', ?, ?, 'precios')", (edicion, URL_INVIAS))
        con.execute("UPDATE ediciones SET publicacion = ?, notas = ? WHERE fuente = 'invias' AND edicion = ?",
                    (publicacion, f"Salario mínimo declarado en la hoja de mano de obra: {datos['smmlv']}", edicion))
        eid = con.execute("SELECT id FROM ediciones WHERE fuente='invias' AND edicion=?",
                          (edicion,)).fetchone()[0]
        r = datos["region"]
        # Aquí borramos lo que hubiera de esta provincia en esta edición antes de recargar
        for t in TABLAS_REGION:
            con.execute(f"DELETE FROM {t} WHERE edicion_id=? AND region=?", (eid, r))
        base = dict(edicion_id=eid, region=r)
        insertar(con, "archivos", [dict(base, archivo=ruta.name, sha256=huella(ruta), bytes=ruta.stat().st_size,
                                        cargado_en=datetime.now().isoformat(timespec="seconds"))])
        insertar(con, "regiones", [dict(base, departamento=datos["departamento"], provincia=datos["provincia"])])
        insertar(con, "insumos", [dict(base, **{c: i[c] for c in ("tipo", "codigo", "descripcion", "unidad",
                                                                  "precio", "categoria", "hoja", "fila")})
                                  for i in datos["insumos"]])
        insertar(con, "mano_obra", [dict(base, **c) for c in datos["mano_obra"]])
        insertar(con, "apu", [dict(base, **a, hoja=a["item"]) for a in datos["indice"]])
        insertar(con, "apu_detalle", [dict(base, item=k, **l) for k, a in datos["apus"].items()
                                      for l in a["lineas"]])
        insertar(con, "verificaciones", [dict(base, chequeo=n, resultado=res, detalle=d)
                                         for n, res, d in datos["verificacion"].resultados])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--edicion", required=True, help="edición INVIAS, ej. 2026-1")
    p.add_argument("--solo-verificar", action="store_true", help="verifica sin escribir en la base")
    p.add_argument("archivos", nargs="+", type=Path)
    args = p.parse_args()

    con = None if args.solo_verificar else conectar()
    fallidos = 0
    for ruta in args.archivos:
        print(f"\n== {ruta.name}")
        datos = leer_excel(ruta)
        datos["verificacion"] = verificar(datos)
        corregir(datos)
        # Aquí mostramos el resultado de cada chequeo
        for nombre, resultado, detalle in datos["verificacion"].resultados:
            print(f"  [{resultado}] {nombre}: {detalle}")
        if not datos["verificacion"].todo_ok:
            fallidos += 1
            print("  NO SE CARGÓ: hay chequeos fallidos.")
        elif con:
            guardar(con, args.edicion, ruta, datos)
            print(f"  Cargado: {datos['departamento']} / {datos['provincia']} (región {datos['region']}), "
                  f"{len(datos['indice'])} APU, {len(datos['insumos'])} insumos, "
                  f"{len(datos['mano_obra'])} cargos.")
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()
