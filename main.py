import discord
from discord.ext import commands, tasks
import sqlite3
import random
import time

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

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


# ===== إنشاء شركة =====
@bot.command()
async def شركة(ctx):
    embed = discord.Embed(
        title="🏢 نظام الشركات",
        description="اكتب اسم شركتك:",
        color=0x2b2d31
    )

    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    msg = await bot.wait_for("message", check=check)

    value = random.randint(10000, 50000)

    c.execute("UPDATE users SET company=?, company_value=? WHERE id=?",
              (msg.content, value, ctx.author.id))
    conn.commit()

    embed = discord.Embed(
        title="📁 تم إنشاء الشركة",
        description=f"🏷️ الاسم: {msg.content}\n💰 القيمة: {value}",
        color=0x00ff99
    )
    await ctx.send(embed=embed)


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
        return await ctx.send("❌ ما عندك فلوس كافية")

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
        return await ctx.send("⏳ انتظر دقيقة")

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


# ===== استثمار عشوائي =====
investments = [
    ("🏝️ فندق على البحر", 5000),
    ("🏢 بناء مستشفى", 500000),
    ("🏠 بيت شمال الرياض", 150000),
    ("🛢️ أرامكو", 3000000)
]


@tasks.loop(minutes=10)
async def investment_event():
    channel = bot.get_channel(YOUR_CHANNEL_ID)

    name, min_amount = random.choice(investments)

    embed = discord.Embed(
        title="📊 فرصة استثمار",
        description=f"{name}\n💰 الحد الأدنى: {min_amount}",
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

    if target[6] > time.time():
        return await ctx.send("🛡️ الشخص محمي")

    question = "ما هو الرقم الصحيح؟\n1) 123\n2) 321\n3) 312"
    await ctx.send(question)

    def check(m):
        return m.author == ctx.author

    msg = await bot.wait_for("message", check=check)

    if msg.content != "123":
        return await ctx.send("❌ إجابة غلط")

    amount = random.randint(1000, min(400000, target[1]))

    c.execute("UPDATE users SET money=money+? WHERE id=?", (amount, ctx.author.id))
    c.execute("UPDATE users SET money=money-? WHERE id=?", (amount, member.id))
    c.execute("UPDATE users SET last_steal=? WHERE id=?", (time.time(), ctx.author.id))
    conn.commit()

    await ctx.send(f"💰 سرقت {amount} من {member.mention}")

    try:
        await member.send(f"🚨 تم سرقتك بواسطة {ctx.author}")
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

    await ctx.send("🛡️ تم تفعيل الحماية ساعتين")


# ===== تشغيل =====
@bot.event
async def on_ready():
    print("Bot is ready")
    investment_event.start()


bot.run("YOUR_TOKEN")
