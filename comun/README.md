# _comun: qué se reutiliza entre proyectos

Andamios reutilizables para arrancar y mantener un proyecto de agente de obra. **No es un proyecto y no contiene datos de ninguna obra.**

## Regla dura

**Nunca guardes aquí un dato de obra** (cifras, cantidades, nombres de oferentes, precios). Esta carpeta es visible desde todos los proyectos por diseño, así que un dato de obra aquí es un dato filtrado a los usuarios de las otras obras. Solo método, plantillas y código.

## Contenido

| Carpeta | Qué hay |
|---|---|
| `plantillas/` | Andamios para crear un proyecto nuevo: `AGENTS.md` de proyecto y los READMEs de los buzones |
| `scripts/` | Utilidades que sirven a cualquier proyecto. Hoy solo `hidratar.py`, que fuerza la descarga de los archivos que OneDrive dejó como placeholder (ver abajo) |

## Sobre `scripts/hidratar.py`

OneDrive en macOS deja archivos como placeholder: el tamaño aparece en `ls`, pero la primera lectura se queda esperando la descarga. En archivos pesados eso son minutos, y para un agente es indistinguible de estar colgado.

`hidratar.py` recorre solo las carpetas listadas en `scripts/carpetas.conf` y lee una vez cada archivo nuevo, lo que obliga a OneDrive a bajarlo. Lleva un manifiesto en `~/.local/state/hidratar-obras/` para no repetir trabajo, así que una corrida sin novedades cuesta un par de segundos.

```
python3 _comun/scripts/hidratar.py --dry-run   # qué falta por descargar
python3 _comun/scripts/hidratar.py             # descargarlo
```

### Automatización

Corre solo cada 5 minutos vía launchd, con el servicio `com.santiago.hidratar-obras`. El plist versionado es `scripts/com.santiago.hidratar-obras.plist` y se instala copiándolo a `~/Library/LaunchAgents/`.

```
launchctl list | grep hidratar                                  # está corriendo?
launchctl kickstart -k gui/$(id -u)/com.santiago.hidratar-obras  # forzar una corrida
tail ~/.local/state/hidratar-obras/hidratar.log                  # qué ha descargado
```

**El detalle que hace o rompe esto:** el plist tiene que invocar el binario real de Python, no `/usr/bin/python3`.

```
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
```

macOS exige Acceso Total al Disco para leer `~/Library/CloudStorage`, y ese permiso está concedido a `Python.app`. `/usr/bin/python3` es un stub: un proceso lanzado por él no hereda el permiso y **todas las lecturas fallan con "Operation not permitted", en silencio y con código de salida 0**. El síntoma es un servicio que parece sano y no hace nada. Es el mismo problema que tuvo el servicio `onedrive-md-sync`.

Como complemento, no como reemplazo, conviene marcar la carpeta en Finder con clic derecho y **"Mantener siempre en este dispositivo"**: es el mecanismo nativo de OneDrive y no depende de ningún script.

## Cómo arrancar un proyecto nuevo

1. Crea la carpeta del proyecto bajo `Agentes para construccion/`, nombrada `<Obra> (<stakeholder>)`.
2. Copia `plantillas/AGENTS-plantilla-proyecto.md` a la raíz del proyecto como `AGENTS.md` y llena los marcadores `<...>`.
3. Crea `_entrada/` y `_restringido/` con los READMEs de `plantillas/`.
4. Define los **dominios** según el ciclo de decisión de ese stakeholder. No copies los dominios de otro proyecto: el contratista y el dueño de obra no se hacen las mismas preguntas.
5. Dentro de cada dominio usa `originales/`, `procesado/` y `analisis/` según apliquen (ver sección 3.1 del `AGENTS.md` padre).
6. Registra el proyecto en la tabla del `AGENTS.md` padre.

## Sobre el código del agente

Desde septiembre de 2026 el código vive en su propio repositorio, fuera de las carpetas de datos, y la obra que lee se le pasa en la variable `OBRA_RAIZ`. Lo que siga siendo específico de una obra se abstrae **cuando exista una segunda instancia en operación**, no antes: con una sola instancia no se distingue lo genérico de lo específico, y una abstracción prematura cuesta más de la que ahorra.

Cuando se abstraiga, se mantiene el principio de **una instancia por obra**: mismo código, procesos separados, cada uno con su token de Telegram, su allowlist y su raíz de datos. Ninguna instancia carga el contexto de otra obra.
