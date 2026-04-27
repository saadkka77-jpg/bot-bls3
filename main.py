import os
import random
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents)

# 📍 رومات
ROOM = 1498037416672493829
ADMIN = 1498037576538259556
FULL_ACCESS = 1498411802957058269

# 🎖️ رتبة المحظوظ
LUCKY_ROLE = 1498410522255687832

# 🎨 ألوان
C = 0x2b2d31
G = 0xFEE75C
S = 0x57F287
E = 0xED4245

db = {}

auction = {
    "active": False,
    "price": 0,
    "owner": None,
    "item": None
}

# ================= مستخدم =================
def user(uid):
    if uid not in db:
        db[uid] = {
            "money": 10000,
            "items": [],
            "company": None,
            "shield": 0,
            "last_trade": 0,
            "last_invest": 0,
            "last_rob": 0,
            "bank": 0
        }

def emb(t, d="", c=C):
    return discord.Embed(title=t, description=d, color=c)

def is_lucky(member):
    return any(r.id == LUCKY_ROLE for r in member.roles)

def is_protected(u):
    return u["shield"] > datetime.now().timestamp()

# ================= READY =================
@bot.event
async def on_ready():
    print("BOT READY")
    auto_auction.start()

# ================= ON MESSAGE =================
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    if msg.channel.id not in [ROOM, ADMIN, FULL_ACCESS]:
        return

    user(msg.author.id)
    u = db[msg.author.id]

    content = msg.content.lower()
    now = datetime.now().timestamp()

    # ================= شركة =================
    if content == "شركة":
        if u["company"]:
            return await msg.reply("❌ عندك شركة")

        await msg.reply("💼 اكتب اسم شركتك")

        def check(m):
            return m.author == msg.author and m.channel == msg.channel

        try:
            m = await bot.wait_for("message", timeout=30, check=check)
            u["company"] = m.content
        except:
            return await msg.reply("❌ انتهى الوقت")

        await msg.reply(f"✅ شركة: {u['company']}")

    # ================= استثمار =================
    elif content == "استثمار":
        if not u["company"]:
            return await msg.reply("❌ لازم شركة")

        if now - u["last_invest"] < 120:
            return await msg.reply("⏳ انتظر دقيقتين")

        u["last_invest"] = now

        result = random.choice(["ربح", "خسارة", "ثبات"])
        amount = random.randint(500, 3000)

        if is_lucky(msg.author):
            result = "ربح"

        if result == "ربح":
            u["money"] += amount
        elif result == "خسارة":
            u["money"] -= amount

        await msg.reply(embed=emb("📈 استثمار", f"{result} | {amount}", G))

    # ================= تداول =================
    elif content == "تداول":
        if not u["company"]:
            return await msg.reply("❌ لازم شركة")

        if now - u["last_trade"] < 120:
            return await msg.reply("⏳ انتظر دقيقتين")

        u["last_trade"] = now

        r = random.choice(["ربح", "خسارة"])
        amount = random.randint(1000, 5000)

        if is_lucky(msg.author):
            r = "ربح"

        if r == "ربح":
            u["money"] += amount
        else:
            u["money"] -= amount

        await msg.reply(embed=emb("📊 تداول", f"{r} | {amount}", G))

    # ================= حماية =================
    elif content == "حماية":
        cost = 3000

        if u["money"] < cost:
            return await msg.reply("❌ ما عندك")

        u["money"] -= cost
        u["shield"] = now + 7200

        await msg.author.send("🛡️ حماية لمدة ساعتين")

    # ================= سرقة =================
    elif content == "سرقة":
        target_id = random.choice(list(db.keys()))
        target = db[target_id]

        if target_id == msg.author.id:
            return

        if is_protected(target):
            return await msg.reply("🛡️ محمي")

        if now - u["last_rob"] < 30:
            return await msg.reply("⏳ انتظر")

        u["last_rob"] = now

        steal = random.randint(500, 2000)

        target["money"] -= steal
        u["money"] += steal

        await msg.reply(embed=emb("🕵️ سرقة", f"+{steal}", S))

    # ================= رصيد =================
    elif content == "رصيدي":
        await msg.reply(embed=emb("💰 رصيد", str(u["money"]), G))

    # ================= بنك =================
    elif content == "بنك":
        await msg.reply(embed=emb("🏦 البنك", str(u["bank"]), G))

    elif content.startswith("إيداع"):
        try:
            amount = int(content.split()[1])
        except:
            return await msg.reply("❌ رقم")

        if u["money"] < amount:
            return await msg.reply("❌ ما عندك")

        u["money"] -= amount
        u["bank"] += amount

        await msg.reply(embed=emb("🏦 إيداع", str(amount), S))

    elif content.startswith("سحب"):
        try:
            amount = int(content.split()[1])
        except:
            return await msg.reply("❌ رقم")

        if u["bank"] < amount:
            return await msg.reply("❌ البنك فاضي")

        u["bank"] -= amount
        u["money"] += amount

        await msg.reply(embed=emb("💸 سحب", str(amount), S))

    elif content.startswith("تحويل"):
        try:
            target = msg.mentions[0]
            amount = int(content.split()[2])
        except:
            return await msg.reply("❌ تحويل @user amount")

        user(target.id)

        if u["money"] < amount:
            return await msg.reply("❌ ما عندك")

        u["money"] -= amount
        db[target.id]["money"] += amount

        await msg.reply(embed=emb("🔁 تحويل", f"{amount} → {target.mention}", G))

    await bot.process_commands(msg)

# ================= مزاد =================
class AuctionView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="مزايدة", style=discord.ButtonStyle.green)
    async def bid(self, i, b):

        if not auction["active"]:
            return await i.response.send_message("انتهى", ephemeral=True)

        user(i.user.id)
        u = db[i.user.id]

        price = auction["price"] + 1000

        if is_lucky(i.user):
            price -= 500

        if u["money"] < price:
            return await i.response.send_message("❌ ما يكفي", ephemeral=True)

        auction["price"] = price
        auction["owner"] = i.user

        await i.channel.send(f"🔥 {i.user.mention} {price}")

# ================= مزاد تلقائي =================
items = ["🚗 سيارة", "🏠 بيت", "🏎️ روز رايز", "🏡 فيلا"]

@tasks.loop(minutes=30)
async def auto_auction():
    if auction["active"]:
        return

    ch = bot.get_channel(ROOM)

    item = random.choice(items)
    price = random.randint(5000, 50000)

    auction["active"] = True
    auction["price"] = price
    auction["item"] = item
    auction["owner"] = None

    await ch.send(embed=emb("🔥 مزاد", f"{item}\n💰 {price}", G), view=AuctionView())

    await asyncio.sleep(300)

    for i in [5,4,3,2,1]:
        await ch.send(f"⏳ {i}")
        await asyncio.sleep(1)

    if auction["owner"]:
        u = db[auction["owner"].id]
        u["money"] -= auction["price"]
        u["items"].append(auction["item"])

        await ch.send(f"🏆 فاز {auction['owner'].mention}")
    else:
        await ch.send("❌ لا أحد شارك")

    auction["active"] = False

TOKEN = os.getenv("BOT_TOKEN") 
