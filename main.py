import discord
from discord.ext import commands, tasks
from discord.ext.commands import has_any_role, CheckFailure
import json
import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import unicodedata
from discord.utils import get
import pytz

def quitar_tildes(texto):
    """Normaliza texto eliminando tildes para comparación."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("No se encontró el token de Discord en .env")

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Archivos JSON
EVENT_FILE = 'evento.json'
INSCRITOS_FILE = 'inscritos.json'
JUGADORES_FILE = 'jugadores.json'
STRIKE_FILE = 'strike.json'
NOTIFIED_TIMES = set()

# Emojis
emojis_rango = {
    "bronce": "🥉", "plata": "🥈", "oro": "🥇",
    "platino": "🔷", "diamante": "💎", "campeon": "🏆",
    "grancampeon": "👑", "ssl": "🚀"
}

emojis_nivel = {
    "1": "①", "2": "②", "3": "③"
}

emojis_pais = {
    "argentina": "🇦🇷", "bolivia": "🇧🇴", "brasil": "🇧🇷", "canada": "🇨🇦",
    "chile": "🇨🇱", "colombia": "🇨🇴", "costarica": "🇨🇷", "cuba": "🇨🇺",
    "ecuador": "🇪🇨", "elsalvador": "🇸🇻", "espana": "🇪🇸", "estadosunidos": "🇺🇸",
    "guatemala": "🇬🇹", "honduras": "🇭🇳", "mexico": "🇲🇽", "nicaragua": "🇳🇮",
    "panama": "🇵🇦", "paraguay": "🇵🇾", "peru": "🇵🇪", "puertorico": "🇵🇷",
    "republicadominicana": "🇩🇴", "uruguay": "🇺🇾", "venezuela": "🇻🇪", "andorra": "🇦🇩 "
}

ZONAS_HORARIAS = {
    "🇨🇴 Colombia": "America/Bogota",
    "🇲🇽 México": "America/Mexico_City",
    "🇦🇷 Argentina": "America/Argentina/Buenos_Aires",
    "🇨🇱 Chile": "America/Santiago",
    "🇵🇪 Perú": "America/Lima",
    "🇻🇪 Venezuela": "America/Caracas",
    "🇪🇸 España (Madrid)": "Europe/Madrid",
    "🇺🇸 EE.UU. (Este)": "America/New_York",
    "🇧🇴 Bolivia": "America/La_Paz",
    "🇺🇾 Uruguay": "America/Montevideo",
    "🇵🇾 Paraguay": "America/Asuncion",
    "🇪🇨 Ecuador": "America/Guayaquil",
    "🇦🇩 Andorra": "Europe/Andorra"
}

def convertir_horarios(fecha_utc: datetime):
    """Convierte la fecha UTC a horarios locales por región."""
    mensaje = ""
    for nombre, zona in ZONAS_HORARIAS.items():
        zona_local = pytz.timezone(zona)
        fecha_local = fecha_utc.astimezone(zona_local)
        mensaje += f"{nombre}: `{fecha_local.strftime('%H:%M')}` ({fecha_local.strftime('%d/%m/%Y')})\n"
    return mensaje

# Funciones de ayuda para JSON
def cargar_json(path, default):
    """Carga un archivo JSON o crea uno con el valor por defecto si no existe."""
    try:
        if not os.path.exists(path):
            with open(path, 'w') as f:
                json.dump(default, f, indent=4)
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR cargar_json] No se pudo cargar {path}: {e}")
        return default

def guardar_json(path, data):
    """Guarda datos en un archivo JSON con respaldo."""
    try:
        # Crear copia de respaldo
        if os.path.exists(path):
            with open(path, 'r') as f:
                backup = f.read()
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[ERROR guardar_json] No se pudo guardar {path}: {e}")
        # Restaurar respaldo si existe
        if 'backup' in locals():
            with open(path, 'w') as f:
                f.write(backup)
        raise

def obtener_evento():
    """Obtiene la fecha y descripción del evento activo."""
    evento = cargar_json(EVENT_FILE, {})
    if 'fecha' in evento and 'descripcion' in evento:
        try:
            fecha = datetime.strptime(evento['fecha'], "%d/%m/%Y %H:%M")
            return fecha, evento['descripcion']
        except ValueError:
            print("[ERROR obtener_evento] Formato de fecha inválido")
            return None, None
    return None, None

@bot.event
async def on_ready():
    """Evento ejecutado cuando el bot se conecta."""
    canal = discord.utils.get(bot.get_all_channels(), name='📢┇anuncios')
    if canal:
        await canal.send("✅ **ZealBot está activo**.")
    else:
        print("[ERROR on_ready] No se encontró el canal 📢┇anuncios")
    verificar_eventos.start()
    print(f"Conectado como {bot.user}")

@bot.command()
async def evento(ctx, *, arg=None):
    """Crea o muestra un evento."""
    if not arg:
        fecha, descripcion = obtener_evento()
        if fecha:
            fecha_utc = pytz.timezone("America/Bogota").localize(fecha).astimezone(pytz.utc)
            horarios = convertir_horarios(fecha_utc)
            await ctx.send(
                f"📅 **Evento actual:** `{fecha.strftime('%d/%m/%Y %H:%M')}`\n"
                f"📝 **Descripción:** {descripcion}\n"
                f"🕒 **Horarios por región:**\n{horarios}"
            )
        else:
            await ctx.send("❌ No hay evento activo.")
        return

    try:
        datos = arg.split("|")
        fecha_str = datos[0].strip()
        descripcion = datos[1].strip()

        fecha = datetime.strptime(fecha_str, "%d/%m/%Y %H:%M")
        guardar_json(EVENT_FILE, {"fecha": fecha_str, "descripcion": descripcion})
        guardar_json(INSCRITOS_FILE, [])

        global NOTIFIED_TIMES
        NOTIFIED_TIMES.clear()

        fecha_utc = pytz.timezone("America/Bogota").localize(fecha).astimezone(pytz.utc)
        horarios = convertir_horarios(fecha_utc)

        canal_anuncios = discord.utils.get(ctx.guild.text_channels, name='🎉┇eventos')
        if canal_anuncios:
            await canal_anuncios.send(
                f"📢 **Nuevo evento creado**:\n"
                f"📆 Fecha: `{fecha_str}`\n"
                f"📝 Descripción: {descripcion}\n"
                f"🕒 **Horarios por región:**\n{horarios}"
            )
        else:
            await ctx.send("⚠️ No se encontró el canal de eventos.")

        await ctx.send("✅ Evento guardado correctamente.")

    except Exception as e:
        await ctx.send("❌ Formato incorrecto. Usa `!evento DD/MM/AAAA HH:MM | Descripción`")
        print(f"[ERROR !evento] {e}")

@bot.command()
async def rango(ctx, id: str = None, *args):
    """Registra los datos de un jugador (ID, alias, rango, nivel, país)."""
    try:
        if not id or len(args) < 3:
            await ctx.send("❌ Uso correcto: `!rango <ID> <Alias (opcional)> <Rango> <Nivel> <País>`")
            return

        if len(args) == 3:
            alias = ctx.author.name
            rango, nivel, pais = args
        else:
            alias = args[0]
            rango = args[1]
            nivel = args[2]
            pais = " ".join(args[3:])

        rango_limpio = rango.lower()
        nivel_limpio = nivel.strip()
        pais_limpio = quitar_tildes(pais.replace(" ", "").lower())

        if rango_limpio not in emojis_rango:
            await ctx.send("❌ Rango no válido. Opciones: " + ", ".join(emojis_rango.keys()))
            return

        if nivel_limpio not in emojis_nivel:
            await ctx.send("❌ Nivel no válido. Opciones: 1, 2, 3")
            return

        if pais_limpio not in emojis_pais:
            await ctx.send("❌ País no válido. Ejemplos: mexico, argentina, chile, venezuela, andorra")
            return

        jugadores = cargar_json(JUGADORES_FILE, {})
        jugadores[str(ctx.author.id)] = {
            "id": id,
            "alias": alias,
            "rango": rango_limpio,
            "nivel": nivel_limpio,
            "pais": pais_limpio
        }
        guardar_json(JUGADORES_FILE, jugadores)

        emoji_rango = emojis_rango[rango_limpio]
        emoji_nivel = emojis_nivel[nivel_limpio]
        emoji_pais = emojis_pais[pais_limpio]

        nuevo_apodo = f"{alias} {emoji_rango}{emoji_nivel}{emoji_pais}"
        try:
            await ctx.author.edit(nick=nuevo_apodo)
        except discord.Forbidden:
            await ctx.send("⚠️ No pude cambiar tu apodo. Revisa mis permisos.")

        await ctx.send(
            f"✅ Información guardada para **{ctx.author.name}**\n"
            f"🆔 ID: `{id}`\n"
            f"🔤 Alias: `{alias}`\n"
            f"🎖️ Rango: {emoji_rango} `{rango_limpio.title()}`\n"
            f"📶 Nivel: {emoji_nivel} `{nivel}`\n"
            f"🌎 País: {emoji_pais} `{pais.title()}`"
        )

    except Exception as e:
        await ctx.send("❌ Error inesperado al guardar el rango.")
        print(f"[ERROR !rango] {e}")

@bot.command()
async def inscribirse(ctx):
    """Inscribe a un usuario al evento activo."""
    jugadores = cargar_json(JUGADORES_FILE, {})
    if str(ctx.author.id) not in jugadores:
        await ctx.send("❌ Primero debes registrarte con `!rango`.")
        return

    inscritos = cargar_json(INSCRITOS_FILE, [])
    if ctx.author.id in inscritos:
        await ctx.send("⚠️ Ya estás inscrito.")
    else:
        inscritos.append(ctx.author.id)
        guardar_json(INSCRITOS_FILE, inscritos)
        await ctx.send("✅ Te has inscrito al evento.")

@bot.command()
async def inscritos(ctx):
    """Muestra la lista de usuarios inscritos al evento."""
    inscritos = cargar_json(INSCRITOS_FILE, [])
    if not inscritos:
        await ctx.send("📭 No hay inscritos.")
        return

    nombres = []
    for user_id in inscritos:
        try:
            user = await bot.fetch_user(user_id)
            nombres.append(f"- {user.name}")
        except discord.NotFound:
            nombres.append(f"- Usuario desconocido (ID: {user_id})")

    await ctx.send("📋 **Inscritos:**\n" + "\n".join(nombres))

@bot.command()
async def info(ctx, member: discord.Member = None):
    """Muestra la información de un usuario."""
    if member is None:
        member = ctx.author

    jugadores = cargar_json(JUGADORES_FILE, {})
    info = jugadores.get(str(member.id))

    strikes = cargar_json(STRIKE_FILE, {})
    strike_count = strikes.get(str(member.id), 0)

    if not info:
        await ctx.send("❌ No hay datos registrados para este usuario.")
        return

    inscritos = cargar_json(INSCRITOS_FILE, [])
    estado = "🟢 Inscrito" if member.id in inscritos else "🔴 No inscrito"

    emoji_rango = emojis_rango.get(info['rango'], "")
    emoji_nivel = emojis_nivel.get(info['nivel'], "")
    emoji_pais = emojis_pais.get(info['pais'].lower(), "")

    roles = [role.name for role in member.roles if role.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "Ninguno"

    mensaje = (
        f"📄 **Información de {member.name}:**\n"
        f"🆔 ID registrado: `{info['id']}`\n"
        f"🔤 Alias: `{info.get('alias', member.name)}`\n"
        f"🎖️ Rango: {emoji_rango} `{info['rango'].title()}`\n"
        f"📶 Nivel: {emoji_nivel} `{info['nivel']}`\n"
        f"🌎 País: {emoji_pais} `{info['pais'].title()}`\n"
        f"🏷️ Apodo: `{member.nick or 'Sin apodo'}`\n"
        f"📛 Strikes: `{strike_count}`\n"
        f"🔗 Roles: {roles_str}\n"
        f"📌 Estado en evento: {estado}"
    )
    await ctx.send(mensaje)

@bot.command()
async def checar_eventos(ctx):
    """Muestra el evento activo actual."""
    fecha, descripcion = obtener_evento()
    if not fecha:
        await ctx.send("❌ No hay evento programado.")
        return

    embed = discord.Embed(title="📅 Evento Activo", description=descripcion, color=0x00ff00)
    embed.add_field(name="Fecha", value=fecha.strftime("%d/%m/%Y %H:%M"), inline=False)
    await ctx.send(embed=embed)

@bot.command()
@has_any_role("Admin", "Owner")
async def fin_evento(ctx):
    """Finaliza el evento activo y limpia los datos."""
    guardar_json(EVENT_FILE, {})
    guardar_json(INSCRITOS_FILE, [])
    await ctx.send("🗑️ Evento e inscripciones eliminados.")

@bot.command()
@has_any_role("Admin", "Owner")
async def fin_inscripciones(ctx):
    """Limpia las inscripciones del evento."""
    guardar_json(INSCRITOS_FILE, [])
    await ctx.send("🧹 Inscripciones eliminadas.")

@bot.command()
@has_any_role("Admin", "Owner")
async def kick(ctx, member: discord.Member, *, reason="No especificado"):
    """Expulsa a un usuario del servidor."""
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.name} ha sido expulsado. Motivo: {reason}")
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para expulsar a este usuario.")

@bot.command()
@has_any_role("Admin", "Owner")
async def ban(ctx, member: discord.Member, *, reason="No especificado"):
    """Banea a un usuario del servidor."""
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.name} ha sido baneado. Motivo: {reason}")
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para banear a este usuario.")

@bot.command()
@has_any_role("Admin", "Owner")
async def strike(ctx, member: discord.Member, cantidad: int = 1, *, razon="Sin razón especificada"):
    """Añade o quita strikes a un usuario."""
    strikes = cargar_json(STRIKE_FILE, {})
    user_id = str(member.id)

    strikes[user_id] = strikes.get(user_id, 0) + cantidad
    if strikes[user_id] < 0:
        strikes[user_id] = 0

    guardar_json(STRIKE_FILE, strikes)

    if strikes[user_id] >= 5:
        try:
            await member.ban(reason="5 strikes acumulados.")
            await ctx.send(
                f"⛔ {member.name} ha sido **baneado** por acumular 5 strikes.\n"
                "📩 *Si no estás de acuerdo con esta decisión o crees que hubo un error, escribe a:* "
                "**elpollo_Asado26** o al TikTok oficial de Zeal **@zeal.ticktocl** 💬📲"
            )
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para banear a este usuario.")
    else:
        await ctx.send(
            f"⚠️ {cantidad:+} strike(s) para {member.name}. Total actual: {strikes[user_id]}\n"
            f"📝 Razón: {razon}"
        )

@bot.command()
async def ayuda_zeal(ctx):
    """Muestra la lista de comandos disponibles."""
    ayuda = (
        "**📘 Lista de comandos de Zeal:**\n"
        "`!evento [DD/MM/AAAA HH:MM | Descripción]` - Crear o ver evento\n"
        "`!inscribirse` - Inscribirse al evento (requiere !rango)\n"
        "`!rango <ID> <Alias> <Rango> <Nivel> <País>` - Registrar datos de jugador\n"
        "`!inscritos` - Ver inscritos\n"
        "`!info @usuario` - Ver info de jugador\n"
        "`!checar_eventos` - Ver evento actual\n"
        "`!fin_evento` - Finalizar evento y limpiar datos (Admin/Owner)\n"
        "`!fin_inscripciones` - Limpiar solo inscripciones (Admin/Owner)\n"
        "`!kick @usuario` - Expulsar (Admin/Owner)\n"
        "`!ban @usuario` - Banear (Admin/Owner)\n"
        "`!strike @usuario` - Añadir strike (5 strikes = ban) (Admin/Owner)\n"
        "`!ayuda_zeal` - Ver esta ayuda\n"
        "`!sala @usuario1 @usuario2 ...` - Crear sala privada\n"
        "`!verificar_inactivos` - Verificar miembros inactivos (Admin/Owner)\n"
        "`!sin_rango` - Listar miembros sin rango (Admin/Owner)\n"
        "`!sin_rol` - Listar miembros sin roles (Admin/Owner)\n"
        "`!strike_inactivos` - Dar strikes a inactivos (Admin/Owner)\n"
        "`!strike_sin_rango` - Dar strikes a quienes no usaron !rango (Admin/Owner)\n"
        "`!strike_sin_rol` - Dar strikes a quienes no tienen roles (Admin/Owner)\n"
        "`!apagar` - Apagar el bot (Admin/Owner)\n"
    )
    await ctx.send(ayuda)

@tasks.loop(minutes=1)
async def verificar_eventos():
    """Verifica eventos y envía recordatorios al canal de eventos."""
    fecha, descripcion = obtener_evento()
    if not fecha:
        return

    ahora = datetime.now(pytz.timezone("America/Bogota"))
    tiempo_restante = int((fecha - ahora).total_seconds() / 60)
    canal = discord.utils.get(bot.get_all_channels(), name='🎉┇eventos')

    if canal and tiempo_restante >= 0:
        for tiempo_objetivo in [60, 30, 10]:
            if (tiempo_objetivo - 1 <= tiempo_restante <= tiempo_objetivo + 1) and tiempo_objetivo not in NOTIFIED_TIMES:
                await canal.send(f"⏰ Faltan **{tiempo_restante} minutos** para el evento: **{descripcion}**")
                NOTIFIED_TIMES.add(tiempo_objetivo)
                break

@bot.command()
@has_any_role("Admin", "Owner")
async def apagar(ctx):
    """Apaga el bot."""
    await ctx.send("🛑 ZealBot ha sido apagado.")
    await bot.close()

@bot.command()
@has_any_role("Admin", "Owner")
async def verificar_inactivos(ctx):
    """Verifica miembros inactivos basándose en reacciones en el canal de actividad semanal."""
    canal = get(ctx.guild.text_channels, name="📍┇actividad-semanal")
    if not canal:
        await ctx.send("❌ Canal #📍┇actividad-semanal no encontrado.")
        return

    mensajes = [msg async for msg in canal.history(limit=10)]
    mensaje = None
    for msg in mensajes:
        if msg.author == bot.user and msg.reactions:
            mensaje = msg
            break

    if not mensaje:
        await ctx.send("❌ No se encontró un mensaje válido con reacciones.")
        return

    reaccionadores = set()
    for reaccion in mensaje.reactions:
        async for usuario in reaccion.users():
            if not usuario.bot:
                reaccionadores.add(usuario.id)

    inactivos = []
    for miembro in ctx.guild.members:
        if not miembro.bot and miembro.id not in reaccionadores:
            inactivos.append(f"<@{miembro.id}>")

    if not inactivos:
        await ctx.send("✅ Todos los miembros están activos.")
    else:
        await ctx.send("🔴 **Jugadores inactivos esta semana:**\n" + "\n".join(inactivos))

@bot.command()
@has_any_role("Admin", "Owner")
async def sin_rango(ctx):
    """Lista miembros que no han usado el comando !rango."""
    jugadores = cargar_json(JUGADORES_FILE, {})
    registrados = set(jugadores.keys())

    no_registrados = []
    for miembro in ctx.guild.members:
        if not miembro.bot and str(miembro.id) not in registrados:
            no_registrados.append(f"<@{miembro.id}>")

    if not no_registrados:
        await ctx.send("✅ Todos los miembros están registrados con `!rango`.")
    else:
        await ctx.send("📛 **Miembros sin registrar con `!rango`:**\n" + "\n".join(no_registrados))

@bot.command()
@has_any_role("Admin", "Owner")
async def sin_rol(ctx):
    """Lista miembros sin roles asignados."""
    sin_roles = []
    for miembro in ctx.guild.members:
        if not miembro.bot and len(miembro.roles) <= 1:  # Solo @everyone
            sin_roles.append(f"<@{miembro.id}>")

    if not sin_roles:
        await ctx.send("✅ Todos los miembros tienen al menos un rol.")
    else:
        await ctx.send("🔖 **Miembros sin ningún rol asignado:**\n" + "\n".join(sin_roles))

@bot.command()
@has_any_role("Admin", "Owner")
async def strike_inactivos(ctx):
    """Aplica strikes a miembros inactivos."""
    try:
        with open("actividad.json", "r") as f:
            data = json.load(f)
        mensaje_id = data.get("mensaje_id")
        canal_id = data.get("canal_id")

        if not mensaje_id or not canal_id:
            await ctx.send("⚠️ No se ha guardado el mensaje de actividad semanal. Usa `!guardar_actividad <mensaje_id>` primero.")
            return

        canal = bot.get_channel(canal_id)
        if not canal:
            await ctx.send("❌ Canal de actividad no encontrado.")
            return

        mensaje = await canal.fetch_message(mensaje_id)
        reacciones = mensaje.reactions[0] if mensaje.reactions else None

        if not reacciones:
            await ctx.send("⚠️ El mensaje no tiene reacciones.")
            return

        usuarios_reaccionaron = [user async for user in reacciones.users() if not user.bot]
        ids_activos = {str(u.id) for u in usuarios_reaccionaron}

        strikes = cargar_json(STRIKE_FILE, {})
        afectados = []

        for miembro in ctx.guild.members:
            if miembro.bot:
                continue
            if str(miembro.id) not in ids_activos:
                uid = str(miembro.id)
                strikes[uid] = strikes.get(uid, 0) + 1
                afectados.append((miembro, strikes[uid]))
                if strikes[uid] >= 5:
                    try:
                        await miembro.ban(reason="5 strikes acumulados por inactividad")
                        await ctx.send(
                            f"⛔ {miembro.name} ha sido **baneado** por acumular 5 strikes.\n"
                            "📩 *Si no estás de acuerdo con esta decisión o crees que hubo un error, escribe a:* "
                            "**elpollo_Asado26** o al TikTok oficial de Zeal **@zeal.ticktocl** 💬📲"
                        )
                    except discord.Forbidden:
                        await ctx.send(f"❌ No tengo permisos para banear a {miembro.name}.")

        guardar_json(STRIKE_FILE, strikes)

        if afectados:
            texto = "\n".join([f"⚠️ Strike para {m.mention} (Total: {s})" for m, s in afectados])
            await ctx.send(f"📋 **Strikes por inactividad:**\n{texto}")
        else:
            await ctx.send("✅ Todos los miembros estuvieron activos esta semana.")

    except Exception as e:
        await ctx.send("❌ Error al aplicar strikes por inactividad.")
        print(f"[ERROR strike_inactivos] {e}")

@bot.command()
@has_any_role("Admin", "Owner")
async def strike_sin_rango(ctx):
    """Aplica strikes a miembros que no han usado !rango."""
    jugadores = cargar_json(JUGADORES_FILE, {})
    registrados = set(jugadores.keys())

    strikes = cargar_json(STRIKE_FILE, {})
    afectados = []

    for miembro in ctx.guild.members:
        if miembro.bot:
            continue
        if str(miembro.id) not in registrados:
            uid = str(miembro.id)
            strikes[uid] = strikes.get(uid, 0) + 1
            afectados.append((miembro, strikes[uid]))

            if strikes[uid] >= 5:
                try:
                    await miembro.ban(reason="5 strikes acumulados por no registrarse con !rango")
                    await ctx.send(
                        f"⛔ {miembro.name} ha sido **baneado** por acumular 5 strikes.\n"
                        "📩 *Si no estás de acuerdo con esta decisión o crees que hubo un error, escribe a:* "
                        "**elpollo_Asado26** o al TikTok oficial de Zeal **@zeal.ticktocl** 💬📲"
                    )
                except discord.Forbidden:
                    await ctx.send(f"❌ No tengo permisos para banear a {miembro.name}.")

    guardar_json(STRIKE_FILE, strikes)

    if afectados:
        texto = "\n".join([f"⚠️ Strike para {m.mention} (Total: {s})" for m, s in afectados])
        await ctx.send(f"📋 **Strikes por no registrarse con `!rango`:**\n{texto}")
    else:
        await ctx.send("✅ Todos los miembros están registrados con `!rango`.")

@bot.command()
@has_any_role("Admin", "Owner")
async def strike_sin_rol(ctx):
    """Aplica strikes a miembros sin roles asignados."""
    strikes = cargar_json(STRIKE_FILE, {})
    afectados = []

    for miembro in ctx.guild.members:
        if miembro.bot:
            continue
        if len(miembro.roles) <= 1:  # Solo tiene el rol @everyone
            uid = str(miembro.id)
            strikes[uid] = strikes.get(uid, 0) + 1
            afectados.append((miembro, strikes[uid]))

            if strikes[uid] >= 5:
                try:
                    await miembro.ban(reason="5 strikes acumulados por no tener ningún rol")
                    await ctx.send(
                        f"⛔ {miembro.name} ha sido **baneado** por acumular 5 strikes.\n"
                        "📩 *Si no estás de acuerdo con esta decisión o crees que hubo un error, escribe a:* "
                        "**elpollo_Asado26** o al TikTok oficial de Zeal **@zeal.ticktocl** 💬📲"
                    )
                except discord.Forbidden:
                    await ctx.send(f"❌ No tengo permisos para banear a {miembro.name}.")

    guardar_json(STRIKE_FILE, strikes)

    if afectados:
        texto = "\n".join([f"⚠️ Strike para {m.mention} (Total: {s})" for m, s in afectados])
        await ctx.send(f"📋 **Strikes por no tener ningún rol:**\n{texto}")
    else:
        await ctx.send("✅ Todos los miembros tienen al menos un rol asignado.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def sala(ctx, *miembros: discord.Member):
    """Crea una sala privada para los usuarios mencionados."""
    if not miembros:
        await ctx.send("❌ Debes mencionar al menos a un usuario. Uso: `!sala @usuario1 @usuario2 ...`")
        return

    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    nombre_usuarios = [ctx.author.name]
    for miembro in miembros:
        overwrites[miembro] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        nombre_usuarios.append(miembro.name)

    nombre_canal = "-".join(nombre_usuarios).lower().replace(" ", "-")
    nombre_canal = f"sala-{nombre_canal}"

    categoria = discord.utils.get(ctx.guild.categories, name="꧁𓆩💬 𝒞𝑜𝓂𝓊𝓃𝒾𝒹𝒶𝒹 𓆪꧂")
    if not categoria:
        try:
            categoria = await ctx.guild.create_category("꧁𓆩💬 𝒞𝑜𝓂𝓊𝓃𝒾𝒹𝒶𝒹 𓆪꧂")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para crear una categoría.")
            return

    try:
        canal = await ctx.guild.create_text_channel(nombre_canal, overwrites=overwrites, category=categoria)
        await canal.send(f"👋 ¡Bienvenid@s {', '.join(m.mention for m in miembros)} y {ctx.author.mention}! Esta es su sala privada.")
        await ctx.send(f"✅ Sala privada creada: {canal.mention}")
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para crear un canal.")

# Manejo de errores para comandos con permisos
@evento.error
@inscritos.error
@info.error
@fin_evento.error
@fin_inscripciones.error
@kick.error
@ban.error
@strike.error
@sala.error
async def permisos_error(ctx, error):
    """Maneja errores de permisos en comandos."""
    if isinstance(error, CheckFailure):
        await ctx.send("❌ No tienes permiso para usar este comando.")
    elif isinstance(error, discord.Forbidden):
        await ctx.send("❌ No tengo permisos suficientes para ejecutar este comando.")
    else:
        await ctx.send("❌ Ocurrió un error inesperado.")
        print(f"[ERROR permisos_error] {error}")

bot.run(TOKEN)