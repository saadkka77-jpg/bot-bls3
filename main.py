import os
import random
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents)

PROPERTY_ROOM = 1498037416672493829
ADMIN_ROOM = 1498037576538259556

# 🎨 ألوان
COLOR = 0x2b2d31
SUCCESS = 0x57F287
ERROR = 0xED4245
GOLD = 0xFEE75C

# 🧠 قاعدة بيانات
db = {}

# 🏁 حالة المزاد
current_auction = {
    "active": False,
    "price": 0,
    "highest": None,
    "message": None
}

def create_user(uid):
    if uid not in db:
        db[uid] = {
            "money": 10000,
            "properties": [],
            "banned": False
        }

def em(title, desc="", color=COLOR):
    return discord.Embed(title=title, description=desc, color=color)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ {bot.user}")
    auto_auction.start()

# ================= شراء =================
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    if msg.channel.id not in [PROPERTY_ROOM, ADMIN_ROOM]:
        return

    create_user(msg.author.id)
    user = db[msg.author.id]

    if user["banned"]:
        return

    content = msg.content.lower()

    # 💰 رصيد
    if content == "رصيدي":
        await msg.reply(embed=em("💰 رصيدك", f"{user['money']}", GOLD))

    # 🏠 شراء
    elif content == "شراء":
        await msg.reply(embed=em("🏠 شراء", "اكتب المبلغ اللي تبغاه"))

        def check(m):
            return m.author == msg.author and m.channel == msg.channel

        try:
            reply = await bot.wait_for("message", timeout=30, check=check)
            amount = int(reply.content)
        except:
            return await msg.channel.send(embed=em("❌ انتهى الوقت", color=ERROR))

        if amount > user["money"]:
            return await msg.channel.send(embed=em("❌ فلوسك ما تكفي", color=ERROR))

        user["money"] -= amount
        user["properties"].append(amount)

        await msg.channel.send(embed=em("✅ تم الشراء", f"دفعت {amount}", SUCCESS))

    await bot.process_commands(msg)

# ================= المزاد =================

class BidView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 مزايدة", style=discord.ButtonStyle.primary)
    async def bid(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not current_auction["active"]:
            return await interaction.response.send_message("❌ المزاد انتهى", ephemeral=True)

        create_user(interaction.user.id)
        user = db[interaction.user.id]

        new_price = current_auction["price"] + 1000

        if user["money"] < new_price:
            return await interaction.response.send_message("❌ فلوسك ما تكفي", ephemeral=True)

        current_auction["price"] = new_price
        current_auction["highest"] = interaction.user

        await interaction.response.send_message(f"🔥 {interaction.user.mention} زاد إلى {new_price}")

# ================= مزاد تلقائي =================

cars = [
    ("🚗 سيارة عادية", 5000),
    ("🏎️ سبورت", 10000),
    ("👑 روز رايز", 30000)
]

houses = [
    ("🏠 بيت شعبي", 4000),
    ("🏡 فيلا", 15000),
    ("🏖️ فيلا على البحر", 40000)
]

@tasks.loop(minutes=30)
async def auto_auction():
    if current_auction["active"]:
        return

    channel = bot.get_channel(PROPERTY_ROOM)

    item_type = random.choice(["car", "house"])

    if item_type == "car":
        name, price = random.choice(cars)
    else:
        name, price = random.choice(houses)

    current_auction["active"] = True
    current_auction["price"] = price
    current_auction["highest"] = None

    embed = em("🔥 مزاد جديد", f"{name}\n\n💰 البداية: {price}", GOLD)

    msg = await channel.send(embed=embed, view=BidView())
    current_auction["message"] = msg

    await asyncio.sleep(600)  # 10 دقائق

    # ⏱️ عد تنازلي
    for i in [5,4,3,2,1]:
        await channel.send(f"⏳ {i}")
        await asyncio.sleep(1)

    if not current_auction["highest"]:
        await channel.send(embed=em("❌ انتهى المزاد", "لم يشارك أحد", ERROR))
    else:
        winner = current_auction["highest"]
        user = db[winner.id]
        user["money"] -= current_auction["price"]

        await channel.send(embed=em("🏆 الفائز", f"{winner.mention}\n💰 {current_auction['price']}", SUCCESS))

    current_auction["active"] = False

bot.run(BOT_TOKEN)
