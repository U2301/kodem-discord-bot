# bot.py
import os
import re
import json
import random
import unicodedata
import asyncio
import datetime
from collections import Counter
from typing import List, Dict

import discord
from discord.ext import commands
from discord import app_commands
from difflib import SequenceMatcher

# =========================
#  CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

# 🔧 Leemos GUILD_ID de forma robusta (quitamos espacios/comillas y dejamos solo dígitos)
RAW_GUILD_ENV = os.getenv("GUILD_ID", "")
RAW_GUILD_ENV_STRIPPED = (RAW_GUILD_ENV or "").strip()
RAW_GUILD_ENV_DIGITS = re.sub(r"\D", "", RAW_GUILD_ENV_STRIPPED)  # deja solo números
GUILD_ID = int(RAW_GUILD_ENV_DIGITS) if RAW_GUILD_ENV_DIGITS else 0
GUILD_OBJ = discord.Object(id=GUILD_ID) if GUILD_ID > 0 else None

print(f"[env] GUILD_ID raw='{RAW_GUILD_ENV}' | stripped='{RAW_GUILD_ENV_STRIPPED}' | parsed={GUILD_ID}")

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TRADES_FILE = os.path.join(DATA_DIR, "trades.json")

# =========================
#  BOT & INTENTS
# =========================
intents = discord.Intents.default()
intents.message_content = True  # compat con comandos "!" y autocitas [[...]]
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
#  CARGA DE CARTAS (compat)
# =========================
CARTAS_FILE_CANDIDATOS = ["cartas.json", "cards.json"]  # primero el nuevo

