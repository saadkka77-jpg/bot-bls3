import asyncio
import json
import logging
import math
import os
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands


DATA_FILE = Path("economy_data.json")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

ADMIN_PANEL_CHANNEL_ID = 1498037576538259556
EVENT_PUBLIC_CHANNEL_ID = 1498037416672493829
ADMIN_ROLE_ID = 1478970736717598840

START_MONEY = 3000
INVEST_COOLDOWN = 180
TRADE_COOLDOWN = 180
STEAL_COOLDOWN = 300
STEAL_PROTECTED_COST = 3500
DAILY_COOLDOWN = 86400
ROULETTE_COOLDOWN = 600
EVENT_DURATION_SECONDS = 300
PROTECTION_COST = 10000
PROTECTION_DURATION_SECONDS = 7200

STOCK_UPDATE_SECONDS = 180
PROPERTY_UPDATE_SECONDS = 600
AUTO_AUCTION_INTERVAL_SECONDS = 900
HIDDEN_AUCTION_INTERVAL_SECONDS = 900
AUCTION_DURATION_SECONDS = 300
AUCTION_COUNTDOWN_SECONDS = 5
AUCTION_BID_CONFIRM_DELETE_AFTER = 60
COMPANY_TICK_SECONDS = 900
COMPANY_PRICE = 250000
LOAN_MAX_AMOUNT = 20000
LOAN_MIN_PAYMENT = 1000
LOAN_DURATION_SECONDS = 3600
LOAN_LATE_FEE = 5000

COLOR_PRIMARY = 0x1E2124
COLOR_SUCCESS = 0x57F287
COLOR_DANGER = 0xED4245
COLOR_WARNING = 0xFEE75C
COLOR_INFO = 0x5865F2
COLOR_GOLD = 0xF1C40F
COLOR_LAND = 0x3BA55D
COLOR_STOCK = 0x11806A
COLOR_SECRET = 0x2F3136

ITEM_DEFINITIONS = {
    "gold": {
        "label": "ذهب",
        "icon": "🥇",
        "base_buy": 1200,
        "base_sell": 850,
        "min_buy": 500,
        "step": 100,
        "auction_quantity": 3,
        "color": COLOR_GOLD,
        "update_seconds": PROPERTY_UPDATE_SECONDS,
    },
    "diamonds": {
        "label": "ألماس",
        "icon": "💎",
        "base_buy": 2500,
        "base_sell": 1800,
        "min_buy": 1000,
        "step": 200,
        "auction_quantity": 2,
        "color": COLOR_INFO,
        "update_seconds": PROPERTY_UPDATE_SECONDS,
    },
    "lands": {
        "label": "أرض",
        "icon": "🏝️",
        "base_buy": 6000,
        "base_sell": 4500,
        "min_buy": 2500,
        "step": 500,
        "auction_quantity": 1,
        "color": COLOR_LAND,
        "update_seconds": PROPERTY_UPDATE_SECONDS,
    },
    "stocks": {
        "label": "أسهم",
        "icon": "📈",
        "base_buy": 1500,
        "base_sell": 1300,
        "min_buy": 700,
        "step": 100,
        "auction_quantity": 5,
        "color": COLOR_STOCK,
        "update_seconds": STOCK_UPDATE_SECONDS,
    },
}

ITEM_ALIASES = {
    "ذهب": "gold",
    "gold": "gold",
    "الماس": "diamonds",
    "ألماس": "diamonds",
    "diamond": "diamonds",
    "diamonds": "diamonds",
    "ارض": "lands",
    "أرض": "lands",
    "land": "lands",
    "lands": "lands",
    "سهم": "stocks",
    "اسهم": "stocks",
    "أسهم": "stocks",
    "stock": "stocks",
    "stocks": "stocks",
    "شركة": "companies",
    "شركه": "companies",
    "company": "companies",
    "companies": "companies",
}

EVENT_REWARD_TYPES = {
    "money": {"label": "فلوس", "key": "money", "icon": "💵", "color": COLOR_SUCCESS},
    "gold": {"label": "ذهب", "key": "gold", "icon": "🥇", "color": COLOR_GOLD},
    "diamonds": {"label": "ألماس", "key": "diamonds", "icon": "💎", "color": COLOR_INFO},
    "lands": {"label": "أراضي", "key": "lands", "icon": "🏝️", "color": COLOR_LAND},
    "stocks": {"label": "أسهم", "key": "stocks", "icon": "📈", "color": COLOR_STOCK},
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
event_cleanup_task: asyncio.Task | None = None
background_task: asyncio.Task | None = None
auto_save_task: asyncio.Task | None = None
views_registered = False
dirty_data = False


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


def mark_dirty() -> None:
    global dirty_data
    dirty_data = True


def build_default_prices() -> dict[str, dict[str, int]]:
    prices: dict[str, dict[str, int]] = {}
    for key, item in ITEM_DEFINITIONS.items():
        prices[key] = {
            "buy_price": item["base_buy"],
            "sell_price": item["base_sell"],
            "last_update": 0,
        }
    return prices


def next_timestamp(seconds: int) -> int:
    return int(time.time()) + seconds


def default_system_settings() -> dict[str, Any]:
    return {
        "auto_auction_enabled": True,
        "hidden_auction_enabled": False,
        "next_auto_auction_at": next_timestamp(AUTO_AUCTION_INTERVAL_SECONDS),
        "next_hidden_auction_at": next_timestamp(HIDDEN_AUCTION_INTERVAL_SECONDS),
    }


def load_data() -> dict[str, Any]:
    defaults = {
        "users": {},
        "active_event": None,
        "panel_message_id": None,
        "price_panel_message_id": None,
        "prices": build_default_prices(),
        "auctions": {},
        "systems": default_system_settings(),
    }

    if not DATA_FILE.exists():
        return defaults

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        logger.exception("Failed to load economy data file.")
        return defaults

    for key, value in defaults.items():
        data.setdefault(key, value)

    data["systems"] = {**default_system_settings(), **data.get("systems", {})}

    for item_key, item_prices in build_default_prices().items():
        existing = data["prices"].setdefault(item_key, item_prices)
        existing.setdefault("buy_price", item_prices["buy_price"])
        existing.setdefault("sell_price", item_prices["sell_price"])
        existing.setdefault("last_update", 0)

    return data


def save_data(force: bool = False) -> None:
    global dirty_data
    if not force and not dirty_data:
        return
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data_store, file, ensure_ascii=False, indent=2)
    dirty_data = False


async def auto_save_loop() -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            save_data()
        except Exception as exc:
            logger.error("Auto save failed: %s", exc)
        await asyncio.sleep(60)


data_store = load_data()


def ensure_state() -> None:
    data_store.setdefault("users", {})
    data_store.setdefault("active_event", None)
    data_store.setdefault("panel_message_id", None)
    data_store.setdefault("price_panel_message_id", None)
    data_store.setdefault("prices", build_default_prices())
    data_store.setdefault("auctions", {})
    data_store["systems"] = {**default_system_settings(), **data_store.get("systems", {})}

    for item_key, item_prices in build_default_prices().items():
        current = data_store["prices"].setdefault(item_key, item_prices)
        current.setdefault("buy_price", item_prices["buy_price"])
        current.setdefault("sell_price", item_prices["sell_price"])
        current.setdefault("last_update", 0)


ensure_state()


def create_user(user_id: int) -> dict[str, Any]:
    now = time.time()
    return {
        "userId": str(user_id),
        "money": START_MONEY,
        "gold": 0,
        "diamonds": 0,
        "lands": 0,
        "stocks": 0,
        "companies": 0,
        "lastInvest": 0,
        "lastTrade": 0,
        "lastSteal": 0,
        "lastDaily": 0,
        "lastRoulette": 0,
        "protectionUntil": 0,
        "loan": None,
        "lastCompanyTick": now,
    }


def reset_user_data(user: dict[str, Any]) -> None:
    user["money"] = START_MONEY
    user["gold"] = 0
    user["diamonds"] = 0
    user["lands"] = 0
    user["stocks"] = 0
    user["companies"] = 0
    user["lastInvest"] = 0
    user["lastTrade"] = 0
    user["lastSteal"] = 0
    user["lastDaily"] = 0
    user["lastRoulette"] = 0
    user["protectionUntil"] = 0
    user["loan"] = None
    user["lastCompanyTick"] = time.time()


def get_user(user_id: int) -> dict[str, Any]:
    key = str(user_id)
    if key not in data_store["users"]:
        data_store["users"][key] = create_user(user_id)
        mark_dirty()
    user = data_store["users"][key]
    user.setdefault("stocks", 0)
    user.setdefault("companies", 0)
    user.setdefault("loan", None)
    user.setdefault("lastCompanyTick", time.time())
    return user


def save_user(user: dict[str, Any]) -> None:
    data_store["users"][user["userId"]] = user
    mark_dirty()


def has_admin_access(member: discord.Member) -> bool:
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)


def base_embed(color: int = COLOR_PRIMARY) -> discord.Embed:
    embed = discord.Embed(color=color)
    embed.set_footer(text="BLS Economy")
    return embed


def info_embed(title: str, description: str, color: int = COLOR_PRIMARY) -> discord.Embed:
    embed = base_embed(color)
    embed.title = title
    embed.description = description
    return embed


def card_embed(title: str, value: str, color: int, icon: str) -> discord.Embed:
    embed = base_embed(color)
    embed.add_field(name=f"{icon} {title}", value=f"```{value}```", inline=False)
    return embed


def format_wait(seconds: int) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes:
        parts.append(f"{minutes} دقيقة")
    if secs or not parts:
        parts.append(f"{secs} ثانية")
    return " و ".join(parts)


