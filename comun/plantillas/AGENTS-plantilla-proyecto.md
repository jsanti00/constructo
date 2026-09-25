# AGENTS.md: <Nombre del proyecto>

> **Última actualización:** <fecha>. Verifica contra el contenido real de la carpeta si lees esto mucho después.

**TL;DR:** <Qué es este proyecto en dos frases: qué obra, dónde, en qué moneda, y cuál es la fuente única de cada dominio.>

**Destino de este espacio:** workspace del agente <nombre del bot> (@<usuario>), <estado: en desarrollo / en producción desde <fecha>>. El agente debe conocer el contexto del proyecto y saber **con cuánta autoridad afirmar cada dato** (ver sección 2).

**Quién consulta el agente:** <nombres y rol>. Los ids autorizados viven en `_agente/config.py` (`ALLOWED_USER_IDS`). Consecuencia al escribir aquí: **lo que se guarde en esta carpeta lo pueden leer esos usuarios**, salvo lo que esté en `_restringido/`.

Este es un contexto hijo. Aplica primero el `AGENTS.md` de `Constructo/` (doctrina común) y el raíz del OneDrive.

---

## 1. El stakeholder y su criterio (leer antes que nada)

**Quién es:** <dueño de obra / contratista / interventor / otro>.

**Qué decide con este agente:** <las 3 a 5 decisiones reales que el agente apoya>.

**Cuál es su exposición económica:** <qué le hace ganar y qué le hace perder plata en este contrato: modelo de contratación, quién asume sobrecostos, quién asume mayores cantidades>. Esto define el sesgo de todo análisis del proyecto.

**Qué NO le interesa:** <lo que sería relevante para otro stakeholder pero no para este; evita importar análisis ajenos>.

---

## 2. Estructura y naturaleza de los archivos

Se aplica la doctrina común (`../AGENTS.md`, sección 3.1): dentro de cada dominio, `originales/` y `procesado/` son **dato oficial**; `analisis/` es **trabajo propio, sujeto a validación** y nunca se presenta como oficial.

### Mapa de la carpeta

| Carpeta / archivo | Contenido | Uso |
|---|---|---|
| `<Dominio 1>/` | <qué hay> | <cómo usarlo> |
| `<Dominio 2>/` | <qué hay> | <cómo usarlo> |
| `_entrada/` | Buzón de ingesta de material sin clasificar | Se clasifica y mueve con revisión humana |
| `_restringido/` | Material fuera del alcance del agente | Único punto de exclusión |
| `_agente/` | Código de la instancia del bot | El agente no lo lee |
| `<Archivo de estado vigente>.md` | Registro vivo de validaciones y decisiones | **El estado vigente de cada ítem se lee y se escribe solo aquí** |

---

## 3. Reglas de trabajo

- **Empieza siempre por `<ruta del contexto principal>`.** <Por qué: dónde está destilado el dato y qué no hay que abrir.>
- **Distingue la naturaleza al responder:** dato de `originales/` o `procesado/` es oficial; de `analisis/` es interno y se presenta como tal. No los mezcles.
- **Regla dura de evidencia:** lo dicho verbalmente es `DECLARADO EN SESION`, no `CONFIRMADO`, y no reemplaza un valor contractual hasta que llegue el documento. Solo `CONFIRMADO`, `AJUSTAR` y `DESCARTADO` fijan un valor.
- **No edites archivos generados** (CSV, Excel o HTML de salida de un script): corrige el original o el script y regenera con `<comando>`, verificando `<criterio de integridad>`.
- **Material nuevo** cae primero en `_entrada/` y se clasifica con revisión humana, nunca en silencio.
- <Reglas específicas del proyecto: qué scripts regeneran qué, qué columnas son de solo lectura, qué se abre con visión y qué no.>
