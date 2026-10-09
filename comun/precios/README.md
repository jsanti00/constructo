# precios: base central de precios de referencia

Una sola base de precios públicos (INVIAS, IDU, ...) que consultan los agentes de todas las obras, cada uno limitado a sus regiones. **No contiene datos de ninguna obra**: solo referencias públicas o con licencia.

## Dónde vive cada cosa

| Qué | Dónde | Por qué |
|---|---|---|
| Código | esta carpeta (`comun/precios/`) | Maquinaria común, versionada en git |
| Base de precios | `~/Datos/constructo/precios.sqlite` | Fuera de OneDrive (OneDrive corrompe SQLite al sincronizar) y fuera de git |
| Excel de respaldo | `~/Datos/constructo/crudos/<fuente>/<edición>/` | El archivo nacional de cada edición (ej. `Territorio_APU_2026_1.xlsx`) y los provinciales que se cargaron, por si la fuente deja de publicarlos |

## Qué hay cargado (al 2026-10-09)

| Fuente | Edición | Regiones | Obra que la usa |
|---|---|---|---|
| INVIAS | 2026-1 | 2510 Cundinamarca / Sabana Centro | Obras en Tocancipá, cuando tengan agente |
| INVIAS | 2026-1 | 6805 Santander / Soto (Bucaramanga) | Obra en Bucaramanga (agente conectado) |
| IDU | 2026-I-Fase-II | bogota | Obra en Bogotá, cuando tenga agente |

Otra provincia de INVIAS se agrega descargando su Excel provincial y cargándolo con `extraer_invias.py`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `base.py` | Define las tablas de la base y utilidades comunes (normalizar texto, huella del archivo) |
| `extraer_invias.py` | Lee un Excel provincial de INVIAS, verifica su integridad y, solo si todo cuadra, lo carga |
| `extraer_idu.py` | Lo mismo para el visor del IDU (Bogotá): insumos y valor total de APU, sin desglose |
| `consultar_precios.py` | La herramienta de solo lectura que usa el agente: `fuentes`, `buscar`, `apu` |

## Cargar una edición de INVIAS

Los Excel son descargados de internet: se copian a `~/Datos/constructo/crudos/` y se leen siempre con `python3 -I`.

```
python3 -I extraer_invias.py --edicion 2026-1 --solo-verificar RUTA/APU_2510_..._2026_1.xlsx   # solo revisa
python3 -I extraer_invias.py --edicion 2026-1 RUTA/APU_*.xlsx                                   # revisa y carga
```

Cada provincia se reemplaza completa, en una sola transacción. Si un chequeo falla, esa provincia no se carga.

### Qué verifica

1. Hay una hoja por cada APU del índice, y ninguna de más.
2. Cada hoja de APU es de la provincia del archivo.
3. Cada línea vale lo que dice su fórmula (cantidad x precio, tarifa x rendimiento, jornal x prestaciones / rendimiento).
4. Las líneas suman el subtotal de su capítulo, y los subtotales suman el costo directo.
5. Cada APU cuadra con su renglón del índice, y la suma total de costos directos coincide.
6. Los precios usados dentro de los APU son los del listado de la provincia.
7. El listado de la provincia coincide con la matriz nacional del mismo archivo.

Los defectos de la propia fuente que no rompen el cuadre quedan como `ADVERTENCIA`: no bloquean la carga.

### Correcciones a la fuente

Cuando un error de la fuente tiene arreglo inequívoco, se corrige **sin borrar lo publicado**: el valor de la fuente queda en `valor` y `costo_directo`, y el corregido en `valor_corregido` y `costo_directo_corregido`, con su `nota`. La consulta muestra ambos y dice que la corrección es de Constructo.

Caso conocido, INVIAS 2026-1: en los APU 801,1 y 801,2 (cercas de alambre de púas) tres materiales traen el código con un salto de línea, la fórmula de INVIAS no los encuentra y los cuenta en $0. Se corrigen con el precio del listado de la misma provincia: el 801,1 pasa de unos $7.300 a unos $20.400 por metro.

## Consultar

Las regiones las fija el arranque del agente en `PRECIOS_REGIONES` (`fuente:región`, separadas por coma). Sin esa variable no responde nada.

```
PRECIOS_REGIONES="invias:2510" python3 -I consultar_precios.py fuentes
PRECIOS_REGIONES="invias:2510" python3 -I consultar_precios.py buscar "acero refuerzo"
PRECIOS_REGIONES="invias:2510" python3 -I consultar_precios.py apu 630,4
```

Toda respuesta empieza con la regla de autoridad: **es una referencia pública, no el precio de la obra**.

## Notas sobre INVIAS

- Los 140 Excel provinciales repiten los mismos datos base (composición de los APU y matrices de precios de las 140 provincias). Lo propio de cada uno es el cálculo ya hecho para su provincia: rendimientos ajustados por altitud y temperatura, y costo de cada APU. Por eso se cargan desde el archivo provincial y no se reimplementan las fórmulas de INVIAS.
- En mano de obra, el "rendimiento" es unidades por jornal (el valor se divide), mientras que en equipo es horas por unidad (el valor se multiplica).
- No cubre Bogotá D.C. ni acabados de edificación: es una base de obra vial.

## Conexión con los agentes

`agente/cerebro.py` le da la herramienta al agente solo si su archivo de arranque define `PRECIOS_REGIONES` (hoy solo la obra en producción: `invias:6805`). Los comandos de Bash del agente corren en el sandbox de Claude Code: pueden leer la carpeta de su obra y `~/Datos/constructo`, pero no otras obras, el resto del OneDrive ni los secretos.

## Actualización de las fuentes

- INVIAS publica dos ediciones al año (AAAA-1 y AAAA-2) sin fecha fija. El IDU publica Fase I (mayo-junio), Fase II (agosto-septiembre) y un ajuste de mano de obra en enero. Ninguna avisa.
- Por ahora la revisión es manual: hay un recordatorio en el calendario cada 15 de febrero, junio y octubre (`Constructo/Calendario/revisar-precios-referencia.json`).
- **Deuda técnica:** automatizar la revisión (un vigía semanal que compare las páginas de descarga y avise si hay edición nueva).
