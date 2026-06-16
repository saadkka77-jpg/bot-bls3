import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from flask import Flask
from threading import Thread

app = Flask("")

@app.route("/")
def home():
    return "Bot is Fully Operational!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run_web).start()


TOKEN = os.getenv("DISCORD_TOKEN")

PANEL_MANAGER_ROLE_ID = 1478970736717598840

ASSITO_ROLE_ID = 1516370348717772971
UFC_ROLE_ID = 1515651907778121828

PANEL_COLOR = 0xE10600

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="", intents=intents)


class AssitoRoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="خذ رتبة Assito Corsa",
        style=discord.ButtonStyle.danger,
        emoji="🏎️",
        custom_id="assito_corsa_role_button"
    )
    async def assito_role(self, interaction: discord.Interaction, button: Button):
        await give_role(interaction, ASSITO_ROLE_ID)


class UFCRoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="خذ رتبة UFC",
        style=discord.ButtonStyle.danger,
        emoji="🥊",
        custom_id="ufc_role_button"
    )
    async def ufc_role(self, interaction: discord.Interaction, button: Button):
        await give_role(interaction, UFC_ROLE_ID)


async def give_role(interaction: discord.Interaction, role_id: int):
    guild = interaction.guild
    member = interaction.user
    role = guild.get_role(role_id)

    if role is None:
        await interaction.response.send_message(
            "❌ لم أجد الرتبة. تأكد من آيدي الرتبة.",
            ephemeral=True
        )
        return

    if role in member.roles:
        await interaction.response.send_message("✅", ephemeral=True)
        return

    try:
        await member.add_roles(role, reason="Game role button")
        await interaction.response.send_message("✅", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ لا أقدر أعطيك الرتبة. تأكد أن رتبة البوت أعلى من الرتبة ومعه صلاحية Manage Roles.",
            ephemeral=True
        )
    except discord.HTTPException:
        await interaction.response.send_message(
            "❌ صار خطأ، حاول مرة ثانية.",
            ephemeral=True
        )


def can_send_panel(ctx):
    return any(role.id == PANEL_MANAGER_ROLE_ID for role in ctx.author.roles)


@bot.event
async def on_ready():
    bot.add_view(AssitoRoleView())
    bot.add_view(UFCRoleView())
    print(f"Logged in as {bot.user}")


@bot.command(name="S")
async def assito_panel(ctx):
    if not can_send_panel(ctx):
        return

    embed = discord.Embed(
        title="🏎️ Assito Corsa",
        description=(
            "**الرتبة الجديدة للعبة Assito Corsa**\n\n"
            "اضغط على الزر بالأسفل وخذ الرتبة عشان يطلع لك كل شيء يخص اللعبة."
        ),
        color=PANEL_COLOR
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_footer(text="Role System")

    message = await ctx.send(embed=embed, view=AssitoRoleView())
    await message.add_reaction("✅")


@bot.command(name="U")
async def ufc_panel(ctx):
    if not can_send_panel(ctx):
        return

    embed = discord.Embed(
        title="🥊 𝐔𝐅𝐂",
        description=(
            "**لمحبين 𝐔𝐅𝐂 وفرنا لكم هذه الرتبة**\n\n"
            "اضغط الزر وخذ الرتبة وتابع كل ما يخص اليو اف سي."
        ),
        color=PANEL_COLOR
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_footer(text="Role System")

    message = await ctx.send(embed=embed, view=UFCRoleView())
    await message.add_reaction("✅")


keep_alive()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.")

bot.run(TOKEN)
