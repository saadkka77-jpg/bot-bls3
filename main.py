import logging
import os
import random
import time
from typing import Any

import discord
from discord.ext import commands
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError


DEFAULT_STARTING_BALANCE = 1000
INVEST_COOLDOWN_SECONDS = 180
TRADE_COOLDOWN_SECONDS = 180
STEAL_COOLDOWN_SECONDS = 300
EMBED_COLOR = 0x2B2D31


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("economy-bot")


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_int_env(name: str) -> int:
    raw_value = get_required_env(name)
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc


def create_mongo() -> tuple[MongoClient, Database, Collection]:
    mongo_uri = get_required_env("MONGO_URI")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    database = client["economy"]
    collection = database["users"]
    collection.create_index("userId", unique=True)
    return client, database, collection


mongo_client, db, users = create_mongo()


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents)
allowed_guild_id = parse_int_env("ALLOWED_GUILD_ID")


def build_embed(title: str, description: str, color: int = EMBED_COLOR) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="نظام الاقتصاد")
    return embed


def get_default_user(user_id: int) -> dict[str, Any]:
    return {
        "userId": str(user_id),
        "money": DEFAULT_STARTING_BALANCE,
        "gold": 0,
        "diamonds": 0,
        "lands": 0,
        "lastInvest": 0,
        "lastTrade": 0,
        "lastSteal": 0,
    }


def get_user(user_id: int) -> dict[str, Any]:
    user = users.find_one({"userId": str(user_id)})
    if user:
        return user

    user = get_default_user(user_id)
    users.insert_one(user)
    return user


def save_user(user: dict[str, Any]) -> None:
    users.update_one({"userId": user["userId"]}, {"$set": user}, upsert=True)


def parse_amount(argument_list: list[str], money: int) -> int:
    if len(argument_list) < 2:
        raise ValueError("لازم تحدد مبلغ أو تكتب `كل`.")

    raw_amount = argument_list[1]
    if raw_amount == "كل":
        amount = money
    else:
        try:
            amount = int(raw_amount)
        except ValueError as exc:
            raise ValueError("المبلغ لازم يكون رقم صحيح أو `كل`.") from exc

    if amount <= 0:
        raise ValueError("المبلغ لازم يكون أكبر من 0.")

    return amount


def remaining_cooldown(last_time: float, cooldown_seconds: int) -> int:
    return max(0, int(cooldown_seconds - (time.time() - last_time)))


