import discord
from discord.ext import commands
import requests
import json
import random
import os
import re
from rapidfuzz import process

TOKEN = os.getenv("TOKEN")

CACHE = "cartas.json"

# directorio donde el sitio guarda las imágenes
IMAGE_BASE = "https://kodem-tcg.com/wp-content/uploads"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cartas = {}

# ---------------- CACHE ----------------

def guardar_cache():
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cartas, f, ensure_ascii=False, indent=2)

def cargar_cache():
    global cartas

    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cartas = json.load(f)
        print(f"{len(cartas)} cartas cargadas desde cache")
    else:
        print("No hay cache, generando cartas...")
        actualizar_cartas()

# ---------------- SCRAPER ----------------

def actualizar_cartas():

    global cartas
    cartas = {}

    print("Buscando imágenes de cartas...")

    # años posibles de subida
    años = ["2023", "2024", "2025", "2026"]

    for año in años:
        for mes in range(1, 13):

            carpeta = f"{IMAGE_BASE}/{año}/{str(mes).zfill(2)}/"

            try:

                r = requests.get(carpeta)

                if r.status_code != 200:
                    continue

                archivos = re.findall(r'href="([^"]+\.png)"', r.text)

                for archivo in archivos:

                    url = carpeta + archivo

                    nombre = archivo.replace(".png", "").replace("-", " ")

                    cartas[nombre.lower()] = {
                        "nombre": nombre.title(),
                        "imagen": url,
                        "url": url
                    }

                    print("Carta encontrada:", nombre)

            except:
                pass

    guardar_cache()

    print(f"{len(cartas)} cartas indexadas")

# ---------------- BUSQUEDA ----------------

def buscar(nombre):

    nombres = list(cartas.keys())

    if not nombres:
        return None

    resultado = process.extractOne(nombre.lower(), nombres)

    if resultado and resultado[1] > 60:
        return cartas[resultado[0]]

    return None

# ---------------- EMBED ----------------

def embed_carta(c):

    e = discord.Embed(
        title=c["nombre"],
        color=0x5865F2
    )

    e.set_image(url=c["imagen"])

    return e

# ---------------- COMANDOS ----------------

@bot.command()
async def carta(ctx, *, nombre):

    c = buscar(nombre)

    if not c:
        await ctx.send("Carta no encontrada.")
        return

    await ctx.send(embed=embed_carta(c))

@bot.command(name="random")
async def carta_random(ctx):

    if not cartas:
        await ctx.send("No hay cartas cargadas.")
        return

    c = random.choice(list(cartas.values()))

    await ctx.send(embed=embed_carta(c))

@bot.command()
async def update(ctx):

    await ctx.send("Actualizando cartas...")

    actualizar_cartas()

    await ctx.send(f"{len(cartas)} cartas actualizadas.")

# ---------------- DETECTOR MENSAJES ----------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    nombres = []

    nombres += re.findall(r"\*\-(.+?)", message.content)
    nombres += re.findall(r"\[\[(.+?)\]\]", message.content)

    for nombre in nombres:

        c = buscar(nombre)

        if c:
            await message.channel.send(embed=embed_carta(c))

    await bot.process_commands(message)

# ---------------- READY ----------------

@bot.event
async def on_ready():

    print(f"Bot conectado como {bot.user}")

    cargar_cache()

bot.run(TOKEN)