def cargar_cartas_crudas():
    """
    Devuelve la lista de cartas tal cual viene del JSON.
    Intenta primero 'cartas.json' y luego 'cards.json' por compatibilidad.
    """
    for fn in CARTAS_FILE_CANDIDATOS:
        if os.path.exists(fn):
            with open(fn, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Soporta formato viejo dict->lista
                posible_lista = []
                for _, v in data.items():
                    if isinstance(v, dict) and "nombre" in v:
                        posible_lista.append(v)
                if posible_lista:
                    return posible_lista
                return data
            return data
    raise FileNotFoundError("No encontré ni 'cartas.json' ni 'cards.json' en la carpeta del bot.")

def construir_indices(cartas_crudas):
    """
    Construye:
    - cartas: lista de dicts (id, nombre, tipo, energia, expansion, imagen)
    - cartas_por_nombre: dict nombre_min -> carta
    - cartas_por_id: dict id -> carta
    - EXPANSIONES: lista única de expansiones (orden alfabético)
    """
    lista_cartas = []
    if isinstance(cartas_crudas, list):
        lista_cartas = cartas_crudas
    elif isinstance(cartas_crudas, dict):
        for v in cartas_crudas.values():
            if isinstance(v, dict):
                lista_cartas.append(v)

    cartas_por_nombre = {}
    cartas_por_id = {}
    for c in lista_cartas:
        nombre = str(c.get("nombre", "")).strip()
        cid = str(c.get("id", "")).strip()
        if nombre:
            cartas_por_nombre[nombre.lower()] = c
        if cid:
            cartas_por_id[cid] = c

    expansiones = sorted({c.get("expansion") for c in lista_cartas if c.get("expansion")})
    return lista_cartas, cartas_por_nombre, cartas_por_id, expansiones

# Carga inicial
_cartas_crudas = cargar_cartas_crudas()
cartas, cartas_por_nombre, cartas_por_id, EXPANSIONES = construir_indices(_cartas_crudas)

# =========================
#  PERSISTENCIA simple (JSON)
# =========================
os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

USERS = _load_json(USERS_FILE, {})     # { "user_id": {"cards": {id:count}, "last_pack_date": "YYYY-MM-DD"} }
TRADES = _load_json(TRADES_FILE, {"next_id": 1, "trades": {}})  # {"next_id": int, "trades": {tid: {...}}}
_users_lock = asyncio.Lock()
_trades_lock = asyncio.Lock()

def _today_str():
    return datetime.date.today().isoformat()

def _add_cards_to_user(user_id: int, ids: List[str]):
    data = USERS.setdefault(str(user_id), {"cards": {}, "last_pack_date": None})
    for cid in ids:
        data["cards"][cid] = data["cards"].get(cid, 0) + 1

def _remove_cards_from_user(user_id: int, ids: List[str]) -> bool:
    data = USERS.setdefault(str(user_id), {"cards": {}, "last_pack_date": None})
    need = Counter(ids)
    for cid, qty in need.items():
        if data["cards"].get(cid, 0) < qty:
            return False
    for cid, qty in need.items():
        data["cards"][cid] -= qty
        if data["cards"][cid] <= 0:
            data["cards"].pop(cid, None)
    return True

def _parse_id_list(s: str) -> List[str]:
    parts = [p.strip().upper() for p in s.replace("—", "-").replace("–", "-").split(",") if p.strip()]
    normed = []
    for p in parts:
        if "-" not in p and len(p) > 3 and p[-3:].isdigit():
            p = p[:-3] + "-" + p[-3:]
        normed.append(p)
    return normed

# =========================
#  NORMALIZACIÓN & FUZZY
# =========================
def norm_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = " ".join(s.split())
    return s

def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def buscar_fuzzy(query: str, top: int = 5):
    if not query:
        return []
    qn = norm_text(query)

    hits_sub = []
    for c in cartas:
        n = norm_text(c.get("nombre", ""))
        if qn in n:
            hits_sub.append((1.0, c))

    already = {id(h[1]) for h in hits_sub}
    scored = []
    for c in cartas:
        if id(c) in already:
            continue
        n = norm_text(c.get("nombre", ""))
        sc = _score(qn, n)
        if sc >= 0.5:
            scored.append((sc, c))

    hits_sub.sort(key=lambda x: x[0], reverse=True)
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [c for _, c in hits_sub] + [c for _, c in scored]
    return results[:top]

# =========================
#  HELPERS: EMBED / ENVÍO
# =========================
def embed_carta(carta: Dict):
    nombre = carta.get("nombre", "Carta")
    tipo = carta.get("tipo", "N/D")
    energia = carta.get("energia", "N/D")
    expansion = carta.get("expansion", "N/D")
    ruta = carta.get("imagen")

    e = discord.Embed(
        title=nombre,
        description=f"ID: `{carta.get('id','N/D')}`\nTipo: **{tipo}**\nEnergía: **{energia}**\nExpansión: **{expansion}**",
        color=discord.Color.orange()
    )
    if ruta and isinstance(ruta, str) and os.path.exists(ruta):
        file = discord.File(ruta, filename="card.jpg")
        e.set_image(url="attachment://card.jpg")
        return e, file
    return e, None

# =========================
#  SINCRONIZACIÓN DE SLASH (GUILD PRIMERO)
# =========================
@bot.event
async def setup_hook():
    # Se ejecuta antes de conectar; ideal para sync de slash.
    try:
        if GUILD_OBJ:
            print(f"[setup_hook] GUILD_ID detectado: {GUILD_ID}. Registrando slash como GUILD (inmediato).")
            # Clona los globales hacia el guild y sincroniza
            bot.tree.copy_global_to(guild=GUILD_OBJ)
            synced_g = await bot.tree.sync(guild=GUILD_OBJ)
            print(f"[setup_hook] Slash (guild={GUILD_ID}) sincronizados: {len(synced_g)}")
        else:
            print("[setup_hook] GUILD_ID no definido. Registrando solo GLOBAL (puede tardar en cliente).")
            synced_glob = await bot.tree.sync()
            print(f"[setup_hook] Slash (global) sincronizados: {len(synced_glob)}")
    except Exception as e:
        print("[setup_hook] Error al sincronizar slash commands:", repr(e))

# =========================
#  EVENTOS
# =========================
@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    print(f"Cartas cargadas: {len(cartas)}")

# =========================
#  COMANDOS DE TEXTO "!"
# =========================
@bot.command(name="carta")
async def cmd_carta(ctx, *, nombre):
    if not nombre:
        await ctx.send("Indica el nombre de la carta. Ej: `!carta Zaykan`")
        return

    q = nombre.strip().lower()
    carta = cartas_por_nombre.get(q)
    if not carta:
        matches = buscar_fuzzy(nombre, top=1)
        carta = matches[0] if matches else None

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

@bot.command(name="list")
async def cmd_list(ctx):
    """
    Lista de comandos disponibles con breve descripción.
    """
    desc = (
        "**Comandos (texto)**\n"
        "• `!carta <nombre>` — Busca una carta (fuzzy y coincidencia parcial)\n"
        "• `!random` — Muestra una carta aleatoria\n"
        "• `!list` — Muestra este listado de ayuda\n"
        "\n"
        "**Slash commands** (usa `/` para verlos y autocompletar):\n"
        "• `/help` — Explicación rápida de todos los comandos\n"
        "• `/carta nombre:<texto>` — Con autocompletar en vivo\n"
        "• `/abrir expansion:<exp>` — Abre 5 cartas (1 sobre por día)\n"
        "• `/coleccion [expansion:<exp>]` — Tu colección total o filtrada\n"
        "• `/trade proponer/aceptar/cancelar` — Intercambio entre jugadores\n"
        "\n"
        "**Autocitas**\n"
        "• Escribe `[[Nombre de carta]]` y el bot responde con la carta\n"
    )
    embed = discord.Embed(
        title="Ayuda • Kodem TCG",
        description=desc,
        color=discord.Color.teal()
    )
    await ctx.send(embed=embed)

# =========================
#  SLASH: /help
# =========================
@bot.tree.command(name="help", description="Ver ayuda de comandos de Kodem TCG")
async def slash_help(interaction: discord.Interaction):
    desc = (
        "**BÚSQUEDA**\n"
        "• `/carta nombre:<texto>` — Autocompletar (nombres parecidos)\n"
        "• `!carta <texto>` — Versión por texto (con fuzzy)\n\n"
        "**TCG VIRTUAL**\n"
        "• `/abrir expansion:<exp>` — 5 cartas de esa expansión (1 sobre/día)\n"
        "• `/coleccion [expansion:<exp>]` — Tu colección (total o filtrada)\n\n"
        "**INTERCAMBIOS**\n"
        "• `/trade proponer` — Crear oferta\n"
        "• `/trade aceptar` — Aceptar oferta para ti\n"
        "• `/trade cancelar` — Cancelar tu oferta\n"
        "\n**TIP**: Autocitas `[[Nombre de carta]]` en cualquier mensaje."
    )
    await interaction.response.send_message(
        embed=discord.Embed(title="Ayuda • Kodem TCG", description=desc, color=0x00ffcc),
        ephemeral=True
    )

# =========================
#  SLASH: /carta (autocomplete)
# =========================
def _top_sugerencias(query: str, limit: int = 25):
    if not query:
        base = sorted([c.get("nombre", "") for c in cartas if c.get("nombre")], key=lambda x: norm_text(x))
        return base[:limit]
    vistos = set()
    out = []
    for c in buscar_fuzzy(query, top=limit*2):
        n = c.get("nombre", "")
        if n and n not in vistos:
            vistos.add(n)
            out.append(n)
        if len(out) >= limit:
            break
    return out

async def autocomplete_carta(interaction: discord.Interaction, current: str):
    opciones = _top_sugerencias(current, limit=25)
    return [app_commands.Choice(name=o[:100], value=o) for o in opciones]

@bot.tree.command(name="carta", description="Busca una carta (fuzzy + autocompletar)")
@app_commands.describe(nombre="Escribe parte del nombre (ej.: Zaykan...)")
@app_commands.autocomplete(nombre=autocomplete_carta)
async def slash_carta(interaction: discord.Interaction, nombre: str):
    carta = cartas_por_nombre.get(nombre.strip().lower())
    if not carta:
        matches = buscar_fuzzy(nombre, top=1)
        carta = matches[0] if matches else None

    if not carta:
        await interaction.response.send_message("Carta no encontrada", ephemeral=True)
        return

    embed, file = embed_carta(carta)
    if file:
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)

