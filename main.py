import discord
from discord.ext import commands
import sqlite3
import os
from dotenv import load_dotenv
import random

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="", intents=intents)

CHANNEL_CREATE = 1499051894235201586
ROLE_COMPANY_OWNER = 1498411802957058269

# ===== DATABASE =====
conn = sqlite3.connect("game.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
company TEXT,
company_value INTEGER DEFAULT 0
)
""")
conn.commit()

def get_user(uid):
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u:
        c.execute("INSERT INTO users(id) VALUES(?)", (uid,))
        conn.commit()
        return get_user(uid)
    return u

# ===== مودال إنشاء شركة =====
class CreateCompanyModal(discord.ui.Modal, title="إنشاء شركة"):
    name = discord.ui.TextInput(label="اسم الشركة", placeholder="اكتب الاسم هنا")

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("UPDATE users SET company=?, company_value=? WHERE id=?",
                  (self.name.value, random.randint(10000, 50000), interaction.user.id))
        conn.commit()

        role = interaction.guild.get_role(ROLE_COMPANY_OWNER)
        if role:
            await interaction.user.add_roles(role)

        embed = discord.Embed(
            title="🏢 تم إنشاء شركتك",
            description=f"اسم الشركة: **{self.name.value}**",
            color=0x00ff99
        )

        await interaction.response.send_message(embed=embed)

# ===== مودال تغيير الاسم =====
class RenameCompanyModal(discord.ui.Modal, title="تغيير اسم الشركة"):
    name = discord.ui.TextInput(label="الاسم الجديد")

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("UPDATE users SET company=? WHERE id=?",
                  (self.name.value, interaction.user.id))
        conn.commit()

        await interaction.response.send_message(
            f"✅ تم تغيير اسم شركتك إلى {self.name.value}"
        )

# ===== الأزرار =====
class CompanyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إنشاء شركة", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateCompanyModal())

    @discord.ui.button(label="تغيير اسم الشركة", style=discord.ButtonStyle.blurple)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        if not user[1]:
            return await interaction.response.send_message("❌ ما عندك شركة", ephemeral=True)

        await interaction.response.send_modal(RenameCompanyModal())

# ===== أمر إرسال القائمة =====
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # الأمر بدون !
    if message.content == "شركة" and message.channel.id == CHANNEL_CREATE:
        embed = discord.Embed(
            title="🏢 نظام الشركات",
            description="اضغط الزر لإنشاء شركتك أو تعديلها",
            color=0x3498db
        )
        await message.channel.send(embed=embed, view=CompanyView())

    await bot.process_commands(message)

# ===== رفع قيمة الشركة عند النجاح =====
@bot.command()
async def نجاح(ctx):
    user = get_user(ctx.author.id)

    if not user[1]:
        return await ctx.send("❌ ما عندك شركة")

    increase = random.randint(5000, 20000)
    c.execute("UPDATE users SET company_value=company_value+? WHERE id=?",
              (increase, ctx.author.id))
    conn.commit()

    embed = discord.Embed(
        title="📈 نجاح!",
        description=f"ارتفعت قيمة شركة **{user[1]}** بمقدار {increase}",
        color=0x2ecc71
    )
    await ctx.send(embed=embed)

bot.run(TOKEN)
