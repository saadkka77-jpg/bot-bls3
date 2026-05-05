import json
import logging
import os
import random
import time
from pathlib import Path

import discord
from discord.ext import commands

DATA_FILE = Path("economy_data.json")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# إذا تبي تخليه لسيرفر واحد فقط، حط الآيدي هنا
ALLOWED_GUILD_ID = None
# مثال:
# ALLOWED_GUILD_ID = 1498037416672493829

START_MONEY = 1000
INVEST_COOLDOWN = 180
TRADE_COOLDOWN = 180
STEAL_COOLDOWN = 300
DAILY_COOLDOWN = 86400

COLOR_PRIMARY = 0x2B2D31
COLOR_SUCCESS = 0x57F287
COLOR_DANGER = 0xED4245
COLOR_WARNING = 0xFEE75C
COLOR_INFO = 0x5865F2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("economy-bot")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="", intents=intents, help_command=None)


def ensure_token():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing in environment variables.")


def load_data():
    if not DATA_FILE.exists():
        return {}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load data file.")
        return {}


def save_data(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


economy_data = load_data()


def create_user(user_id: int):
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
    }


def get_user(user_id: int):
    user_id = str(user_id)
    if user_id not in economy_data:
        economy_data[user_id] = create_user(int(user_id))
        save_data(economy_data)
    return economy_data[user_id]


def save_user(user):
    economy_data[user["userId"]] = user
    save_data(economy_data)


def card_embed(title: str, value: str, color: int, icon: str = "💰"):
    embed = discord.Embed(color=color)
    embed.add_field(name=f"{icon} {title}", value=f"```{value}```", inline=False)
    embed.set_footer(text="BLS Economy")
    return embed


def info_embed(title: str, description: str, color: int = COLOR_PRIMARY):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="BLS Economy")
    return embed


def format_assets(user):
    return (
        f"💵 المال: {user['money']}\n"
        f"🥇 الذهب: {user['gold']}\n"
        f"💎 الألماس: {user['diamonds']}\n"
        f"🏝️ الأراضي: {user['lands']}"
    )


def parse_amount(args, balance: int):
    if len(args) < 2:
        raise ValueError("اكتب المبلغ أو اكتب `كل`.")

    raw = args[1].strip()

    if raw == "كل":
        amount = balance
    else:
        if not raw.isdigit():
            raise ValueError("المبلغ لازم يكون رقم صحيح أو `كل`.")
        amount = int(raw)

    if amount <= 0:
        raise ValueError("المبلغ لازم يكون أكبر من 0.")

    return amount


