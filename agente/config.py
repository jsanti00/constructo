# =============================================================================
# CONFIGURACIÓN DEL AGENTE DE TELEGRAM
# Este archivo tiene los ajustes que tú puedes cambiar sin tocar el código.
# Los datos secretos (token del bot, API key de Claude) NO van aquí:
# van en el archivo de llaves ~/.config/agente-obra/.env (ver el README).
# =============================================================================

import os                    # Para meter las llaves en el entorno del programa
from pathlib import Path     # Para ubicar el archivo de llaves

# -----------------------------------------------------------------------------
# CARGA DE LAS LLAVES SECRETAS
# Esto corre automáticamente al importar este archivo, y pasa siempre antes de
# que el cerebro cree su conexión con Claude (porque cerebro.py importa config
# primero). Por eso vive aquí y no en bot_telegram.py.
# -----------------------------------------------------------------------------

# El archivo de llaves vive FUERA de OneDrive, en la carpeta personal del Mac.
# Si estuviera dentro del proyecto, los secretos se subirían a la nube y se
# sincronizarían con cualquiera que tenga acceso a esa carpeta.
ARCHIVO_LLAVES = Path.home() / ".config" / "agente-obra" / ".env"


def _cargar_llaves() -> None:
    """Lee el archivo de llaves (si existe) y mete sus valores en el entorno.
    Así no hay que escribir los 'export' a mano en cada terminal nueva.
    Cada línea tiene la forma NOMBRE=valor; se ignoran las vacías y las que
    empiezan por #."""
    if not ARCHIVO_LLAVES.is_file():
        return  # No hay archivo: usamos lo que ya esté en el entorno

    for linea in ARCHIVO_LLAVES.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        # Saltamos comentarios y líneas que no sean NOMBRE=valor
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, valor = linea.split("=", 1)
        # Quitamos espacios y comillas que a veces se pegan al copiar
        nombre = nombre.strip()
        valor = valor.strip().strip("'\"")
        # Lo que ya esté definido en la terminal manda sobre el archivo
        os.environ.setdefault(nombre, valor)


_cargar_llaves()


# Lista de personas autorizadas a hablarle al agente por Telegram.
# Cada persona se identifica con su "user id" de Telegram (un número, no el
# @usuario). Cómo conseguirlo: que la persona le escriba al bot @userinfobot en
# Telegram; ese bot le responde con su "Id".
#
# Esos números NO van escritos aquí, porque este archivo es código público y un
# user id identifica a una persona real. Van en el archivo de llaves privado
# (~/.config/agente-obra/.env), en una sola línea separada por comas:
#
#     TELEGRAM_ALLOWED_IDS=111111111,222222222
#
# Mientras la lista esté vacía, el agente no le responde a nadie (por seguridad).
def _leer_ids_autorizados() -> list[int]:
    """Convierte la línea de ids del archivo de llaves en una lista de números.
    Ignora espacios y entradas que no sean números, para que una coma de más no
    tumbe el arranque del agente."""
    crudo = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
    ids = []
    for parte in crudo.split(","):
        parte = parte.strip()
        if parte.isdigit():
            ids.append(int(parte))
    return ids


ALLOWED_USER_IDS = _leer_ids_autorizados()


# Modelo de Claude que usa el agente. Opus 4.8 es el más capaz.
MODEL = "claude-opus-4-8"

# "Esfuerzo" de razonamiento: cuánto piensa antes de responder.
# "medium" es un buen balance de calidad y costo; súbelo a "high" si quieres
# respuestas más cuidadosas (cuesta un poco más por pregunta).
EFFORT = "medium"

# Máximo de texto que puede generar en una respuesta (incluye su razonamiento).
MAX_TOKENS = 8192

# Cuántos turnos de conversación recuerda por chat (para que las preguntas
# de seguimiento tengan contexto). 6 turnos = 3 preguntas y 3 respuestas.
MAX_TURNOS_MEMORIA = 6
