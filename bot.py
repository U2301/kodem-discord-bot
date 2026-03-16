import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
from rapidfuzz import process
import json
import re
import random
import os
import time

TOKEN = os.getenv("TOKEN")

CACHE = "cartas.json"
BASE = "https://kodem-tcg.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cartas = {}

# ------------------------
# CACHE
# ------------------------

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

        print("No hay cache, scrapeando...")
        actualizar_cartas()


# ------------------------
# SCRAPER MEJORADO
# ------------------------

def actualizar_cartas():

    global cartas
    cartas = {}

    print("Indexando expansiones...")

    r = requests.get(f"{BASE}/cartas", headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")

    expansion_links = []

    for link in soup.find_all("a"):

        href = link.get("href")

        if href and "/cartas/" in href and "detalle" not in href:

            expansion_links.append(BASE + href)

    expansion_links = list(set(expansion_links))

    print(f"{len(expansion_links)} expansiones detectadas")

    carta_links = []

    # recorrer expansiones
    for exp in expansion_links:

        try:

            r = requests.get(exp, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")

            for link in soup.find_all("a"):

                href = link.get("href")

                if href and "detalle" in href:

                    carta_links.append(BASE + href)

        except:
            pass

    carta_links = list(set(carta_links))

    print(f"{len(carta_links)} cartas detectadas")

    # scrapear cada carta
    for i, pagina in enumerate(carta_links):

        try:

            r = requests.get(pagina, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")

            nombre = soup.find("h1")
            imagen = soup.find("img")

            if nombre and imagen:

                nombre = nombre.text.strip()

                cartas[nombre.lower()] = {
                    "nombre": nombre,
                    "imagen": imagen["src"],
                    "url": pagina
                }

            if i % 20 == 0:
                print(f"{i}/{len(carta_links)} cartas indexadas")

            time.sleep(0.2)

        except:
            pass

    guardar_cache()

    print(f"{len(cartas)} cartas indexadas correctamente")


# ------------------------
# BUSQUEDA
# ------------------------

def buscar(nombre):

    nombres = list(cartas.keys())

    resultado = process.extractOne(nombre.lower(), nombres)

    if resultado and resultado[1] > 60:

        return cartas[resultado[0]]

    return None


# ------------------------
# EMBED
# ------------------------

def embed_carta(c):

    embed = discord.Embed(
        title=c["nombre"],
        url=c["url"],
        color=0x5865F2
    )

    embed.set_image(url=c["imagen"])

    return embed


# ------------------------
# COMANDO CARTA
# ------------------------

@bot.command()
async def carta(ctx, *, nombre):

    c = buscar(nombre)

    if not c:
        await ctx.send("Carta no encontrada.")
        return

    await ctx.send(embed=embed_carta(c))


# ------------------------
# RANDOM
# ------------------------

@bot.command()
async def random(ctx):

    c = random.choice(list(cartas.values()))

    await ctx.send(embed=embed_carta(c))


# ------------------------
# UPDATE
# ------------------------

@bot.command()
async def update(ctx):

    await ctx.send("Actualizando cartas desde la web...")

    actualizar_cartas()

    await ctx.send(f"{len(cartas)} cartas actualizadas.")


# ------------------------
# DETECCION MENSAJES
# ------------------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    nombres = []

    # formato *-
    nombres += re.findall(r"\*\-(.+?)", message.content)

    # formato [[ ]]
    nombres += re.findall(r"\[\[(.+?)\]\]", message.content)

    for nombre in nombres:

        c = buscar(nombre)

        if c:

            await message.channel.send(embed=embed_carta(c))

    await bot.process_commands(message)


# ------------------------

@bot.event
async def on_ready():

    print(f"Bot conectado como {bot.user}")

    cargar_cache()


if not TOKEN:
    print("ERROR: TOKEN no encontrado")
else:
    bot.run(TOKEN)