# =========================
#  SLASH: /abrir (1 sobre / día)
# =========================
def expansion_choices():
    return [app_commands.Choice(name=e, value=e) for e in EXPANSIONES]

@bot.tree.command(name="abrir", description="Abre 5 cartas de una expansión (1 sobre al día)")
@app_commands.describe(expansion="Selecciona la expansión")
@app_commands.choices(expansion=expansion_choices())
async def slash_abrir(interaction: discord.Interaction, expansion: app_commands.Choice[str]):
    user = interaction.user
    async with _users_lock:
        data = USERS.setdefault(str(user.id), {"cards": {}, "last_pack_date": None})
        hoy = _today_str()
        if data.get("last_pack_date") == hoy:
            await interaction.response.send_message("⛔ Ya abriste tu sobre de hoy. Vuelve mañana.", ephemeral=True)
            return

        pool = [c for c in cartas if c.get("expansion") == expansion.value]
        if not pool:
            await interaction.response.send_message("No hay cartas en esa expansión.", ephemeral=True)
            return

        k = min(5, len(pool))
        pack = random.sample(pool, k=k)
        ids = [c["id"] for c in pack]
        _add_cards_to_user(user.id, ids)
        data["last_pack_date"] = hoy
        _save_json(USERS_FILE, USERS)

    lines = [f"• **{c['nombre']}** (`{c['id']}`) — {c['tipo']} · {c['energia']}" for c in pack]
    await interaction.response.send_message(
        embed=discord.Embed(
            title=f"🎁 Sobre abierto — {expansion.value}",
            description="\n".join(lines),
            color=0x00ffcc
        ),
        ephemeral=False
    )

