import discord
from discord.ext import commands, tasks
import sqlite3
import random
import time
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")

# ===== DATABASE =====
conn = sqlite3.connect("game.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
money INTEGER DEFAULT 50000,
company TEXT,
company_value INTEGER DEFAULT 0,
last_trade INTEGER DEFAULT 0,
last_steal INTEGER DEFAULT 0,
last_invest INTEGER DEFAULT 0,
shield_until INTEGER DEFAULT 0
)
""")
conn.commit()


def get_user(uid):
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users(id) VALUES(?)", (uid,))
        conn.commit()
        return get_user(uid)
    return user


# ===== شركة =====
@bot.command()
async def شركة(ctx):
    await ctx.send("🏢 اكتب اسم شركتك:")

    def check(m):
        return m.author == ctx.author

    msg = await bot.wait_for("message", check=check)

    value = random.randint(10000, 50000)

    c.execute("UPDATE users SET company=?, company_value=? WHERE id=?",
              (msg.content, value, ctx.author.id))
    conn.commit()

    await ctx.send(f"✅ تم إنشاء شركتك: {msg.content} | 💰 {value}")


# ===== فلوسي =====
@bot.command()
async def فلوسي(ctx):
    user = get_user(ctx.author.id)

    embed = discord.Embed(
        title="💳 حسابك",
        description=f"💰 فلوسك: {user[1]}\n🏢 شركتك: {user[2] or 'لا يوجد'}\n📈 قيمة الشركة: {user[3]}",
        color=0x3498db
    )
    await ctx.send(embed=embed)


# ===== تحويل =====
@bot.command()
async def تحويل(ctx, member: discord.Member, amount: int):
    user = get_user(ctx.author.id)

    if user[1] < amount:
        return await ctx.send("❌ فلوسك ما تكفي")

    c.execute("UPDATE users SET money=money-? WHERE id=?", (amount, ctx.author.id))
    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, member.id))
    conn.commit()

    await ctx.send(f"💸 حولت {amount} إلى {member.mention}")


# ===== تداول =====
@bot.command()
async def تداول(ctx, amount: int):
    user = get_user(ctx.author.id)

    if user[1] < amount:
        return await ctx.send("❌ فلوسك ما تكفي")

    if time.time() - user[4] < 60:
        return await ctx.send("⏳ لازم تنتظر دقيقة")

    win = random.choice([True, False])

    if win:
        profit = int(amount * random.uniform(0.5, 1.5))
        c.execute("UPDATE users SET money=money+? WHERE id=?", (profit, ctx.author.id))
        msg = f"📈 ربحت {profit}"
    else:
        loss = int(amount * random.uniform(0.3, 1))
        c.execute("UPDATE users SET money=money-? WHERE id=?", (loss, ctx.author.id))
        msg = f"📉 خسرت {loss}"

    c.execute("UPDATE users SET last_trade=? WHERE id=?", (time.time(), ctx.author.id))
    conn.commit()

    await ctx.send(msg)


# ===== الاستثمار =====
current_investment = None

@bot.command()
async def استثمار(ctx, amount: int):
    global current_investment

    user = get_user(ctx.author.id)

    if not current_investment:
        return await ctx.send("❌ ما فيه استثمار حالياً")

    if amount < current_investment["min"]:
        return await ctx.send("❌ أقل من الحد الأدنى")

    if user[1] < amount:
        return await ctx.send("❌ فلوسك ما تكفي")

    if time.time() - user[6] < 60:
        return await ctx.send("⏳ لازم تنتظر دقيقة")

    win = random.random() < current_investment["win"]

    if win:
        profit = int(amount * random.uniform(1.2, 2))
        c.execute("UPDATE users SET money=money+? WHERE id=?", (profit, ctx.author.id))
        msg = f"📈 ربحت {profit}"
    else:
        loss = int(amount * random.uniform(0.5, 1))
        c.execute("UPDATE users SET money=money-? WHERE id=?", (loss, ctx.author.id))
        msg = f"📉 خسرت {loss}"

    c.execute("UPDATE users SET last_invest=? WHERE id=?", (time.time(), ctx.author.id))
    conn.commit()

    await ctx.send(msg)


# ===== استثمار تلقائي =====
investments = [
    {"name": "🏝️ فندق", "min": 5000, "win": 0.6},
    {"name": "🏢 مستشفى", "min": 500000, "win": 0.5},
    {"name": "🏠 بيت", "min": 150000, "win": 0.55},
    {"name": "🛢️ أرامكو", "min": 3000000, "win": 0.8},
]

CHANNEL_ID = 123456789  # حط آيدي الروم هنا


@tasks.loop(minutes=10)
async def investment_event():
    global current_investment

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    current_investment = random.choice(investments)

    embed = discord.Embed(
        title="📊 استثمار جديد",
        description=f"{current_investment['name']}\n💰 الحد الأدنى: {current_investment['min']}\nاكتب: !استثمار مبلغ",
        color=0xf1c40f
    )

    await channel.send(embed=embed)


# ===== سرقة =====
@bot.command()
async def سرقة(ctx, member: discord.Member):
    user = get_user(ctx.author.id)
    target = get_user(member.id)

    if time.time() - user[5] < 300:
        return await ctx.send("⏳ انتظر 5 دقايق")

    if target[7] > time.time():
        return await ctx.send("🛡️ الشخص محمي")

    await ctx.send("ما هو الصحيح؟ 123 / 321 / 312")

    def check(m):
        return m.author == ctx.author

    msg = await bot.wait_for("message", check=check)

    if msg.content != "123":
        return await ctx.send("❌ غلط")

    amount = random.randint(1000, min(400000, target[1]))

    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, ctx.author.id))
    c.execute("UPDATE users SET money=money-? WHERE id=?", (amount, member.id))
    c.execute("UPDATE users SET last_steal=? WHERE id=?", (time.time(), ctx.author.id))
    conn.commit()

    await ctx.send(f"💰 سرقت {amount}")

    try:
        await member.send(f"🚨 انسرقت من {ctx.author}")
    except:
        pass


# ===== حماية =====
@bot.command()
async def حماية(ctx):
    user = get_user(ctx.author.id)

    if user[1] < 300000:
        return await ctx.send("❌ تحتاج 300k")

    c.execute("UPDATE users SET money=money-?, shield_until=? WHERE id=?",
              (300000, time.time() + 7200, ctx.author.id))
    conn.commit()

    await ctx.send("🛡️ حماية لمدة ساعتين")


# ===== تشغيل =====
@bot.event
async def on_ready():
    print("✅ Bot Ready")
    investment_event.start()


bot.run(TOKEN)
