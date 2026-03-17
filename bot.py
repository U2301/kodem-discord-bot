import os
import re
import random
from collections import defaultdict

import discord
from discord.ext import commands
from pdfminer.high_level import extract_text

TOKEN = os.getenv("TOKEN")

PDF_PATH = "Kodem base de datos .pdf"
IMG_DIR = "imagenes"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

cartas = {}
cartas_por_tipo = defaultdict(list)
cartas_por_energia = defaultdict(list)
cartas_por_expansion = defaultdict(list)

def normalizar(s):
    return s.lower().strip()

def parsear_pdf():
    """
    Extrae cartas del PDF en orden y les asigna imageN.jpeg según su índice.
    """
    texto = extract_text(PDF_PATH)

    # Detectar expansiones por títulos conocidos
    expansion = None
    expansiones_keywords = {
        "RAICES MISTICAS": "Raíces Místicas",
        "La guerra roja": "La Guerra Roja",
        "Titanes de la corteza": "Titanes de la Corteza y Ojos del Océano",
    }

    # Regex para cartas
    patron = re.compile(
        r"([A-Z]{3,5}-?\d{3})\s+Nombre:\s*(.*?)\s+Tipo:\s*(.*?)\s+Energ[ií]a:\s*(.*?)\s",
        re.DOTALL
    )

    coincidencias = list(patron.finditer(texto))

    resultado = {}
    idx = 1

    for m in coincidencias:
        cid = m.group(1).strip()
        nombre = m.group(2).strip().replace("\n", " ")
        tipo = m.group(3).strip()
        energia = m.group(4).strip()

        # detectar expansión por cercanía en el texto
        bloque = texto[max(0, m.start()-200):m.start()]
        for k, v in expansiones_keywords.items():
            if k.lower() in bloque.lower():
                expansion = v

        imagen = os.path.join(IMG_DIR, f"image{idx}.jpeg")

        carta = {
            "id": cid,
            "nombre": nombre,
            "tipo": tipo,
            "energia": energia,
            "expansion": expansion if expansion else "Desconocida",
            "imagen": imagen if os.path.exists(imagen) else None
        }

        resultado[normalizar(nombre)] = carta

        idx += 1

    return resultado

def indexar():
    cartas_por_tipo.clear()
    cartas_por_energia.clear()
    cartas_por_expansion.clear()

    for c in cartas.values():
        cartas_por_tipo[normalizar(c["tipo"])].append(c)
        cartas_por_energia[normalizar(c["energia"])].append(c)
        cartas_por_expansion[normalizar(c["expansion"])].append(c)

@bot.event
async def on_ready():
    global cartas
    print(f"Bot conectado como {bot.user}")

    cartas = parsear_pdf()
    indexar()

    print(f"{len(cartas)} cartas cargadas.")

def embed_carta(c):
    emb = discord.Embed(
        title=c["nombre"],
        description=f"**Tipo:** {c['tipo']}\n**Energía:** {c['energia']}\n**Expansión:** {c['expansion']}",
        color=discord.Color.orange()
    )

    if c["imagen"] and os.path.exists(c["imagen"]):
        file = discord.File(c["imagen"], filename="carta.jpeg")
        emb.set_image(url="attachment://carta.jpeg")
        return emb, file
    else:
        return emb, None

@bot.command()
async def carta(ctx, *, nombre):
    c = cartas.get(normalizar(nombre))
    if not c:
        await ctx.send("Carta no encontrada.")
        return

    emb, file = embed_carta(c)
    if file:
        await ctx.send(embed=emb, file=file)
    else:
        await ctx.send(embed=emb)

@bot.command()
async def random(ctx):
    if not cartas:
        await ctx.send("No hay cartas cargadas.")
        return

    c = random.choice(list(cartas.values()))
    emb, file = embed_carta(c)

    if file:
        await ctx.send(embed=emb, file=file)
    else:
        await ctx.send(embed=emb)

@bot.command()
async def tipo(ctx, *, tipo):
    lista = cartas_por_tipo.get(normalizar(tipo))
    if not lista:
        await ctx.send("No se encontraron cartas de ese tipo.")
        return

    nombres = "\n".join(c["nombre"] for c in lista[:20])
    await ctx.send(f"Cartas tipo **{tipo}**:\n{nombres}")

@bot.command()
async def energia(ctx, *, energia):
    lista = cartas_por_energia.get(normalizar(energia))
    if not lista:
        await ctx.send("No se encontraron cartas con esa energía.")
        return

    nombres = "\n".join(c["nombre"] for c in lista[:20])
    await ctx.send(f"Cartas energía **{energia}**:\n{nombres}")

@bot.command()
async def expansion(ctx, *, expansion):
    lista = cartas_por_expansion.get(normalizar(expansion))
    if not lista:
        await ctx.send("No se encontraron cartas de esa expansión.")
        return

    nombres = "\n".join(c["nombre"] for c in lista[:20])
    await ctx.send(f"Cartas de **{expansion}**:\n{nombres}")

@bot.command()
async def update(ctx):
    global cartas
    cartas = parsear_pdf()
    indexar()
    await ctx.send(f"Base actualizada: {len(cartas)} cartas.")

bot.run(TOKEN)

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    texto = message.content.lower()

    # detectar formato [[carta]]
    matches = re.findall(r"\[\[(.*?)\]\]", texto)

    for m in matches:
        carta = cartas.get(normalizar(m))
        if carta:
            emb, file = embed_carta(carta)

            if file:
                await message.channel.send(embed=emb, file=file)
            else:
                await message.channel.send(embed=emb)

    # detectar nombre simple
    for nombre, carta in cartas.items():
        if nombre in texto:
            emb, file = embed_carta(carta)

            if file:
                await message.channel.send(embed=emb, file=file)
            else:
                await message.channel.send(embed=emb)

            break

    await bot.process_commands(message)
