import asyncio
import datetime
import json
import os
import re
from pathlib import Path
from threading import Thread

import discord
from discord.ext import commands, tasks
from flask import Flask


# =========================
# KEEP ALIVE
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Points and promotion bot is running"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    Thread(target=run_web, daemon=True).start()


# =========================
# BOT
# =========================

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
views_registered = False


# =========================
# IDS
# =========================

POINT_CHANNEL = 1497204458680090779
INTERACTION_PANEL_CHANNEL = 1497642199859593388
KEYWORD_CHANNEL = 1497911384191668254
PROMOTION_REQUEST_CHANNEL = 1497203612432990259
HACKED_PROTECTION_CHANNEL = 1514000444349878483

POINTS_ACTION_LOG_CHANNEL = 1516309944129818735
SPAM_LOG_CHANNEL = 1516295642824310824

POINT_ROLES = {
    1482194383515422752,
    1480443913557905499,
}

IMAGE_REVIEW_ROLES = {
    1477492633847857252,
}

ADMIN_ROLES = {
    1478970736717598840,
    1495873706923393205,
    1490386915629989948,
    1478971845729583276,
}

PROMOTION_REVIEW_ROLES = {
    1478971845729583276,
    1490386915629989948,
    1505984803839676466,
}

ADMIN_RANK_ORDER = [
    1485560413146841210,  # Support
    1485549583861022802,  # Moderator
    1480649204593332324,  # Admin
    1485551861334540378,  # Manager
    1518903745637908540,  # Major
    1518903845198237807,  # Director
    1488591572042780725,  # Head Admin
    1518903808778960896,  # Controller
    1518903917927338074,  # Consultant
    1480818082426392637,  # Executive
]

# SETTINGS
# =========================

TEXT_POINTS = 15
DOUBLE_TEXT_POINTS = 30
VOICE_POINTS_EVERY_10_MINUTES = 5
DOUBLE_VOICE_POINTS_EVERY_10_MINUTES = 10
IMAGE_POINTS = 10

TEXT_POINTS_BLOCKED_CHANNELS = {POINT_CHANNEL, KEYWORD_CHANNEL}
SPAM_MESSAGE_LIMIT_PER_SECOND = 10
SPAM_ALERT_COOLDOWN_SECONDS = 300
LOGIN_RETRY_SECONDS = 1800
PROTECTION_TIMEOUT_DAYS = 7


# =========================
# FILES
# =========================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

POINT_FILE = DATA_DIR / "points.json"
REQUIRE_FILE = DATA_DIR / "requirements.json"
DOUBLE_FILE = DATA_DIR / "double.json"
TEXT_TOGGLE_FILE = DATA_DIR / "text_points_toggle.json"


def load_json(file: Path, default=None):
    if default is None:
        default = {}
    if not file.exists():
        save_json(file, default)
        return default.copy() if isinstance(default, dict) else default
    try:
        with file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default.copy() if isinstance(default, dict) else default


def save_json(file: Path, data):
    file.parent.mkdir(exist_ok=True)
    with file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def has_any_role(member: discord.Member, role_ids: set[int]) -> bool:
    return any(role.id in role_ids for role in getattr(member, "roles", []))


def is_admin(member: discord.Member) -> bool:
    return has_any_role(member, ADMIN_ROLES)


def is_points_member(member: discord.Member) -> bool:
    return not member.bot and has_any_role(member, POINT_ROLES)


def can_review_images(member: discord.Member) -> bool:
    return is_admin(member) or has_any_role(member, IMAGE_REVIEW_ROLES)


def can_review_promotions(member: discord.Member) -> bool:
    return has_any_role(member, PROMOTION_REVIEW_ROLES)


def double_active() -> bool:
    return load_json(DOUBLE_FILE, {"active": False}).get("active", False)


def parse_member_id(value: str) -> int | None:
    match = re.search(r"\d{15,25}", value)
    return int(match.group(0)) if match else None


def get_guild_icon_url(guild: discord.Guild | None):
    return guild.icon.url if guild and guild.icon else None


def apply_guild_brand(embed: discord.Embed, guild: discord.Guild | None):
    icon_url = get_guild_icon_url(guild)
    if icon_url:
        embed.set_footer(text=guild.name, icon_url=icon_url)
    return embed


def get_points(user_id: int):
    points = load_json(POINT_FILE)
    requirements = load_json(REQUIRE_FILE)
    uid = str(user_id)
    return points.get(uid, 0), requirements.get(uid, 0)


def change_points_value(file: Path, user_id: int, amount: int):
    data = load_json(file)
    uid = str(user_id)
    data[uid] = max(0, data.get(uid, 0) + amount)
    save_json(file, data)
    return data[uid]


def should_award_text_points(user_id: int) -> bool:
    toggles = load_json(TEXT_TOGGLE_FILE)
    uid = str(user_id)
    should_count = toggles.get(uid, True)
    toggles[uid] = not should_count
    save_json(TEXT_TOGGLE_FILE, toggles)
    return should_count


def get_admin_rank_progress(member: discord.Member):
    current_role = None
    current_index = None
    for index, role_id in enumerate(ADMIN_RANK_ORDER):
        if any(role.id == role_id for role in member.roles):
            current_role = member.guild.get_role(role_id)
            current_index = index

    if current_index is None:
        return None, member.guild.get_role(ADMIN_RANK_ORDER[0])
    if current_index + 1 >= len(ADMIN_RANK_ORDER):
        return current_role, None
    return current_role, member.guild.get_role(ADMIN_RANK_ORDER[current_index + 1])


def build_promotion_panel_embed(guild: discord.Guild):
    embed = discord.Embed(
        title="ظ„ظˆط­ط© ط·ظ„ط¨ ط§ظ„طھط±ظ‚ظٹط©",
        description="ط§ط¶ط؛ط· ط§ظ„ط²ط± ظ„ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹط© ظٹط­طھظˆظٹ ط¹ظ„ظ‰ طµظˆط±طھظƒطŒ ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©طŒ ط±طھط¨طھظƒ ط§ظ„ط­ط§ظ„ظٹط©طŒ ظˆط§ظ„ط±طھط¨ط© ط§ظ„ظ…ط·ظ„ظˆط¨ط©.",
        color=discord.Color.blurple(),
    )
    return apply_guild_brand(embed, guild)


async def send_promotion_request(source):
    user = source.author if hasattr(source, "author") else source.user
    guild = source.guild
    channel = source.channel

    if not isinstance(user, discord.Member) or not is_points_member(user):
        if hasattr(source, "response"):
            await source.response.send_message("â‌Œ ظ†ط¸ط§ظ… ط·ظ„ط¨ ط§ظ„طھط±ظ‚ظٹط© ظ…ط®طµطµ ظ„ظ„ط±طھط¨ ط§ظ„ظ…ط¹طھظ…ط¯ط© ظپظٹ ط§ظ„طھظپط§ط¹ظ„ ظپظ‚ط·.", ephemeral=True)
        return

    current_role, next_role = get_admin_rank_progress(user)
    if not next_role:
        if hasattr(source, "response"):
            await source.response.send_message("âœ… ط£ظ†طھ ط¹ظ„ظ‰ ط£ط¹ظ„ظ‰ ط±طھط¨ط© ط¥ط¯ط§ط±ظٹط© ط­ط§ظ„ظٹظ‹ط§.", ephemeral=True)
        return

    total, req = get_points(user.id)
    embed = discord.Embed(
        title="ط·ظ„ط¨ طھط±ظ‚ظٹط© ط¬ط¯ظٹط¯",
        description=f"طھظ… ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹط© ظ…ظ† {user.mention}.",
        color=discord.Color.blurple(),
        timestamp=now_utc(),
    )
    embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", value=f"`{total}`", inline=True)
    embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", value=f"`{req}`", inline=True)
    embed.add_field(name="ط§ظ„ط±طھط¨ط© ط§ظ„ط­ط§ظ„ظٹط©", value=current_role.mention if current_role else "ظ„ط§ طھظˆط¬ط¯ ط±طھط¨ط© ط¥ط¯ط§ط±ظٹط©", inline=True)
    embed.add_field(name="ط§ظ„ط±طھط¨ط© ط§ظ„ظ…ط·ظ„ظˆط¨ط©", value=next_role.mention, inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    apply_guild_brand(embed, guild)

    await channel.send(embed=embed, view=PromotionReviewView(user.id, current_role.id if current_role else None, next_role.id))
    if hasattr(source, "response"):
        await source.response.send_message("âœ… طھظ… ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹطھظƒ ظ„ظ„ظ…ط±ط§ط¬ط¹ط©.", ephemeral=True)


async def send_points_action_log(guild: discord.Guild, moderator: discord.Member, target: discord.Member | None, action: str, amount: int | None = None, new_value: int | None = None):
    return
    channel = guild.get_channel(POINTS_ACTION_LOG_CHANNEL) or bot.get_channel(POINTS_ACTION_LOG_CHANNEL)
    if not channel:
        return

    embed = discord.Embed(title="ط³ط¬ظ„ ط¥ط¯ط§ط±ط© ط§ظ„ظ†ظ‚ط§ط·", color=discord.Color.dark_teal(), timestamp=now_utc())
    embed.add_field(name="ط§ظ„ط¥ط¬ط±ط§ط،", value=action, inline=True)
    embed.add_field(name="ط§ظ„ظ…ط³ط¤ظˆظ„", value=moderator.mention, inline=True)
    if target:
        embed.add_field(name="ط§ظ„ط¹ط¶ظˆ", value=target.mention, inline=True)
    if amount is not None:
        embed.add_field(name="ط§ظ„ظ‚ظٹظ…ط©", value=f"`{amount}`", inline=True)
    if new_value is not None:
        embed.add_field(name="ط§ظ„ط±طµظٹط¯ ط¨ط¹ط¯ ط§ظ„ط¹ظ…ظ„ظٹط©", value=f"`{new_value}`", inline=True)
    apply_guild_brand(embed, guild)
    await channel.send(embed=embed)


# =========================
# POINTS PANEL
# =========================

class ChangeValueModal(discord.ui.Modal):
    def __init__(self, title: str, file: Path, action_name: str, multiplier: int):
        super().__init__(title=title)
        self.file = file
        self.action_name = action_name
        self.multiplier = multiplier
        self.user_id = discord.ui.TextInput(label="ط¢ظٹط¯ظٹ ط£ظˆ ظ…ظ†ط´ظ† ط§ظ„ط¹ط¶ظˆ", required=True, max_length=40)
        self.amount = discord.ui.TextInput(label="ط¹ط¯ط¯ ط§ظ„ظ†ظ‚ط§ط·", required=True, max_length=8)
        self.add_item(self.user_id)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return

        member_id = parse_member_id(self.user_id.value)
        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            amount = None

        if not member_id or amount is None or amount <= 0:
            await interaction.response.send_message("â‌Œ ط§ظ„ط¨ظٹط§ظ†ط§طھ ط؛ظٹط± طµط­ظٹط­ط©.", ephemeral=True)
            return

        member = interaction.guild.get_member(member_id)
        if not member:
            await interaction.response.send_message("â‌Œ ظ„ظ… ط£ط¬ط¯ ط§ظ„ط¹ط¶ظˆ ط¯ط§ط®ظ„ ط§ظ„ط³ظٹط±ظپط±.", ephemeral=True)
            return

        signed_amount = amount * self.multiplier
        new_value = change_points_value(self.file, member.id, signed_amount)
        await send_points_action_log(interaction.guild, interaction.user, member, self.action_name, signed_amount, new_value)
        await interaction.response.send_message(f"âœ… طھظ… طھظ†ظپظٹط°: **{self.action_name}** ظ„ظ€ {member.mention}. ط§ظ„ط±طµظٹط¯ ط§ظ„ط¢ظ†: `{new_value}`", ephemeral=True)


class ResetUserModal(discord.ui.Modal):
    def __init__(self, title: str, file: Path, action_name: str):
        super().__init__(title=title)
        self.file = file
        self.action_name = action_name
        self.user_id = discord.ui.TextInput(label="ط¢ظٹط¯ظٹ ط£ظˆ ظ…ظ†ط´ظ† ط§ظ„ط¹ط¶ظˆ", required=True, max_length=40)
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return

        member_id = parse_member_id(self.user_id.value)
        if not member_id:
            await interaction.response.send_message("â‌Œ ط¢ظٹط¯ظٹ ط§ظ„ط¹ط¶ظˆ ط؛ظٹط± طµط­ظٹط­.", ephemeral=True)
            return

        data = load_json(self.file)
        data[str(member_id)] = 0
        save_json(self.file, data)
        member = interaction.guild.get_member(member_id)
        await send_points_action_log(interaction.guild, interaction.user, member, self.action_name, 0, 0)
        await interaction.response.send_message("âœ… طھظ… ط§ظ„طھطµظپظٹط± ط¨ظ†ط¬ط§ط­.", ephemeral=True)


class InteractionPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ظ†ظ‚ط§ط·ظٹ", style=discord.ButtonStyle.primary, custom_id="points:mine", row=0)
    async def my_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        total, req = get_points(interaction.user.id)
        embed = discord.Embed(title="ظ…ظ„ظپ ط§ظ„طھظپط§ط¹ظ„ ط§ظ„ط¥ط¯ط§ط±ظٹ", description=f"ظ…ظ„ط®طµ ظ†ظ‚ط§ط· {interaction.user.mention}.", color=discord.Color.blue(), timestamp=now_utc())
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", value=f"`{total}`", inline=True)
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", value=f"`{req}`", inline=True)
        embed.add_field(name="ط­ط§ظ„ط© ط§ظ„ط¯ط¨ظ„", value="`ظ…ظپط¹ظ„`" if double_active() else "`ظ…ط؛ظ„ظ‚`", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        icon_url = get_guild_icon_url(interaction.guild)
        if icon_url:
            embed.set_author(name=interaction.guild.name, icon_url=icon_url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="ط§ظ„طھظˆط¨", style=discord.ButtonStyle.success, custom_id="points:top", row=0)
    async def top_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("âœ… طھظ… ط¥ط±ط³ط§ظ„ ط§ظ„طھظˆط¨طŒ ظˆط³ظٹطھظ… ط­ط°ظپظ‡ ط¨ط¹ط¯ 10 ط¯ظ‚ط§ط¦ظ‚.", ephemeral=True)
        await send_temporary_top(interaction.channel, interaction.guild)

    @discord.ui.button(label="ط²ظٹط§ط¯ط© طھظپط§ط¹ظ„", style=discord.ButtonStyle.secondary, custom_id="points:add_interaction", row=1)
    async def add_interaction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChangeValueModal("ط²ظٹط§ط¯ط© ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", POINT_FILE, "ط²ظٹط§ط¯ط© ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", 1))

    @discord.ui.button(label="ط®طµظ… طھظپط§ط¹ظ„", style=discord.ButtonStyle.danger, custom_id="points:remove_interaction", row=1)
    async def remove_interaction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChangeValueModal("ط®طµظ… ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", POINT_FILE, "ط®طµظ… ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", -1))

    @discord.ui.button(label="طھطµظپظٹط± طھظپط§ط¹ظ„ ط´ط®طµ", style=discord.ButtonStyle.danger, custom_id="points:reset_interaction", row=1)
    async def reset_interaction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetUserModal("طھطµظپظٹط± ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", POINT_FILE, "طھطµظپظٹط± ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„"))

    @discord.ui.button(label="ط²ظٹط§ط¯ط© طھط±ظ‚ظٹط©", style=discord.ButtonStyle.secondary, custom_id="points:add_upgrade", row=2)
    async def add_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChangeValueModal("ط²ظٹط§ط¯ط© ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", REQUIRE_FILE, "ط²ظٹط§ط¯ط© ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", 1))

    @discord.ui.button(label="ط®طµظ… طھط±ظ‚ظٹط©", style=discord.ButtonStyle.danger, custom_id="points:remove_upgrade", row=2)
    async def remove_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChangeValueModal("ط®طµظ… ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", REQUIRE_FILE, "ط®طµظ… ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", -1))

    @discord.ui.button(label="طھطµظپظٹط± طھط±ظ‚ظٹط© ط´ط®طµ", style=discord.ButtonStyle.danger, custom_id="points:reset_upgrade", row=2)
    async def reset_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetUserModal("طھطµظپظٹط± ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", REQUIRE_FILE, "طھطµظپظٹط± ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©"))

    @discord.ui.button(label="طھطµظپظٹط± طھظپط§ط¹ظ„ ط§ظ„ظƒظ„", style=discord.ButtonStyle.danger, custom_id="points:reset_all", row=3)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return
        points = load_json(POINT_FILE)
        for uid in list(points):
            points[uid] = 0
        save_json(POINT_FILE, points)
        await send_points_action_log(interaction.guild, interaction.user, None, "طھطµظپظٹط± طھظپط§ط¹ظ„ ط¬ظ…ظٹط¹ ط§ظ„ط£ط¹ط¶ط§ط،", 0, 0)
        await interaction.response.send_message("âœ… طھظ… طھطµظپظٹط± ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„ ظ„ط¬ظ…ظٹط¹ ط§ظ„ط£ط¹ط¶ط§ط،.", ephemeral=True)

    @discord.ui.button(label="ط§ظ„ط¯ط¨ظ„", style=discord.ButtonStyle.secondary, custom_id="points:double", row=3)
    async def toggle_double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return
        data = load_json(DOUBLE_FILE, {"active": False})
        data["active"] = not data.get("active", False)
        save_json(DOUBLE_FILE, data)
        await interaction.response.send_message(f"âœ… ط§ظ„ط¯ط¨ظ„ ط§ظ„ط¢ظ†: {'ظ…ظپط¹ظ„' if data['active'] else 'ظ…ط؛ظ„ظ‚'}.", ephemeral=True)


def build_top_embed(guild: discord.Guild):
    points = load_json(POINT_FILE)
    requirements = load_json(REQUIRE_FILE)
    embed = discord.Embed(title="طھظˆط¨ ط§ظ„طھظپط§ط¹ظ„ ظˆط§ظ„طھط±ظ‚ظٹط©", color=discord.Color.gold(), timestamp=now_utc())

    interaction_points = []
    promotion_points = []

    for uid, value in points.items():
        member = guild.get_member(int(uid))
        if member and is_points_member(member):
            interaction_points.append((uid, value))

    for uid, value in requirements.items():
        member = guild.get_member(int(uid))
        if member and is_points_member(member):
            promotion_points.append((uid, value))

    if not interaction_points and not promotion_points:
        embed.description = "ظ„ط§ طھظˆط¬ط¯ ظ†ظ‚ط§ط· ط­ط§ظ„ظٹظ‹ط§."
        return apply_guild_brand(embed, guild)

    medals = ["ًں¥‡", "ًں¥ˆ", "ًں¥‰"]

    interaction_lines = []
    for index, (uid, pts) in enumerate(sorted(interaction_points, key=lambda item: item[1], reverse=True)[:10], start=1):
        member = guild.get_member(int(uid))
        prefix = medals[index - 1] if index <= 3 else f"`#{index}`"
        interaction_lines.append(f"{prefix} {member.mention} - `{pts}` ظ†ظ‚ط·ط©")

    promotion_lines = []
    for index, (uid, pts) in enumerate(sorted(promotion_points, key=lambda item: item[1], reverse=True)[:10], start=1):
        member = guild.get_member(int(uid))
        prefix = medals[index - 1] if index <= 3 else f"`#{index}`"
        promotion_lines.append(f"{prefix} {member.mention} - `{pts}` ظ†ظ‚ط·ط©")

    embed.add_field(
        name="طھظˆط¨ ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„",
        value="\n".join(interaction_lines) if interaction_lines else "ظ„ط§ طھظˆط¬ط¯ ظ†ظ‚ط§ط· طھظپط§ط¹ظ„.",
        inline=False,
    )
    embed.add_field(
        name="طھظˆط¨ ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©",
        value="\n".join(promotion_lines) if promotion_lines else "ظ„ط§ طھظˆط¬ط¯ ظ†ظ‚ط§ط· طھط±ظ‚ظٹط©.",
        inline=False,
    )
    return apply_guild_brand(embed, guild)


async def send_temporary_top(channel: discord.abc.Messageable, guild: discord.Guild):
    message = await channel.send(embed=build_top_embed(guild))
    try:
        await message.delete(delay=600)
    except discord.HTTPException:
        pass


@bot.command(name="ظ„ظˆط­ط©")
@commands.cooldown(1, 30, commands.BucketType.channel)
async def interaction_panel(ctx: commands.Context):
    if ctx.channel.id != INTERACTION_PANEL_CHANNEL or not is_admin(ctx.author):
        return
    embed = discord.Embed(
        title="ظ„ظˆط­ط© ط¥ط¯ط§ط±ط© ط§ظ„طھظپط§ط¹ظ„ ظˆط§ظ„طھط±ظ‚ظٹط©",
        description="ط¥ط¯ط§ط±ط© ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„ ظˆط§ظ„طھط±ظ‚ظٹط© ظˆط§ظ„ط¯ط¨ظ„ ظ…ظ† ظ„ظˆط­ط© ظˆط§ط­ط¯ط©.",
        color=discord.Color.dark_teal(),
    )
    await ctx.send(embed=apply_guild_brand(embed, ctx.guild), view=InteractionPanel())


# =========================
# IMAGE REVIEW
# =========================

class RejectImageModal(discord.ui.Modal, title="ط³ط¨ط¨ ط±ظپط¶ ط§ظ„طµظˆط±ط©"):
    reason = discord.ui.TextInput(label="ط³ط¨ط¨ ط§ظ„ط±ظپط¶", style=discord.TextStyle.paragraph, required=True, max_length=300)

    def __init__(self, target_id: int):
        super().__init__()
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        target = interaction.guild.get_member(self.target_id)
        embed = discord.Embed(
            title="ط·ظ„ط¨ طµظˆط±ط© ظ…ط±ظپظˆط¶",
            description=f"**ط³ط¨ط¨ ط§ظ„ط±ظپط¶:** {self.reason.value}",
            color=discord.Color.red(),
            timestamp=now_utc(),
        )
        if target:
            embed.add_field(name="ط§ظ„ط¥ط¯ط§ط±ظٹ", value=target.mention, inline=True)
            embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ط§ظ„ظ…ط±ط§ط¬ط¹", value=interaction.user.mention, inline=True)
        await interaction.response.edit_message(embed=apply_guild_brand(embed, interaction.guild), view=None)
        return
        if target:
            try:
                await target.send(f"â‌Œ طھظ… ط±ظپط¶ طµظˆط±طھظƒ.\n**ط§ظ„ط³ط¨ط¨:** {self.reason.value}")
            except discord.HTTPException:
                pass
        embed = discord.Embed(title="ط·ظ„ط¨ طµظˆط±ط© ظ…ط±ظپظˆط¶", description=f"**ط³ط¨ط¨ ط§ظ„ط±ظپط¶:** {self.reason.value}", color=discord.Color.red(), timestamp=now_utc())
        if target:
            embed.add_field(name="ط§ظ„ط¥ط¯ط§ط±ظٹ", value=target.mention, inline=True)
            embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ط§ظ„ظ…ط±ط§ط¬ط¹", value=interaction.user.mention, inline=True)
        if interaction.message and interaction.message.embeds and interaction.message.embeds[0].image:
            embed.set_image(url=interaction.message.embeds[0].image.url)
        await interaction.response.edit_message(embed=apply_guild_brand(embed, interaction.guild), view=None)


class ImageReviewView(discord.ui.View):
    def __init__(self, target_id: int):
        super().__init__(timeout=None)
        self.target_id = target_id

    @discord.ui.button(label="ظ‚ط¨ظˆظ„", style=discord.ButtonStyle.success, custom_id="image_review:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_review_images(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return
        target = interaction.guild.get_member(self.target_id)
        if not target or not is_points_member(target):
            await interaction.response.send_message("â‌Œ ط§ظ„ط¹ط¶ظˆ ط؛ظٹط± ظ…ظˆط¬ظˆط¯ ط£ظˆ ظ„ط§ ظٹظ…ظ„ظƒ ط±طھط¨ط© ط§ظ„طھظپط§ط¹ظ„.", ephemeral=True)
            return
        total = change_points_value(REQUIRE_FILE, target.id, IMAGE_POINTS)
        await send_points_action_log(interaction.guild, interaction.user, target, "ظ‚ط¨ظˆظ„ طµظˆط±ط© ظˆظ…ظ†ط­ ظ†ظ‚ط§ط· طھط±ظ‚ظٹط©", IMAGE_POINTS, total)
        embed = discord.Embed(title="ط·ظ„ط¨ طµظˆط±ط© ظ…ظ‚ط¨ظˆظ„", description=f"âœ… طھظ… ظ‚ط¨ظˆظ„ طµظˆط±ط© {target.mention}.", color=discord.Color.green(), timestamp=now_utc())
        embed.add_field(name="ط§ظ„ظ…ط±ط§ط¬ط¹", value=interaction.user.mention, inline=True)
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط© ط§ظ„ظ…ط¶ط§ظپط©", value=f"`{IMAGE_POINTS}`", inline=True)
        embed.add_field(name="ط±طµظٹط¯ ط§ظ„طھط±ظ‚ظٹط©", value=f"`{total}`", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        if interaction.message and interaction.message.embeds and interaction.message.embeds[0].image:
            embed.set_image(url=interaction.message.embeds[0].image.url)
        await interaction.response.edit_message(embed=apply_guild_brand(embed, interaction.guild), view=None)

    @discord.ui.button(label="ط±ظپط¶", style=discord.ButtonStyle.danger, custom_id="image_review:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_review_images(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط©.", ephemeral=True)
            return
        await interaction.response.send_modal(RejectImageModal(self.target_id))


# =========================
# PROMOTION REQUESTS
# =========================

class PromotionRejectModal(discord.ui.Modal, title="ط³ط¨ط¨ ط±ظپط¶ ط·ظ„ط¨ ط§ظ„طھط±ظ‚ظٹط©"):
    reason = discord.ui.TextInput(label="ط³ط¨ط¨ ط§ظ„ط±ظپط¶", style=discord.TextStyle.paragraph, required=True, max_length=300)

    def __init__(self, target_id: int):
        super().__init__()
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        target = interaction.guild.get_member(self.target_id)
        if target:
            try:
                await target.send(f"â‌Œ طھظ… ط±ظپط¶ ط·ظ„ط¨ طھط±ظ‚ظٹطھظƒ.\n**ط§ظ„ط³ط¨ط¨:** {self.reason.value}")
            except discord.HTTPException:
                pass
        embed = discord.Embed(title="ط·ظ„ط¨ طھط±ظ‚ظٹط© ظ…ط±ظپظˆط¶", description=f"**ط³ط¨ط¨ ط§ظ„ط±ظپط¶:** {self.reason.value}", color=discord.Color.red(), timestamp=now_utc())
        if target:
            embed.add_field(name="ط§ظ„ط¥ط¯ط§ط±ظٹ", value=target.mention, inline=True)
            embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ط§ظ„ظ…ط±ط§ط¬ط¹", value=interaction.user.mention, inline=True)
        await interaction.response.edit_message(embed=apply_guild_brand(embed, interaction.guild), view=None)


class PromotionReviewView(discord.ui.View):
    def __init__(self, target_id: int, current_role_id: int | None, next_role_id: int):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.current_role_id = current_role_id
        self.next_role_id = next_role_id

    @discord.ui.button(label="ظ‚ط¨ظˆظ„ ط§ظ„طھط±ظ‚ظٹط©", style=discord.ButtonStyle.success, custom_id="promotion:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_review_promotions(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط© ظ…ط±ط§ط¬ط¹ط© ط§ظ„طھط±ظ‚ظٹط§طھ.", ephemeral=True)
            return
        target = interaction.guild.get_member(self.target_id)
        next_role = interaction.guild.get_role(self.next_role_id)
        current_role = interaction.guild.get_role(self.current_role_id) if self.current_role_id else None
        if not target or not next_role:
            await interaction.response.send_message("â‌Œ طھط¹ط°ط± ط§ظ„ط¹ط«ظˆط± ط¹ظ„ظ‰ ط§ظ„ط¹ط¶ظˆ ط£ظˆ ط±طھط¨ط© ط§ظ„طھط±ظ‚ظٹط©.", ephemeral=True)
            return
        try:
            await target.add_roles(next_role, reason=f"ظ‚ط¨ظˆظ„ ط·ظ„ط¨ طھط±ظ‚ظٹط© ط¨ظˆط§ط³ط·ط© {interaction.user}")
            if current_role:
                await target.remove_roles(current_role, reason="ط§ط³طھط¨ط¯ط§ظ„ ط±طھط¨ط© ط§ظ„ط¥ط¯ط§ط±ط© ط¨ط¹ط¯ ط§ظ„طھط±ظ‚ظٹط©")
        except discord.Forbidden:
            await interaction.response.send_message("â‌Œ ظ„ط§ ط£ظ…ظ„ظƒ طµظ„ط§ط­ظٹط© طھط¹ط¯ظٹظ„ ط±طھط¨ ظ‡ط°ط§ ط§ظ„ط¹ط¶ظˆ.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("â‌Œ ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، طھظ†ظپظٹط° ط§ظ„طھط±ظ‚ظٹط©.", ephemeral=True)
            return
        try:
            await target.send(f"âœ… طھظ… ظ‚ط¨ظˆظ„ ط·ظ„ط¨ طھط±ظ‚ظٹطھظƒ ط¥ظ„ظ‰ ط±طھط¨ط© {next_role.mention}.")
        except discord.HTTPException:
            pass
        total, req = get_points(target.id)
        embed = discord.Embed(title="ط·ظ„ط¨ طھط±ظ‚ظٹط© ظ…ظ‚ط¨ظˆظ„", description=f"âœ… طھظ… ظ‚ط¨ظˆظ„ طھط±ظ‚ظٹط© {target.mention}.", color=discord.Color.green(), timestamp=now_utc())
        embed.add_field(name="ط§ظ„ظ…ط±ط§ط¬ط¹", value=interaction.user.mention, inline=True)
        embed.add_field(name="ط§ظ„ط±طھط¨ط© ط§ظ„ط¬ط¯ظٹط¯ط©", value=next_role.mention, inline=True)
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", value=f"`{req}`", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.edit_message(embed=apply_guild_brand(embed, interaction.guild), view=None)

    @discord.ui.button(label="ط±ظپط¶ ط§ظ„طھط±ظ‚ظٹط©", style=discord.ButtonStyle.danger, custom_id="promotion:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_review_promotions(interaction.user):
            await interaction.response.send_message("â‌Œ ظ„ط§ طھظ…ظ„ظƒ طµظ„ط§ط­ظٹط© ظ…ط±ط§ط¬ط¹ط© ط§ظ„طھط±ظ‚ظٹط§طھ.", ephemeral=True)
            return
        await interaction.response.send_modal(PromotionRejectModal(self.target_id))


class PromotionRequestPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ط·ظ„ط¨ طھط±ظ‚ظٹط©", style=discord.ButtonStyle.primary, custom_id="promotion:request")
    async def request_promotion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_points_member(interaction.user):
            await interaction.response.send_message("â‌Œ ظ†ط¸ط§ظ… ط·ظ„ط¨ ط§ظ„طھط±ظ‚ظٹط© ظ…ط®طµطµ ظ„ظ„ط±طھط¨ ط§ظ„ظ…ط¹طھظ…ط¯ط© ظپظٹ ط§ظ„طھظپط§ط¹ظ„ ظپظ‚ط·.", ephemeral=True)
            return
        current_role, next_role = get_admin_rank_progress(interaction.user)
        if not next_role:
            await interaction.response.send_message("âœ… ط£ظ†طھ ط¹ظ„ظ‰ ط£ط¹ظ„ظ‰ ط±طھط¨ط© ط¥ط¯ط§ط±ظٹط© ط­ط§ظ„ظٹظ‹ط§.", ephemeral=True)
            return
        total, req = get_points(interaction.user.id)
        embed = discord.Embed(title="ط·ظ„ط¨ طھط±ظ‚ظٹط© ط¬ط¯ظٹط¯", description=f"طھظ… ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹط© ظ…ظ† {interaction.user.mention}.", color=discord.Color.blurple(), timestamp=now_utc())
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", value=f"`{total}`", inline=True)
        embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", value=f"`{req}`", inline=True)
        embed.add_field(name="ط§ظ„ط±طھط¨ط© ط§ظ„ط­ط§ظ„ظٹط©", value=current_role.mention if current_role else "ظ„ط§ طھظˆط¬ط¯ ط±طھط¨ط© ط¥ط¯ط§ط±ظٹط©", inline=True)
        embed.add_field(name="ط§ظ„ط±طھط¨ط© ط§ظ„ظ…ط·ظ„ظˆط¨ط©", value=next_role.mention, inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        apply_guild_brand(embed, interaction.guild)
        await interaction.response.send_message("âœ… طھظ… ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹطھظƒ ظ„ظ„ظ…ط±ط§ط¬ط¹ط©.", ephemeral=True)
        await interaction.channel.send(embed=embed, view=PromotionReviewView(interaction.user.id, current_role.id if current_role else None, next_role.id))
        return
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        await interaction.channel.send(embed=embed, view=PromotionReviewView(interaction.user.id, current_role.id if current_role else None, next_role.id))
        await interaction.channel.send(embed=build_promotion_panel_embed(interaction.guild), view=PromotionRequestPanel())
        await interaction.response.send_message("âœ… طھظ… ط¥ط±ط³ط§ظ„ ط·ظ„ط¨ طھط±ظ‚ظٹطھظƒ ظ„ظ„ظ…ط±ط§ط¬ط¹ط©.", ephemeral=True)


@bot.command(name="طھط±ظ‚ظٹط©")
@commands.cooldown(1, 30, commands.BucketType.channel)
async def promotion_panel(ctx: commands.Context):
    if ctx.channel.id != PROMOTION_REQUEST_CHANNEL:
        return
    await ctx.send(embed=build_promotion_panel_embed(ctx.guild), view=PromotionRequestPanel())


# =========================
# POINTS EVENTS
# =========================

voice_times: dict[str, datetime.datetime] = {}
spam_tracker: dict[int, list[float]] = {}
spam_alert_times: dict[int, float] = {}


async def check_spam(message: discord.Message) -> bool:
    current = now_utc().timestamp()
    timestamps = spam_tracker.setdefault(message.author.id, [])
    timestamps = [item for item in timestamps if current - item < 1]
    timestamps.append(current)
    spam_tracker[message.author.id] = timestamps
    if len(timestamps) <= SPAM_MESSAGE_LIMIT_PER_SECOND:
        return False
    last_alert = spam_alert_times.get(message.author.id, 0)
    if current - last_alert < SPAM_ALERT_COOLDOWN_SECONDS:
        return True
    spam_alert_times[message.author.id] = current
    return True
    channel = message.guild.get_channel(SPAM_LOG_CHANNEL) or bot.get_channel(SPAM_LOG_CHANNEL)
    if channel:
        embed = discord.Embed(title="طھظ†ط¨ظٹظ‡ ط³ط¨ط§ظ… ظ†ظ‚ط§ط·", color=discord.Color.red(), timestamp=now_utc())
        embed.add_field(name="ط§ظ„ط¹ط¶ظˆ", value=message.author.mention, inline=True)
        embed.add_field(name="ط¹ط¯ط¯ ط§ظ„ط±ط³ط§ط¦ظ„ ط®ظ„ط§ظ„ ط«ط§ظ†ظٹط©", value=f"`{len(timestamps)}`", inline=True)
        embed.add_field(name="ط§ظ„ط±ظˆظ…", value=message.channel.mention, inline=True)
        await channel.send(embed=apply_guild_brand(embed, message.guild))
    return True


async def handle_message_points(message: discord.Message):
    if not isinstance(message.author, discord.Member) or not is_points_member(message.author):
        return

    has_image = any(a.content_type and a.content_type.startswith("image/") for a in message.attachments)
    if message.channel.id == KEYWORD_CHANNEL and has_image:
        embed = discord.Embed(
            title="ط¥ط¶ط§ظپط© ظ†ظ‚ط§ط·",
            description=(
                f"طھظ… ط§ط³طھظ„ط§ظ… طµظˆط±ط© ظ…ظ† {message.author.mention}\n\n"
                f"ط§ظ„ظ†ظ‚ط§ط· ط§ظ„ظ…ط±ط´ط­ط©: `{IMAGE_POINTS}` ظ†ظ‚ط§ط· طھط±ظ‚ظٹط©\n"
                "ط§ظ„ط­ط§ظ„ط©: ط¨ط§ظ†طھط¸ط§ط± ط§ظ„ظ‚ط¨ظˆظ„ ط£ظˆ ط§ظ„ط±ظپط¶"
            ),
            color=discord.Color.gold(),
            timestamp=now_utc(),
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="ط§ظ„ط¹ط¶ظˆ", value=message.author.mention, inline=True)
        embed.add_field(name="ط§ظ„ظ†ظ‚ط§ط·", value=f"`{IMAGE_POINTS}`", inline=True)
        apply_guild_brand(embed, message.guild)
        await message.channel.send(content=message.author.mention, embed=embed, view=ImageReviewView(message.author.id))
        return
        image_attachment = next((a for a in message.attachments if a.content_type and a.content_type.startswith("image/")), None)
        review_file = None
        image_url = image_attachment.url if image_attachment else None
        if image_attachment:
            extension = Path(image_attachment.filename or "image.png").suffix or ".png"
            filename = f"review_{message.id}{extension}"
            try:
                review_file = await image_attachment.to_file(filename=filename)
                image_url = f"attachment://{filename}"
            except discord.HTTPException:
                image_url = image_attachment.url
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        embed = discord.Embed(
            title="ظ…ط±ط§ط¬ط¹ط© طµظˆط±ط© ظ„ظ„طھظپط§ط¹ظ„",
            description=f"طھظ… ط§ط³طھظ„ط§ظ… طµظˆط±ط© ظ…ظ† {message.author.mention}. ط§ط®طھط± ظ‚ط¨ظˆظ„ ظ„ظ…ظ†ط­ظ‡ `{IMAGE_POINTS}` ظ†ظ‚ط§ط· طھط±ظ‚ظٹط© ط£ظˆ ط±ظپط¶ ظ„ط¥ط±ط³ط§ظ„ ط§ظ„ط³ط¨ط¨ ظ„ظ‡ ط¨ط§ظ„ط®ط§طµ.",
            color=discord.Color.blurple(),
            timestamp=now_utc(),
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        if image_url:
            embed.set_image(url=image_url)
        if review_file:
            await message.channel.send(embed=embed, view=ImageReviewView(message.author.id), file=review_file)
        else:
            await message.channel.send(embed=embed, view=ImageReviewView(message.author.id))
        return

    if message.channel.id in TEXT_POINTS_BLOCKED_CHANNELS:
        return
    if await check_spam(message):
        return
    if not should_award_text_points(message.author.id):
        return
    amount = DOUBLE_TEXT_POINTS if double_active() else TEXT_POINTS
    change_points_value(POINT_FILE, message.author.id, amount)
    change_points_value(REQUIRE_FILE, message.author.id, amount)


async def handle_protection(message: discord.Message) -> bool:
    if message.channel.id != HACKED_PROTECTION_CHANNEL:
        return False
    if not isinstance(message.author, discord.Member):
        return False
    if is_admin(message.author) or has_any_role(message.author, POINT_ROLES | IMAGE_REVIEW_ROLES | PROMOTION_REVIEW_ROLES):
        return False

    until = now_utc() + datetime.timedelta(days=PROTECTION_TIMEOUT_DAYS)
    try:
        await message.author.timeout(until, reason="ظ†ط¸ط§ظ… ط§ظ„ط­ظ…ط§ظٹط©: ط¥ط±ط³ط§ظ„ ظپظٹ ط±ظˆظ… ظ…ط­ظ…ظٹ")
    except discord.Forbidden:
        pass
    except discord.HTTPException:
        pass

    try:
        await message.delete()
    except discord.HTTPException:
        pass

    return True


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if not is_points_member(member):
        return
    uid = str(member.id)
    if before.channel is None and after.channel is not None:
        voice_times[uid] = now_utc()
    elif before.channel is not None and after.channel is None:
        voice_times.pop(uid, None)


@tasks.loop(minutes=5)
async def award_voice_points():
    current_time = now_utc()
    amount = DOUBLE_VOICE_POINTS_EVERY_10_MINUTES if double_active() else VOICE_POINTS_EVERY_10_MINUTES
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            for member in channel.members:
                if not is_points_member(member):
                    continue
                uid = str(member.id)
                if uid not in voice_times:
                    voice_times[uid] = current_time
                    continue
                elapsed = (current_time - voice_times[uid]).total_seconds() / 60
                count = int(elapsed // 10)
                if count <= 0:
                    continue
                total_amount = amount * count
                change_points_value(POINT_FILE, member.id, total_amount)
                change_points_value(REQUIRE_FILE, member.id, total_amount)
                voice_times[uid] += datetime.timedelta(minutes=10 * count)


# =========================
# COMMANDS
# =========================

@bot.command(name="طھظپط§ط¹ظ„")
async def show_points(ctx: commands.Context):
    total, req = get_points(ctx.author.id)
    embed = discord.Embed(title="ظ…ظ„ظپ ط§ظ„طھظپط§ط¹ظ„ ط§ظ„ط¥ط¯ط§ط±ظٹ", description=f"ظ…ظ„ط®طµ ظ†ظ‚ط§ط· {ctx.author.mention}.", color=discord.Color.blue(), timestamp=now_utc())
    embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھظپط§ط¹ظ„", value=f"`{total}`", inline=True)
    embed.add_field(name="ظ†ظ‚ط§ط· ط§ظ„طھط±ظ‚ظٹط©", value=f"`{req}`", inline=True)
    embed.add_field(name="ط­ط§ظ„ط© ط§ظ„ط¯ط¨ظ„", value="`ظ…ظپط¹ظ„`" if double_active() else "`ظ…ط؛ظ„ظ‚`", inline=True)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    icon_url = get_guild_icon_url(ctx.guild)
    if icon_url:
        embed.set_author(name=ctx.guild.name, icon_url=icon_url)
    await ctx.send(embed=embed)


@bot.command(name="top")
async def top_points_command(ctx: commands.Context):
    if ctx.channel.id == INTERACTION_PANEL_CHANNEL:
        await send_temporary_top(ctx.channel, ctx.guild)


@bot.command(name="double")
async def double_on(ctx: commands.Context):
    if is_admin(ctx.author):
        save_json(DOUBLE_FILE, {"active": True})
        await ctx.send("ًں”¥ طھظ… طھظپط¹ظٹظ„ ط§ظ„ط¯ط¨ظ„.")


@bot.command(name="doubleoff")
async def double_off(ctx: commands.Context):
    if is_admin(ctx.author):
        save_json(DOUBLE_FILE, {"active": False})
        await ctx.send("â‌„ï¸ڈ طھظ… ط¥ظٹظ‚ط§ظپ ط§ظ„ط¯ط¨ظ„.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return
    if await handle_protection(message):
        return
    if message.channel.id == PROMOTION_REQUEST_CHANNEL and message.content.strip() == "طھط±ظ‚ظٹط©":
        await send_promotion_request(message)
        return
    await handle_message_points(message)
    await bot.process_commands(message)


@bot.event
async def on_ready():
    global views_registered
    if not views_registered:
        bot.add_view(InteractionPanel())
        bot.add_view(PromotionRequestPanel())
        views_registered = True
    if not award_voice_points.is_running():
        award_voice_points.start()
    print(f"Logged in as {bot.user}")


keep_alive()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


async def run_discord_bot():
    while True:
        try:
            await bot.start(DISCORD_TOKEN)
            break
        except discord.HTTPException as exc:
            if getattr(exc, "status", None) == 429:
                print(f"Discord rate limit while logging in. Retrying in {LOGIN_RETRY_SECONDS} seconds.")
                await asyncio.sleep(LOGIN_RETRY_SECONDS)
                continue
            raise


if not DISCORD_TOKEN:
    print("DISCORD_TOKEN is missing")
else:
    asyncio.run(run_discord_bot())
