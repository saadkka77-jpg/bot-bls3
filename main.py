import asyncio
import json
import logging
import math
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

ADMIN_PANEL_CHANNEL_ID = 1498037576538259556
EVENT_PUBLIC_CHANNEL_ID = 1498037416672493829

ADMIN_ROLE_IDS = {
    1478970736717598840,
    1495873706923393205,
    1490386915629989948,
}

START_MONEY = 3000
INVEST_COOLDOWN = 180
TRADE_COOLDOWN = 180
STEAL_COOLDOWN = 300
DAILY_COOLDOWN = 86400
ROULETTE_COOLDOWN = 600
EVENT_DURATION_SECONDS = 300

PRICE_AUTO_UPDATE_SECONDS = 3600
AUCTION_INTERVAL_SECONDS = 1800
AUCTION_DURATION_SECONDS = 300
AUCTION_COUNTDOWN_SECONDS = 5
AUCTION_BID_CONFIRM_DELETE_AFTER = 60

COLOR_PRIMARY = 0x1E2124
COLOR_SUCCESS = 0x57F287
COLOR_DANGER = 0xED4245
COLOR_WARNING = 0xFEE75C
COLOR_INFO = 0x5865F2
COLOR_GOLD = 0xF1C40F
COLOR_LAND = 0x3BA55D

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
}