# =========================
#  SLASH: /coleccion
# =========================
@bot.tree.command(name="coleccion", description="Muestra tu colección (total o por expansión)")
@app_commands.describe(expansion="(Opcional) Filtra por expansión")
@app_commands.choices(expansion=expansion_choices())
async def slash_coleccion(interaction: discord.Interaction, expansion: app_commands.Choice[str] = None):
    user = interaction.user
    uid = str(user.id)
    async with _users_lock:
        data = USERS.get(uid)
        if not data or not data.get("cards"):
            await interaction.response.send_message("Aún no tienes cartas en tu colección.", ephemeral=True)
            return
        inv = data["cards"].copy()

    subtitulo = ""
    if expansion:
        ids_exp = {c["id"] for c in cartas if c.get("expansion") == expansion.value}
        inv = {cid: cnt for cid, cnt in inv.items() if cid in ids_exp}
        subtitulo = f" (Expansión: {expansion.value})"

    if not inv:
        await interaction.response.send_message(f"No tienes cartas para ese filtro{subtitulo}.", ephemeral=True)
        return

    filas = []
    for cid, cnt in sorted(inv.items(), key=lambda kv: cartas_por_id.get(kv[0], {}).get("nombre", kv[0])):
        nombre = cartas_por_id.get(cid, {}).get("nombre", cid)
        filas.append(f"• `{cid}` ×{cnt} — {nombre}")

    description = f"**Total:** {sum(inv.values())} cartas{subtitulo}\n\n" + "\n".join(filas)
    if len(description) > 3900:
        description = description[:3900] + "\n…"

    await interaction.response.send_message(
        embed=discord.Embed(title="📚 Tu colección", description=description, color=0x00ffcc),
        ephemeral=True
    )

# =========================
#  SLASH GROUP: /trade
# =========================
trade_group = app_commands.Group(name="trade", description="Intercambios entre jugadores")
bot.tree.add_command(trade_group)  # se clona a guild en setup_hook

