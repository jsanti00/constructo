# =============================================================================
# BOT DE TELEGRAM
# Este es el programa que se ejecuta para poner el agente en línea.
# Conecta Telegram con el "cerebro" (cerebro.py): recibe los mensajes de los
# ingenieros, los pasa al agente, y devuelve la respuesta en el chat.
# También recibe archivos y los guarda en la carpeta _entrada/.
# =============================================================================

import os                    # Para leer el token del bot desde el entorno
import shutil                # Para comprobar que el programa 'claude' esté instalado
import asyncio               # Para no bloquear el bot mientras el agente piensa
import datetime              # Para ponerle fecha a los archivos que llegan
from pathlib import Path     # Para manejar rutas

# Librería del bot de Telegram (python-telegram-bot).
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

# Nuestros archivos: la configuración y el cerebro del agente.
import config
import cerebro

# Carpeta donde caen los archivos nuevos que mandan los ingenieros.
# Está al lado de _agente, dentro del proyecto.
CARPETA_ENTRADA = Path(__file__).resolve().parent.parent / "_entrada"


# -----------------------------------------------------------------------------
# CONTROL DE ACCESO
# -----------------------------------------------------------------------------

def esta_autorizado(update: Update) -> bool:
    """Devuelve True solo si quien escribe está en la lista blanca de config.py."""
    usuario = update.effective_user            # Quién mandó el mensaje
    if usuario is None:
        return False
    return usuario.id in config.ALLOWED_USER_IDS


# -----------------------------------------------------------------------------
# UTILIDAD: MANDAR RESPUESTAS LARGAS
# Telegram no deja mensajes de más de 4096 caracteres, así que si la respuesta
# es muy larga, la partimos en pedazos.
# -----------------------------------------------------------------------------

async def responder_largo(update: Update, texto: str) -> None:
    LIMITE = 4000  # Un poco por debajo de 4096 por seguridad
    for inicio in range(0, len(texto), LIMITE):
        await update.message.reply_text(texto[inicio:inicio + LIMITE])


# -----------------------------------------------------------------------------
# MANEJADORES DE MENSAJES (qué hacer cuando llega cada tipo de mensaje)
# -----------------------------------------------------------------------------

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde al comando /start (primer mensaje que suele mandar la gente)."""
    if not esta_autorizado(update):
        # Le decimos su id para que pueda pedir acceso al administrador.
        await update.message.reply_text(
            "No tienes acceso a este agente todavía. "
            f"Tu id de Telegram es: {update.effective_user.id}. "
            "Compártelo con el administrador para que te agregue.")
        return
    await update.message.reply_text(
        f"Soy el asistente del proyecto {cerebro.OBRA}. Pregúntame sobre el "
        "presupuesto, los planos, el cronograma o los análisis de la obra. "
        "También puedes enviarme archivos (fotos de avance, planos, cotizaciones) "
        "y los guardo para clasificarlos. Usa /reiniciar para empezar una "
        "conversación desde cero.")


async def comando_reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Olvida el hilo de conversación de este chat."""
    if not esta_autorizado(update):
        return
    cerebro.reiniciar_conversacion(update.effective_chat.id)
    await update.message.reply_text("Listo, empecemos de cero.")


