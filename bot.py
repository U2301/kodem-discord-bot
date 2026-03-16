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

    print("Actualizando cartas desde la web...")

    try:

        r = requests.get(f"{BASE}/cartas", headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")

        expansiones = []

        # encontrar links de expansiones
        for a in soup.find_all("a", href=True):

            href = a["href"]

            if "/cartas/" in href and "detalle" not in href:
                url = BASE + href if href.startswith("/") else href

                if url not in expansiones:
                    expansiones.append(url)

        print(f"Expansiones encontradas: {len(expansiones)}")

        # recorrer expansiones
        for exp in expansiones:

            try:

                r2 = requests.get(exp, headers={"User-Agent": "Mozilla/5.0"})
                soup2 = BeautifulSoup(r2.text, "html.parser")

                for a in soup2.find_all("a", href=True):

                    href = a["href"]

                    if "detalle" in href:

                        pagina = BASE + href if href.startswith("/") else href

                        r3 = requests.get(pagina, headers={"User-Agent": "Mozilla/5.0"})
                        soup3 = BeautifulSoup(r3.text, "html.parser")

                        nombre = soup3.find("h1")
                        imagen = soup3.find("img")

                        if nombre and imagen:

                            nombre = nombre.text.strip()

                            cartas[nombre.lower()] = {
                                "nombre": nombre,
                                "imagen": imagen["src"],
                                "url": pagina
                            }

                            print("Carta indexada:", nombre)

            except Exception as e:
                print("Error en expansión:", e)

        guardar_cache()

        print(f"{len(cartas)} cartas indexadas")

    except Exception as e:
        print("Error general:", e)


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
