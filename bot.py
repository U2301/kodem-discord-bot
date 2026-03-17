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

cartas = {}


def cargar_cartas():

    global cartas

    with open("cartas.json", encoding="utf8") as f:
        data = json.load(f)

    for c in data:
        cartas[c["nombre"].lower()] = c


def crear_embed(carta):

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

        file = discord.File(carta["imagen"], filename="carta.jpg")
        embed.set_image(url="attachment://carta.jpg")

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

    embed, file = crear_embed(carta)

    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


@bot.command()
async def random(ctx):

    carta = random.choice(list(cartas.values()))

    embed, file = crear_embed(carta)

    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


@bot.command()
async def buscar(ctx, *, filtro):

    resultados = []

    for c in cartas.values():

        if filtro.lower() in c["tipo"].lower() or filtro.lower() in c["energia"].lower():

            resultados.append(c["nombre"])

    if not resultados:
        await ctx.send("No se encontraron cartas")
        return

    texto = "\n".join(resultados[:20])

    await ctx.send(texto)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    texto = message.content.lower()

    matches = re.findall(r"\[\[(.*?)\]\]", texto)

    for m in matches:

        carta = cartas.get(m.lower())

        if carta:

            embed, file = crear_embed(carta)

            if file:
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)

    await bot.process_commands(message)


bot.run(TOKEN)
