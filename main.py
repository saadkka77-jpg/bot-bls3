import discord
from discord.ext import commands
import sqlite3
import asyncio
import os
from flask import Flask
from threading import Thread

# --- إعداد الويب للـ UptimeRobot ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Fully Operational!"
def run_web(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run_web).start()

# --- قاعدة البيانات ---
conn = sqlite3.connect('server_stats.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (uid INTEGER PRIMARY KEY, interaction INTEGER DEFAULT 0, promo INTEGER DEFAULT 0)''')
conn.commit()

# --- الإعدادات ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# الثوابت
ALLOWED_ROLES = [1482194383515422752, 1480443913557905499]
EXCLUDED_ROLES = [1514389169089020125]
EXCLUDED_CHANNELS = [1516298849981825134, 1516298935185178845]
ADMIN_ROLES = [1490386915629989948, 1478971845729583276, 1505984803839676466]
CONTROL_CHANNEL = 1516300938472849458
PHOTO_CHANNEL = 1516298935185178845

def update_db(uid, col, val):
    cursor.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
    cursor.execute(f"UPDATE users SET {col} = {col} + ? WHERE uid = ?", (val, uid))
    conn.commit()

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # أوامر التحكم
    if message.channel.id == CONTROL_CHANNEL:
        await bot.process_commands(message)
    
    # استثناء الرومات والرتب
    if message.channel.id in EXCLUDED_CHANNELS: return
    if any(r.id in EXCLUDED_ROLES for r in message.author.roles): return

    # نظام الصور
    if message.channel.id == PHOTO_CHANNEL and message.attachments:
        if len(message.attachments) > 1:
            await message.author.send("❌ **يرجى إرسال صورة واحدة فقط في كل رسالة!**")
            await message.delete()
            return
        await message.add_reaction("✅")
        await message.add_reaction("❌")
        return

    # حساب نقاط الرسائل
    if any(r.id in ALLOWED_ROLES for r in message.author.roles):
        if not message.content.startswith("!"):
            update_db(message.author.id, "interaction", 13)
            
    # عرض النقاط
    if message.content.lower() == "تفاعل":
        cursor.execute("SELECT interaction, promo FROM users WHERE uid = ?", (message.author.id,))
        res = cursor.fetchone()
        embed = discord.Embed(title="📊 إحصائياتك", description=f"تفاعل: `{res[0] if res else 0}`\nترقية: `{res[1] if res else 0}`", color=0x2b2d31)
        await message.channel.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != PHOTO_CHANNEL or payload.member.bot: return
    if not any(r.id in ADMIN_ROLES for r in payload.member.roles): return
    
    msg = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
    if str(payload.emoji) == "✅":
        update_db(msg.author.id, "promo", 10)
        await msg.author.send("✅ **تم حساب 10 نقاط ترقية لك.**")
    elif str(payload.emoji) == "❌":
        await msg.author.send("❌ **تم رفض الصورة. يرجى مراجعة الإدارة.**")

@bot.command()
async def توب(ctx):
    cursor.execute("SELECT uid, interaction, promo FROM users ORDER BY promo DESC LIMIT 10")
    data = cursor.fetchall()
    embed = discord.Embed(title="👑 توب الإداريين والترقية", color=0x2b2d31)
    for row in data:
        embed.add_field(name=f"عضو {row[0]}", value=f"تفاعل: {row[1]} | ترقية: {row[2]}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def تصفير_الكل(ctx):
    if ctx.channel.id == CONTROL_CHANNEL:
        cursor.execute("UPDATE users SET interaction = 0, promo = 0")
        conn.commit()
        await ctx.send("✅ **تم تصفير النقاط للجميع.**")

keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
