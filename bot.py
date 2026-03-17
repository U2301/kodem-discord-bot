import discord
from discord.ext import commands
import json
import os
import random
import re

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cartas = cargar_cartas()

import json, os

CARTAS_FILE_CANDIDATOS = ["cartas.json", "cards.json"]  # primero el nuevo nombre
def cargar_cartas():
    for fn in CARTAS_FILE_CANDIDATOS:
        if os.path.exists(fn):
            with open(fn, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("No encontré ni 'cartas.json' ni 'cards.json' en la carpeta del bot.")


def embed_carta(carta):

    embed = discord.Embed(
        title=carta["nombre"],
        description=f"""
Tipo: {carta['tipo']}
Energía: {carta['energia']}
Expansión: {carta['expansion']}
""",
        color=discord.Color.orange()
    )

    if os.path.exists(carta["imagen"]):
        file = discord.File(carta["imagen"], filename="card.jpg")
        embed.set_image(url="attachment://card.jpg")
        return embed, file

    return embed, None


@bot.event
async def on_ready():

    print("Bot conectado como", bot.user)

    cargar_cartas()

    print("Cartas cargadas:", len(cartas))


@bot.command()
async def carta(ctx, *, nombre):

    carta = cartas.get(nombre.lower())

    if not carta:
        await ctx.send("Carta no encontrada")
        return

    embed, file = embed_carta(carta)

    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


@bot.command()
async def random(ctx):

    carta = random.choice(list(cartas.values()))

    embed, file = embed_carta(carta)

    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    texto = message.content.lower()

    matches = re.findall(r"\[\[(.*?)\]\]", texto)

    for m in matches:

        carta = cartas.get(m.lower())

        if carta:

            embed, file = embed_carta(carta)

            if file:
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)

    await bot.process_commands(message)


bot.run(TOKEN)
