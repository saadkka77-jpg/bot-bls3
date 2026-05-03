import discord
from discord.ext import commands
import random
import time
import os
from pymongo import MongoClient

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents)

# 🔥 سيرفرك فقط
ALLOWED_GUILD_ID = 1498037416672493829

# MongoDB
mongo = MongoClient(os.getenv("MONGO_URI"))
db = mongo["economy"]
users = db["users"]

def get_user(user_id):
    user = users.find_one({"userId": str(user_id)})
    if not user:
        user = {
            "userId": str(user_id),
            "money": 1000,
            "gold": 0,
            "diamonds": 0,
            "lands": 0,
            "lastInvest": 0,
            "lastTrade": 0,
            "lastSteal": 0
        }
        users.insert_one(user)
    return user

def save_user(user):
    users.update_one({"userId": user["userId"]}, {"$set": user})

def embed(title, desc, color=0x2b2d31):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text="نظام الاقتصاد")
    return e


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


@bot.event
async def on_message(msg):

    # ❌ يمنع أي شيء خارج سيرفرك
    if msg.guild is None or msg.guild.id != ALLOWED_GUILD_ID:
        return

    if msg.author.bot:
        return

    args = msg.content.split()
    if len(args) == 0:
        return

    cmd = args[0]
    user = get_user(msg.author.id)

    # 📊 ممتلكاتي
    if cmd == "ممتلكاتي":
        await msg.reply(embed=embed("📊 ممتلكاتك",
        f"""💵 {user['money']}
🥇 {user['gold']}
💎 {user['diamonds']}
🏝️ {user['lands']}""", 0x00bcd4))


    # 📈 استثمار
    elif cmd == "استثمار":
        now = time.time()
        if now - user["lastInvest"] < 180:
            return await msg.reply(embed=embed("⏳", "انتظر 3 دقايق"))

        amount = user["money"] if len(args) > 1 and args[1] == "كل" else int(args[1])

        if user["money"] < amount:
            return await msg.reply(embed=embed("❌", "ما عندك المبلغ"))

        user["money"] -= amount
        user["lastInvest"] = now

        change = int(amount * random.uniform(0, 0.5))

        if random.random() < 0.5:
            user["money"] += amount + change
            await msg.reply(embed=embed("📈 نجاح", f"+{change}", 0x4caf50))
        else:
            await msg.reply(embed=embed("📉 خسارة", f"-{change}", 0xf44336))

        save_user(user)


    # 📊 تداول
    elif cmd == "تداول":
        now = time.time()
        if now - user["lastTrade"] < 180:
            return await msg.reply(embed=embed("⏳", "انتظر 3 دقايق"))

        amount = user["money"] if args[1] == "كل" else int(args[1])

        if user["money"] < amount:
            return await msg.reply(embed=embed("❌", "ما عندك"))

        user["money"] -= amount
        user["lastTrade"] = now

        change = int(amount * random.uniform(0, 0.7))

        if random.random() < 0.5:
            user["money"] += amount + change
            await msg.reply(embed=embed("💹 ربح", f"+{change}", 0x4caf50))
        else:
            await msg.reply(embed=embed("📉 خسارة", f"-{change}", 0xf44336))

        save_user(user)


    # 🎰 روليت
    elif cmd == "روليت":
        r = random.randint(0, 3)

        if r == 0:
            x = random.randint(1, 500)
            user["gold"] += x
            text = f"🥇 {x}"
        elif r == 1:
            x = random.randint(1, 300)
            user["diamonds"] += x
            text = f"💎 {x}"
        elif r == 2:
            x = random.randint(1, 3)
            user["lands"] += x
            text = f"🏝️ {x}"
        else:
            x = random.randint(1, 1000)
            user["money"] += x
            text = f"💵 {x}"

        save_user(user)
        await msg.reply(embed=embed("🎰 روليت", text))


    # 🕵️ سرقة
    elif cmd == "سرقة":
        if not msg.mentions:
            return await msg.reply("من تبي تنهب؟")

        target = msg.mentions[0]
        victim = get_user(target.id)

        now = time.time()
        if now - user["lastSteal"] < 300:
            return await msg.reply(embed=embed("⏳", "انتظر 5 دقايق"))

        if victim["money"] <= 0:
            return await msg.reply(embed=embed("❌", "ما عنده فلوس"))

        stolen = random.randint(0, victim["money"])

        victim["money"] -= stolen
        user["money"] += stolen
        user["lastSteal"] = now

        save_user(victim)
        save_user(user)

        await msg.reply(
            content=f"🚨 {target.mention}",
            embed=embed("🕵️ نهب!", f"تم سرقة {stolen} 😈", 0xff9800)
        )


    # مهم جدًا 👇
    await bot.process_commands(msg)


bot.run(os.getenv("DISCORD_TOKEN"))
