# Agente de Telegram de una obra

Este es el código del asistente que los ingenieros consultan por Telegram. Corre
en tu Mac, lee la carpeta de la obra (la que le indique la variable `OBRA_RAIZ`) y responde
preguntas sobre el presupuesto, los planos, el cronograma y los análisis.

**Esta carpeta (`_agente/`) es código, no información del proyecto.** El propio
agente no la lee (está en su lista de exclusión, junto con `_restringido/`).

## Qué hace cada archivo

| Archivo | Para qué |
|---|---|
| `config.py` | Ajustes que tú cambias: lista de ingenieros autorizados, modelo, esfuerzo |
| `cerebro.py` | La lógica del agente: lee los archivos del proyecto y le pregunta a Claude |
| `bot_telegram.py` | Conecta con Telegram; es el que se ejecuta para poner el agente en línea |
| `requirements.txt` | Las librerías que hay que instalar |

## Puesta en marcha (una sola vez)

### 1. Crear el bot en Telegram
En Telegram, escríbele a **@BotFather**, manda `/newbot` y sigue los pasos
(nombre y usuario del bot). Al final te da un **token** (una cadena larga tipo
`8123456:AAH...`). Guárdalo, es la llave del bot.

### 2. Instalar las librerías
En la terminal, dentro de esta carpeta `_agente/`:
```
pip3 install -r requirements.txt
```

### 3. Conseguir el id de cada ingeniero
Cada ingeniero debe escribirle a **@userinfobot** en Telegram; ese bot le
responde con su **Id** (un número). Pon esos números en `config.py`, en la lista
`ALLOWED_USER_IDS`. Sin esto, el agente no le responde a nadie (es la seguridad).

### 4. Guardar el token del bot
Es la única llave que hace falta. **No se usa API key**: el agente piensa
llamando al programa `claude` (Claude Code) ya instalado en el Mac, con la
suscripción de Santiago.

El token no va en el código ni dentro de esta carpeta (está en OneDrive y se
sincroniza a la nube). Va en un archivo aparte, en la carpeta personal del Mac:

```
~/.config/agente-obra/.env
```

Ábrelo y reemplaza el valor de ejemplo por el real:
```
TELEGRAM_BOT_TOKEN=el-token-que-te-dio-BotFather
```
Sin comillas y sin espacios alrededor del `=`. El agente lo lee al arrancar, así
que no hay que hacer `export` en cada terminal nueva.

### 5. Correr el agente
```
python3 bot_telegram.py
```
Verás "Agente en línea". Deja esa terminal abierta: mientras esté abierta y tu
Mac encendido, los ingenieros autorizados pueden escribirle al bot. Para
apagarlo, cierra la terminal o pulsa Ctrl+C.

## Probar sin Telegram (opcional)
Para verificar que el agente lee bien la carpeta, sin montar Telegram:
```
python3 cerebro.py
```
Te deja hacerle preguntas desde la terminal. No necesita el token de Telegram.

## Cómo funciona por dentro (resumen)
- El agente arranca leyendo el `AGENTS.md` de la raíz y navega los `contexto.md`
  y datos según la pregunta, usando tres herramientas: listar, leer y buscar.
- **Cita la procedencia**: distingue dato oficial (`originales/`, `procesado/`)
  de análisis interno (`analisis/`), y avisa cuándo una cifra es interna y no
  certificada. Esa regla está en el "system prompt" dentro de `cerebro.py`.
- **Ingesta**: si un ingeniero envía un archivo, cae en `_entrada/` con la fecha
  en el nombre, para clasificarlo después con revisión humana.
- **Seguridad**: el agente no puede leer `_restringido/` ni `_agente/`; la
  restricción está forzada en el código de `cerebro.py`, no depende de pedírselo.

## Cambiar la visibilidad más adelante
Hoy todos los ingenieros ven todo. El día que quieras ocultar algo, muévelo a
`_restringido/` (ver el README de esa carpeta). El agente dejará de tener acceso
automáticamente, sin tocar el código.