def format_assets(user: dict[str, Any]) -> str:
    return (
        f"💵 المال: {user['money']}\n"
        f"🥇 الذهب: {user['gold']}\n"
        f"💎 الألماس: {user['diamonds']}\n"
        f"🏝️ الأراضي: {user['lands']}"
    )


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if message.guild is None or message.guild.id != allowed_guild_id:
        return

    content = message.content.strip()
    if not content:
        return

    args = content.split()
    command_name = args[0]
    user = get_user(message.author.id)

    try:
        if command_name == "ممتلكاتي":
            await message.reply(
                embed=build_embed("📊 ممتلكاتك", format_assets(user), 0x00BCD4)
            )
            return

        if command_name == "استثمار":
            cooldown = remaining_cooldown(user["lastInvest"], INVEST_COOLDOWN_SECONDS)
            if cooldown > 0:
                await message.reply(
                    embed=build_embed("⏳", f"انتظر {cooldown} ثانية قبل الاستثمار مرة ثانية.")
                )
                return

            amount = parse_amount(args, user["money"])
            if user["money"] < amount:
                await message.reply(embed=build_embed("❌", "ما عندك المبلغ المطلوب."))
                return

            user["money"] -= amount
            user["lastInvest"] = time.time()
            change = int(amount * random.uniform(0, 0.5))

            if random.random() < 0.5:
                user["money"] += amount + change
                await message.reply(
                    embed=build_embed("📈 نجاح الاستثمار", f"ربحت {change} 💵", 0x4CAF50)
                )
            else:
                await message.reply(
                    embed=build_embed("📉 خسارة الاستثمار", f"خسرت {change} 💵", 0xF44336)
                )

            save_user(user)
            return

        if command_name == "تداول":
            cooldown = remaining_cooldown(user["lastTrade"], TRADE_COOLDOWN_SECONDS)
            if cooldown > 0:
                await message.reply(
                    embed=build_embed("⏳", f"انتظر {cooldown} ثانية قبل التداول مرة ثانية.")
                )
                return

            amount = parse_amount(args, user["money"])
            if user["money"] < amount:
                await message.reply(embed=build_embed("❌", "ما عندك المبلغ المطلوب."))
                return

            user["money"] -= amount
            user["lastTrade"] = time.time()
            change = int(amount * random.uniform(0, 0.7))

            if random.random() < 0.5:
                user["money"] += amount + change
                await message.reply(embed=build_embed("💹 ربح", f"ربحت {change} 💵", 0x4CAF50))
            else:
                await message.reply(
                    embed=build_embed("📉 خسارة", f"خسرت {change} 💵", 0xF44336)
                )

            save_user(user)
            return

        if command_name == "روليت":
            reward_type = random.randint(0, 3)

            if reward_type == 0:
                amount = random.randint(1, 500)
                user["gold"] += amount
                reward_text = f"🥇 حصلت على {amount} ذهب"
            elif reward_type == 1:
                amount = random.randint(1, 300)
                user["diamonds"] += amount
                reward_text = f"💎 حصلت على {amount} ألماس"
            elif reward_type == 2:
                amount = random.randint(1, 3)
                user["lands"] += amount
                reward_text = f"🏝️ حصلت على {amount} أرض"
            else:
                amount = random.randint(1, 1000)
                user["money"] += amount
                reward_text = f"💵 حصلت على {amount} مال"

            save_user(user)
            await message.reply(embed=build_embed("🎰 روليت", reward_text, 0x9C27B0))
            return

        if command_name == "سرقة":
            if not message.mentions:
                await message.reply(embed=build_embed("❌", "حدد الشخص اللي تبي تسرقه."))
                return

            target = message.mentions[0]
            if target.bot:
                await message.reply(embed=build_embed("❌", "ما تقدر تسرق بوت."))
                return

            if target.id == message.author.id:
                await message.reply(embed=build_embed("❌", "ما تقدر تسرق نفسك."))
                return

            cooldown = remaining_cooldown(user["lastSteal"], STEAL_COOLDOWN_SECONDS)
            if cooldown > 0:
                await message.reply(
                    embed=build_embed("⏳", f"انتظر {cooldown} ثانية قبل السرقة مرة ثانية.")
                )
                return

            victim = get_user(target.id)
            if victim["money"] <= 0:
                await message.reply(embed=build_embed("❌", "الشخص هذا ما عنده فلوس."))
                return

            stolen = random.randint(1, victim["money"])
            victim["money"] -= stolen
            user["money"] += stolen
            user["lastSteal"] = time.time()

            save_user(victim)
            save_user(user)

            await message.reply(
                content=f"🚨 {target.mention}",
                embed=build_embed("🕵️ نهب!", f"تمت سرقة {stolen} 💵", 0xFF9800),
            )
            return

    except ValueError as exc:
        await message.reply(embed=build_embed("❌", str(exc)))
        return
    except PyMongoError:
        logger.exception("Database operation failed.")
        await message.reply(
            embed=build_embed("⚠️", "صار خطأ في قاعدة البيانات، حاول مرة ثانية بعد شوي.")
        )
        return
    except Exception:
        logger.exception("Unexpected error while processing message.")
        await message.reply(embed=build_embed("⚠️", "صار خطأ غير متوقع."))
        return


def main() -> None:
    token = get_required_env("DISCORD_TOKEN")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
