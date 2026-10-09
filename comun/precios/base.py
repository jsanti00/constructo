"""Piezas compartidas de la base central de precios de referencia.

La base es un solo archivo SQLite (una base de datos guardada en un archivo) que
vive fuera de OneDrive y fuera de git. Guarda fuentes públicas de precios (INVIAS,
IDU, ...) por edición y por región, con la procedencia de cada dato.

Ningún dato de obra entra aquí: solo precios de referencia públicos o con licencia.
"""

from __future__ import annotations

import hashlib
import sqlite3
import unicodedata
from pathlib import Path

# Aquí definimos dónde vive la base y la carpeta de los Excel crudos (fuera de OneDrive)
DATOS = Path.home() / "Datos" / "constructo"
BASE = DATOS / "precios.sqlite"
CRUDOS = DATOS / "crudos"

# Aquí describimos las tablas de la base. Cada fila guarda de qué edición, región,
# hoja y fila del Excel salió, para que el agente pueda citar la procedencia.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS ediciones (
    id INTEGER PRIMARY KEY,
    fuente TEXT NOT NULL,              -- ej. 'invias'
    edicion TEXT NOT NULL,             -- ej. '2026-1'
    publicacion TEXT,                  -- fecha o texto de publicación que trae el Excel
    url TEXT,                          -- página oficial de donde se descarga
    uso TEXT NOT NULL,                 -- 'precios' o 'solo rendimientos'
    notas TEXT,
    UNIQUE (fuente, edicion)
);
CREATE TABLE IF NOT EXISTS archivos (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    archivo TEXT NOT NULL,             -- nombre del Excel original
    sha256 TEXT NOT NULL,              -- huella digital: prueba qué archivo exacto se usó
    bytes INTEGER NOT NULL,
    cargado_en TEXT NOT NULL,
    PRIMARY KEY (edicion_id, region)
);
CREATE TABLE IF NOT EXISTS regiones (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,              -- código de la fuente, ej. '2510'
    departamento TEXT,
    provincia TEXT,
    PRIMARY KEY (edicion_id, region)
);
CREATE TABLE IF NOT EXISTS insumos (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    tipo TEXT NOT NULL,                -- 'material', 'equipo' o 'transporte'
    codigo TEXT NOT NULL,
    descripcion TEXT,
    unidad TEXT,
    precio REAL,
    categoria TEXT,
    actualizacion TEXT,                -- cuándo actualizó la fuente este precio (si lo dice)
    hoja TEXT, fila INTEGER
);
CREATE TABLE IF NOT EXISTS mano_obra (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    codigo TEXT NOT NULL,
    cargo TEXT,
    salario_mensual REAL,              -- salario base mensual del cargo
    factor_jornal REAL,                -- múltiplo del salario del Obrero, tal como lo publica INVIAS
    factor_prestacional REAL,          -- multiplicador por prestaciones sociales
    hoja TEXT, fila INTEGER
);
CREATE TABLE IF NOT EXISTS apu (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    item TEXT NOT NULL,                -- ítem de pago, ej. '200,1,1'
    capitulo TEXT, articulo TEXT, clasificacion TEXT,
    descripcion TEXT, unidad TEXT,
    sub_equipo REAL, sub_materiales REAL, sub_transporte REAL, sub_mano_obra REAL,
    costo_directo REAL,                -- tal como lo publica la fuente
    costo_directo_corregido REAL,      -- igual al anterior, salvo que corrijamos un error de la fuente
    nota TEXT,                         -- explica la corrección, si la hay
    actualizacion TEXT,
    hoja TEXT
);
CREATE TABLE IF NOT EXISTS apu_detalle (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    item TEXT NOT NULL,
    componente TEXT NOT NULL,          -- 'equipo', 'materiales', 'transporte', 'mano_obra'
    codigo TEXT, descripcion TEXT, unidad TEXT,
    cantidad REAL,                     -- cantidad de material o de transporte
    distancia REAL,                    -- solo transporte
    precio REAL,                       -- tarifa/hora, precio unitario, tarifa o jornal
    prestaciones REAL,                 -- solo mano de obra
    rendimiento REAL,                  -- equipo y mano de obra: horas o jornales por unidad
    valor REAL,                        -- lo que aporta la línea al costo del APU, según la fuente
    valor_corregido REAL,              -- igual al anterior, salvo que corrijamos un error de la fuente
    nota TEXT,                         -- explica la corrección, si la hay
    hoja TEXT, fila INTEGER
);
CREATE TABLE IF NOT EXISTS verificaciones (
    edicion_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    chequeo TEXT NOT NULL,
    resultado TEXT NOT NULL,           -- 'OK' o 'FALLA'
    detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_insumos ON insumos (edicion_id, region, codigo);
CREATE INDEX IF NOT EXISTS ix_apu ON apu (edicion_id, region, item);
CREATE INDEX IF NOT EXISTS ix_detalle ON apu_detalle (edicion_id, region, item);
"""

# Tablas que guardan datos de una región: se borran y recargan juntas
TABLAS_REGION = ["insumos", "mano_obra", "apu", "apu_detalle", "verificaciones",
                 "regiones", "archivos"]


def conectar(ruta: Path = BASE) -> sqlite3.Connection:
    """Abre la base (la crea si no existe) y se asegura de que tenga las tablas."""
    # Aquí creamos la carpeta de datos si todavía no existe
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA)
    # Aquí registramos una función para buscar texto sin importar tildes ni mayúsculas
    con.create_function("norm", 1, normalizar)
    return con


def normalizar(texto) -> str:
    """Quita tildes, espacios dobles y mayúsculas para comparar textos."""
    if texto is None:
        return ""
    # Aquí separamos cada letra de su tilde y nos quedamos solo con la letra
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", str(texto))
                         if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def huella(ruta: Path) -> str:
    """Calcula la huella digital (sha256) de un archivo para probar cuál se usó."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        # Aquí leemos el archivo por pedazos de 1 MB para no llenar la memoria
        for pedazo in iter(lambda: f.read(1 << 20), b""):
            h.update(pedazo)
    return h.hexdigest()
