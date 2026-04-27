import discord
from discord.ext import commands
from discord.ui import View, Select
import os
import datetime
import json
import io

from flask import Flask
from threading import Thread

# ===============================
# Flask (Web Service)
# ===============================

app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_web).start()

# ===============================

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ===============================
# الترقيم
# ===============================

COUNTER_FILE = "ticket_counter.json"

def get_ticket_number():

    if not os.path.exists(COUNTER_FILE):

        with open(COUNTER_FILE, "w") as f:
            json.dump({"ticket": 0}, f)

    with open(COUNTER_FILE, "r") as f:
        data = json.load(f)

    data["ticket"] += 1

    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f)

    return data["ticket"]

# ===============================
# الإعدادات
# ===============================

RANK_CATEGORY = 1494665237717323907
PERSON_CATEGORY = 1494665311331291258
SHOP_CATEGORY = 1487848330804330699
SUPPORT_CATEGORY = 1487721982945394728
ADMIN_CATEGORY = 1487709726765748295

LOG_CHANNEL = 1480456866613170267

SUPPORT_ROLES = [
1477492633847857252,
1482194383515422752,
1480443913557905499,
1478970736717598840
]

SPECIAL_ROLES = [
1490386915629989948,
1495873706923393205,
1478971845729583276
]

ALL_ROLES = list(set(SUPPORT_ROLES + SPECIAL_ROLES))

# ===============================
# أمر إضافة عضو للتكت
# ===============================

@bot.command()
async def add(ctx, member: discord.Member):

    if not any(r.id in ALL_ROLES for r in ctx.author.roles):
        return await ctx.send("❌ لا تملك صلاحية لاستخدام هذا الأمر.")

    channel = ctx.channel

    await channel.set_permissions(
        member,
        read_messages=True,
        send_messages=True
    )

    embed = discord.Embed(
        title="➕ تم إضافة عضو",
        description=f"تم إضافة {member.mention} إلى التكت بنجاح.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )

    await ctx.send(embed=embed)

# ===============================
# إغلاق التكت
# ===============================

class CloseModal(discord.ui.Modal, title="🔒 إغلاق التكت"):

    reason = discord.ui.TextInput(
        label="سبب الإغلاق",
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction):

        await interaction.response.defer()

        channel = interaction.channel
        log = bot.get_channel(LOG_CHANNEL)

        opener_id = None

        if channel.topic and "|" in channel.topic:
            opener_id = channel.topic.split("|")[0]

        messages = []

        async for m in channel.history(limit=200):
            messages.append(f"{m.author}: {m.content}")

        transcript = "\n".join(messages)

        file = discord.File(
            io.BytesIO(transcript.encode()),
            filename="transcript.txt"
        )

        embed = discord.Embed(
            title="📁 تم إغلاق التكت",
            description=f"📌 السبب:\n{self.reason.value}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )

        if log:
            await log.send(embed=embed, file=file)

        # ===============================
        # رسالة خاصة احترافية
        # ===============================

        try:

            if opener_id:

                user = await bot.fetch_user(int(opener_id))

                private_embed = discord.Embed(
                    title="📁 تم إغلاق تذكرتك",
                    description=(
                        "نشكر تواصلك معنا 💙\n\n"
                        f"📌 **سبب الإغلاق:**\n{self.reason.value}\n\n"
                        "⭐ **تشرفنا في خدمتك في سيرفر BLS**\n"
                        "نتمنى لك تجربة ممتعة معنا دائماً."
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(datetime.UTC)
                )

                await user.send(embed=private_embed)

        except:
            pass

        await channel.delete()

# ===============================
# أزرار التكت
# ===============================

class TicketButtons(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📌 استلام التكت",
        style=discord.ButtonStyle.green,
        custom_id="claim_ticket"
    )
    async def claim_ticket(self, interaction, button):

        if not any(r.id in ALL_ROLES for r in interaction.user.roles):

            return await interaction.response.send_message(
                "❌ لا تملك صلاحية",
                ephemeral=True
            )

        channel = interaction.channel
        guild = interaction.guild

        opener, claimed = channel.topic.split("|")

        if claimed != "0":

            user = await bot.fetch_user(int(claimed))

            return await interaction.response.send_message(
                f"❌ التكت مستلمة بالفعل بواسطة {user.mention}",
                ephemeral=True
            )

        new_topic = f"{opener}|{interaction.user.id}"
        await channel.edit(topic=new_topic)

        for role_id in ALL_ROLES:

            role = guild.get_role(role_id)

            if role:

                await channel.set_permissions(
                    role,
                    read_messages=True,
                    send_messages=False
                )

        await channel.set_permissions(
            interaction.user,
            read_messages=True,
            send_messages=True
        )

        embed = discord.Embed(
            title="📌 تم استلام التكت",
            description=f"👤 بواسطة: {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(
        label="🔒 إغلاق التكت",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction, button):

        if not any(r.id in ALL_ROLES for r in interaction.user.roles):

            return await interaction.response.send_message(
                "❌ لا تملك صلاحية",
                ephemeral=True
            )

        await interaction.response.send_modal(
            CloseModal()
        )

# ===============================
# إنشاء التكت
# ===============================

async def create_ticket(interaction, ticket_type):

    guild = interaction.guild
    user = interaction.user

    ticket_number = get_ticket_number()

    categories = {

        "support": SUPPORT_CATEGORY,
        "shop": SHOP_CATEGORY,
        "admin": ADMIN_CATEGORY,
        "rank": RANK_CATEGORY,
        "person": PERSON_CATEGORY

    }

    category = guild.get_channel(categories[ticket_type])

    if ticket_type in ["shop", "admin"]:
        roles_to_add = SPECIAL_ROLES
    else:
        roles_to_add = SUPPORT_ROLES

    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                read_messages=False
            ),

        user:
            discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
    }

    for role_id in roles_to_add:

        role = guild.get_role(role_id)

        if role:

            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )

    channel = await guild.create_text_channel(

        name=f"ticket-{ticket_number}",
        category=category,
        overwrites=overwrites,
        topic=f"{user.id}|0"

    )

    embed = discord.Embed(

        title="🎫 تم فتح التكت",

        description=(
            "📜 **قوانين التكت:**\n"
            "• اشرح مشكلتك بوضوح\n"
            "• احترام الإدارة\n"
            "• يمنع الإزعاج\n\n"
            "⏳ سيتم الرد عليك قريباً"
        ),

        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.UTC)

    )

    if guild.icon:
        embed.set_thumbnail(
            url=guild.icon.url
        )

    await channel.send(
        content=user.mention,
        embed=embed,
        view=TicketButtons()
    )

    await interaction.response.send_message(
        f"✅ تم فتح التكت: {channel.mention}",
        ephemeral=True
    )