@trade_group.command(name="proponer", description="Proponer intercambio a otro jugador")
@app_commands.describe(
    usuario="Usuario destinatario",
    doy="IDs que ofreces (ej: IDRMA-001, LGRO-012)",
    recibo="IDs que pides (ej: IDRMA-002, TCOO-010)"
)
async def trade_proponer(interaction: discord.Interaction, usuario: discord.Member, doy: str, recibo: str):
    autor = interaction.user
    if usuario.id == autor.id:
        await interaction.response.send_message("No puedes proponerte un intercambio a ti mismo.", ephemeral=True)
        return

    give = _parse_id_list(doy)
    want = _parse_id_list(recibo)
    if not give or not want:
        await interaction.response.send_message("Listas de IDs inválidas.", ephemeral=True)
        return

    async with _users_lock:
        USERS.setdefault(str(autor.id), {"cards": {}, "last_pack_date": None})
        if not _remove_cards_from_user(autor.id, give):
            await interaction.response.send_message("No tienes suficiente inventario para ofrecer esas cartas.", ephemeral=True)
            return
        _add_cards_to_user(autor.id, give)  # rollback validación

    async with _trades_lock:
        tid = str(TRADES["next_id"])
        TRADES["next_id"] += 1
        TRADES["trades"][tid] = {
            "from": autor.id,
            "to": usuario.id,
            "give": give,
            "receive": want,
            "status": "open",
            "created_at": datetime.datetime.utcnow().isoformat() + "Z"
        }
        _save_json(TRADES_FILE, TRADES)

    desc = (
        f"**De:** {autor.mention} → **Para:** {usuario.mention}\n"
        f"**Ofrece:** {', '.join(give)}\n"
        f"**Pide:** {', '.join(want)}\n"
        f"**ID de trade:** `{tid}`\n\n"
        f"El destinatario puede usar `/trade aceptar id:{tid}`."
    )
    await interaction.response.send_message(
        embed=discord.Embed(title="🤝 Propuesta de intercambio creada", description=desc, color=0x00ffcc),
        ephemeral=False
    )

@trade_group.command(name="aceptar", description="Aceptar una propuesta de intercambio por ID")
@app_commands.describe(id="ID numérico del intercambio")
async def trade_aceptar(interaction: discord.Interaction, id: str):
    uid = interaction.user.id
    async with _trades_lock:
        trade = TRADES["trades"].get(id)
        if not trade or trade["status"] != "open":
            await interaction.response.send_message("Trade no encontrado o no está abierto.", ephemeral=True)
            return
        if trade["to"] != uid:
            await interaction.response.send_message("Este trade no está dirigido a ti.", ephemeral=True)
            return

    from_id = trade["from"]
    to_id = trade["to"]
    give = trade["give"]
    receive = trade["receive"]

    async with _users_lock:
        if not _remove_cards_from_user(from_id, give):
            await interaction.response.send_message("El proponente ya no tiene las cartas ofrecidas.", ephemeral=True)
            return
        if not _remove_cards_from_user(to_id, receive):
            _add_cards_to_user(from_id, give)
            await interaction.response.send_message("No tienes las cartas requeridas para aceptar.", ephemeral=True)
            return

        _add_cards_to_user(from_id, receive)
        _add_cards_to_user(to_id, give)
        _save_json(USERS_FILE, USERS)

    async with _trades_lock:
        trade["status"] = "done"
        trade["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        _save_json(TRADES_FILE, TRADES)

    await interaction.response.send_message("✅ Intercambio completado.", ephemeral=False)

@trade_group.command(name="cancelar", description="Cancelar una propuesta propia (abierta)")
@app_commands.describe(id="ID numérico del intercambio")
async def trade_cancelar(interaction: discord.Interaction, id: str):
    uid = interaction.user.id
    async with _trades_lock:
        trade = TRADES["trades"].get(id)
        if not trade or trade["status"] != "open":
            await interaction.response.send_message("Trade no encontrado o no está abierto.", ephemeral=True)
            return
        if trade["from"] != uid:
            await interaction.response.send_message("Solo el creador puede cancelar este trade.", ephemeral=True)
            return
        trade["status"] = "canceled"
        trade["canceled_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        _save_json(TRADES_FILE, TRADES)

    await interaction.response.send_message("❎ Trade cancelado.", ephemeral=True)

# =========================
#  AUTOCITAS [[nombre]]
# =========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    texto_low = (message.content or "").lower()
    matches = re.findall(r"\[\[(.*?)\]\]", texto_low)
    for m in matches:
        key_raw = m.strip()
        carta = cartas_por_nombre.get(key_raw.lower())
        if not carta:
            hits = buscar_fuzzy(key_raw, top=1)
            carta = hits[0] if hits else None
        if carta:
            embed, file = embed_carta(carta)
            if file:
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)

    await bot.process_commands(message)

# =========================
#  RUN
# =========================
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Define la variable de entorno TOKEN con el token de tu bot")
    bot.run(TOKEN)