EVENT_REWARD_TYPES = {
    "money": {"label": "فلوس", "key": "money", "icon": "💵", "color": COLOR_SUCCESS},
    "gold": {"label": "ذهب", "key": "gold", "icon": "🥇", "color": COLOR_GOLD},
    "diamonds": {"label": "ألماس", "key": "diamonds", "icon": "💎", "color": COLOR_INFO},
    "lands": {"label": "أراضي", "key": "lands", "icon": "🏝️", "color": COLOR_LAND},
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
views_registered = False


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


def build_default_prices() -> dict[str, dict[str, int]]:
    prices: dict[str, dict[str, int]] = {}
    for key, item in ITEM_DEFINITIONS.items():
        prices[key] = {
            "buy_price": item["base_buy"],
            "sell_price": item["base_sell"],
        }
    return prices


def next_auction_timestamp() -> int:
    return int(time.time()) + AUCTION_INTERVAL_SECONDS


def load_data() -> dict[str, Any]:
    defaults = {
        "users": {},
        "active_event": None,
        "panel_message_id": None,
        "price_panel_message_id": None,
        "prices": build_default_prices(),
        "last_price_update": 0,
        "active_auction": None,
        "next_auction_at": next_auction_timestamp(),
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

    for item_key, item_prices in build_default_prices().items():
        existing = data["prices"].setdefault(item_key, item_prices)
        existing.setdefault("buy_price", item_prices["buy_price"])
        existing.setdefault("sell_price", item_prices["sell_price"])

    return data


def save_data() -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data_store, file, ensure_ascii=False, indent=2)


data_store = load_data()


def ensure_state() -> None:
    data_store.setdefault("users", {})
    data_store.setdefault("active_event", None)
    data_store.setdefault("panel_message_id", None)
    data_store.setdefault("price_panel_message_id", None)
    data_store.setdefault("prices", build_default_prices())
    data_store.setdefault("last_price_update", 0)
    data_store.setdefault("active_auction", None)
    data_store.setdefault("next_auction_at", next_auction_timestamp())

    for item_key, item_prices in build_default_prices().items():
        current = data_store["prices"].setdefault(item_key, item_prices)
        current.setdefault("buy_price", item_prices["buy_price"])
        current.setdefault("sell_price", item_prices["sell_price"])


ensure_state()


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


def reset_user_data(user: dict[str, Any]) -> None:
    user["money"] = START_MONEY
    user["gold"] = 0
    user["diamonds"] = 0
    user["lands"] = 0
    user["lastInvest"] = 0
    user["lastTrade"] = 0
    user["lastSteal"] = 0
    user["lastDaily"] = 0
    user["lastRoulette"] = 0


def get_user(user_id: int) -> dict[str, Any]:
    key = str(user_id)
    if key not in data_store["users"]:
        data_store["users"][key] = create_user(user_id)
        save_data()
    return data_store["users"][key]


def save_user(user: dict[str, Any]) -> None:
    data_store["users"][user["userId"]] = user
    save_data()


def has_admin_access(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    return any(role.id in ADMIN_ROLE_IDS for role in member.roles)


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


def get_price(item_key: str) -> dict[str, int]:
    return data_store["prices"][item_key]


def get_current_buy_price(item_key: str) -> int:
    return get_price(item_key)["buy_price"]


def get_current_sell_price(item_key: str) -> int:
    return get_price(item_key)["sell_price"]


def format_prices_lines() -> str:
    lines = []
    for item_key in ("gold", "diamonds", "lands"):
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
    embed = base_embed(COLOR_INFO)
    embed.title = "لوحة الإدارة"
    embed.description = (
        "هذه اللوحة خاصة بالإدارة فقط.\n"
        f"الأحداث والمزادات تنزل في روم الأعضاء: `{EVENT_PUBLIC_CHANNEL_ID}`\n"
        "كل حدث مدته `5 دقائق`.\n"
        "يوجد زر لتصفير الاقتصاد مع رسالة تأكيد قبل التنفيذ."
    )
    return embed


def price_panel_embed() -> discord.Embed:
    embed = base_embed(COLOR_GOLD)
    embed.title = "لوحة التحكم بالأسعار"
    embed.description = (
        f"{format_prices_lines()}\n\n"
        "الأسعار تتحرك تلقائيًا كل ساعة بشكل عشوائي، وتقدر تعدلها يدويًا من الأزرار."
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


def format_wait(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
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


def parse_item_key(raw_name: str) -> str:
    item_key = ITEM_ALIASES.get(raw_name)
    if not item_key:
        raise ValueError("العنصر غير معروف. استخدم: ذهب، الماس، ارض.")
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


def add_asset(user: dict[str, Any], key: str, amount: int) -> None:
    user[key] += amount


def recalculate_sell_price(item_key: str, buy_price: int) -> int:
    item = ITEM_DEFINITIONS[item_key]
    ratio = item["base_sell"] / item["base_buy"]
    step = max(50, item["step"] // 2)
    sell_price = int(round((buy_price * ratio) / step) * step)
    return max(step, sell_price)


def adjust_price(item_key: str, direction: int, auto: bool = False) -> tuple[int, int]:
    item = ITEM_DEFINITIONS[item_key]
    current = get_price(item_key)
    current_buy = current["buy_price"]

    if auto:
        multiplier = 1 + random.uniform(-0.15, 0.15)
        new_buy = int(round((current_buy * multiplier) / item["step"]) * item["step"])
        if new_buy == current_buy:
            new_buy = current_buy + random.choice((-item["step"], item["step"]))
    else:
        new_buy = current_buy + (item["step"] * direction)

    new_buy = max(item["min_buy"], new_buy)
    new_sell = recalculate_sell_price(item_key, new_buy)
    current["buy_price"] = new_buy
    current["sell_price"] = new_sell
    return new_buy, new_sell


def estimate_user_total_value(user: dict[str, Any]) -> int:
    return (
        user["money"]
        + user["gold"] * get_current_sell_price("gold")
        + user["diamonds"] * get_current_sell_price("diamonds")
        + user["lands"] * get_current_sell_price("lands")
    )


def get_active_event() -> dict[str, Any] | None:
    event = data_store.get("active_event")
    if not event:
        return None
    if event.get("expires_at", 0) <= time.time() or event.get("remaining", 0) <= 0:
        data_store["active_event"] = None
        save_data()
        return None
    return event


def set_active_event(event: dict[str, Any] | None) -> None:
    data_store["active_event"] = event
    save_data()


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

    save_data()
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
    save_data()


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
    save_data()


async def refresh_admin_room_panels() -> None:
    channel = bot.get_channel(ADMIN_PANEL_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        await update_panel_message(channel)
        await update_price_panel_message(channel)
    except discord.HTTPException:
        logger.exception("Failed to refresh admin room panels.")


def get_active_auction() -> dict[str, Any] | None:
    auction = data_store.get("active_auction")
    if not auction:
        return None
    return auction


def set_active_auction(auction: dict[str, Any] | None) -> None:
    data_store["active_auction"] = auction
    save_data()


def auction_embed(auction: dict[str, Any]) -> discord.Embed:
    item = ITEM_DEFINITIONS[auction["item_key"]]
    embed = base_embed(item["color"])
    embed.title = "مزاد جديد"

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

    embed.description = (
        f"{item['icon']} العنصر: `{item['label']}`\n"
        f"📦 الكمية: `{auction['quantity']}`\n"
        f"{top_bid_line}\n"
        f"{top_user_line}\n"
        f"{timer_line}\n"
        f"{status_line}"
    )
    return embed


async def update_auction_message() -> None:
    auction = get_active_auction()
    if not auction:
        return

    channel = bot.get_channel(auction["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(auction["message_id"])
        await message.edit(embed=auction_embed(auction), view=AuctionBidView())
    except discord.NotFound:
        pass
    except discord.HTTPException:
        logger.exception("Failed to update auction message.")


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


async def create_auction() -> None:
    if get_active_auction():
        return

    channel = bot.get_channel(EVENT_PUBLIC_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return

    item_key = random.choice(["gold", "diamonds", "lands"])
    item = ITEM_DEFINITIONS[item_key]
    current_buy = get_current_buy_price(item_key)
    quantity = item["auction_quantity"]
    starting_bid = max(item["step"], int(round((current_buy * quantity * 0.6) / item["step"]) * item["step"]))

    auction = {
        "item_key": item_key,
        "quantity": quantity,
        "starting_bid": starting_bid,
        "current_bid": 0,
        "current_winner_id": None,
        "channel_id": channel.id,
        "message_id": 0,
        "expires_at": time.time() + AUCTION_DURATION_SECONDS,
        "state": "running",
        "countdown_end_at": 0,
        "last_countdown_value": 0,
        "bid_history": [],
    }

    message = await channel.send(embed=auction_embed(auction), view=AuctionBidView())
    auction["message_id"] = message.id
    set_active_auction(auction)
    data_store["next_auction_at"] = next_auction_timestamp()
    save_data()


async def finish_auction_without_winner(reason: str) -> None:
    auction = get_active_auction()
    if not auction:
        return

    channel = bot.get_channel(auction["channel_id"])
    if isinstance(channel, discord.TextChannel):
        try:
            message = await channel.fetch_message(auction["message_id"])
            await message.edit(embed=info_embed("انتهى المزاد", reason, COLOR_WARNING), view=None)
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to finish auction message.")

    set_active_auction(None)


async def finish_auction_with_winner() -> None:
    auction = get_active_auction()
    if not auction:
        return

    best_bid = get_best_valid_bid(auction)
    channel = bot.get_channel(auction["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        set_active_auction(None)
        return

    if not best_bid:
        await finish_auction_without_winner("انتهى المزاد لكن لا يوجد مزايد يملك المبلغ حاليًا.")
        return

    winner = get_user(best_bid["user_id"])
    item = ITEM_DEFINITIONS[auction["item_key"]]
    winner["money"] -= best_bid["amount"]
    winner[auction["item_key"]] += auction["quantity"]
    save_user(winner)

    result_embed = base_embed(COLOR_SUCCESS)
    result_embed.title = "انتهى المزاد"
    result_embed.description = (
        f"🏆 الفائز: <@{best_bid['user_id']}>\n"
        f"{item['icon']} الجائزة: `{auction['quantity']}` {item['label']}\n"
        f"💰 السعر النهائي: `{best_bid['amount']}`"
    )

    try:
        message = await channel.fetch_message(auction["message_id"])
        await message.edit(embed=result_embed, view=None)
    except discord.NotFound:
        pass
    except discord.HTTPException:
        logger.exception("Failed to update final auction message.")

    set_active_auction(None)


async def run_auction_countdown_step(auction: dict[str, Any]) -> None:
    remaining = max(0, int(math.ceil(auction["countdown_end_at"] - time.time())))
    if remaining <= 0:
        await finish_auction_with_winner()
        return

    if remaining != auction.get("last_countdown_value"):
        auction["last_countdown_value"] = remaining
        save_data()
        channel = bot.get_channel(auction["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(f"⏳ ينتهي المزاد خلال `{remaining}`", delete_after=2)
            except discord.HTTPException:
                logger.exception("Failed to send auction countdown message.")
        await update_auction_message()


async def tick_auction_system() -> None:
    auction = get_active_auction()
    if not auction:
        if time.time() >= data_store.get("next_auction_at", 0):
            await create_auction()
        return

    if auction["state"] == "running":
        if time.time() >= auction["expires_at"]:
            if auction["current_bid"] <= 0:
                await finish_auction_without_winner("انتهت مدة المزاد بدون أي مزايدة.")
                return

            auction["state"] = "countdown"
            auction["countdown_end_at"] = time.time() + AUCTION_COUNTDOWN_SECONDS
            auction["last_countdown_value"] = 0
            save_data()
            await update_auction_message()
            await run_auction_countdown_step(auction)
    elif auction["state"] == "countdown":
        await run_auction_countdown_step(auction)


async def maybe_auto_update_prices() -> None:
    now = time.time()
    last_update = data_store.get("last_price_update", 0)
    if last_update <= 0:
        data_store["last_price_update"] = now
        save_data()
        return
    if now - last_update < PRICE_AUTO_UPDATE_SECONDS:
        return

    for item_key in ITEM_DEFINITIONS:
        adjust_price(item_key, 0, auto=True)

    data_store["last_price_update"] = now
    save_data()
    await refresh_admin_room_panels()


async def background_loop() -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await maybe_auto_update_prices()
            await tick_auction_system()
        except Exception:
            logger.exception("Background loop crashed.")
        await asyncio.sleep(1)


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
        add_asset(user, EVENT_REWARD_TYPES[event["reward_type"]]["key"], event["amount"])
        save_user(user)

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
        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتب المصرح لها.", ephemeral=True)
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


class ResetConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("استخدم هذه اللوحة داخل روم الإدارة فقط.", ephemeral=True)
            return False

        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتب المصرح لها.", ephemeral=True)
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

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True


class PriceControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("هذه اللوحة تعمل فقط في روم الإدارة.", ephemeral=True)
            return False

        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتب المصرح لها.", ephemeral=True)
            return False

        return True

    async def update_price(self, interaction: discord.Interaction, item_key: str, direction: int) -> None:
        new_buy, new_sell = adjust_price(item_key, direction, auto=False)
        save_data()
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


class AuctionBidModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="المزايدة على المزاد")
        self.bid_amount = discord.ui.TextInput(
            label="المبلغ",
            placeholder="اكتب مبلغ المزايدة",
            max_length=12,
        )
        self.add_item(self.bid_amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        auction = get_active_auction()
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
            await interaction.response.send_message(
                f"لازم تكون المزايدة `{minimum_required}` أو أعلى.",
                ephemeral=True,
            )
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

        save_data()
        await update_auction_message()

        await interaction.response.send_message("تم تسجيل مزايدتك.", ephemeral=True)

        channel = bot.get_channel(auction["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    content=f"📢 {interaction.user.mention}",
                    embed=info_embed(
                        "تمت المزايدة من قبل",
                        f"رفع المزاد إلى `{amount}` على {ITEM_DEFINITIONS[auction['item_key']]['label']}.",
                        COLOR_SUCCESS,
                    ),
                    delete_after=AUCTION_BID_CONFIRM_DELETE_AFTER,
                )
            except discord.HTTPException:
                logger.exception("Failed to send bid confirmation message.")


class AuctionBidView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="مزايدة", style=discord.ButtonStyle.success, custom_id="auction_bid_button")
    async def bid_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        auction = get_active_auction()
        if not auction:
            await interaction.response.send_message("لا يوجد مزاد نشط الآن.", ephemeral=True)
            return

        if interaction.channel_id != auction["channel_id"]:
            await interaction.response.send_message("هذا الزر خاص بروم المزاد فقط.", ephemeral=True)
            return

        await interaction.response.send_modal(AuctionBidModal())


class AdminPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def open_modal(self, interaction: discord.Interaction, reward_type: str) -> None:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("هذه اللوحة تعمل فقط في روم الإدارة.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتب المصرح لها.", ephemeral=True)
            return

        await interaction.response.send_modal(EventCreateModal(reward_type))

    @discord.ui.button(label="حدث فلوس", style=discord.ButtonStyle.success, custom_id="panel_money")
    async def money_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "money")

    @discord.ui.button(label="حدث ذهب", style=discord.ButtonStyle.secondary, custom_id="panel_gold")
    async def gold_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "gold")

    @discord.ui.button(label="حدث ألماس", style=discord.ButtonStyle.primary, custom_id="panel_diamonds")
    async def diamonds_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "diamonds")

    @discord.ui.button(label="حدث أراضي", style=discord.ButtonStyle.danger, custom_id="panel_lands")
    async def lands_event(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_modal(interaction, "lands")

    @discord.ui.button(label="تصفير الاقتصاد", style=discord.ButtonStyle.danger, custom_id="panel_reset_economy", row=1)
    async def reset_economy(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.channel_id != ADMIN_PANEL_CHANNEL_ID:
            await interaction.response.send_message("هذه اللوحة تعمل فقط في روم الإدارة.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not has_admin_access(interaction.user):
            await interaction.response.send_message("هذه اللوحة مخصصة فقط للرتب المصرح لها.", ephemeral=True)
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
    global background_task, views_registered

    logger.info("Logged in as %s", bot.user)

    if not views_registered:
        bot.add_view(AdminPanelView())
        bot.add_view(PriceControlView())
        bot.add_view(ClaimEventView())
        bot.add_view(AuctionBidView())
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
        if cmd in {"ممتلكاتي", "رصيدي", "فلوسي"}:
            await message.reply(embed=dashboard_embed(user, message.author))
            return

        if cmd in {"اوامر", "أوامر"}:
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
                "أوامر الإدارة: `لوحة الادارة`"
            )
            await message.reply(embed=embed)
            return

        if cmd == "شراء" and len(args) == 1:
            await message.reply(embed=shop_embed())
            return

        if cmd in {"اسعار", "أسعار"}:
            await message.reply(embed=shop_embed())
            return

        if cmd == "راتب":
            left = cooldown_left(user["lastDaily"], DAILY_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed("انتظر شوي", f"تقدر تستلم راتبك بعد `{format_wait(left)}`.", COLOR_WARNING)
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
                embed=card_embed("تم الشراء", f"{quantity} {item['label']} مقابل {total_price}", COLOR_SUCCESS, item["icon"])
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
                embed=card_embed("تم البيع", f"{quantity} {item['label']} مقابل {total_price}", COLOR_WARNING, item["icon"])
            )
            return

        if cmd == "لوحة" and len(args) > 1 and args[1] == "الادارة":
            if not isinstance(message.author, discord.Member) or not has_admin_access(message.author):
                raise ValueError("هذا الأمر فقط للرتب المصرح لها.")
            if message.channel.id != ADMIN_PANEL_CHANNEL_ID:
                raise ValueError(f"استخدم هذا الأمر داخل روم الإدارة: {ADMIN_PANEL_CHANNEL_ID}")
            await refresh_admin_room_panels()
            await message.reply(embed=info_embed("تم", "تم تحديث لوحات الإدارة والأسعار.", COLOR_SUCCESS), delete_after=8)
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
