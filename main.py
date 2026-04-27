import os
import random
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# 🎯 الرومات
PROPERTY_ROOM = 1498037416672493829
ADMIN_ROOM = 1498037576538259556

# 🧠 قاعدة بيانات بسيطة (بديل quick.db)
db = {}

def create_user(user_id):
    if user_id not in db:
        db[user_id] = {
            "money": 1000,
            "stocks": 3,
            "properties": [],
            "firstWin": True,
            "lastCommand": 0,
            "banned": False
        }

def cooldown(user):
    now = int(asyncio.get_event_loop().time() * 1000)
    if now - user["lastCommand"] < 3000:
        return False
    user["lastCommand"] = now
    return True

@bot.event
async def on_ready():
    print(f"✅ شغال: {bot.user}")

@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    user_id = msg.author.id
    create_user(user_id)
    user = db[user_id]

    if user["banned"]:
        return

    if not cooldown(user):
        return

    content = msg.content

    # 📊 رصيد
    if content == "/رصيدي":
        await msg.reply(f"💰 رصيدك: {user['money']}")

    # 📊 محفظتي
    elif content == "/محفظتي":
        embed = discord.Embed(title="📊 | حسابك")
        embed.add_field(name="💰 الرصيد", value=str(user["money"]))
        embed.add_field(name="🏠 العقارات", value=str(len(user["properties"])))
        await msg.reply(embed=embed)

    # 🏠 شراء
    elif content == "/شراء":
        if msg.channel.id != PROPERTY_ROOM:
            return await msg.reply("❌ هذا الأمر فقط في روم العقارات")

        price = random.randint(500, 1000)

        if user["money"] < price:
            return await msg.reply("❌ فلوسك ما تكفي")

        user["money"] -= price
        user["properties"].append({
            "id": int(asyncio.get_event_loop().time()),
            "price": price
        })

        await msg.reply(f"✅ اشتريت عقار بـ {price}")

        await asyncio.sleep(600)

        if user["firstWin"]:
            result = "ربح"
            user["firstWin"] = False
        else:
            r = random.random()
            if r < 0.4:
                result = "ربح"
            elif r < 0.8:
                result = "خسارة"
            else:
                result = "ثبات"

        if result == "ربح":
            user["money"] += random.randint(0, 300)

        if result == "خسارة" and random.random() < 0.3:
            if user["properties"]:
                user["properties"].pop()

        try:
            await msg.author.send(f"📩 نتيجة الاستثمار: {result}")
        except:
            pass

    # 💸 بيع
    elif content == "/بيع":
        if msg.channel.id != PROPERTY_ROOM:
            return

        if len(user["properties"]) < 100:
            return await msg.reply("❌ تحتاج 100 عقار")

        p = user["properties"].pop()
        user["money"] += p["price"]

        await msg.reply("✅ تم البيع")

    # ================= ADMIN =================
    if msg.channel.id == ADMIN_ROOM:

        # 💰 إضافة
        if content.startswith("/اضافة"):
            parts = content.split()
            if len(parts) < 3:
                return

            target = msg.mentions[0]
            amount = int(parts[2])

            create_user(target.id)
            db[target.id]["money"] += amount

            await msg.reply("✅ تم الإضافة")

        # ❌ خصم
        elif content.startswith("/خصم"):
            parts = content.split()
            target = msg.mentions[0]
            amount = int(parts[2])

            db[target.id]["money"] -= amount
            await msg.reply("✅ تم الخصم")

        # 🚫 حظر
        elif content.startswith("/حظر"):
            target = msg.mentions[0]
            db[target.id]["banned"] = True
            await msg.reply("🚫 تم الحظر")

        # 🔓 فك
        elif content.startswith("/فك"):
            target = msg.mentions[0]
            db[target.id]["banned"] = False
            await msg.reply("✅ تم فك الحظر")

        # 🔄 تصفير
        elif content == "/تصفير":
            db.clear()
            await msg.reply("⚠️ تم تصفير الاقتصاد")

    await bot.process_commands(msg)

bot.run(BOT_TOKEN)