def cooldown_left(last_time: float, cooldown: int):
    remaining = int(cooldown - (time.time() - last_time))
    return max(0, remaining)


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if ALLOWED_GUILD_ID is not None:
        if message.guild is None or message.guild.id != ALLOWED_GUILD_ID:
            return

    content = message.content.strip()
    if not content:
        return

    args = content.split()
    cmd = args[0].lower()
    user = get_user(message.author.id)

    try:
        if cmd in ["ممتلكاتي", "رصيدي", "فلوسي"]:
            await message.reply(
                embed=info_embed("ممتلكاتك", format_assets(user), COLOR_INFO)
            )
            return

        if cmd == "راتب":
            left = cooldown_left(user["lastDaily"], DAILY_COOLDOWN)
            if left > 0:
                hours = left // 3600
                minutes = (left % 3600) // 60
                await message.reply(
                    embed=info_embed(
                        "انتظر شوي",
                        f"تقدر تستلم راتبك بعد `{hours} ساعة و {minutes} دقيقة`.",
                        COLOR_WARNING,
                    )
                )
                return

            salary = random.randint(500, 2000)
            user["money"] += salary
            user["lastDaily"] = time.time()
            save_user(user)

            await message.reply(
                embed=card_embed("راتبك", str(salary), COLOR_WARNING, "💰")
            )
            return

        if cmd == "استثمار":
            left = cooldown_left(user["lastInvest"], INVEST_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed(
                        "انتظر",
                        f"باقي `{left}` ثانية على الاستثمار.",
                        COLOR_WARNING,
                    )
                )
                return

            amount = parse_amount(args, user["money"])

            if user["money"] < amount:
                await message.reply(
                    embed=info_embed("خطأ", "ما عندك المبلغ المطلوب.", COLOR_DANGER)
                )
                return

            user["money"] -= amount
            user["lastInvest"] = time.time()
            profit_or_loss = int(amount * random.uniform(0.10, 0.50))

            if random.random() < 0.55:
                user["money"] += amount + profit_or_loss
                save_user(user)
                await message.reply(
                    embed=card_embed("ربح الاستثمار", f"+{profit_or_loss}", COLOR_SUCCESS, "📈")
                )
            else:
                save_user(user)
                await message.reply(
                    embed=card_embed("خسارة الاستثمار", f"-{profit_or_loss}", COLOR_DANGER, "📉")
                )
            return

        if cmd == "تداول":
            left = cooldown_left(user["lastTrade"], TRADE_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed(
                        "انتظر",
                        f"باقي `{left}` ثانية على التداول.",
                        COLOR_WARNING,
                    )
                )
                return

            amount = parse_amount(args, user["money"])

            if user["money"] < amount:
                await message.reply(
                    embed=info_embed("خطأ", "ما عندك المبلغ المطلوب.", COLOR_DANGER)
                )
                return

            user["money"] -= amount
            user["lastTrade"] = time.time()
            profit_or_loss = int(amount * random.uniform(0.15, 0.70))

            if random.random() < 0.50:
                user["money"] += amount + profit_or_loss
                save_user(user)
                await message.reply(
                    embed=card_embed("ربح التداول", f"+{profit_or_loss}", COLOR_SUCCESS, "💹")
                )
            else:
                save_user(user)
                await message.reply(
                    embed=card_embed("خسارة التداول", f"-{profit_or_loss}", COLOR_DANGER, "📉")
                )
            return

        if cmd == "روليت":
            reward_type = random.randint(0, 3)

            if reward_type == 0:
                amount = random.randint(1, 500)
                user["gold"] += amount
                save_user(user)
                await message.reply(
                    embed=card_embed("جائزتك", f"{amount} ذهب", COLOR_WARNING, "🥇")
                )
                return

            if reward_type == 1:
                amount = random.randint(1, 300)
                user["diamonds"] += amount
                save_user(user)
                await message.reply(
                    embed=card_embed("جائزتك", f"{amount} ألماس", COLOR_INFO, "💎")
                )
                return

            if reward_type == 2:
                amount = random.randint(1, 3)
                user["lands"] += amount
                save_user(user)
                await message.reply(
                    embed=card_embed("جائزتك", f"{amount} أرض", 0x3BA55D, "🏝️")
                )
                return

            amount = random.randint(1, 1500)
            user["money"] += amount
            save_user(user)
            await message.reply(
                embed=card_embed("جائزتك", f"{amount}", COLOR_SUCCESS, "💵")
            )
            return

        if cmd == "سرقة":
            if not message.mentions:
                await message.reply(
                    embed=info_embed("خطأ", "منشن الشخص اللي تبي تسرقه.", COLOR_DANGER)
                )
                return

            target = message.mentions[0]

            if target.bot:
                await message.reply(
                    embed=info_embed("خطأ", "ما تقدر تسرق بوت.", COLOR_DANGER)
                )
                return

            if target.id == message.author.id:
                await message.reply(
                    embed=info_embed("خطأ", "ما تقدر تسرق نفسك.", COLOR_DANGER)
                )
                return

            left = cooldown_left(user["lastSteal"], STEAL_COOLDOWN)
            if left > 0:
                await message.reply(
                    embed=info_embed(
                        "انتظر",
                        f"باقي `{left}` ثانية على السرقة.",
                        COLOR_WARNING,
                    )
                )
                return

            victim = get_user(target.id)

            if victim["money"] <= 0:
                await message.reply(
                    embed=info_embed("فشل", "الهدف ما عنده فلوس.", COLOR_DANGER)
                )
                return

            stolen = random.randint(1, max(1, min(victim["money"], 2000)))
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

        if cmd == "اوامر":
            await message.reply(
                embed=info_embed(
                    "الأوامر",
                    "`ممتلكاتي`\n`راتب`\n`استثمار <مبلغ/كل>`\n`تداول <مبلغ/كل>`\n`روليت`\n`سرقة @شخص`",
                    COLOR_INFO,
                )
            )
            return

    except ValueError as exc:
        await message.reply(embed=info_embed("خطأ", str(exc), COLOR_DANGER))
    except Exception:
        logger.exception("Unexpected error while handling message.")
        await message.reply(
            embed=info_embed("خطأ", "صار خطأ غير متوقع، حاول مرة ثانية.", COLOR_DANGER)
        )


ensure_token()
bot.run(DISCORD_TOKEN, log_handler=None)
