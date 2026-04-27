import discord
from discord.ext import commands
import random
import asyncio
import os
from datetime import datetime

# إعدادات البوت
TOKEN = os.getenv('DISCORD_TOKEN')
PROPERTY_ROOM_ID = 1498037416672493829
ADMIN_ROOM_ID = 1498037576538259556

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# قاعدة بيانات بسيطة (في ملف json)
import json
def load_db():
    if not os.path.exists('db.json'):
        return {}
    with open('db.json', 'r') as f:
        return json.load(f)

def save_db(data):
    with open('db.json', 'w') as f:
        json.dump(data, f)

def get_user(user_id, db):
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"money": 1000, "properties": [], "first_win": True, "banned": False}
    return db[uid]

@bot.event
async def on_ready():
    print(f'✅ البوت شغال باسم: {bot.user}')

@bot.command(name='رصيدي')
async def balance(ctx):
    db = load_db()
    user = get_user(ctx.author.id, db)
    if user['banned']: return
    await ctx.reply(f"💰 رصيدك الحالي: {user['money']}")

@bot.command(name='شراء')
async def buy(ctx):
    if ctx.channel.id != PROPERTY_ROOM_ID:
        return await ctx.reply("❌ هذا الأمر فقط في روم العقارات")
    
    db = load_db()
    user = get_user(ctx.author.id, db)
    if user['banned']: return

    price = random.randint(500, 1000)
    if user['money'] < price:
        return await ctx.reply("❌ فلوسك ما تكفي!")

    user['money'] -= price
    user['properties'].append({"id": str(datetime.now()), "price": price})
    save_db(db)
    
    await ctx.reply(f"✅ اشتريت عقار بـ {price}. انتظر 10 دقائق لنتيجة الاستثمار.")
    
    # محاكاة الاستثمار بعد 10 دقائق
    await asyncio.sleep(600)
    result_money = random.randint(100, 300)
    user['money'] += result_money
    save_db(db)
    try:
        await ctx.author.send(f"📩 نتيجة استثمارك: ربحت {result_money}")
    except:
        pass

@bot.command(name='اضافة')
async def add_money(ctx, member: discord.Member, amount: int):
    if ctx.channel.id != ADMIN_ROOM_ID: return
    db = load_db()
    user = get_user(member.id, db)
    user['money'] += amount
    save_db(db)
    await ctx.reply(f"✅ تم إضافة {amount} لـ {member.display_name}")

@bot.command(name='تصفير')
async def reset(ctx):
    if ctx.channel.id != ADMIN_ROOM_ID: return
    save_db({})
    await ctx.reply("⚠️ تم تصفير الاقتصاد بالكامل")

bot.run(TOKEN)
