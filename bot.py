# bot.py
import os
import re
import json
import random
import discord
from discord.ext import commands

# =========================
#  CONFIG E INTENTS
# =========================
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # mantiene compatibilidad con comandos "!"
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
#  CARGA DE CARTAS (compat)
# =========================
CARTAS_FILE_CANDIDATOS = ["cartas.json", "cards.json"]  # primero el nuevo nombre

def cargar_cartas_crudas():
    """
    Devuelve la lista de cartas tal cual viene del JSON.
    Intenta primero 'cartas.json' y luego 'cards.json' por compatibilidad.
    """
    for fn in CARTAS_FILE_CANDIDATOS:
        if os.path.exists(fn):
            with open(fn, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Puede venir como lista (nuevo generador) o como dict (versiones viejas)
            if isinstance(data, dict):
                # intentar convertir dict->lista si viene indexado por nombre
                posible_lista = []
                for k, v in data.items():
                    if isinstance(v, dict) and "nombre" in v:
                        posible_lista.append(v)
                if posible_lista:
                    return posible_lista
                # si no, lo regresamos tal cual
                return data
            return data
    raise FileNotFoundError("No encontré ni 'cartas.json' ni 'cards.json' en la carpeta del bot.")

def construir_indices(cartas_crudas):
    """
    Construye:
    - lista_cartas: lista de dicts (cada carta con id, nombre, tipo, energia, expansion, imagen)
    - cartas_por_nombre: dict nombre_min -> carta
    """
    lista_cartas = []
    if isinstance(cartas_crudas, list):
        lista_cartas = cartas_crudas
    elif isinstance(cartas_crudas, dict):
        # si viniera como dict raro, lo pasamos a lista
        for v in cartas_crudas.values():
            if isinstance(v, dict):
                lista_cartas.append(v)

    # índice por nombre en minúsculas
    cartas_por_nombre = {}
    for c in lista_cartas:
        nombre = str(c.get("nombre", "")).strip()
        if nombre:
            cartas_por_nombre[nombre.lower()] = c
    return lista_cartas, cartas_por_nombre

# Cargamos una vez al inicio
_cartas_crudas = cargar_cartas_crudas()
cartas, cartas_por_nombre = construir_indices(_cartas_crudas)

# =========================
#  HELPERS DE EMBED/ENVÍO
# =========================
def embed_carta(carta: dict):
    """
    Devuelve (embed, file_or_none) para enviar al canal.
    Si 'imagen' es None o archivo no existe, envía solo el embed.
    """
    nombre = carta.get("nombre", "Carta")
    tipo = carta.get("tipo", "N/D")
    energia = carta.get("energia", "N/D")
    expansion = carta.get("expansion", "N/D")
    ruta = carta.get("imagen")

    e = discord.Embed(
        title=nombre,
        description=f"Tipo: **{tipo}**\nEnergía: **{energia}**\nExpansión: **{expansion}**",
        color=discord.Color.orange()
    )

    if ruta and isinstance(ruta, str) and os.path.exists(ruta):
        file = discord.File(ruta, filename="card.jpg")
        e.set_image(url="attachment://card.jpg")
        return e, file

    return e, None

# =========================
#  EVENTOS
# =========================
@bot.event
async def on_ready():
    try:
        print(f"Bot conectado como {bot.user}")
        print(f"Cartas cargadas: {len(cartas)}")
    except Exception as e:
        # Evita reventar si algo sale mal
        print("Error en on_ready:", repr(e))

# =========================
#  COMANDOS DE TEXTO "!"
# =========================
@bot.command(name="carta")
async def cmd_carta(ctx, *, nombre):
    if not nombre:
        await ctx.send("Indica el nombre de la carta. Ej: `!carta Zaykan`")
        return

    q = nombre.strip().lower()
    # Búsqueda por coincidencia exacta primero
    carta = cartas_por_nombre.get(q)

    # Si no, buscamos por contiene
    if not carta:
        for c in cartas:
            if q in str(c.get("nombre", "")).lower():
                carta = c
                break

    if not carta:
        await ctx.send("Carta no encontrada")
        return

    embed, file = embed_carta(carta)
    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

@bot.command(name="random")
async def cmd_random(ctx):
    if not cartas:
        await ctx.send("Aún no hay cartas cargadas.")
        return
    carta = random.choice(cartas)
    embed, file = embed_carta(carta)
    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

# =========================
#  AUTOCITAS [[nombre]]
# =========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    texto = message.content or ""
    texto_low = texto.lower()

    # Patrón [[nombre de carta]]
    matches = re.findall(r"\[\[(.*?)\]\]", texto_low)
    for m in matches:
        key = m.strip().lower()
        carta = cartas_por_nombre.get(key)

        # Si no hay exacta, buscamos por contiene
        if not carta:
            for c in cartas:
                if key in str(c.get("nombre", "")).lower():
                    carta = c
                    break

        if carta:
            embed, file = embed_carta(carta)
            if file:
                await message.channel.send(embed=embed, file=file)
            else:
