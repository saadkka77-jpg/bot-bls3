import json
import logging
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands


DATA_FILE = Path("economy_data.json")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

ALLOWED_GUILD_ID = 1498037416672493829
EVENT_CHANNEL_ID = 1498037576538259556

START_MONEY = 3000
INVEST_COOLDOWN = 180
TRADE_COOLDOWN = 180
STEAL_COOLDOWN = 300
DAILY_COOLDOWN = 86400
ROULETTE_COOLDOWN = 600

COLOR_PRIMARY = 0x2B2D31
COLOR_SUCCESS = 0x57F287
COLOR_DANGER = 0xED4245
COLOR_WARNING = 0xFEE75C
COLOR_INFO = 0x5865F2
COLOR_GOLD = 0xF1C40F

SHOP_ITEMS = {
    "ذهب": {"key": "gold", "buy_price": 1200, "sell_price": 850, "icon": "🥇"},
    "الماس": {"key": "diamonds", "buy_price": 2500, "sell_price": 1800, "icon": "💎"},
    "ارض": {"key": "lands", "buy_price": 6000, "sell_price": 4500, "icon": "🏝️"},
    "أرض": {"key": "lands", "buy_price": 6000, "sell_price": 4500, "icon": "🏝️"},
}

EVENT_REWARD_TYPES = {
    "money": {"label": "فلوس", "key": "money", "icon": "💵", "color": COLOR_SUCCESS},
    "gold": {"label": "ذهب", "key": "gold", "icon": "🥇", "color": COLOR_GOLD},
    "diamonds": {"label": "ألماس", "key": "diamonds", "icon": "💎", "color": COLOR_INFO},
    "lands": {"label": "أراضي", "key": "lands", "icon": "🏝️", "color": 0x3BA55D},
}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bls-economy")


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="", intents=intents, help_command=None)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_web_server() -> None:
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


def ensure_token() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing in environment variables.")


def load_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {
            "users": {},
            "active_event": None,
            "panel_message_id": None,
        }

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        logger.exception("Failed to load economy data file.")
        return {
            "users": {},
            "active_event": None,
            "panel_message_id": None,
        }

    data.setdefault("users", {})
    data.setdefault("active_event", None)
    data.setdefault("panel_message_id", None)
    return data


def save_data() -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data_store, file, ensure_ascii=False, indent=2)


data_store = load_data()


def create_user(user_id: int) -> dict[str, Any]:
    return {
        "userId": str(user_id),
        "money": START_MONEY,
        "gold": 0,
        "diamonds": 0,
        "lands": 0,
        "lastInvest": 0,
        "lastTrade": 0,
        "lastSteal": 0,
        "lastDaily": 0,
        "lastRoulette": 0,
    }


def get_user(user_id: int) -> dict[str, Any]:
    key = str(user_id)
    if key not in data_store["users"]:
        data_store["users"][key] = create_user(user_id)
        save_data()
    return data_store["users"][key]


def save_user(user: dict[str, Any]) -> None:
    data_store["users"][user["userId"]] = user
    save_data()


def is_allowed_message(message: discord.Message) -> bool:
    return message.guild is not None and message.guild.id == ALLOWED_GUILD_ID


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


def base_embed(color: int = COLOR_PRIMARY) -> discord.Embed:
    embed = discord.Embed(color=color)
    embed.set_footer(text="BLS Economy")
    return embed


def card_embed(title: str, value: str, color: int, icon: str) -> discord.Embed:
    embed = base_embed(color)
    embed.add_field(name=f"{icon} {title}", value=f"```{value}```", inline=False)
    return embed


def info_embed(title: str, description: str, color: int = COLOR_PRIMARY) -> discord.Embed:
    embed = base_embed(color)
    embed.title = title
    embed.description = description
    return embed


def dashboard_embed(user: dict[str, Any], member: discord.abc.User) -> discord.Embed:
    embed = base_embed(COLOR_INFO)
    embed.title = "لوحة ممتلكاتك"
    embed.description = (
        f"💵 المال: `{user['money']}`\n"
        f"🥇 الذهب: `{user['gold']}`\n"
        f"💎 الألماس: `{user['diamonds']}`\n"
        f"🏝️ الأراضي: `{user['lands']}`"
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    return embed


def shop_embed() -> discord.Embed:
    embed = base_embed(COLOR_GOLD)
    embed.title = "المتجر"
    lines = []
    for name, item in SHOP_ITEMS.items():
        if name != "أرض":
            lines.append(
                f"{item['icon']} {name}: شراء `{item['buy_price']}` | بيع `{item['sell_price']}`"
            )
    embed.description = "\n".join(lines)
    return embed


def cooldown_left(last_time: float, cooldown: int) -> int:
    return max(0, int(cooldown - (time.time() - last_time)))


def format_wait(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{minutes} دقيقة و {secs} ثانية"
    return f"{secs} ثانية"


def parse_amount(raw: str) -> int:
    if not raw.isdigit():
        raise ValueError("الكمية لازم تكون رقم صحيح.")
    amount = int(raw)
    if amount <= 0:
        raise ValueError("الكمية لازم تكون أكبر من 0.")
    return amount


def parse_buy_sell_item(raw_name: str) -> dict[str, Any]:
    item = SHOP_ITEMS.get(raw_name)
    if not item:
        raise ValueError("العنصر غير معروف. استخدم: ذهب، الماس، ارض.")
    return item


def add_asset(user: dict[str, Any], key: str, amount: int) -> None:
    user[key] += amount


def get_active_event() -> dict[str, Any] | None:
    event = data_store.get("active_event")
    if not event:
        return None
    if event.get("remaining", 0) <= 0:
        data_store["active_event"] = None
        save_data()
        return None
    return event


def set_active_event(event: dict[str, Any] | None) -> None:
    data_store["active_event"] = event
    save_data()


def event_post_embed(event: dict[str, Any], creator_name: str) -> discord.Embed:
    reward = EVENT_REWARD_TYPES[event["reward_type"]]
    embed = base_embed(reward["color"])
    embed.title = "حدث خاص"
    embed.description = (
        f"{reward['icon']} الجائزة: `{event['amount']}` {reward['label']}\n"
        f"🎟️ عدد المستفيدين المتبقي: `{event['remaining']}`\n"
        f"🛡️ الحدث حصري ومنشور من الإدارة\n"
        f"👤 بواسطة: `{creator_name}`"
    )
    return embed


def admin_panel_embed() -> discord.Embed:
    embed = base_embed(COLOR_INFO)
    embed.title = "لوحة الإدارة الخاصة"
    embed.description = (
        "استخدم الأزرار بالأسفل لإنشاء أحداث حصرية داخل هذا الروم.\n"
        "كل زر يفتح نافذة تحدد فيها كمية الجائزة وعدد الأشخاص المسموح لهم بالاستلام."
    )
    return embed


async def update_panel_message(channel: discord.TextChannel) -> None:
    panel_view = AdminPanelView()
    panel_id = data_store.get("panel_message_id")

    if panel_id:
        try:
            message = await channel.fetch_message(panel_id)
            await message.edit(embed=admin_panel_embed(), view=panel_view)
            return
        except discord.NotFound:
            logger.info("Admin panel message not found, creating a new one.")
        except discord.HTTPException:
            logger.exception("Failed to update admin panel message.")

    message = await channel.send(embed=admin_panel_embed(), view=panel_view)
    data_store["panel_message_id"] = message.id
    save_data()


class ClaimEventView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام الحدث", style=discord.ButtonStyle.success, custom_id="claim_event")
    async def claim_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.guild is None or interaction.guild.id != ALLOWED_GUILD_ID:
            await interaction.response.send_message("هذا الزر غير متاح هنا.", ephemeral=True)
            return

        event = get_active_event()
        if not event:
            await interaction.response.send_message("لا يوجد حدث نشط الآن.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if user_id in event["claimed_by"]:
            await interaction.response.send_message("أنت أخذت الحدث بالفعل.", ephemeral=True)
            return

        user = get_user(interaction.user.id)
        add_asset(user, EVENT_REWARD_TYPES[event["reward_type"]]["key"], event["amount"])
        save_user(user)

        event["claimed_by"].append(user_id)
        event["remaining"] -= 1

        if event["remaining"] <= 0:
            set_active_event(None)
            await interaction.response.edit_message(
                embed=info_embed("انتهى الحدث", "تم استلام جميع الجوائز.", COLOR_DANGER),
                view=None,
            )
            await interaction.followup.send(
                embed=card_embed(
                    "استلمت جائزتك",
                    f"{event['amount']} {EVENT_REWARD_TYPES[event['reward_type']]['label']}",
                    EVENT_REWARD_TYPES[event["reward_type"]]["color"],
                    EVENT_REWARD_TYPES[event["reward_type"]]["icon"],
                ),
                ephemeral=True,
            )
            return

        set_active_event(event)
        await interaction.response.edit_message(
            embed=event_post_embed(event, event["creator_name"]),
            view=ClaimEventView(),
        )
        await interaction.followup.send(
            embed=card_embed(
                "استلمت جائزتك",
                f"{event['amount']} {EVENT_REWARD_TYPES[event['reward_type']]['label']}",
                EVENT_REWARD_TYPES[event["reward_type"]]["color"],
                EVENT_REWARD_TYPES[event["reward_type"]]["icon"],
            ),
            ephemeral=True,
        )


class EventCreateModal(discord.ui.Modal):
    def __init__(self, reward_type: str) -> None:
        reward = EVENT_REWARD_TYPES[reward_type]
        super().__init__(title=f"إنشاء حدث {reward['label']}")
        self.reward_type = reward_type
        self.reward_amount = discord.ui.TextInput(
            label="كمية الجائزة لكل شخص",
            placeholder="مثال: 500",
            max_length=10,
        )
        self.claim_limit = discord.ui.TextInput(
            label="عدد الأشخاص المسموح لهم",
            placeholder="مثال: 10",
            max_length=10,
        )
        self.add_item(self.reward_amount)
        self.add_item(self.claim_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or interaction.guild.id != ALLOWED_GUILD_ID:
            await interaction.response.send_message("هذا النموذج غير متاح هنا.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_admin(member):
            await interaction.response.send_message("هذه اللوحة للإدارة فقط.", ephemeral=True)
            return

        try:
            amount = parse_amount(str(self.reward_amount))
            limit = parse_amount(str(self.claim_limit))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        event = {
            "reward_type": self.reward_type,
            "amount": amount,
            "remaining": limit,
            "claimed_by": [],
            "creator_id": member.id,
            "creator_name": str(member),
            "created_at": int(time.time()),
        }
        set_active_event(event)

        channel = interaction.guild.get_channel(EVENT_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("ما قدرت أوصل لروم الأحداث.", ephemeral=True)
            return

        await channel.send(embed=event_post_embed(event, str(member)), view=ClaimEventView())
        await interaction.response.send_message("تم نشر الحدث الخاص بنجاح.", ephemeral=True)


class AdminPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def open_modal(
        self, interaction: discord.Interaction, reward_type: str
    ) -> None:
        if not interaction.guild or interaction.guild.id != ALLOWED_GUILD_ID:
            await interaction.response.send_message("هذا الزر غير متاح هنا.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_admin(member):
            await interaction.response.send_message("هذه اللوحة للإدارة فقط.", ephemeral=True)
            return

        await interaction.response.send_modal(EventCreateModal(reward_type))

    @discord.ui.button(label="توزيع فلوس", style=discord.ButtonStyle.success, custom_id="admin_money_event")
    async def money_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "money")

    @discord.ui.button(label="توزيع ذهب", style=discord.ButtonStyle.secondary, custom_id="admin_gold_event")
    async def gold_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "gold")

    @discord.ui.button(label="توزيع ألماس", style=discord.ButtonStyle.primary, custom_id="admin_diamond_event")
    async def diamond_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "diamonds")

    @discord.ui.button(label="توزيع أراضي", style=discord.ButtonStyle.danger, custom_id="admin_land_event")
    async def land_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "lands")


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)
    bot.add_view(AdminPanelView())
    bot.add_view(ClaimEventView())

    guild = bot.get_guild(ALLOWED_GUILD_ID)
    if not guild:
        logger.warning("Allowed guild not found.")
        return

    channel = guild.get_channel(EVENT_CHANNEL_ID)
    if isinstance(channel, discord.TextChannel):
        try:
            await update_panel_message(channel)
        except discord.HTTPException:
            logger.exception("Failed to ensure admin panel message.")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not is_allowed_message(message):
        return

    content = message.content.strip()
    if not content:
        return

    args = content.split()
    cmd = args[0].lower()
    user = get_user(message.author.id)

    try:
        if cmd in {"ممتلكاتي", "رصيدي", "فلوسي"}:
            await message.reply(embed=dashboard_embed(user, message.author))
            return

        if cmd == "اوامر":
            embed = base_embed(COLOR_INFO)
            embed.title = "قائمة الأوامر"
            embed.description = (
                "`ممتلكاتي` أو `رصيدي`\n"
                "`راتب`\n"
                "`استثمار <مبلغ/كل>`\n"
                "`تداول <مبلغ/كل>`\n"
                "`روليت`\n"
                "`تحويل @شخص <مبلغ>`\n"
                "`سرقة @شخص`\n"
                "`توب`\n"
                "`شراء`\n"
                "`شراء <العنصر> <الكمية>`\n"
                "`بيع <العنصر> <الكمية/كل>`\n"
                "`اوامر`\n"
                "أوامر الإدارة: `لوحة الادارة` و `حدث <فلوس|ذهب|الماس|اراضي> <كمية> <عدد>`"
            )
            await message.reply(embed=embed)
            return

        if cmd == "شراء" and len(args) == 1:
            await message.reply(embed=shop_embed())
            return

        if cmd == "راتب":
            left = cooldown_left(user["lastDaily"], DAILY_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed(
                        "انتظر شوي",
                        f"تقدر تستلم راتبك بعد `{format_wait(left)}`.",
                        COLOR_WARNING,
                    )
                )
                return

            salary = random.randint(350, 900)
            user["money"] += salary
            user["lastDaily"] = time.time()
            save_user(user)
            await message.reply(embed=card_embed("راتبك", str(salary), COLOR_WARNING, "💰"))
            return

        if cmd == "استثمار":
            left = cooldown_left(user["lastInvest"], INVEST_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على الاستثمار.", COLOR_WARNING)
                )
                return

            if len(args) < 2:
                raise ValueError("اكتب: استثمار <مبلغ/كل>")

            amount = user["money"] if args[1] == "كل" else parse_amount(args[1])
            if amount > user["money"]:
                raise ValueError("ما عندك المبلغ المطلوب.")

            user["money"] -= amount
            user["lastInvest"] = time.time()
            change = int(amount * random.uniform(0.08, 0.30))

            if random.random() < 0.55:
                user["money"] += amount + change
                save_user(user)
                await message.reply(embed=card_embed("ربح الاستثمار", f"+{change}", COLOR_SUCCESS, "📈"))
            else:
                save_user(user)
                await message.reply(embed=card_embed("خسارة الاستثمار", f"-{change}", COLOR_DANGER, "📉"))
            return

        if cmd == "تداول":
            left = cooldown_left(user["lastTrade"], TRADE_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على التداول.", COLOR_WARNING)
                )
                return

            if len(args) < 2:
                raise ValueError("اكتب: تداول <مبلغ/كل>")

            amount = user["money"] if args[1] == "كل" else parse_amount(args[1])
            if amount > user["money"]:
                raise ValueError("ما عندك المبلغ المطلوب.")

            user["money"] -= amount
            user["lastTrade"] = time.time()
            change = int(amount * random.uniform(0.10, 0.40))

            if random.random() < 0.50:
                user["money"] += amount + change
                save_user(user)
                await message.reply(embed=card_embed("ربح التداول", f"+{change}", COLOR_SUCCESS, "💹"))
            else:
                save_user(user)
                await message.reply(embed=card_embed("خسارة التداول", f"-{change}", COLOR_DANGER, "📉"))
            return

        if cmd == "روليت":
            left = cooldown_left(user["lastRoulette"], ROULETTE_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر", f"الروليت كل 10 دقائق. باقي `{format_wait(left)}`.", COLOR_WARNING)
                )
                return

            user["lastRoulette"] = time.time()
            reward_type = random.choice(["money", "gold", "diamonds", "lands"])
            if reward_type == "money":
                amount = random.randint(100, 450)
            elif reward_type == "gold":
                amount = random.randint(1, 4)
            elif reward_type == "diamonds":
                amount = random.randint(1, 2)
            else:
                amount = 1

            add_asset(user, EVENT_REWARD_TYPES[reward_type]["key"], amount)
            save_user(user)
            reward = EVENT_REWARD_TYPES[reward_type]
            await message.reply(
                embed=card_embed("جائزة الروليت", f"{amount} {reward['label']}", reward["color"], reward["icon"])
            )
            return

        if cmd == "تحويل":
            if len(args) < 3 or not message.mentions:
                raise ValueError("اكتب: تحويل @شخص <مبلغ>")

            target = message.mentions[0]
            if target.bot:
                raise ValueError("ما تقدر تحول لبوت.")
            if target.id == message.author.id:
                raise ValueError("ما تقدر تحول لنفسك.")

            amount = parse_amount(args[-1])
            if amount > user["money"]:
                raise ValueError("رصيدك ما يكفي.")

            receiver = get_user(target.id)
            user["money"] -= amount
            receiver["money"] += amount
            save_user(user)
            save_user(receiver)
            await message.reply(
                embed=card_embed("تم التحويل", f"{amount} إلى {target.display_name}", COLOR_SUCCESS, "💸")
            )
            return

        if cmd == "سرقة":
            if not message.mentions:
                raise ValueError("اكتب: سرقة @شخص")

            target = message.mentions[0]
            if target.bot:
                raise ValueError("ما تقدر تسرق بوت.")
            if target.id == message.author.id:
                raise ValueError("ما تقدر تسرق نفسك.")

            left = cooldown_left(user["lastSteal"], STEAL_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على السرقة.", COLOR_WARNING)
                )
                return

            victim = get_user(target.id)
            if victim["money"] <= 0:
                raise ValueError("الهدف ما عنده فلوس.")

            stolen = random.randint(1, max(1, min(victim["money"], 1200)))
            victim["money"] -= stolen
            user["money"] += stolen
            user["lastSteal"] = time.time()
            save_user(victim)
            save_user(user)
            await message.reply(
                content=f"🚨 {target.mention}",
                embed=card_embed("المبلغ المسروق", str(stolen), 0xFF8C00, "🕵️"),
            )
            return

        if cmd == "توب":
            all_users = list(data_store["users"].values())
            ranked = sorted(
                all_users,
                key=lambda item: item["money"] + (item["gold"] * 850) + (item["diamonds"] * 1800) + (item["lands"] * 4500),
                reverse=True,
            )[:10]

            lines = []
            for index, ranked_user in enumerate(ranked, start=1):
                member = message.guild.get_member(int(ranked_user["userId"]))
                name = member.display_name if member else f"User {ranked_user['userId']}"
                total_value = (
                    ranked_user["money"]
                    + ranked_user["gold"] * 850
                    + ranked_user["diamonds"] * 1800
                    + ranked_user["lands"] * 4500
                )
                lines.append(f"`#{index}` {name} - `{total_value}`")

            embed = base_embed(COLOR_GOLD)
            embed.title = "أغنى اللاعبين"
            embed.description = "\n".join(lines) if lines else "لا يوجد بيانات بعد."
            await message.reply(embed=embed)
            return

        if cmd == "شراء":
            if len(args) < 3:
                raise ValueError("اكتب: شراء <العنصر> <الكمية>")

            item = parse_buy_sell_item(args[1])
            quantity = parse_amount(args[2])
            total_price = item["buy_price"] * quantity

            if user["money"] < total_price:
                raise ValueError("فلوسك ما تكفي للشراء.")

            user["money"] -= total_price
            user[item["key"]] += quantity
            save_user(user)
            await message.reply(
                embed=card_embed(
                    "تم الشراء",
                    f"{quantity} {args[1]} مقابل {total_price}",
                    COLOR_SUCCESS,
                    item["icon"],
                )
            )
            return

        if cmd == "بيع":
            if len(args) < 3:
                raise ValueError("اكتب: بيع <العنصر> <الكمية/كل>")

            item = parse_buy_sell_item(args[1])
            owned = user[item["key"]]
            quantity = owned if args[2] == "كل" else parse_amount(args[2])
            if quantity > owned:
                raise ValueError("أنت ما تملك هذه الكمية.")

            total_price = item["sell_price"] * quantity
            user[item["key"]] -= quantity
            user["money"] += total_price
            save_user(user)
            await message.reply(
                embed=card_embed(
                    "تم البيع",
                    f"{quantity} {args[1]} مقابل {total_price}",
                    COLOR_WARNING,
                    item["icon"],
                )
            )
            return

        if cmd == "لوحة" and len(args) > 1 and args[1] == "الادارة":
            if not isinstance(message.author, discord.Member) or not is_admin(message.author):
                raise ValueError("هذا الأمر للإدارة فقط.")
            if message.channel.id != EVENT_CHANNEL_ID:
                raise ValueError(f"استخدم هذا الأمر داخل روم الإدارة: {EVENT_CHANNEL_ID}")
            await update_panel_message(message.channel)
            await message.reply(embed=info_embed("تم", "تم تحديث لوحة الإدارة.", COLOR_SUCCESS))
            return

        if cmd == "حدث":
            if not isinstance(message.author, discord.Member) or not is_admin(message.author):
                raise ValueError("هذا الأمر للإدارة فقط.")
            if len(args) < 4:
                raise ValueError("اكتب: حدث <فلوس|ذهب|الماس|اراضي> <كمية> <عدد>")

            type_map = {
                "فلوس": "money",
                "ذهب": "gold",
                "الماس": "diamonds",
                "ألماس": "diamonds",
                "اراضي": "lands",
                "أراضي": "lands",
            }
            reward_type = type_map.get(args[1])
            if not reward_type:
                raise ValueError("نوع الحدث غير معروف.")

            amount = parse_amount(args[2])
            limit = parse_amount(args[3])
            event = {
                "reward_type": reward_type,
                "amount": amount,
                "remaining": limit,
                "claimed_by": [],
                "creator_id": message.author.id,
                "creator_name": str(message.author),
                "created_at": int(time.time()),
            }
            set_active_event(event)

            channel = message.guild.get_channel(EVENT_CHANNEL_ID)
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("ما قدرت أوصل لروم الأحداث.")

            await channel.send(embed=event_post_embed(event, str(message.author)), view=ClaimEventView())
            await message.reply(embed=info_embed("تم", "تم نشر الحدث الخاص.", COLOR_SUCCESS))
            return

    except ValueError as exc:
        await message.reply(embed=info_embed("خطأ", str(exc), COLOR_DANGER))
        return
    except Exception:
        logger.exception("Unexpected error while processing a message.")
        await message.reply(
            embed=info_embed("خطأ", "صار خطأ غير متوقع، حاول مرة ثانية.", COLOR_DANGER)
        )
        return


threading.Thread(target=run_web_server, daemon=True).start()
ensure_token()
bot.run(DISCORD_TOKEN, log_handler=None)
