import discord
from discord.ext import commands, tasks
import sqlite3
import random
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== DATABASE =====
conn = sqlite3.connect("game.db")
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    money INTEGER DEFAULT 100000,
    company TEXT,
    protected_until INTEGER DEFAULT 0
)""")

conn.commit()

# ===== READY =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    investment_loop.start()
    auction_loop.start()

# ===== USER CHECK =====
def get_user(user_id):
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)
    return user

# ===== فلوس =====
@bot.command()
async def فلوس(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 فلوسك: {user[1]}")

# ===== شركة =====
@bot.command()
async def شركة(ctx, name):
    c.execute("UPDATE users SET company=? WHERE id=?", (name, ctx.author.id))
    conn.commit()
    await ctx.send(f"🏢 تم إنشاء شركتك: {name}")

# ===== تحويل =====
@bot.command()
async def تحويل(ctx, member: discord.Member, amount: int):
    user = get_user(ctx.author.id)
    if user[1] < amount:
        return await ctx.send("❌ ما عندك فلوس")

    c.execute("UPDATE users SET money=money-? WHERE id=?", (amount, ctx.author.id))
    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, member.id))
    conn.commit()

    await ctx.send(f"💸 حولت {amount} إلى {member.mention}")

# ===== تداول =====
@bot.command()
async def تداول(ctx, amount: int):
    user = get_user(ctx.author.id)

    if user[1] < amount:
        return await ctx.send("❌ فلوسك قليلة")

    win = random.choice([True, False])

    if win:
        profit = int(amount * 0.2)
        c.execute("UPDATE users SET money=money+? WHERE id=?", (profit, ctx.author.id))
        await ctx.send(f"📈 ربحت {profit}")
    else:
        loss = int(amount * 0.2)
        c.execute("UPDATE users SET money=money-? WHERE id=?", (loss, ctx.author.id))
        await ctx.send(f"📉 خسرت {loss}")

    conn.commit()

# ===== سرقة =====
@bot.command()
async def سرقة(ctx, member: discord.Member):
    if member.bot:
        return

    amount = random.randint(1000, 400000)

    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, ctx.author.id))
    c.execute("UPDATE users SET money=money-? WHERE id=?", (amount, member.id))
    conn.commit()

    await ctx.send(f"🕵️ سرقت {amount} من {member.mention}")

# ===== حماية =====
@bot.command()
async def حماية(ctx):
    user = get_user(ctx.author.id)

    if user[1] < 300000:
        return await ctx.send("❌ تحتاج 300 ألف")

    c.execute("UPDATE users SET money=money-? WHERE id=?", (300000, ctx.author.id))
    conn.commit()

    await ctx.send("🛡️ تم تفعيل الحماية لمدة ساعتين")

# ===== استثمار كل 10 دقايق =====
@tasks.loop(minutes=10)
async def investment_loop():
    channel = bot.get_channel(1498037416672493829)

    investments = [
        ("🏨 فندق على البحر", 5000),
        ("🏗️ بناء مستشفى", 500000),
        ("🏠 بيت في الرياض", 150000),
        ("🛢️ أرامكو", 3000000)
    ]

    inv = random.choice(investments)

    await channel.send(f"📢 فرصة استثمار: {inv[0]}\n💰 الحد الأدنى: {inv[1]}")

# ===== مزاد كل 30 دقيقة =====
@tasks.loop(minutes=30)
async def auction_loop():
    channel = bot.get_channel(1498037416672493829)

    items = ["🚗 سيارة", "🏠 بيت", "🏨 فندق"]

    item = random.choice(items)
    price = random.randint(100000, 500000)

    await channel.send(f"🔥 مزاد جديد: {item}\n💰 يبدأ من {price}")

# ===== اوامر الادارة =====
ADMIN_CHANNEL = 1498037576538259556

@bot.command()
async def تصفير(ctx, member: discord.Member):
    if ctx.channel.id != ADMIN_CHANNEL:
        return

    c.execute("UPDATE users SET money=0 WHERE id=?", (member.id,))
    conn.commit()
    await ctx.send("تم تصفيره")

@bot.command()
async def زيادة(ctx, member: discord.Member, amount: int):
    if ctx.channel.id != ADMIN_CHANNEL:
        return

    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, member.id))
    conn.commit()
    await ctx.send("تمت الزيادة")

bot.run(TOKEN)