async def mensaje_de_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Se ejecuta cuando un ingeniero escribe una pregunta de texto."""
    if not esta_autorizado(update):
        await update.message.reply_text(
            "No tienes acceso a este agente. "
            f"Tu id de Telegram es: {update.effective_user.id}.")
        return

    pregunta = update.message.text                 # El texto que escribió
    chat_id = update.effective_chat.id             # Identifica la conversación

    # Mostramos "escribiendo..." mientras el agente piensa (puede tardar unos segundos).
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # El agente puede tardar; para no congelar el bot lo corremos en un hilo aparte.
    # Devuelve (texto, archivos): archivos son los entregables que dejó en _salidas/.
    archivos = []
    try:
        respuesta, archivos = await asyncio.to_thread(cerebro.preguntar, chat_id, pregunta)
    except Exception as e:
        # Si algo falla (por ejemplo, sin API key), avisamos sin romper el bot.
        respuesta = f"Hubo un error al procesar la pregunta: {e}"

    await responder_largo(update, respuesta)
    await enviar_archivos(update, archivos)


# Extensiones que Telegram muestra bien como imagen inline (el resto va como documento).
EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".webp"}


async def enviar_archivos(update: Update, archivos: list) -> None:
    """Envía por el chat los archivos que el agente generó. Las imágenes van
    inline (se ven en el chat); lo demás (Excel, PDF, HTML) va como documento
    descargable."""
    for ruta in archivos:
        try:
            if ruta.suffix.lower() in EXTENSIONES_IMAGEN:
                with open(ruta, "rb") as f:
                    await update.message.reply_photo(photo=f)
            else:
                with open(ruta, "rb") as f:
                    await update.message.reply_document(document=f, filename=ruta.name)
        except Exception as e:
            await update.message.reply_text(
                f"(Generé el archivo '{ruta.name}' pero no pude enviarlo: {e})")


async def mensaje_con_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Se ejecuta cuando un ingeniero envía un documento o una foto."""
    if not esta_autorizado(update):
        await update.message.reply_text("No tienes acceso a este agente.")
        return

    # Nos aseguramos de que la carpeta _entrada exista.
    CARPETA_ENTRADA.mkdir(exist_ok=True)

    # Un documento y una foto se manejan un poco distinto en Telegram.
    documento = update.message.document
    if documento is not None:
        # Documento (PDF, Excel, etc.): tiene nombre de archivo original.
        archivo = await documento.get_file()
        nombre_original = documento.file_name or "archivo"
    elif update.message.photo:
        # Foto: tomamos la de mayor resolución (la última de la lista).
        archivo = await update.message.photo[-1].get_file()
        nombre_original = "foto.jpg"
    else:
        return  # Otro tipo de adjunto que no manejamos

    # Le ponemos fecha y hora al inicio del nombre para que no se pisen archivos.
    marca_tiempo = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino = CARPETA_ENTRADA / f"{marca_tiempo}_{nombre_original}"

    # Descargamos el archivo a la carpeta _entrada.
    await archivo.download_to_drive(custom_path=str(destino))

    # Confirmamos y recordamos que _entrada es un buzón, no el archivo definitivo.
    await update.message.reply_text(
        f"Recibido y guardado en _entrada como '{destino.name}'. "
        "Queda ahí para clasificarlo y moverlo a su carpeta del proyecto.")


# -----------------------------------------------------------------------------
# ARRANQUE DEL BOT
# -----------------------------------------------------------------------------

def main() -> None:
    # Las llaves ya se cargaron al importar config (ver config.py).
    # Leemos el token del bot desde la variable de entorno (nunca del código).
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Falta el token del bot. Guárdalo en el archivo de llaves:\n"
            "  ~/.config/agente-obra/.env\n"
            "con la línea:  TELEGRAM_BOT_TOKEN=el-token-que-te-dio-BotFather")

    # El agente usa el programa `claude` (la suscripción de Santiago), no una
    # API key. Comprobamos que esté instalado antes de arrancar, porque si no
    # el bot se vería en línea pero fallaría en la primera pregunta.
    if shutil.which("claude") is None and not (
            Path.home() / ".local" / "bin" / "claude").is_file():
        raise SystemExit(
            "No encuentro el programa 'claude' (Claude Code) en este Mac.\n"
            "El agente lo necesita: es lo que usa para pensar, con tu suscripción.")

    # Avisamos si la lista blanca está vacía (el bot no respondería a nadie).
    if not config.ALLOWED_USER_IDS:
        print("AVISO: la lista ALLOWED_USER_IDS en config.py está vacía. "
              "El agente no responderá a nadie hasta que agregues ids.")

    # Creamos la aplicación del bot con ese token.
    app = Application.builder().token(token).build()

    # Conectamos cada tipo de mensaje con su función:
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("reiniciar", comando_reiniciar))
    # Documentos y fotos van al manejador de archivos.
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, mensaje_con_archivo))
    # Cualquier texto que no sea un comando va al manejador de preguntas.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_de_texto))

    print("Agente en línea. Los ingenieros autorizados ya pueden escribirle. "
          "Deja esta terminal abierta; ciérrala para apagar el agente.")
    # Arrancamos: el bot se queda escuchando mensajes hasta que lo detengas.
    app.run_polling()


# Si ejecutas este archivo directamente, arranca el bot.
if __name__ == "__main__":
    main()
