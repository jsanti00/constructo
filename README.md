# Constructo

Un agente de IA que los ingenieros de una obra consultan por Telegram para
preguntarle sobre su propio proyecto: el presupuesto, los planos, el cronograma,
el contrato.

Está en producción desde julio de 2026 en una obra de edificación comercial, y lo
usan a diario ingenieros que no son quien lo escribió.

## El problema

En un contrato a precios unitarios, el margen del contratista se decide por si lo
que se ejecuta coincide con lo que se presupuestó. Esa información existe, pero
vive en un presupuesto de 3.000 filas, una carpeta de planos y un contrato
firmado. El ingeniero que está parado en la obra no puede consultar nada de eso,
así que la respuesta llega días después, por teléfono, o no llega.

## La restricción de diseño que resultó importante

Lo difícil no fue responder preguntas. Fue **que no le crean a ciegas**.

Un presupuesto de obra guarda dos tipos de número muy distintos: lo que dice el
contrato firmado, y lo que estima nuestro propio análisis. Confundirlos es como un
contratista termina comprometiendo un precio que no se sostiene. Por eso cada
respuesta del agente dice cuál de los dos está usando, nombra el archivo de donde
salió, y advierte con todas las letras lo que sigue sin conciliar en lugar de
maquillarlo.

La regla es: un número equivocado nunca debe poder viajar como si fuera oficial.

## Cómo funciona

```
Telegram  ->  bot_telegram.py  ->  cerebro.py  ->  claude (headless)  ->  carpeta de la obra
```

| Archivo | Qué hace |
|---|---|
| `agente/bot_telegram.py` | Habla con Telegram: recibe las preguntas, aplica la lista de autorizados, devuelve respuestas y los archivos que el agente haya generado |
| `agente/cerebro.py` | El paso de razonamiento. Ejecuta `claude` en modo headless dentro de la carpeta de la obra, con las carpetas excluidas bloqueadas, y recoge lo que escribió |
| `agente/config.py` | Los ajustes que sí se tocan: modelo, esfuerzo de razonamiento, memoria de la conversación |
| `comun/` | Plantillas y el script de hidratación para montar la carpeta de una obra nueva |

Decisiones que vale la pena nombrar:

- **Una instancia por obra.** Mismo código, procesos separados, cada uno con su
  token de bot, su lista de autorizados y su raíz de datos. Ninguna instancia
  puede leer la carpeta de otra obra: la información de construcción es
  confidencial por cliente.
- **El código no contiene datos.** La carpeta de la obra se le pasa en la
  variable `OBRA_RAIZ`, y su nombre en `OBRA_NOMBRE`. Por eso este repositorio
  puede ser público mientras las obras siguen siendo privadas.
- **Hay carpetas invisibles para el agente.** En `_restringido/` va el material
  que deliberadamente queda fuera de su alcance.
- **Sin API key.** El agente razona llamando al programa `claude` instalado en el
  Mac, con una suscripción personal. Eso fue lo que lo hizo barato de operar a
  diario mientras todavía era un experimento.

## Qué no está en este repositorio, a propósito

Ningún presupuesto, plano, contrato ni documento de cliente. Ni una sola cifra de
una obra real. Eso es de los contratistas, no mío, y un repositorio público no es
su lugar. Aquí está la maquinaria; los datos se quedan donde se produjeron.

Los nombres de clientes y proyectos tampoco aparecen, por la misma razón.

## Cómo ponerlo a andar

En `agente/README.md` está el paso a paso: crear el bot, instalar las librerías,
conseguir los id de Telegram de los ingenieros y guardar el token.

Los secretos viven en `~/.config/agente-obra/.env`, nunca en el repositorio.