def dashboard_embed(user: dict[str, Any], member: discord.abc.User) -> discord.Embed:
    embed = base_embed(COLOR_INFO)
    embed.title = "لوحة ممتلكاتك"
    protection_left = max(0, int(user.get("protectionUntil", 0) - time.time()))
    loan = user.get("loan")
    if loan:
        loan_text = f"`{loan['balance']}` | المتبقي: `{format_wait(int(loan['due_at'] - time.time()))}`"
    elif user["money"] < 0:
        loan_text = f"رصيد سالب `{abs(user['money'])}`"
    else:
        loan_text = "لا يوجد"
    protection_text = "لا توجد حماية" if protection_left <= 0 else f"مفعلة لمدة `{format_wait(protection_left)}`"
    company_hint = "قيمتها تعتمد على الأسهم التي تملكها وقت البيع"
    embed.description = (
        f"💵 المال: `{user['money']}`\n"
        f"🥇 الذهب: `{user['gold']}`\n"
        f"💎 الألماس: `{user['diamonds']}`\n"
        f"🏝️ الأراضي: `{user['lands']}`\n"
        f"📈 الأسهم: `{user['stocks']}`\n"
        f"🏢 الشركات: `{user['companies']}` - {company_hint}\n"
        f"🏦 القرض/الدين: {loan_text}\n"
        f"🛡️ الحماية: {protection_text}"
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    return embed


def get_price(item_key: str) -> dict[str, int]:
    return data_store["prices"][item_key]


def get_current_buy_price(item_key: str) -> int:
    return get_price(item_key)["buy_price"]


def get_current_sell_price(item_key: str) -> int:
    return get_price(item_key)["sell_price"]


def format_prices_lines() -> str:
    lines = []
    for item_key in ("gold", "diamonds", "lands", "stocks"):
        item = ITEM_DEFINITIONS[item_key]
        price = get_price(item_key)
        lines.append(
            f"{item['icon']} {item['label']}: شراء `{price['buy_price']}` | بيع `{price['sell_price']}`"
        )
    return "\n".join(lines)


def shop_embed() -> discord.Embed:
    embed = base_embed(COLOR_GOLD)
    embed.title = "المتجر"
    embed.description = format_prices_lines()
    return embed


def admin_panel_embed() -> discord.Embed:
    systems = data_store["systems"]
    embed = base_embed(COLOR_INFO)
    embed.title = "لوحة الإدارة"
    embed.description = (
        "هذه اللوحة خاصة بالرتبة الإدارية المحددة فقط.\n"
        f"روم التحكم: `{ADMIN_PANEL_CHANNEL_ID}`\n"
        f"روم الأعضاء: `{EVENT_PUBLIC_CHANNEL_ID}`\n"
        f"المزاد التلقائي: `{'شغال' if systems['auto_auction_enabled'] else 'متوقف'}` كل `15 دقيقة`\n"
        f"المزاد المخفي: `{'شغال' if systems['hidden_auction_enabled'] else 'متوقف'}` كل `15 دقيقة`\n"
        "كل المزادات مدتها `5 دقائق` مع عد نهائي عند الإغلاق."
    )
    return embed


def price_panel_embed() -> discord.Embed:
    embed = base_embed(COLOR_GOLD)
    embed.title = "لوحة التحكم بالأسعار"
    embed.description = (
        f"{format_prices_lines()}\n\n"
        "الأسهم تتحرك تلقائيًا كل 3 دقائق، والذهب والألماس والأراضي كل 10 دقائق."
    )
    return embed


def event_post_embed(event: dict[str, Any]) -> discord.Embed:
    reward = EVENT_REWARD_TYPES[event["reward_type"]]
    remaining_time = max(0, int(event["expires_at"] - time.time()))
    embed = base_embed(reward["color"])
    embed.title = "حدث خاص"
    embed.description = (
        f"{reward['icon']} الجائزة لكل شخص: `{event['amount']}` {reward['label']}\n"
        f"🎟️ المقاعد المتبقية: `{event['remaining']}`\n"
        f"⏳ الوقت المتبقي: `{format_wait(remaining_time)}`\n"
        f"👤 المنشئ: `{event['creator_name']}`"
    )
    return embed


def cooldown_left(last_time: float, cooldown: int) -> int:
    return max(0, int(cooldown - (time.time() - last_time)))


def parse_amount(raw: str) -> int:
    if not raw.isdigit():
        raise ValueError("الكمية لازم تكون رقم صحيح.")
    amount = int(raw)
    if amount <= 0:
        raise ValueError("الكمية لازم تكون أكبر من 0.")
    return amount


def parse_item_key(raw_name: str) -> str:
    item_key = ITEM_ALIASES.get(raw_name.strip().lower())
    if not item_key:
        raise ValueError("العنصر غير معروف. استخدم: ذهب، الماس، ارض، اسهم.")
    return item_key


def parse_buy_sell_item(raw_name: str) -> dict[str, Any]:
    item_key = parse_item_key(raw_name)
    item = ITEM_DEFINITIONS[item_key]
    return {
        "key": item_key,
        "label": item["label"],
        "icon": item["icon"],
        "buy_price": get_current_buy_price(item_key),
        "sell_price": get_current_sell_price(item_key),
    }


def get_auction_asset_meta(item_key: str) -> dict[str, Any]:
    if item_key == "companies":
        return {
            "label": "شركة",
            "icon": "🏢",
            "color": COLOR_INFO,
        }
    return ITEM_DEFINITIONS[item_key]


def add_asset(user: dict[str, Any], key: str, amount: int) -> None:
    user[key] += amount
    save_user(user)


def credit_money(user: dict[str, Any], amount: int) -> tuple[int, int]:
    if amount <= 0:
        return 0, 0
    used_for_negative = 0
    if user["money"] < 0:
        needed = min(amount, abs(user["money"]))
        user["money"] += needed
        amount -= needed
        used_for_negative = needed
    if amount > 0:
        user["money"] += amount
    save_user(user)
    return amount, used_for_negative


def can_afford(user: dict[str, Any], amount: int) -> bool:
    return user["money"] >= amount


def debit_money(user: dict[str, Any], amount: int, allow_negative: bool = False) -> None:
    if amount <= 0:
        return
    if not allow_negative and user["money"] < amount:
        raise ValueError("رصيدك ما يكفي.")
    user["money"] -= amount
    save_user(user)


def recalculate_sell_price(item_key: str, buy_price: int) -> int:
    item = ITEM_DEFINITIONS[item_key]
    ratio = item["base_sell"] / item["base_buy"]
    step = max(50, item["step"] // 2)
    sell_price = int(round((buy_price * ratio) / step) * step)
    return max(step, sell_price)


def price_movement_multiplier(item_key: str) -> float:
    roll = random.random()
    if item_key == "stocks":
        if roll < 0.60:
            return random.uniform(0.95, 1.05)
        if roll < 0.82:
            return random.uniform(1.10, 1.35)
        if roll < 0.96:
            return random.uniform(0.75, 0.92)
        return random.uniform(0.88, 1.12)
    if roll < 0.65:
        return random.uniform(0.96, 1.04)
    if roll < 0.82:
        return random.uniform(1.07, 1.18)
    if roll < 0.96:
        return random.uniform(0.82, 0.94)
    return random.uniform(0.90, 1.08)


def adjust_price(item_key: str, direction: int, auto: bool = False) -> tuple[int, int]:
    item = ITEM_DEFINITIONS[item_key]
    current = get_price(item_key)
    current_buy = current["buy_price"]

    if auto:
        multiplier = price_movement_multiplier(item_key)
        new_buy = int(round((current_buy * multiplier) / item["step"]) * item["step"])
        if new_buy == current_buy:
            new_buy = current_buy + random.choice((-item["step"], 0, item["step"]))
    else:
        new_buy = current_buy + (item["step"] * direction)

    new_buy = max(item["min_buy"], new_buy)
    new_sell = recalculate_sell_price(item_key, new_buy)
    current["buy_price"] = new_buy
    current["sell_price"] = new_sell
    current["last_update"] = time.time()
    mark_dirty()
    return new_buy, new_sell


def estimate_user_total_value(user: dict[str, Any]) -> int:
    return (
        user["money"]
        + user["gold"] * get_current_sell_price("gold")
        + user["diamonds"] * get_current_sell_price("diamonds")
        + user["lands"] * get_current_sell_price("lands")
        + user["stocks"] * get_current_sell_price("stocks")
        + user["companies"] * COMPANY_PRICE
    )


def get_active_event() -> dict[str, Any] | None:
    event = data_store.get("active_event")
    if not event:
        return None
    if event.get("expires_at", 0) <= time.time() or event.get("remaining", 0) <= 0:
        data_store["active_event"] = None
        mark_dirty()
        return None
    return event


def set_active_event(event: dict[str, Any] | None) -> None:
    data_store["active_event"] = event
    mark_dirty()


async def clear_active_event(reason: str = "انتهى الحدث.") -> None:
    global event_cleanup_task

    event = data_store.get("active_event")
    if not event:
        return

    channel = bot.get_channel(event["channel_id"])
    if isinstance(channel, discord.TextChannel):
        try:
            message = await channel.fetch_message(event["message_id"])
            await message.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to delete event message.")

        try:
            await channel.send(embed=info_embed("انتهى الحدث", reason, COLOR_WARNING), delete_after=10)
        except discord.HTTPException:
            logger.exception("Failed to send event end message.")

    set_active_event(None)
    if event_cleanup_task and not event_cleanup_task.done():
        event_cleanup_task.cancel()
    event_cleanup_task = None


async def reset_economy_data() -> int:
    users = data_store.get("users", {})
    reset_count = len(users)

    for user in users.values():
        reset_user_data(user)

    data_store["auctions"] = {}
    data_store["systems"] = default_system_settings()
    mark_dirty()
    await clear_active_event("تم تصفير الاقتصاد وإرجاع كل لاعب إلى 3000 وإغلاق الحدث الحالي.")
    return reset_count


def schedule_event_cleanup() -> None:
    global event_cleanup_task

    event = get_active_event()
    if not event:
        return

    if event_cleanup_task and not event_cleanup_task.done():
        event_cleanup_task.cancel()

    async def cleanup_after_delay() -> None:
        delay = max(0, event["expires_at"] - time.time())
        await asyncio.sleep(delay)
        await clear_active_event("انتهت مدة الحدث وتم إغلاقه تلقائيًا.")

    event_cleanup_task = asyncio.create_task(cleanup_after_delay())


async def update_panel_message(channel: discord.TextChannel) -> None:
    panel_id = data_store.get("panel_message_id")
    view = AdminPanelView()

    if panel_id:
        try:
            message = await channel.fetch_message(panel_id)
            await message.edit(embed=admin_panel_embed(), view=view)
            return
        except discord.NotFound:
            logger.info("Admin panel message not found, creating a new one.")
        except discord.HTTPException:
            logger.exception("Failed to update admin panel message.")

    message = await channel.send(embed=admin_panel_embed(), view=view)
    data_store["panel_message_id"] = message.id
    mark_dirty()


async def update_price_panel_message(channel: discord.TextChannel) -> None:
    panel_id = data_store.get("price_panel_message_id")
    view = PriceControlView()

    if panel_id:
        try:
            message = await channel.fetch_message(panel_id)
            await message.edit(embed=price_panel_embed(), view=view)
            return
        except discord.NotFound:
            logger.info("Price panel message not found, creating a new one.")
        except discord.HTTPException:
            logger.exception("Failed to update price panel message.")

    message = await channel.send(embed=price_panel_embed(), view=view)
    data_store["price_panel_message_id"] = message.id
    mark_dirty()


async def refresh_admin_room_panels() -> None:
    channel = bot.get_channel(ADMIN_PANEL_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        await update_panel_message(channel)
        await update_price_panel_message(channel)
    except discord.HTTPException:
        logger.exception("Failed to refresh admin room panels.")


def get_auction(auction_id: str) -> dict[str, Any] | None:
    auction = data_store["auctions"].get(auction_id)
    if not auction:
        return None
    if auction.get("closed"):
        return None
    return auction


def find_auction_by_message(message_id: int) -> dict[str, Any] | None:
    for auction in data_store["auctions"].values():
        if auction.get("message_id") == message_id and not auction.get("closed"):
            return auction
    return None


def list_open_auctions() -> list[dict[str, Any]]:
    return [auction for auction in data_store["auctions"].values() if not auction.get("closed")]


def auction_title(auction: dict[str, Any]) -> str:
    if auction["kind"] == "hidden":
        return "مزاد مخفي"
    if auction["kind"] == "special":
        return auction["title"]
    if auction["kind"] == "user":
        return f"مزاد {auction['title']}"
    return "مزاد تلقائي"


def auction_embed(auction: dict[str, Any]) -> discord.Embed:
    asset_meta = get_auction_asset_meta(auction["item_key"])
    color = COLOR_SECRET if auction["kind"] == "hidden" else asset_meta["color"]
    embed = base_embed(color)
    embed.title = auction_title(auction)

    if auction["state"] == "countdown":
        remaining = max(0, int(math.ceil(auction["countdown_end_at"] - time.time())))
        timer_line = f"⏳ العد النهائي: `{remaining}`"
        status_line = "الحالة: الإغلاق النهائي"
    else:
        remaining = max(0, int(auction["expires_at"] - time.time()))
        timer_line = f"⏳ الوقت المتبقي: `{format_wait(remaining)}`"
        status_line = "الحالة: مفتوح"

    if auction["current_bid"] > 0:
        top_bid_line = f"💰 أعلى مزايدة: `{auction['current_bid']}`"
        top_user_line = f"👑 أعلى مزايد: <@{auction['current_winner_id']}>"
    else:
        top_bid_line = f"💰 السعر المطروح: `{auction['starting_bid']}`"
        top_user_line = "👑 أعلى مزايد: لا يوجد حتى الآن"

    if auction["kind"] == "hidden":
        item_line = "🎁 الجائزة: شيء مخفي وحصري"
        quantity_line = "❔ التفاصيل: مجهولة"
    else:
        item_line = f"{asset_meta['icon']} العنصر: `{asset_meta['label']}`"
        quantity_line = f"📦 الكمية: `{auction['quantity']}`"

    owner_line = ""
    if auction.get("creator_id"):
        owner_line = f"\n👤 صاحب المزاد: <@{auction['creator_id']}>"

    embed.description = (
        f"{item_line}\n"
        f"{quantity_line}\n"
        f"{top_bid_line}\n"
        f"{top_user_line}\n"
        f"{timer_line}\n"
        f"{status_line}{owner_line}"
    )
    return embed


def build_auction_view(auction: dict[str, Any]) -> discord.ui.View:
    if auction["kind"] == "user":
        return AuctionActionView()
    return AuctionBidOnlyView()


async def update_auction_message(auction: dict[str, Any]) -> None:
    channel = bot.get_channel(auction["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(auction["message_id"])
        await message.edit(embed=auction_embed(auction), view=build_auction_view(auction))
    except discord.NotFound:
        pass
    except discord.HTTPException:
        logger.exception("Failed to update auction message.")


async def repost_auction_message(auction: dict[str, Any]) -> None:
    channel = bot.get_channel(auction["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return

    old_message_id = auction.get("message_id", 0)
    if old_message_id:
        try:
            old_message = await channel.fetch_message(old_message_id)
            await old_message.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to delete old auction message during repost.")

    message = await channel.send(embed=auction_embed(auction), view=build_auction_view(auction))
    auction["message_id"] = message.id
    mark_dirty()


def upsert_bid_history(auction: dict[str, Any], user_id: int, amount: int, user_name: str) -> None:
    bids = auction.setdefault("bid_history", [])
    filtered = [bid for bid in bids if bid["user_id"] != user_id]
    filtered.append(
        {
            "user_id": user_id,
            "amount": amount,
            "user_name": user_name,
            "timestamp": time.time(),
        }
    )
    filtered.sort(key=lambda bid: (bid["amount"], bid["timestamp"]), reverse=True)
    auction["bid_history"] = filtered


def get_best_valid_bid(auction: dict[str, Any]) -> dict[str, Any] | None:
    for bid in sorted(
        auction.get("bid_history", []),
        key=lambda entry: (entry["amount"], entry["timestamp"]),
        reverse=True,
    ):
        user = get_user(bid["user_id"])
        if user["money"] >= bid["amount"]:
            return bid
    return None


def create_auction_payload(
    *,
    kind: str,
    item_key: str,
    quantity: int,
    starting_bid: int,
    title: str,
    creator_id: int | None,
    creator_name: str,
) -> dict[str, Any]:
    return {
        "auction_id": uuid.uuid4().hex,
        "kind": kind,
        "item_key": item_key,
        "quantity": quantity,
        "starting_bid": starting_bid,
        "current_bid": 0,
        "current_winner_id": None,
        "channel_id": EVENT_PUBLIC_CHANNEL_ID,
        "message_id": 0,
        "expires_at": time.time() + AUCTION_DURATION_SECONDS,
        "state": "running",
        "countdown_end_at": 0,
        "last_countdown_value": 0,
        "bid_history": [],
        "title": title,
        "creator_id": creator_id,
        "creator_name": creator_name,
        "closed": False,
    }


async def post_auction(auction: dict[str, Any]) -> None:
    channel = bot.get_channel(EVENT_PUBLIC_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return
    message = await channel.send(embed=auction_embed(auction), view=build_auction_view(auction))
    auction["message_id"] = message.id
    auction["channel_id"] = channel.id
    data_store["auctions"][auction["auction_id"]] = auction
    mark_dirty()


async def create_auto_auction() -> None:
    item_key = random.choice(["gold", "diamonds", "lands", "stocks"])
    item = ITEM_DEFINITIONS[item_key]
    current_buy = get_current_buy_price(item_key)
    quantity = item["auction_quantity"]
    starting_bid = max(item["step"], int(round((current_buy * quantity * 0.65) / item["step"]) * item["step"]))
    auction = create_auction_payload(
        kind="auto",
        item_key=item_key,
        quantity=quantity,
        starting_bid=starting_bid,
        title="مزاد تلقائي",
        creator_id=None,
        creator_name="BLS Economy",
    )
    await post_auction(auction)
    data_store["systems"]["next_auto_auction_at"] = next_timestamp(AUTO_AUCTION_INTERVAL_SECONDS)
    mark_dirty()


async def create_hidden_auction() -> None:
    starting_bid = random.choice([2000, 3000, 4000, 5000, 7500])
    auction = create_auction_payload(
        kind="hidden",
        item_key="stocks",
        quantity=1,
        starting_bid=starting_bid,
        title="مزاد مخفي",
        creator_id=None,
        creator_name="BLS Economy",
    )
    await post_auction(auction)
    data_store["systems"]["next_hidden_auction_at"] = next_timestamp(HIDDEN_AUCTION_INTERVAL_SECONDS)
    mark_dirty()


def hidden_auction_reward() -> tuple[str, str]:
    if random.random() < 0.68:
        reward_roll = random.random()
        if reward_roll < 0.35:
            amount = random.randint(5000, 18000)
            return "money", f"💵 ربح نقدي قوي `{amount}`"
        if reward_roll < 0.60:
            amount = random.randint(2, 6)
            return "gold", f"🥇 ربحت `{amount}` ذهب"
        if reward_roll < 0.82:
            amount = random.randint(1, 3)
            return "diamonds", f"💎 ربحت `{amount}` ألماس"
        if reward_roll < 0.94:
            amount = random.randint(6, 15)
            return "stocks", f"📈 ربحت `{amount}` أسهم"
        return "lands", "🏝️ ربحت أرض نادرة واحدة"
    small_reward = random.choice(
        [
            ("money_small", "💵 طلعت لك جائزة بسيطة جدًا `250`"),
            ("money_small", "💵 طلعت لك جائزة بسيطة جدًا `500`"),
            ("gold_small", "🥇 طلعت لك قطعة ذهب واحدة"),
        ]
    )
    return small_reward


async def close_auction_message(auction: dict[str, Any], embed: discord.Embed) -> None:
    channel = bot.get_channel(auction["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        message = await channel.fetch_message(auction["message_id"])
        await message.edit(embed=embed, view=None)
    except discord.NotFound:
        pass
    except discord.HTTPException:
        logger.exception("Failed to update final auction message.")


async def finish_auction_without_winner(auction: dict[str, Any], reason: str) -> None:
    if auction["kind"] == "user" and auction.get("creator_id"):
        owner = get_user(auction["creator_id"])
        owner[auction["item_key"]] += auction["quantity"]
        save_user(owner)
        reason = f"{reason}\nتم إرجاع العنصر لصاحب المزاد."
    embed = info_embed("انتهى المزاد", reason, COLOR_WARNING)
    await close_auction_message(auction, embed)
    auction["closed"] = True
    mark_dirty()


async def finish_auction_with_winner(auction: dict[str, Any]) -> None:
    best_bid = get_best_valid_bid(auction)
    if not best_bid:
        await finish_auction_without_winner(auction, "انتهى المزاد لكن لا يوجد مزايد يملك المبلغ حاليًا.")
        return

    winner = get_user(best_bid["user_id"])
    debit_money(winner, best_bid["amount"])

    result_embed = base_embed(COLOR_SUCCESS)
    result_embed.title = "انتهى المزاد"
    result_embed.description = f"🏆 الفائز: <@{best_bid['user_id']}>\n💰 السعر النهائي: `{best_bid['amount']}`"

    if auction["kind"] == "hidden":
        reward_type, reward_text = hidden_auction_reward()
        if reward_type == "money":
            amount = int(reward_text.split("`")[1])
            credit_money(winner, amount)
        elif reward_type == "gold":
            amount = int(reward_text.split("`")[1])
            winner["gold"] += amount
            save_user(winner)
        elif reward_type == "diamonds":
            amount = int(reward_text.split("`")[1])
            winner["diamonds"] += amount
            save_user(winner)
        elif reward_type == "stocks":
            amount = int(reward_text.split("`")[1])
            winner["stocks"] += amount
            save_user(winner)
        elif reward_type == "lands":
            winner["lands"] += 1
            save_user(winner)
        elif reward_type == "money_small":
            amount = int(reward_text.split("`")[1])
            credit_money(winner, amount)
        else:
            winner["gold"] += 1
            save_user(winner)
        result_embed.description += f"\n🎁 نتيجة المزاد المخفي: {reward_text}"
    else:
        winner[auction["item_key"]] += auction["quantity"]
        save_user(winner)
        item = get_auction_asset_meta(auction["item_key"])
        result_embed.description += f"\n{item['icon']} الجائزة: `{auction['quantity']}` {item['label']}"

    if auction["kind"] == "user" and auction.get("creator_id") and auction["creator_id"] != best_bid["user_id"]:
        seller = get_user(auction["creator_id"])
        credited, absorbed = credit_money(seller, best_bid["amount"])
        seller_text = f"💸 تم تحويل `{best_bid['amount']}` لصاحب المزاد."
        if absorbed > 0:
            seller_text += f"\nتم استخدام `{absorbed}` لتسديد الرصيد السالب أولًا."
        result_embed.description += f"\n{seller_text}"

    await close_auction_message(auction, result_embed)
    auction["closed"] = True
    mark_dirty()


async def cancel_user_auction(auction: dict[str, Any], actor: discord.abc.User) -> None:
    embed = info_embed("تم إلغاء المزاد", f"تم إلغاء المزاد بواسطة {actor.mention}.", COLOR_WARNING)
    await close_auction_message(auction, embed)
    auction["closed"] = True
    mark_dirty()


async def run_auction_countdown_step(auction: dict[str, Any]) -> None:
    remaining = max(0, int(math.ceil(auction["countdown_end_at"] - time.time())))
    if remaining <= 0:
        await finish_auction_with_winner(auction)
        return

    if remaining != auction.get("last_countdown_value"):
        auction["last_countdown_value"] = remaining
        mark_dirty()
        channel = bot.get_channel(auction["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(f"⏳ ينتهي المزاد خلال `{remaining}`", delete_after=2)
            except discord.HTTPException:
                logger.exception("Failed to send auction countdown message.")
        await update_auction_message(auction)


async def tick_auction_system() -> None:
    systems = data_store["systems"]
    now = time.time()

    if systems["auto_auction_enabled"] and now >= systems["next_auto_auction_at"]:
        await create_auto_auction()
    if systems["hidden_auction_enabled"] and now >= systems["next_hidden_auction_at"]:
        await create_hidden_auction()

    for auction in list(list_open_auctions()):
        if auction["state"] == "running" and now >= auction["expires_at"]:
            if auction["current_bid"] <= 0:
                await finish_auction_without_winner(auction, "انتهت مدة المزاد بدون أي مزايدة.")
                continue
            auction["state"] = "countdown"
            auction["countdown_end_at"] = time.time() + AUCTION_COUNTDOWN_SECONDS
            auction["last_countdown_value"] = 0
            mark_dirty()
            await update_auction_message(auction)
            await run_auction_countdown_step(auction)
        elif auction["state"] == "countdown":
            await run_auction_countdown_step(auction)


async def maybe_auto_update_prices() -> None:
    changed = False
    now = time.time()
    for item_key, item in ITEM_DEFINITIONS.items():
        last_update = data_store["prices"][item_key].get("last_update", 0)
        if now - last_update >= item["update_seconds"]:
            adjust_price(item_key, 0, auto=True)
            changed = True
    if changed:
        await refresh_admin_room_panels()


def resolve_company_change() -> int:
    return 0


def calculate_company_sale_total(user: dict[str, Any], quantity: int, include_stocks: bool) -> tuple[int, int]:
    base_total = 0
    for _ in range(quantity):
        base_total += random.randint(185000, 235000)

    bundled_stocks = 0
    if include_stocks and user["stocks"] > 0:
        bundled_stocks = user["stocks"]
        stock_value = bundled_stocks * get_current_sell_price("stocks")
        stock_bonus = int(bundled_stocks * 350)
        base_total += stock_value + stock_bonus

    return base_total, bundled_stocks


async def process_company_income() -> None:
    return


async def process_loans() -> None:
    now = time.time()
    changed = False
    for user in data_store["users"].values():
        loan = user.get("loan")
        if not loan:
            continue
        if now >= loan["due_at"]:
            user["money"] -= loan["balance"] + LOAN_LATE_FEE
            user["loan"] = None
            changed = True
    if changed:
        mark_dirty()


async def background_loop() -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await maybe_auto_update_prices()
            await process_company_income()
            await process_loans()
            await tick_auction_system()
        except Exception:
            logger.exception("Background loop crashed.")
        await asyncio.sleep(5)


def investment_profit(amount: int) -> int:
    base_floor = max(50, int(amount * 0.35))
    scaled_floor = max(base_floor, int(amount * 0.70) if amount >= 1000 else int(amount * 0.30))
    scaled_ceiling = max(scaled_floor + 50, int(amount * 1.30))
    return random.randint(scaled_floor, scaled_ceiling)


def investment_loss(amount: int, all_in: bool) -> int:
    if all_in:
        return amount
    return max(1, amount // 2)


def trade_profit(amount: int) -> int:
    floor = max(50, int(amount * 0.40))
    if amount >= 1000:
        floor = max(floor, 700)
    ceiling = max(floor + 50, int(amount * 1.60))
    return random.randint(floor, ceiling)


def trade_loss(amount: int, all_in: bool) -> int:
    if all_in:
        return amount
    return max(1, amount // 2)


def resolve_steal_amount(victim_money: int) -> int:
    roll = random.random()
    if victim_money <= 0:
        return 0
    if victim_money >= 50000 and roll < 0.30:
        return min(victim_money, random.randint(3500, 6000))
    if victim_money >= 15000 and roll < 0.65:
        return min(victim_money, random.randint(1800, 3500))
    if roll < 0.90:
        return min(victim_money, random.randint(250, min(1500, max(300, victim_money // 6))))
    return min(victim_money, random.randint(1500, min(4500, victim_money)))


def build_commands_embed() -> discord.Embed:
    embed = base_embed(COLOR_INFO)
    embed.title = "قائمة الأوامر"
    embed.description = (
        "`ممتلكاتي` أو `رصيدي`\n"
        "`راتب`\n"
        "`استثمار <مبلغ/كل>`\n"
        "`تداول <مبلغ/كل>`\n"
        "`روليت`\n"
        "`حماية`\n"
        "`تحويل @شخص <مبلغ>`\n"
        "`سرقة @شخص`\n"
        "`توب`\n"
        "`شراء`\n"
        "`شراء <العنصر> <الكمية>`\n"
        "`بيع <العنصر> <الكمية/كل>`\n"
        "`شراء شركة <عدد>`\n"
        "`بيع شركة <عدد>`\n"
        "`بيع شركة <عدد> مع_الاسهم`\n"
        "`قرض <مبلغ>`\n"
        "`سداد <مبلغ>`\n"
        "`مزاد` لفتح نموذج مزاد لاعب\n"
        "أوامر الإدارة: `لوحة الادارة`"
    )
    return embed


class ClaimEventView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام الحدث", style=discord.ButtonStyle.success, custom_id="claim_event")
    async def claim_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        event = get_active_event()
        if not event:
            await interaction.response.send_message("لا يوجد حدث نشط الآن.", ephemeral=True)
            return

        if interaction.channel_id != event["channel_id"]:
            await interaction.response.send_message("هذا الزر ليس لهذا الروم.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if user_id in event["claimed_by"]:
            await interaction.response.send_message("أنت استلمت الحدث بالفعل.", ephemeral=True)
            return

        user = get_user(interaction.user.id)
        reward_key = EVENT_REWARD_TYPES[event["reward_type"]]["key"]
        if reward_key == "money":
            credit_money(user, event["amount"])
        else:
            add_asset(user, reward_key, event["amount"])

        event["claimed_by"].append(user_id)
        event["remaining"] -= 1
        reward = EVENT_REWARD_TYPES[event["reward_type"]]

        if event["remaining"] <= 0:
            await interaction.response.send_message(
                embed=card_embed("تم الاستلام", f"{event['amount']} {reward['label']}", reward["color"], reward["icon"]),
                ephemeral=True,
            )
            await clear_active_event("تم استلام جميع الجوائز وانتهى الحدث.")
            return

        set_active_event(event)
        await interaction.response.edit_message(embed=event_post_embed(event), view=ClaimEventView())
        await interaction.followup.send(
            embed=card_embed("تم الاستلام", f"{event['amount']} {reward['label']}", reward["color"], reward["icon"]),
            ephemeral=True,
        )


class EventCreateModal(discord.ui.Modal):
    def __init__(self, reward_type: str) -> None:
        reward = EVENT_REWARD_TYPES[reward_type]
        super().__init__(title=f"إنشاء حدث {reward['label']}")
        self.reward_type = reward_type
        self.reward_amount = discord.ui.TextInput(label="كمية الجائزة لكل شخص", placeholder="مثال: 500", max_length=10)
        self.claim_limit = discord.ui.TextInput(label="عدد الأشخاص المسموح لهم", placeholder="مثال: 10", max_length=10)
        self.add_item(self.reward_amount)
        self.add_item(self.claim_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتبة المصرح لها.", ephemeral=True)
            return
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("استخدم اللوحة داخل روم الإدارة فقط.", ephemeral=True)
            return

        try:
            amount = parse_amount(str(self.reward_amount))
            limit = parse_amount(str(self.claim_limit))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        old_event = get_active_event()
        if old_event:
            await clear_active_event("تم استبدال الحدث بحدث جديد.")

        public_channel = bot.get_channel(EVENT_PUBLIC_CHANNEL_ID)
        if not isinstance(public_channel, discord.TextChannel):
            await interaction.response.send_message("ما قدرت أوصل لروم الحدث العام.", ephemeral=True)
            return

        reward = EVENT_REWARD_TYPES[self.reward_type]
        event = {
            "reward_type": self.reward_type,
            "amount": amount,
            "remaining": limit,
            "claimed_by": [],
            "creator_name": str(interaction.user),
            "channel_id": public_channel.id,
            "message_id": 0,
            "expires_at": time.time() + EVENT_DURATION_SECONDS,
        }

        message = await public_channel.send(embed=event_post_embed(event), view=ClaimEventView())
        event["message_id"] = message.id
        set_active_event(event)
        schedule_event_cleanup()

        await interaction.response.send_message(
            embed=card_embed(
                "تم إنشاء الحدث",
                f"{amount} {reward['label']} لعدد {limit} أشخاص",
                reward["color"],
                reward["icon"],
            ),
            ephemeral=True,
        )


class SpecialAuctionModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="مزاد خاص وحصري")
        self.auction_name = discord.ui.TextInput(label="اسم المزاد", placeholder="مثال: مزاد خاص وحصري", max_length=50)
        self.item_name = discord.ui.TextInput(label="العنصر", placeholder="ذهب أو ألماس أو أرض أو أسهم", max_length=20)
        self.start_price = discord.ui.TextInput(label="السعر الابتدائي", placeholder="مثال: 5000", max_length=12)
        self.quantity = discord.ui.TextInput(label="الكمية", placeholder="مثال: 1", default="1", max_length=6)
        self.add_item(self.auction_name)
        self.add_item(self.item_name)
        self.add_item(self.start_price)
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            item_key = parse_item_key(str(self.item_name))
            start_price = parse_amount(str(self.start_price))
            quantity = parse_amount(str(self.quantity))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        auction = create_auction_payload(
            kind="special",
            item_key=item_key,
            quantity=quantity,
            starting_bid=start_price,
            title=str(self.auction_name),
            creator_id=interaction.user.id,
            creator_name=str(interaction.user),
        )
        await post_auction(auction)
        await interaction.response.send_message("تم إنشاء المزاد الخاص وحصريًا في روم الأعضاء.", ephemeral=True)


class PlayerAuctionModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="إنشاء مزاد لاعب")
        self.item_name = discord.ui.TextInput(label="العنصر", placeholder="ذهب أو ألماس أو أرض أو أسهم", max_length=20)
        self.quantity = discord.ui.TextInput(label="الكمية", placeholder="مثال: 1", max_length=10)
        self.start_price = discord.ui.TextInput(label="السعر الابتدائي", placeholder="مثال: 2500", max_length=12)
        self.add_item(self.item_name)
        self.add_item(self.quantity)
        self.add_item(self.start_price)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            item_key = parse_item_key(str(self.item_name))
            quantity = parse_amount(str(self.quantity))
            start_price = parse_amount(str(self.start_price))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        user = get_user(interaction.user.id)
        if user[item_key] < quantity:
            await interaction.response.send_message("ما تملك الكمية المطلوبة لإنشاء المزاد.", ephemeral=True)
            return

        user[item_key] -= quantity
        save_user(user)

        auction = create_auction_payload(
            kind="user",
            item_key=item_key,
            quantity=quantity,
            starting_bid=start_price,
            title=ITEM_DEFINITIONS[item_key]["label"],
            creator_id=interaction.user.id,
            creator_name=str(interaction.user),
        )
        await post_auction(auction)
        await interaction.response.send_message("تم تنزيل مزادك في روم الأعضاء.", ephemeral=True)


class LoanModal(discord.ui.Modal):
    def __init__(self, mode: str, current_amount: int = 0) -> None:
        super().__init__(title="طلب قرض" if mode == "loan" else "سداد الدين")
        self.mode = mode
        self.amount = discord.ui.TextInput(
            label="المبلغ",
            placeholder="اكتب المبلغ",
            default=str(current_amount) if current_amount else "",
            max_length=12,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        user = get_user(interaction.user.id)
        try:
            amount = parse_amount(str(self.amount))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if self.mode == "loan":
            if user.get("loan"):
                await interaction.response.send_message("عندك قرض قائم بالفعل، سدده أولًا.", ephemeral=True)
                return
            if amount > LOAN_MAX_AMOUNT:
                await interaction.response.send_message(f"الحد الأقصى للقرض هو `{LOAN_MAX_AMOUNT}`.", ephemeral=True)
                return
            user["loan"] = {"balance": amount, "due_at": time.time() + LOAN_DURATION_SECONDS}
            credit_money(user, amount)
            await interaction.response.send_message(
                embed=info_embed("تم القرض", f"تم صرف قرض بقيمة `{amount}` وموعد السداد خلال `ساعة`.", COLOR_SUCCESS),
                ephemeral=True,
            )
            return

        if user.get("loan"):
            if amount < LOAN_MIN_PAYMENT:
                await interaction.response.send_message(f"أقل مبلغ للسداد هو `{LOAN_MIN_PAYMENT}`.", ephemeral=True)
                return
            if user["money"] < amount:
                await interaction.response.send_message("رصيدك ما يكفي للسداد.", ephemeral=True)
                return
            loan = user["loan"]
            pay = min(amount, loan["balance"])
            user["money"] -= pay
            loan["balance"] -= pay
            if loan["balance"] <= 0:
                user["loan"] = None
                save_user(user)
                await interaction.response.send_message(
                    embed=info_embed("تم السداد", "تم سداد القرض بالكامل.", COLOR_SUCCESS),
                    ephemeral=True,
                )
                return
            loan["due_at"] = time.time() + LOAN_DURATION_SECONDS
            save_user(user)
            await interaction.response.send_message(
                embed=info_embed(
                    "تم السداد الجزئي",
                    f"تم سداد `{pay}` والمتبقي `{loan['balance']}` وتم إعادة العداد إلى `ساعة` جديدة.",
                    COLOR_SUCCESS,
                ),
                ephemeral=True,
            )
            return

        if user["money"] >= 0:
            await interaction.response.send_message("لا يوجد عليك قرض أو رصيد سالب.", ephemeral=True)
            return
        await interaction.response.send_message(
            "رصيدك الآن بالسالب، وأي مبلغ يدخل حسابك سيتخصم تلقائيًا حتى يرجع طبيعي.",
            ephemeral=True,
        )
        return


class ProtectedStealAttemptView(discord.ui.View):
    def __init__(self, thief_id: int, victim_id: int) -> None:
        super().__init__(timeout=60)
        self.thief_id = thief_id
        self.victim_id = victim_id
        self.correct_choice = random.choice(["A", "B", "C"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.thief_id:
            await interaction.response.send_message("هذه المحاولة ليست لك.", ephemeral=True)
            return False
        return True

    async def resolve_choice(self, interaction: discord.Interaction, choice: str) -> None:
        thief = get_user(self.thief_id)
        victim = get_user(self.victim_id)
        for child in self.children:
            child.disabled = True
        if choice != self.correct_choice:
            thief["lastSteal"] = time.time()
            save_user(thief)
            await interaction.response.edit_message(
                embed=info_embed("فشلت المحاولة", "اختيارك كان خطأ وما قدرت تتجاوز الحماية.", COLOR_DANGER),
                view=self,
            )
            return
        stolen = resolve_steal_amount(max(1, victim["money"]))
        victim["money"] -= stolen
        thief["money"] += stolen
        thief["lastSteal"] = time.time()
        save_user(victim)
        save_user(thief)
        await interaction.response.edit_message(
            embed=info_embed("نجحت السرقة", f"تجاوزت الحماية وسرقت `{stolen}`.", COLOR_SUCCESS),
            view=self,
        )

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def choice_a(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.resolve_choice(interaction, "A")

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def choice_b(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.resolve_choice(interaction, "B")

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def choice_c(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.resolve_choice(interaction, "C")


class ProtectedStealConfirmView(discord.ui.View):
    def __init__(self, thief_id: int, victim_id: int) -> None:
        super().__init__(timeout=60)
        self.thief_id = thief_id
        self.victim_id = victim_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.thief_id:
            await interaction.response.send_message("هذه المحاولة ليست لك.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="إي", style=discord.ButtonStyle.danger)
    async def yes_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        thief = get_user(self.thief_id)
        if thief["money"] < STEAL_PROTECTED_COST:
            await interaction.response.send_message("تحتاج 500 لبدء محاولة تجاوز الحماية.", ephemeral=True)
            return
        thief["money"] -= STEAL_PROTECTED_COST
        save_user(thief)
        await interaction.response.edit_message(
            embed=info_embed(
                "اختر الخيار الصحيح",
                "واحد فقط صحيح. إذا اخترته تنجح السرقة، وإذا أخطأت تفشل المحاولة.",
                COLOR_WARNING,
            ),
            view=ProtectedStealAttemptView(self.thief_id, self.victim_id),
        )

    @discord.ui.button(label="لا", style=discord.ButtonStyle.secondary)
    async def no_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=info_embed("تم الإلغاء", "تم إلغاء محاولة السرقة المحمية.", COLOR_WARNING),
            view=None,
        )


class ResetConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("استخدم هذه اللوحة داخل روم الإدارة فقط.", ephemeral=True)
            return False
        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتبة المصرح لها.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="نعم", style=discord.ButtonStyle.danger, custom_id="confirm_reset_yes")
    async def confirm_yes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        reset_count = await reset_economy_data()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=info_embed(
                "تم التصفير",
                f"تم تصفير الاقتصاد وإرجاع عدد `{reset_count}` مستخدم إلى `{START_MONEY}` مع حذف كل الممتلكات.",
                COLOR_DANGER,
            ),
            view=self,
        )
        self.stop()

    @discord.ui.button(label="لا", style=discord.ButtonStyle.secondary, custom_id="confirm_reset_no")
    async def confirm_no(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=info_embed("تم الإلغاء", "تم إلغاء عملية تصفير الاقتصاد.", COLOR_WARNING),
            view=self,
        )
        self.stop()


class PriceControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("هذه اللوحة تعمل فقط في روم الإدارة.", ephemeral=True)
            return False
        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتبة المصرح لها.", ephemeral=True)
            return False
        return True

    async def update_price(self, interaction: discord.Interaction, item_key: str, direction: int) -> None:
        new_buy, new_sell = adjust_price(item_key, direction, auto=False)
        await refresh_admin_room_panels()
        item = ITEM_DEFINITIONS[item_key]
        action = "رفع" if direction > 0 else "تنزيل"
        await interaction.response.send_message(
            embed=info_embed(
                "تم تحديث السعر",
                f"تم {action} سعر {item['label']} إلى شراء `{new_buy}` وبيع `{new_sell}`.",
                COLOR_SUCCESS,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="رفع الذهب", style=discord.ButtonStyle.success, custom_id="price_gold_up")
    async def price_gold_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "gold", 1)

    @discord.ui.button(label="تنزيل الذهب", style=discord.ButtonStyle.secondary, custom_id="price_gold_down")
    async def price_gold_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "gold", -1)

    @discord.ui.button(label="رفع الألماس", style=discord.ButtonStyle.success, custom_id="price_diamonds_up")
    async def price_diamonds_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "diamonds", 1)

    @discord.ui.button(label="تنزيل الألماس", style=discord.ButtonStyle.secondary, custom_id="price_diamonds_down")
    async def price_diamonds_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "diamonds", -1)

    @discord.ui.button(label="رفع الأرض", style=discord.ButtonStyle.success, custom_id="price_lands_up", row=1)
    async def price_lands_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "lands", 1)

    @discord.ui.button(label="تنزيل الأرض", style=discord.ButtonStyle.secondary, custom_id="price_lands_down", row=1)
    async def price_lands_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "lands", -1)

    @discord.ui.button(label="رفع الأسهم", style=discord.ButtonStyle.success, custom_id="price_stocks_up", row=2)
    async def price_stocks_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "stocks", 1)

    @discord.ui.button(label="تنزيل الأسهم", style=discord.ButtonStyle.secondary, custom_id="price_stocks_down", row=2)
    async def price_stocks_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.update_price(interaction, "stocks", -1)


class AuctionBidModal(discord.ui.Modal):
    def __init__(self, auction_id: str) -> None:
        super().__init__(title="المزايدة على المزاد")
        self.auction_id = auction_id
        self.bid_amount = discord.ui.TextInput(label="المبلغ", placeholder="اكتب مبلغ المزايدة", max_length=12)
        self.add_item(self.bid_amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        auction = get_auction(self.auction_id)
        if not auction:
            await interaction.response.send_message("لا يوجد مزاد نشط الآن.", ephemeral=True)
            return
        if interaction.channel_id != auction["channel_id"]:
            await interaction.response.send_message("هذا الزر خاص بروم المزاد فقط.", ephemeral=True)
            return

        try:
            amount = parse_amount(str(self.bid_amount))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        minimum_required = auction["current_bid"] + 1 if auction["current_bid"] > 0 else auction["starting_bid"]
        if amount < minimum_required:
            await interaction.response.send_message(f"لازم تكون المزايدة `{minimum_required}` أو أعلى.", ephemeral=True)
            return
        if auction["kind"] == "user" and auction.get("creator_id") == interaction.user.id:
            await interaction.response.send_message("ما تقدر تزايد على مزادك الشخصي.", ephemeral=True)
            return

        user = get_user(interaction.user.id)
        if user["money"] < amount:
            await interaction.response.send_message("ما تقدر تشارك لأن فلوسك ما تكفي لهذه المزايدة.", ephemeral=True)
            return

        auction["current_bid"] = amount
        auction["current_winner_id"] = interaction.user.id
        upsert_bid_history(auction, interaction.user.id, amount, str(interaction.user))

        if auction["state"] == "countdown":
            auction["countdown_end_at"] = time.time() + AUCTION_COUNTDOWN_SECONDS
            auction["last_countdown_value"] = 0

        mark_dirty()
        await interaction.response.send_message("تم تسجيل مزايدتك.", ephemeral=True)
        await repost_auction_message(auction)

        channel = bot.get_channel(auction["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    content=f"📢 {interaction.user.mention}",
                    embed=info_embed("تمت المزايدة من قبل", f"رفع المزاد إلى `{amount}`.", COLOR_SUCCESS),
                    delete_after=AUCTION_BID_CONFIRM_DELETE_AFTER,
                )
            except discord.HTTPException:
                logger.exception("Failed to send bid confirmation message.")


class AuctionActionView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="مزايدة", style=discord.ButtonStyle.success, custom_id="auction_bid_button")
    async def bid_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message("تعذر قراءة رسالة المزاد.", ephemeral=True)
            return
        auction = find_auction_by_message(interaction.message.id)
        if not auction:
            await interaction.response.send_message("لا يوجد مزاد نشط الآن.", ephemeral=True)
            return
        await interaction.response.send_modal(AuctionBidModal(auction["auction_id"]))

    @discord.ui.button(label="إلغاء المزاد", style=discord.ButtonStyle.danger, custom_id="auction_cancel_button")
    async def cancel_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message("تعذر قراءة رسالة المزاد.", ephemeral=True)
            return
        auction = find_auction_by_message(interaction.message.id)
        if not auction:
            await interaction.response.send_message("المزاد غير موجود أو منتهٍ.", ephemeral=True)
            return
        if auction["kind"] != "user":
            await interaction.response.send_message("إلغاء المزاد متاح لمزاد اللاعبين فقط.", ephemeral=True)
            return
        if interaction.user.id != auction.get("creator_id"):
            await interaction.response.send_message("فقط صاحب المزاد نفسه يقدر يلغيه.", ephemeral=True)
            return
        seller = get_user(auction["creator_id"])
        seller[auction["item_key"]] += auction["quantity"]
        save_user(seller)
        await cancel_user_auction(auction, interaction.user)
        await interaction.response.send_message("تم إلغاء المزاد وإرجاع العنصر لصاحبه.", ephemeral=True)


class AuctionBidOnlyView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="مزايدة", style=discord.ButtonStyle.success, custom_id="auction_bid_only_button")
    async def bid_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message("تعذر قراءة رسالة المزاد.", ephemeral=True)
            return
        auction = find_auction_by_message(interaction.message.id)
        if not auction:
            await interaction.response.send_message("لا يوجد مزاد نشط الآن.", ephemeral=True)
            return
        await interaction.response.send_modal(AuctionBidModal(auction["auction_id"]))


class LauncherView(discord.ui.View):
    def __init__(self, mode: str, owner_id: int, current_amount: int = 0) -> None:
        super().__init__(timeout=120)
        self.mode = mode
        self.owner_id = owner_id
        self.current_amount = current_amount

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("هذه النافذة خاصة بصاحب الأمر فقط.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="فتح النموذج", style=discord.ButtonStyle.primary)
    async def open_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.mode == "player_auction":
            await interaction.response.send_modal(PlayerAuctionModal())
            return
        if self.mode == "loan":
            await interaction.response.send_modal(LoanModal("loan"))
            return
        if self.mode == "repay":
            await interaction.response.send_modal(LoanModal("repay", self.current_amount))
            return


class AdminPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def ensure_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("هذه اللوحة تعمل فقط في روم الإدارة.", ephemeral=True)
            return False
        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتبة المصرح لها.", ephemeral=True)
            return False
        return True

    async def open_event_modal(self, interaction: discord.Interaction, reward_type: str) -> None:
        if not await self.ensure_admin(interaction):
            return
        await interaction.response.send_modal(EventCreateModal(reward_type))

    @discord.ui.button(label="حدث فلوس", style=discord.ButtonStyle.success, custom_id="panel_money")
    async def money_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_event_modal(interaction, "money")

    @discord.ui.button(label="حدث ذهب", style=discord.ButtonStyle.secondary, custom_id="panel_gold")
    async def gold_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_event_modal(interaction, "gold")

    @discord.ui.button(label="حدث ألماس", style=discord.ButtonStyle.primary, custom_id="panel_diamonds")
    async def diamonds_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_event_modal(interaction, "diamonds")

    @discord.ui.button(label="حدث أراضي", style=discord.ButtonStyle.danger, custom_id="panel_lands")
    async def lands_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_event_modal(interaction, "lands")

    @discord.ui.button(label="تشغيل/إيقاف المزاد", style=discord.ButtonStyle.success, custom_id="panel_toggle_auto", row=1)
    async def toggle_auto(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.ensure_admin(interaction):
            return
        systems = data_store["systems"]
        systems["auto_auction_enabled"] = not systems["auto_auction_enabled"]
        if systems["auto_auction_enabled"]:
            systems["next_auto_auction_at"] = next_timestamp(AUTO_AUCTION_INTERVAL_SECONDS)
        mark_dirty()
        await refresh_admin_room_panels()
        await interaction.response.send_message(
            f"المزاد التلقائي الآن: `{'شغال' if systems['auto_auction_enabled'] else 'متوقف'}`",
            ephemeral=True,
        )

    @discord.ui.button(label="مزاد خاص", style=discord.ButtonStyle.primary, custom_id="panel_special_auction", row=1)
    async def special_auction(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.ensure_admin(interaction):
            return
        await interaction.response.send_modal(SpecialAuctionModal())

    @discord.ui.button(label="تشغيل/إيقاف المخفي", style=discord.ButtonStyle.secondary, custom_id="panel_toggle_hidden", row=1)
    async def toggle_hidden(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.ensure_admin(interaction):
            return
        systems = data_store["systems"]
        systems["hidden_auction_enabled"] = not systems["hidden_auction_enabled"]
        if systems["hidden_auction_enabled"]:
            systems["next_hidden_auction_at"] = next_timestamp(HIDDEN_AUCTION_INTERVAL_SECONDS)
        mark_dirty()
        await refresh_admin_room_panels()
        await interaction.response.send_message(
            f"المزاد المخفي الآن: `{'شغال' if systems['hidden_auction_enabled'] else 'متوقف'}`",
            ephemeral=True,
        )

    @discord.ui.button(label="تصفير الاقتصاد", style=discord.ButtonStyle.danger, custom_id="panel_reset_economy", row=2)
    async def reset_economy(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.ensure_admin(interaction):
            return
        await interaction.response.send_message(
            embed=info_embed(
                "تأكيد التصفير",
                f"هل أنت متأكد؟ سيتم حذف الممتلكات وإرجاع كل لاعب إلى `{START_MONEY}`.",
                COLOR_DANGER,
            ),
            view=ResetConfirmView(),
            ephemeral=True,
        )


@bot.event
async def on_ready() -> None:
    global background_task, views_registered, auto_save_task

    logger.info("Logged in as %s", bot.user)

    if not views_registered:
        bot.add_view(AdminPanelView())
        bot.add_view(PriceControlView())
        bot.add_view(ClaimEventView())
        bot.add_view(AuctionActionView())
        bot.add_view(AuctionBidOnlyView())
        views_registered = True

    panel_channel = bot.get_channel(ADMIN_PANEL_CHANNEL_ID)
    if isinstance(panel_channel, discord.TextChannel):
        try:
            await update_panel_message(panel_channel)
            await update_price_panel_message(panel_channel)
        except discord.HTTPException:
            logger.exception("Failed to ensure admin panel messages.")

    schedule_event_cleanup()

    if background_task is None or background_task.done():
        background_task = asyncio.create_task(background_loop())
    if auto_save_task is None or auto_save_task.done():
        auto_save_task = bot.loop.create_task(auto_save_loop())


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None:
        return

    content = message.content.strip()
    if not content:
        return

    args = content.split()
    cmd = args[0].lower()
    user = get_user(message.author.id)

    try:
        if cmd == "لوحة" and len(args) > 1 and args[1] == "الادارة":
            if not isinstance(message.author, discord.Member) or not has_admin_access(message.author):
                raise ValueError("هذا الأمر فقط للرتبة المصرح لها.")
            if message.channel.id != ADMIN_PANEL_CHANNEL_ID:
                raise ValueError(f"استخدم هذا الأمر داخل روم الإدارة: {ADMIN_PANEL_CHANNEL_ID}")
            await refresh_admin_room_panels()
            await message.reply(embed=info_embed("تم", "تم تحديث لوحات الإدارة والأسعار.", COLOR_SUCCESS), delete_after=8)
            return

        if message.channel.id != EVENT_PUBLIC_CHANNEL_ID:
            return

        if cmd in {"ممتلكاتي", "رصيدي", "فلوسي"}:
            await message.reply(embed=dashboard_embed(user, message.author))
            return

        if cmd in {"اوامر", "أوامر"}:
            await message.reply(embed=build_commands_embed())
            return

        if cmd == "شراء" and len(args) == 1:
            await message.reply(embed=shop_embed())
            return

        if cmd in {"اسعار", "أسعار"}:
            await message.reply(embed=shop_embed())
            return

        if cmd == "مزاد":
            await message.reply(
                embed=info_embed("فتح مزاد", "اضغط الزر لكتابة بيانات مزادك الشخصي.", COLOR_INFO),
                view=LauncherView("player_auction", message.author.id),
            )
            return

        if cmd == "قرض":
            if len(args) == 1:
                await message.reply(
                    embed=info_embed("طلب قرض", f"الحد الأقصى للقرض هو `{LOAN_MAX_AMOUNT}`.", COLOR_INFO),
                    view=LauncherView("loan", message.author.id),
                )
                return
            amount = parse_amount(args[1])
            if user.get("loan"):
                raise ValueError("عندك قرض قائم بالفعل، سدده أولًا.")
            if amount > LOAN_MAX_AMOUNT:
                raise ValueError(f"الحد الأقصى للقرض هو `{LOAN_MAX_AMOUNT}`.")
            user["loan"] = {"balance": amount, "due_at": time.time() + LOAN_DURATION_SECONDS}
            credit_money(user, amount)
            await message.reply(embed=info_embed("تم القرض", f"تم صرف `{amount}` ومدة السداد `ساعة`.", COLOR_SUCCESS))
            return

        if cmd == "سداد":
            if len(args) == 1:
                current_amount = 0
                if user.get("loan"):
                    current_amount = min(user["loan"]["balance"], LOAN_MIN_PAYMENT)
                elif user["money"] < 0:
                    current_amount = min(abs(user["money"]), LOAN_MIN_PAYMENT)
                await message.reply(
                    embed=info_embed("سداد", "اضغط الزر لفتح نموذج السداد.", COLOR_INFO),
                    view=LauncherView("repay", message.author.id, current_amount),
                )
                return
            amount = parse_amount(args[1])
            if user.get("loan"):
                if amount < LOAN_MIN_PAYMENT:
                    raise ValueError(f"أقل مبلغ للسداد هو `{LOAN_MIN_PAYMENT}`.")
                if user["money"] < amount:
                    raise ValueError("رصيدك ما يكفي.")
                pay = min(amount, user["loan"]["balance"])
                user["money"] -= pay
                user["loan"]["balance"] -= pay
                if user["loan"]["balance"] <= 0:
                    user["loan"] = None
                    save_user(user)
                    await message.reply(embed=info_embed("تم السداد", "تم سداد القرض بالكامل.", COLOR_SUCCESS))
                    return
                user["loan"]["due_at"] = time.time() + LOAN_DURATION_SECONDS
                save_user(user)
                await message.reply(
                    embed=info_embed(
                        "تم السداد الجزئي",
                        f"سددت `{pay}` والمتبقي `{user['loan']['balance']}` وتم تجديد المهلة لساعة.",
                        COLOR_SUCCESS,
                    )
                )
                return
            if user["money"] >= 0:
                raise ValueError("لا يوجد عليك قرض أو رصيد سالب.")
            raise ValueError("رصيدك الآن بالسالب، وأي مبلغ يدخل حسابك سيتخصم تلقائيًا حتى يرجع طبيعي.")

        if cmd == "راتب":
            left = cooldown_left(user["lastDaily"], DAILY_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر شوي", f"تقدر تستلم راتبك بعد `{format_wait(left)}`.", COLOR_WARNING)
                )
                return
            salary = random.randint(350, 900)
            credited, absorbed = credit_money(user, salary)
            user["lastDaily"] = time.time()
            save_user(user)
            text = f"{salary}"
            if absorbed > 0:
                text += f"\nذهب `{absorbed}` لتقليل الرصيد السالب"
            elif credited != salary:
                text += f"\nالمضاف فعليًا `{credited}`"
            await message.reply(embed=card_embed("راتبك", text, COLOR_WARNING, "💰"))
            return

        if cmd == "حماية":
            if user["money"] < PROTECTION_COST:
                raise ValueError(f"تحتاج `{PROTECTION_COST}` لتفعيل الحماية.")
            user["money"] -= PROTECTION_COST
            start_from = max(time.time(), float(user.get("protectionUntil", 0)))
            user["protectionUntil"] = start_from + PROTECTION_DURATION_SECONDS
            save_user(user)
            await message.reply(
                embed=info_embed(
                    "تم تفعيل الحماية",
                    f"تم خصم `{PROTECTION_COST}` وتفعيل الحماية لمدة `ساعتين`.\nتنتهي بعد `{format_wait(int(user['protectionUntil'] - time.time()))}`.",
                    COLOR_SUCCESS,
                )
            )
            return

        if cmd == "استثمار":
            left = cooldown_left(user["lastInvest"], INVEST_COOLDOWN)
            if left > 0:
                await message.reply(embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على الاستثمار.", COLOR_WARNING))
                return
            if len(args) < 2:
                raise ValueError("اكتب: استثمار <مبلغ/كل>")
            all_in = args[1] == "كل"
            amount = user["money"] if all_in else parse_amount(args[1])
            if amount > user["money"]:
                raise ValueError("ما عندك المبلغ المطلوب.")
            user["money"] -= amount
            user["lastInvest"] = time.time()
            if random.random() < 0.58:
                gain = investment_profit(amount)
                returned, absorbed = credit_money(user, amount + gain)
                text = f"رجع لك رأس المال `{amount}` + ربح `{gain}`"
                if absorbed > 0:
                    text += f"\nتم امتصاص `{absorbed}` للرصد السالب"
                save_user(user)
                await message.reply(embed=card_embed("ربح الاستثمار", text, COLOR_SUCCESS, "📈"))
            else:
                loss = investment_loss(amount, all_in)
                if not all_in:
                    user["money"] += amount - loss
                save_user(user)
                await message.reply(embed=card_embed("خسارة الاستثمار", f"-{loss}", COLOR_DANGER, "📉"))
            return

        if cmd == "تداول":
            left = cooldown_left(user["lastTrade"], TRADE_COOLDOWN)
            if left > 0:
                await message.reply(embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على التداول.", COLOR_WARNING))
                return
            if len(args) < 2:
                raise ValueError("اكتب: تداول <مبلغ/كل>")
            all_in = args[1] == "كل"
            amount = user["money"] if all_in else parse_amount(args[1])
            if amount > user["money"]:
                raise ValueError("ما عندك المبلغ المطلوب.")
            user["money"] -= amount
            user["lastTrade"] = time.time()
            if random.random() < 0.52:
                gain = trade_profit(amount)
                credit_money(user, amount + gain)
                save_user(user)
                await message.reply(embed=card_embed("ربح التداول", f"رأس المال `{amount}` + ربح `{gain}`", COLOR_SUCCESS, "💹"))
            else:
                loss = trade_loss(amount, all_in)
                if not all_in:
                    user["money"] += amount - loss
                save_user(user)
                await message.reply(embed=card_embed("خسارة التداول", f"-{loss}", COLOR_DANGER, "📉"))
            return

        if cmd == "روليت":
            left = cooldown_left(user["lastRoulette"], ROULETTE_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر", f"الروليت كل 10 دقائق. باقي `{format_wait(left)}`.", COLOR_WARNING)
                )
                return
            user["lastRoulette"] = time.time()
            reward_type = random.choice(["money", "gold", "diamonds", "lands", "stocks"])
            if reward_type == "money":
                amount = random.randint(100, 450)
                credit_money(user, amount)
            elif reward_type == "gold":
                amount = random.randint(1, 4)
                user["gold"] += amount
                save_user(user)
            elif reward_type == "diamonds":
                amount = random.randint(1, 2)
                user["diamonds"] += amount
                save_user(user)
            elif reward_type == "lands":
                amount = 1
                user["lands"] += amount
                save_user(user)
            else:
                amount = random.randint(1, 4)
                user["stocks"] += amount
                save_user(user)
            reward = EVENT_REWARD_TYPES[reward_type]
            await message.reply(embed=card_embed("جائزة الروليت", f"{amount} {reward['label']}", reward["color"], reward["icon"]))
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
            credited, absorbed = credit_money(receiver, amount)
            save_user(user)
            await message.reply(embed=card_embed("تم التحويل", f"{amount} إلى {target.display_name}", COLOR_SUCCESS, "💸"))
            if absorbed > 0:
                await message.channel.send(f"تم استخدام `{absorbed}` من التحويل لتقليل الرصيد السالب لدى {target.mention}.", delete_after=10)
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
                await message.reply(embed=info_embed("انتظر", f"باقي `{format_wait(left)}` على السرقة.", COLOR_WARNING))
                return
            victim = get_user(target.id)
            if victim["money"] <= 0:
                raise ValueError("الهدف ما عنده فلوس.")
            protection_left = max(0, int(victim.get("protectionUntil", 0) - time.time()))
            if protection_left > 0:
                await message.reply(
                    embed=info_embed(
                        "الهدف عليه حماية",
                        f"باقي على الحماية `{format_wait(protection_left)}`.\nهل تريد محاولة تجاوز الحماية مقابل `{STEAL_PROTECTED_COST}`؟",
                        COLOR_WARNING,
                    ),
                    view=ProtectedStealConfirmView(message.author.id, target.id),
                )
                return
            stolen = resolve_steal_amount(victim["money"])
            victim["money"] -= stolen
            user["money"] += stolen
            user["lastSteal"] = time.time()
            save_user(victim)
            save_user(user)
            await message.reply(content=f"🚨 {target.mention}", embed=card_embed("المبلغ المسروق", str(stolen), 0xFF8C00, "🕵️"))
            return

        if cmd == "توب":
            all_users = list(data_store["users"].values())
            ranked = sorted(all_users, key=estimate_user_total_value, reverse=True)[:10]
            lines = []
            for index, ranked_user in enumerate(ranked, start=1):
                member = message.guild.get_member(int(ranked_user["userId"]))
                name = member.display_name if member else f"User {ranked_user['userId']}"
                lines.append(f"`#{index}` {name} - `{estimate_user_total_value(ranked_user)}`")
            embed = base_embed(COLOR_GOLD)
            embed.title = "أغنى اللاعبين"
            embed.description = "\n".join(lines) if lines else "لا يوجد بيانات بعد."
            await message.reply(embed=embed)
            return

        if cmd == "شراء" and len(args) >= 2 and args[1] == "شركة":
            quantity = 1 if len(args) < 3 else parse_amount(args[2])
            total = COMPANY_PRICE * quantity
            if user["money"] < total:
                raise ValueError(f"تحتاج `{total}` لشراء {quantity} شركة.")
            user["money"] -= total
            user["companies"] += quantity
            save_user(user)
            await message.reply(embed=card_embed("تم شراء شركة", f"{quantity} شركة مقابل {total}", COLOR_SUCCESS, "🏢"))
            return

        if cmd == "بيع" and len(args) >= 2 and args[1] == "شركة":
            quantity = 1 if len(args) < 3 else parse_amount(args[2])
            if user["companies"] < quantity:
                raise ValueError("ما عندك هذا العدد من الشركات.")
            include_stocks = len(args) >= 4 and args[3] in {"مع_الاسهم", "مع-الاسهم", "معالاسهم"}
            total_sale, bundled_stocks = calculate_company_sale_total(user, quantity, include_stocks)
            user["companies"] -= quantity
            if include_stocks and bundled_stocks > 0:
                user["stocks"] = 0
            credit_money(user, total_sale)
            save_user(user)
            sale_text = f"{quantity} شركة مقابل {total_sale}"
            if include_stocks:
                sale_text += f"\nتم نقل `{bundled_stocks}` أسهم مع الشركة"
            await message.reply(embed=card_embed("تم بيع الشركة", sale_text, COLOR_WARNING, "🏢"))
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
            await message.reply(embed=card_embed("تم الشراء", f"{quantity} {item['label']} مقابل {total_price}", COLOR_SUCCESS, item["icon"]))
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
            credit_money(user, total_price)
            save_user(user)
            await message.reply(embed=card_embed("تم البيع", f"{quantity} {item['label']} مقابل {total_price}", COLOR_WARNING, item["icon"]))
            return

    except ValueError as exc:
        await message.reply(embed=info_embed("خطأ", str(exc), COLOR_DANGER))
        return
    except Exception:
        logger.exception("Unexpected error while processing a message.")
        await message.reply(embed=info_embed("خطأ", "صار خطأ غير متوقع، حاول مرة ثانية.", COLOR_DANGER))
        return


threading.Thread(target=run_web_server, daemon=True).start()
ensure_token()
bot.run(DISCORD_TOKEN, log_handler=None)
