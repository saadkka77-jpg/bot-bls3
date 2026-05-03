import discord
from discord.ext import commands
import random
import time
import os
from pymongo import MongoClient

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents)

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
    if msg.author.bot:
        return

    args = msg.content.split()
    cmd = args[0]

    user = get_user(msg.author.id)

    # ممتلكاتي
    if cmd == "ممتلكاتي":
        await msg.reply(embed=embed("📊 ممتلكاتك",
        f"""
💵 الفلوس: **{user['money']}**
🥇 الذهب: **{user['gold']}**
💎 الماس: **{user['diamonds']}**
🏝️ الأراضي: **{user['lands']}**
""", 0x00bcd4))

    # استثمار
    elif cmd == "استثمار":
        now = time.time()
        if now - user["lastInvest"] < 180:
            return await msg.reply(embed=embed("⏳", "انتظر 3 دقايق"))

        try:
            amount = user["money"] if args[1] == "كل" else int(args[1])
        except:
            return await msg.reply(embed=embed("❌", "اكتب مبلغ صحيح"))

        if user["money"] < amount or amount <= 0:
            return await msg.reply(embed=embed("❌", "ما عندك المبلغ"))

        user["money"] -= amount
        user["lastInvest"] = now

        change = int(amount * random.uniform(0, 0.5))

        if random.random() < 0.5:
            user["money"] += amount + change
            await msg.reply(embed=embed("📈 استثمار ناجح", f"ربحت **{change}** 💰", 0x4caf50))
        else:
            await msg.reply(embed=embed("📉 استثمار فاشل", f"خسرت **{change}**", 0xf44336))

        save_user(user)

    # تداول
    elif cmd == "تداول":
        now = time.time()
        if now - user["lastTrade"] < 180:
            return await msg.reply(embed=embed("⏳", "انتظر 3 دقايق"))

        try:
            amount = user["money"] if args[1] == "كل" else int(args[1])
        except:
            return await msg.reply(embed=embed("❌", "اكتب مبلغ صحيح"))

        if user["money"] < amount or amount <= 0:
            return await msg.reply(embed=embed("❌", "ما عندك"))

        user["money"] -= amount
        user["lastTrade"] = now

        change = int(amount * random.uniform(0, 0.7))

        if random.random() < 0.5:
            user["money"] += amount + change
            await msg.reply(embed=embed("💹 تداول ناجح", f"كسبت **{change}**", 0x4caf50))
        else:
            await msg.reply(embed=embed("📉 تداول خاسر", f"خسرت **{change}**", 0xf44336))

        save_user(user)

    # روليت
    elif cmd == "روليت":
        r = random.randint(0, 3)

        if r == 0:
            x = random.randint(1, 500)
            user["gold"] += x
            text = f"🥇 حصلت **{x} ذهب**"
        elif r == 1:
            x = random.randint(1, 300)
            user["diamonds"] += x
            text = f"💎 حصلت **{x} ماس**"
        elif r == 2:
            x = random.randint(1, 3)
            user["lands"] += x
            text = f"🏝️ حصلت **{x} أرض**"
        else:
            x = random.randint(1, 1000)
            user["money"] += x
            text = f"💵 حصلت **{x} فلوس**"

        save_user(user)
        await msg.reply(embed=embed("🎰 روليت", text))

    # سرقة (نهب + منشن)
    elif cmd == "سرقة":
        if not msg.mentions:
            return await msg.reply("من تبي تنهب؟")

        target = msg.mentions[0]
        victim = get_user(target.id)

        now = time.time()
        if now - user["lastSteal"] < 300:
            return await msg.reply(embed=embed("⏳", "انتظر 5 دقايق"))

        if victim["money"] <= 0:
            return await msg.reply(embed=embed("❌", "الشخص لا يملك مال"))

        stolen = random.randint(0, victim["money"])

        victim["money"] -= stolen
        user["money"] += stolen
        user["lastSteal"] = now

        save_user(victim)
        save_user(user)

        await msg.reply(
            content=f"🚨 {target.mention}",
            embed=embed("🕵️ نهب!", f"تم نهب **{stolen}** 💰 من {target.mention}\nيا حرامي وش اليد الخفيفة هذي 😈", 0xff9800)
        )

    # بيع
    elif cmd == "بيع":
        try:
            type_ = args[2]
        except:
            return await msg.reply("اكتب: بيع [كم] [gold/diamonds/lands]")

        if type_ not in ["gold", "diamonds", "lands"]:
            return await msg.reply("gold / diamonds / lands")

        if args[1] == "كل":
            amount = user[type_]
        elif args[1] == "نص":
            amount = user[type_] // 2
        else:
            try:
                amount = int(args[1])
            except:
                return await msg.reply("اكتب رقم صحيح")

        if amount <= 0 or user[type_] < amount:
            return await msg.reply(embed=embed("❌", "ما عندك الكمية"))

        price = random.randint(1, 100)

        user[type_] -= amount
        user["money"] += amount * price

        save_user(user)

        await msg.reply(embed=embed("💰 بيع ناجح", f"بعت **{amount} {type_}** بسعر **{price}**", 0x4caf50))

bot.run(os.getenv("DISCORD_TOKEN"))
