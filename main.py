import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from flask import Flask
from threading import Thread

# =========================
# Web Server for UptimeRobot
# =========================

app = Flask("")

@app.route("/")
def home():
    return "Bot is Fully Operational!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run_web).start()


# =========================
# Bot Settings
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

GAME_ROLE_ID = 1516370348717772971
REQUIRED_ROLE_ID = 1478970736717598840
PANEL_COLOR = 0xE10600

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="", intents=intents)


# =========================
# Role Button View
# =========================

class GameRoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="خذ رتبة 𝐀𝐬𝐬𝐢𝐭𝐨 𝐂𝐨𝐫𝐬𝐚",
        style=discord.ButtonStyle.danger,
        emoji="🏎️",
        custom_id="assetto_corsa_role_button"
    )
    async def assetto_corsa_role(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        member = interaction.user

        role = guild.get_role(GAME_ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ لم أجد رتبة اللعبة. تأكد أن آيدي الرتبة صحيح.",
                ephemeral=True
            )
            return

        if role in member.roles:
            await interaction.response.send_message(
                "✅ أنت تملك رتبة 𝐀𝐬𝐬𝐢𝐭𝐨 𝐂𝐨𝐫𝐬𝐚 بالفعل.",
                ephemeral=True
            )
            return

        try:
            await member.add_roles(role, reason="Assetto Corsa role panel")
            await interaction.response.send_message(
                "✅ تم إعطاؤك رتبة 𝐀𝐬𝐬𝐢𝐭𝐨 𝐂𝐨𝐫𝐬𝐚 بنجاح.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ لا أستطيع إعطاء الرتبة. تأكد أن رتبة البوت أعلى من رتبة اللعبة وأن لديه صلاحية Manage Roles.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ صار خطأ أثناء إعطاء الرتبة، حاول مرة ثانية.",
                ephemeral=True
            )


# =========================
# Events
# =========================

@bot.event
async def on_ready():
    bot.add_view(GameRoleView())
    print(f"Logged in as {bot.user}")


# =========================
# Commands
# =========================

@bot.command(name="S")
async def role_panel(ctx):
    if not any(role.id == REQUIRED_ROLE_ID for role in ctx.author.roles):
        return

    embed = discord.Embed(
        title="🏎️ 𝐀𝐬𝐬𝐢𝐭𝐨 𝐂𝐨𝐫𝐬𝐚",
        description=(
            "**الرتبة الجديدة للعبة 𝐀𝐬𝐬𝐢𝐭𝐨 𝐂𝐨𝐫𝐬𝐚**\n\n"
            "اضغط على الزر بالأسفل وخذ الرتبة عشان يطلع لك كل شيء يخص اللعبة."
        ),
        color=PANEL_COLOR
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_footer(text="Role System")

    await ctx.send(embed=embed, view=GameRoleView())


# =========================
# Run Bot
# =========================

keep_alive()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.")

bot.run(TOKEN)
