import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
from rapidfuzz import process
import json
import re
import random
import os

import os
TOKEN = os.getenv("https://discord.com/oauth2/authorize?client_id=1483212729501356283")

CACHE = "cartas.json"
BASE = "https://kodem-tcg.com"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cartas = {}

# ------------------------
# CACHE
# ------------------------

def guardar_cache():

    with open(CACHE,"w",encoding="utf-8") as f:
        json.dump(cartas,f,ensure_ascii=False,indent=2)


def cargar_cache():

    global cartas

    if os.path.exists(CACHE):

        with open(CACHE,encoding="utf-8") as f:
            cartas=json.load(f)

        print(f"{len(cartas)} cartas cargadas desde cache")

    else:

        print("No hay cache, scrapeando...")
        actualizar_cartas()

# ------------------------
# SCRAPEO
# ------------------------

def actualizar_cartas():

    global cartas

    cartas={}

    print("Indexando cartas...")

    r=requests.get(f"{BASE}/cartas")
    soup=BeautifulSoup(r.text,"html.parser")

    links=soup.find_all("a")

    for link in links:

        href=link.get("href")

        if href and "detalle" in href:

            pagina=BASE+href

            try:

                r2=requests.get(pagina)
                soup2=BeautifulSoup(r2.text,"html.parser")

                nombre=soup2.find("h1")
                imagen=soup2.find("img")

                if nombre and imagen:

                    nombre=nombre.text.strip()

                    cartas[nombre.lower()]={
                        "nombre":nombre,
                        "imagen":imagen["src"],
                        "url":pagina
                    }

            except:
                pass

    guardar_cache()

    print(f"{len(cartas)} cartas indexadas")

# ------------------------
# BUSQUEDA
# ------------------------

def buscar(nombre):

    nombres=list(cartas.keys())

    resultado=process.extractOne(nombre.lower(),nombres)

    if resultado and resultado[1]>60:

        return cartas[resultado[0]]

    return None

# ------------------------
# EMBED
# ------------------------

def embed_carta(c):

    e=discord.Embed(
        title=c["nombre"],
        url=c["url"],
        color=0x5865F2
    )

    e.set_image(url=c["imagen"])

    return e

# ------------------------
# COMANDO CARTA
# ------------------------

@bot.command()
async def carta(ctx,*,nombre):

    c=buscar(nombre)

    if not c:
        await ctx.send("Carta no encontrada.")
        return

    await ctx.send(embed=embed_carta(c))

# ------------------------
# RANDOM
# ------------------------

@bot.command()
async def random(ctx):

    c=random.choice(list(cartas.values()))

    await ctx.send(embed=embed_carta(c))

# ------------------------
# UPDATE
# ------------------------

@bot.command()
async def update(ctx):

    await ctx.send("Actualizando cartas...")

    actualizar_cartas()

    await ctx.send(f"{len(cartas)} cartas actualizadas.")

# ------------------------
# DETECCION MENSAJES
# ------------------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    nombres=[]

    # formato *-
    nombres+=re.findall(r"\*\-(.+?)",message.content)

    # formato [[ ]]
    nombres+=re.findall(r"\[\[(.+?)\]\]",message.content)

    for nombre in nombres:

        c=buscar(nombre)

        if c:

            await message.channel.send(embed=embed_carta(c))

    await bot.process_commands(message)

# ------------------------

@bot.event
async def on_ready():

    print(f"Bot conectado como {bot.user}")

    cargar_cache()

bot.run(TOKEN)