# ===============================
# القائمة
# ===============================

class TicketSelect(Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="الدعم الفني",
                emoji="🛠️",
                value="support"
            ),

            discord.SelectOption(
                label="المتجر",
                emoji="🛒",
                value="shop"
            ),

            discord.SelectOption(
                label="شكوى على إداري",
                emoji="⚖️",
                value="admin"
            ),

            discord.SelectOption(
                label="طلب رانك",
                emoji="⭐",
                value="rank"
            ),

            discord.SelectOption(
                label="شكوى على شخص",
                emoji="🚫",
                value="person"
            )

        ]

        super().__init__(
            placeholder="اختر نوع التكت",
            options=options,
            custom_id="ticket_select_menu"
        )

    async def callback(self, interaction):

        await create_ticket(
            interaction,
            self.values[0]
        )

class TicketPanel(View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(
            TicketSelect()
        )

# ===============================
# أمر اللوحة
# ===============================

@bot.command()
async def panel(ctx):

    embed = discord.Embed(

        title="🎫 نظام التكت",

        description=(
            "📜 **قوانين فتح التكت:**\n"
            "• اختر القسم المناسب\n"
            "• لا تفتح أكثر من تكت\n"
            "• احترام الإدارة\n\n"
            "⬇️ اختر نوع التكت"
        ),

        color=discord.Color.blue()

    )

    if ctx.guild.icon:

        embed.set_thumbnail(
            url=ctx.guild.icon.url
        )

    await ctx.send(
        embed=embed,
        view=TicketPanel()
    )

# ===============================
# تشغيل
# ===============================

@bot.event
async def on_ready():

    print(f"✅ Logged in as {bot.user}")

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())

keep_alive()

bot.run(TOKEN)
