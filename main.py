import asyncio
import datetime as dt
import json
import os
import re
import sqlite3
import uuid

from pathlib import Path
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands


# ======================================================
# الإعدادات
# ======================================================

BOT_NAME = "ميلان بوت"
GUILD_ID = 1556038627170066463
TOKEN = os.getenv("MILAN_BOT_TOKEN", "").strip()

# الصلاحيات للرتب الثلاث فقط.
# لا توجد صلاحية إضافية تلقائية للأدمن أو صاحب السيرفر.
ADMIN_ROLES = {
    1556038791922327652,
    1556038793386008699,
    1556038812298121277,
}

LOG_CHANNEL = 1556039742485827707

POINTS_CHANNELS = {
    1556039842230566949,
    1556039678774214768,
}

AUDIT_CHANNEL = 1557928608662823042
ADJUST_CHANNEL = AUDIT_CHANNEL
WARNING_CHANNEL = 1556039849088258200
SCENARIO_CHANNEL = 1556039764996522074

# الأولوية إذا حمل الشخص أكثر من رتبة:
# هاي، ثم لو هاي، ثم عادي.
REQUIREMENTS = [
    (1556038839380877392, "هاي", 7),
    (1556038840513200260, "لو هاي", 10),
    (1556038858284736603, "عادي ادمن", 13),
]

TASK_CHANNELS = {
    1556039749360422922: "مهام الباند",
    1556039753344753754: "مهام التعويض",
    1556039757866344489: "مهام الدعم الفني",
    1556039761893003386: "مهام الادمن منجر",
    1556039764996522074: "مراقبة السيناريوهات",
}

POINTS_PER_TASK = 1
MAX_IMAGE_MB = 10
ALLOW_SELF_REVIEW = False


# ======================================================
# قاعدة البيانات ونقل بيانات النسخة السابقة
# ======================================================

if not hasattr(discord.ui, "FileUpload"):
    raise SystemExit("ثبّت discord.py إصدار 2.7 أو أحدث.")

BASE = Path(
    os.getenv(
        "MILAN_DATA_DIR",
        str(Path(__file__).resolve().parent / "data"),
    )
)

IMAGES = BASE / "images"
IMAGES.mkdir(parents=True, exist_ok=True)

DB = sqlite3.connect(BASE / "tasks.sqlite")
DB.execute("PRAGMA journal_mode=WAL")

for table in ("tasks", "audits", "events"):
    DB.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )

DB.execute("""
    CREATE TABLE IF NOT EXISTS ledger (
        ref TEXT PRIMARY KEY,
        user INTEGER NOT NULL,
        delta INTEGER NOT NULL,
        at REAL NOT NULL
    )
""")

# نقل نقاط المهام المقبولة من النسخة السابقة مرة واحدة.
# لا ترجع النقاط القديمة بعد التصفير.
for row in DB.execute("SELECT payload FROM tasks").fetchall():
    task = json.loads(row[0])

    if task["status"] == "accepted":
        DB.execute(
            "INSERT OR IGNORE INTO ledger VALUES (?, ?, ?, ?)",
            (
                f"task:{task['id']}",
                task["user"],
                task.get("awarded", 1),
                task.get("reviewed", 0),
            ),
        )

DB.commit()
LOCKS = {}


def now():
    return dt.datetime.now(dt.timezone.utc)


def put(table, item):
    DB.execute(
        f"""
        INSERT INTO {table} VALUES (?, ?)
        ON CONFLICT(id)
        DO UPDATE SET payload=excluded.payload
        """,
        (
            str(item["id"]),
            json.dumps(item, ensure_ascii=False),
        ),
    )


def save(item, table="tasks"):
    put(table, item)
    DB.commit()


def load(item_id, table="tasks"):
    result = DB.execute(
        f"SELECT payload FROM {table} WHERE id=?",
        (str(item_id),),
    ).fetchone()

    return json.loads(result[0]) if result else None


def records(table="tasks"):
    return [
        json.loads(row[0])
        for row in DB.execute(
            f"SELECT payload FROM {table}"
        ).fetchall()
    ]


def balance(user_id):
    return DB.execute(
        """
        SELECT COALESCE(SUM(delta), 0)
        FROM ledger
        WHERE user=?
        """,
        (user_id,),
    ).fetchone()[0]


def clean(text):
    return discord.utils.escape_markdown(
        discord.utils.escape_mentions(str(text))
    ).strip()


def admin(interaction):
    return (
        interaction.guild_id == GUILD_ID
        and isinstance(interaction.user, discord.Member)
        and any(
            role.id in ADMIN_ROLES
            for role in interaction.user.roles
        )
    )


def error_log(error):
    print(
        f"خطأ: {type(error).__name__} "
        f"| code={getattr(error, 'code', '-')}",
        flush=True,
    )


async def reply(interaction, text):
    # جميع ردود السيرفر عامة وثابتة.
    if interaction.response.is_done():
        await interaction.followup.send(text)
    else:
        await interaction.response.send_message(text)


# ======================================================
# التحقق من المسودة والمراجعة
# ======================================================

def draft(task, interaction):
    if not bot.ready or interaction.guild_id != GUILD_ID:
        raise ValueError("البوت غير جاهز الآن.")

    if (
        not task
        or task["user"] != interaction.user.id
        or task["channel"] != interaction.channel_id
        or task["status"] != "draft"
    ):
        raise ValueError("المعاينة غير متاحة لك أو سبق إرسالها.")

    if now().timestamp() - task["created"] > 86400:
        raise ValueError("انتهت المسودة. افتح مهمة جديدة.")


def review(task, interaction):
    if (
        not bot.ready
        or not task
        or task["channel"] != interaction.channel_id
    ):
        raise ValueError("المهمة غير متاحة.")

    if (
        interaction.message
        and interaction.message.id != task.get("message")
    ):
        raise ValueError("بطاقة المهمة غير صالحة.")

    if not ALLOW_SELF_REVIEW and task["user"] == interaction.user.id:
        raise ValueError("لا يمكنك مراجعة مهمتك بنفسك.")

    if task["status"] != "pending":
        raise ValueError(
            "سبق اتخاذ قرار للمهمة. لم تُحتسب نقاط إضافية."
        )


# ======================================================
# الصور وبطاقة المهمة
# ======================================================

def image_extension(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    raise ValueError("ارفع صورة PNG أو JPG أو GIF أو WEBP.")


def files(task):
    return [
        discord.File(IMAGES / name, filename=name)
        for name in task["images"]
    ]


def ref(task, kind):
    return f"مرجع: {task['id']}:{kind}"


def task_view(task):
    view = discord.ui.LayoutView(timeout=None)

    state = {
        "draft": "📝 معاينة",
        "pending": "⏳ بانتظار المراجعة",
        "accepted": "✅ مقبولة",
        "rejected": "❌ مرفوضة",
    }[task["status"]]

    text = (
        f"## {TASK_CHANNELS[task['channel']]}\n"
        f"**الإداري:** <@{task['user']}>\n"
        f"**الحالة:** {state}\n"
    )

    fields = task["fields"]

    if fields.get("description"):
        text += f"**التفاصيل:** {clean(fields['description'])}\n"

    if fields.get("start"):
        text += (
            f"**وقت البداية:** {clean(fields['start'])}\n"
            f"**وقت النهاية:** {clean(fields['end'])}\n"
        )

    for key, title in [
        ("police", "آيديات العسكر"),
        ("criminals", "آيديات المجرمين"),
        ("winner", "الفائز"),
    ]:
        if fields.get(key):
            text += f"**{title}:** {clean(fields[key])}\n"

    # التاريخ والوقت تلقائيان، لا يُطلبان في النموذج.
    text += (
        f"**تاريخ الإرسال:** <t:{int(task['created'])}:F>\n"
    )

    if task.get("reviewer"):
        text += f"**المسؤول:** <@{task['reviewer']}>\n"

    text += f"-# {ref(task, 'task')}"

    color = (
        0x22C55E if task["status"] == "accepted"
        else 0xEF4444 if task["status"] == "rejected"
        else 0x5865F2
    )

    box = discord.ui.Container(accent_colour=color)
    box.add_item(discord.ui.TextDisplay(text))

    if task["images"]:
        gallery = discord.ui.MediaGallery()

        for index, name in enumerate(task["images"]):
            if task["channel"] == SCENARIO_CHANNEL:
                caption = [
                    "المتفاوض والمجرمون",
                    "نهاية السيناريو",
                ][min(index, 1)]
            else:
                caption = "إثبات المهمة"

            gallery.add_item(
                media=f"attachment://{name}",
                description=caption,
            )

        box.add_item(gallery)

    if task["status"] == "draft":
        options = [
            ("add", "+ تعديل الصور", 2, False),
            ("form", "كتابة البيانات", 1, False),
            ("send", "إرسال", 3, not bool(fields.get("start"))),
            ("cancel", "إلغاء", 4, False),
        ]
    else:
        options = [
            ("accept", "قبول", 3, task["status"] != "pending"),
            ("reject", "رفض", 4, task["status"] != "pending"),
        ]

    row = discord.ui.ActionRow()

    for action, label, style, disabled in options:
        row.add_item(
            TaskButton(
                task["id"],
                action,
                label,
                style,
                disabled,
            )
        )

    box.add_item(row)
    view.add_item(box)
    return view


class TaskButton(discord.ui.Button):
    def __init__(
        self, task_id, action, label, style, disabled
    ):
        super().__init__(
            label=label,
            style=discord.ButtonStyle(style),
            custom_id=f"task:{action}:{task_id}",
            disabled=disabled,
        )

        self.task_id = task_id
        self.action = action

    async def callback(self, interaction):
        if self.action in ("accept", "reject") and not admin(interaction):
            return

        try:
            task = load(self.task_id)

            if self.action in ("accept", "reject"):
                review(task, interaction)

                if self.action == "reject":
                    await interaction.response.send_modal(
                        RejectModal(self.task_id)
                    )
                else:
                    await decide(
                        interaction,
                        self.task_id,
                        "accepted",
                    )
                return

            lock = LOCKS.setdefault(
                self.task_id,
                asyncio.Lock(),
            )

            if lock.locked():
                raise ValueError("انتظر العملية الحالية.")

            async with lock:
                task = load(self.task_id)
                draft(task, interaction)

                if self.action == "add":
                    await interaction.response.send_modal(
                        UploadModal(task)
                    )

                elif self.action == "form":
                    if not task["images"]:
                        raise ValueError("أضف الصور أولًا.")

                    await interaction.response.send_modal(
                        DetailsModal(task)
                    )

                else:
                    if self.action == "send" and (
                        not task["images"]
                        or not task["fields"].get("start")
                        or (
                            task["channel"] == SCENARIO_CHANNEL
                            and len(task["images"]) != 2
                        )
                    ):
                        raise ValueError("أكمل الصور والبيانات.")

                    task["status"] = (
                        "publishing"
                        if self.action == "send"
                        else "cancelled"
                    )
                    save(task)

                    view = discord.ui.LayoutView(timeout=None)
                    view.add_item(
                        discord.ui.TextDisplay(
                            "✅ تم استلام المهمة للنشر."
                            if self.action == "send"
                            else "تم الإلغاء."
                        )
                    )

                    await interaction.response.edit_message(
                        view=view,
                        attachments=[],
                    )

        except ValueError as error:
            await reply(interaction, str(error))

        except Exception as error:
            error_log(error)
            await reply(
                interaction,
                "تعذر تنفيذ العملية الآن.",
            )


# ======================================================
# نماذج الصور والبيانات والرفض
# ======================================================

class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction, error):
        error_log(error)
        await reply(
            interaction,
            "تعذر حفظ النموذج الآن. أعد المحاولة.",
        )


class UploadModal(SafeModal):
    def __init__(self, task):
        super().__init__(
            title="صور المهمة",
            timeout=900,
        )
        self.task_id = task["id"]
        scenario = task["channel"] == SCENARIO_CHANNEL

        self.first = discord.ui.FileUpload(
            min_values=1,
            max_values=1,
            required=True,
        )

        self.second = discord.ui.FileUpload(
            min_values=1 if scenario else 0,
            max_values=1,
            required=scenario,
        )

        self.add_item(
            discord.ui.Label(
                text=(
                    "صورة المتفاوض والمجرمين"
                    if scenario
                    else "صورة إثبات المهمة"
                ),
                component=self.first,
            )
        )

        self.add_item(
            discord.ui.Label(
                text=(
                    "صورة نهاية السيناريو"
                    if scenario
                    else "صورة إضافية (اختياري)"
                ),
                component=self.second,
            )
        )

    async def on_submit(self, interaction):
        lock = LOCKS.setdefault(
            self.task_id,
            asyncio.Lock(),
        )

        if lock.locked():
            return await reply(
                interaction,
                "انتظر العملية الحالية.",
            )

        async with lock:
            try:
                task = load(self.task_id)
                draft(task, interaction)

                await interaction.response.defer(thinking=True)

                names = []
                uploaded = self.first.values + self.second.values

                for index, attachment in enumerate(uploaded):
                    if (
                        not (attachment.content_type or "").startswith("image/")
                        or attachment.size > MAX_IMAGE_MB * 1024 * 1024
                    ):
                        raise ValueError(
                            f"ارفع صورة لا تتجاوز {MAX_IMAGE_MB} ميجابايت."
                        )

                    data = await asyncio.wait_for(
                        attachment.read(),
                        30,
                    )

                    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
                        raise ValueError("الصورة كبيرة.")

                    name = (
                        f"{task['id']}-{index}-"
                        f"{uuid.uuid4().hex}.{image_extension(data)}"
                    )

                    (IMAGES / name).write_bytes(data)
                    names.append(name)

                task["images"] = names
                save(task)

                await interaction.edit_original_response(
                    content=None,
                    embeds=[],
                    attachments=files(task),
                    view=task_view(task),
                )

            except ValueError as error:
                if interaction.response.is_done():
                    await interaction.edit_original_response(
                        content=str(error)
                    )
                else:
                    await reply(interaction, str(error))


class DetailsModal(SafeModal):
    def __init__(self, task):
        super().__init__(
            title="بيانات المهمة",
            timeout=900,
        )
        self.task_id = task["id"]
        self.fields = {}

        spec = [
            ("start", "وقت البداية فقط — مثال 21:30", 5),
            ("end", "وقت النهاية فقط — مثال 22:00", 5),
        ]

        if task["channel"] == SCENARIO_CHANNEL:
            spec += [
                ("police", "آيديات العسكر", 350),
                ("criminals", "آيديات المجرمين", 350),
                ("winner", "الفائز", 100),
            ]
        else:
            spec += [
                ("description", "تفاصيل المهمة", 1000),
            ]

        for key, title, maximum in spec:
            default = task["fields"].get(key)

            if default and len(default) > maximum:
                default = None

            item = discord.ui.TextInput(
                required=True,
                max_length=maximum,
                default=default,
                style=(
                    discord.TextStyle.paragraph
                    if maximum > 100
                    else discord.TextStyle.short
                ),
            )

            self.fields[key] = item
            self.add_item(
                discord.ui.Label(
                    text=title,
                    component=item,
                )
            )

    async def on_submit(self, interaction):
        try:
            lock = LOCKS.setdefault(
                self.task_id,
                asyncio.Lock(),
            )

            if lock.locked():
                raise ValueError("انتظر العملية الحالية.")

            async with lock:
                task = load(self.task_id)
                draft(task, interaction)

                values = {
                    key: field.value.strip()
                    for key, field in self.fields.items()
                }

                if not all(values.values()):
                    raise ValueError("أكمل الحقول.")

                for key in ("start", "end"):
                    if not re.fullmatch(
                        r"(?:[01]\d|2[0-3]):[0-5]\d",
                        values[key],
                    ):
                        raise ValueError(
                            "اكتب الوقت بصيغة 24 ساعة، مثل 21:30."
                        )

                task["fields"] = values
                save(task)

                await interaction.response.defer(thinking=True)

                await interaction.edit_original_response(
                    content=None,
                    embeds=[],
                    attachments=files(task),
                    view=task_view(task),
                )

        except ValueError as error:
            await reply(interaction, str(error))


class RejectModal(SafeModal):
    def __init__(self, task_id):
        super().__init__(
            title="رفض المهمة",
            timeout=900,
        )
        self.task_id = task_id

        self.reason = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=700,
            required=True,
        )

        self.add_item(
            discord.ui.Label(
                text="سبب الرفض",
                component=self.reason,
            )
        )

    async def on_submit(self, interaction):
        if not admin(interaction):
            return

        try:
            reason = self.reason.value.strip()

            if not reason:
                raise ValueError("اكتب سبب الرفض.")

            await decide(
                interaction,
                self.task_id,
                "rejected",
                reason,
            )

        except ValueError as error:
            await reply(interaction, str(error))


# ======================================================
# القرار — احتساب مرة واحدة فقط
# ======================================================

async def decide(
    interaction,
    task_id,
    status,
    reason="",
):
    if not admin(interaction):
        return

    try:
        DB.execute("BEGIN IMMEDIATE")

        task = load(task_id)
        review(task, interaction)

        task.update(
            status=status,
            reason=reason,
            reviewer=interaction.user.id,
            reviewed=now().timestamp(),
            awarded=POINTS_PER_TASK if status == "accepted" else 0,
            accept_count=1 if status == "accepted" else 0,
            dm_state="pending",
            updated=False,
        )

        if status == "accepted":
            DB.execute(
                "INSERT INTO ledger VALUES (?, ?, ?, ?)",
                (
                    f"task:{task_id}",
                    task["user"],
                    POINTS_PER_TASK,
                    task["reviewed"],
                ),
            )

        task["points_at_decision"] = balance(task["user"])
        put("tasks", task)
        DB.commit()

    except Exception:
        DB.rollback()
        raise

    await reply(
        interaction,
        "✅ تم قبول المهمة مرة واحدة."
        if status == "accepted"
        else "❌ تم رفض المهمة.",
    )


# ======================================================
# إشعار الخاص واللوق المختصر
# ======================================================

def decision_embed(task, private=False):
    accepted = task["status"] == "accepted"

    embed = discord.Embed(
        title="✅ تم قبول المهام" if accepted else "❌ تم رفض المهام",
        color=0x22C55E if accepted else 0xEF4444,
        timestamp=dt.datetime.fromtimestamp(
            task["reviewed"],
            dt.timezone.utc,
        ),
    )

    link = (
        f"https://discord.com/channels/{GUILD_ID}/"
        f"{task['channel']}/{task['message']}"
    )

    if private:
        embed.description = (
            f"**المسؤول:** <@{task['reviewer']}>"
        )

        if accepted:
            embed.description += (
                f"\n**مجموع نقاطك:** {task['points_at_decision']}"
            )
        else:
            embed.add_field(
                name="السبب",
                value=clean(task["reason"]),
                inline=False,
            )

    else:
        embed.description = (
            f"**المرسل:** <@{task['user']}>\n"
            f"**المسؤول:** <@{task['reviewer']}>\n"
            f"**الروم:** <#{task['channel']}>"
        )

        if accepted:
            embed.add_field(
                name="عدد مرات القبول",
                value="1",
                inline=True,
            )
        else:
            embed.add_field(
                name="سبب الرفض",
                value=clean(task["reason"]),
                inline=False,
            )

    embed.add_field(
        name="المهمة المرفقة",
        value=f"[Link]({link})",
        inline=True,
    )

    embed.set_footer(
        text=(
            f"{BOT_NAME} • "
            f"{ref(task, 'dm' if private else 'log')}"
        )
    )

    return embed


async def channel(channel_id):
    return (
        bot.get_channel(channel_id)
        or await bot.fetch_channel(channel_id)
    )


async def send_once(
    target_channel,
    reference,
    retry=False,
    **kwargs,
):
    # يقلل تكرار الرسائل عند إعادة المحاولة بعد تعطل مفاجئ.
    try:
        if retry:
            async for message in target_channel.history(limit=200):
                if message.author.id != bot.user.id:
                    continue

                body = message.content

                body += json.dumps(
                    [embed.to_dict() for embed in message.embeds],
                    ensure_ascii=False,
                )

                body += json.dumps(
                    [component.to_dict() for component in message.components],
                    ensure_ascii=False,
                )

                if reference in body:
                    return message

        return await target_channel.send(**kwargs)

    finally:
        for file in kwargs.get("files", []):
            file.close()


async def notify(task):
    if task.get("dm_state") in ("sent", "closed"):
        return

    try:
        user = (
            bot.get_user(task["user"])
            or await bot.fetch_user(task["user"])
        )

        target_channel = (
            user.dm_channel
            or await user.create_dm()
        )

        retry = task.get("dm_attempted", False)
        task["dm_attempted"] = True
        save(task)

        await send_once(
            target_channel,
            ref(task, "dm"),
            retry=retry,
            embed=decision_embed(task, True),
        )

        task["dm_state"] = "sent"
        save(task)

    except discord.Forbidden:
        task["dm_state"] = "closed"
        save(task)

        print(
            f"الخاص مغلق لصاحب المهمة {task['id']}",
            flush=True,
        )

    except Exception as error:
        error_log(error)


# ======================================================
# زيادة وسحب النقاط
# ======================================================

def adjustment(user_id, amount, actor, operation_id):
    try:
        DB.execute("BEGIN IMMEDIATE")

        if DB.execute(
            "SELECT 1 FROM ledger WHERE ref=?",
            (f"adjust:{operation_id}",),
        ).fetchone():
            raise ValueError("هذه العملية مسجلة مسبقًا.")

        if balance(user_id) + amount < 0:
            raise ValueError(
                "النقاط المطلوب سحبها أكبر من رصيد الشخص."
            )

        DB.execute(
            "INSERT INTO ledger VALUES (?, ?, ?, ?)",
            (
                f"adjust:{operation_id}",
                user_id,
                amount,
                now().timestamp(),
            ),
        )

        result = balance(user_id)

        put(
            "events",
            {
                "id": str(operation_id),
                "user": user_id,
                "actor": actor,
                "delta": amount,
                "balance": result,
                "at": now().timestamp(),
            },
        )

        DB.commit()
        return result

    except Exception:
        DB.rollback()
        raise


async def adjust_command(
    interaction,
    person,
    count,
    sign,
):
    if not admin(interaction):
        return

    if interaction.channel_id != ADJUST_CHANNEL:
        return await reply(
            interaction,
            f"هذا الأمر يعمل في <#{ADJUST_CHANNEL}> فقط.",
        )

    if not bot.ready:
        return await reply(
            interaction,
            "البوت يجهز الآن.",
        )

    try:
        if person.bot:
            raise ValueError("اختر عضوًا بشريًا.")

        result = adjustment(
            person.id,
            sign * count,
            interaction.user.id,
            interaction.id,
        )

        action = "➕ تمت زيادة" if sign > 0 else "➖ تم سحب"

        await reply(
            interaction,
            f"{action} {count} نقطة لـ <@{person.id}>. "
            f"المجموع: **{result}**.",
        )

    except ValueError as error:
        await reply(interaction, str(error))


# ======================================================
# الجرد والتصفير
# ======================================================

def requirement(role_ids):
    for role_id, name, target in REQUIREMENTS:
        if role_id in role_ids:
            return name, target

    return None


def create_audit(
    members,
    actor,
    audit_id,
    reset=False,
):
    try:
        DB.execute("BEGIN IMMEDIATE")

        if load(audit_id, "audits"):
            raise ValueError("هذا الجرد مسجل مسبقًا.")

        rows = []

        for member in members:
            if member.bot:
                continue

            required = requirement(
                {role.id for role in member.roles}
            )

            if required:
                name, target = required
                value = balance(member.id)

                rows.append(
                    {
                        "user": member.id,
                        "rank": name,
                        "required": target,
                        "points": value,
                        "passed": value >= target,
                    }
                )

        audit = {
            "id": str(audit_id),
            "actor": actor,
            "created": now().timestamp(),
            "reset": reset,
            "rows": sorted(rows, key=lambda row: row["user"]),
            "reports": {},
            "warning_messages": {},
        }

        if reset:
            balances = DB.execute(
                """
                SELECT user, SUM(delta)
                FROM ledger
                GROUP BY user
                HAVING SUM(delta) != 0
                """
            ).fetchall()

            for user_id, value in balances:
                DB.execute(
                    "INSERT INTO ledger VALUES (?, ?, ?, ?)",
                    (
                        f"reset:{audit_id}:{user_id}",
                        user_id,
                        -value,
                        audit["created"],
                    ),
                )

            put(
                "events",
                {
                    "id": f"reset:{audit_id}",
                    "kind": "reset",
                    "actor": actor,
                    "count": len(balances),
                    "removed": sum(value for _, value in balances),
                    "at": audit["created"],
                },
            )

        put("audits", audit)
        DB.commit()

        return audit

    except Exception:
        DB.rollback()
        raise


def audit_pages(audit):
    output = []

    for passed, label in [
        (True, "✅ أكملوا المتطلب"),
        (False, "❌ لم يكملوا المتطلب"),
    ]:
        rows = [
            row for row in audit["rows"]
            if row["passed"] == passed
        ]

        batches = [
            rows[index:index + 20]
            for index in range(0, len(rows), 20)
        ] or [[]]

        for number, batch in enumerate(batches):
            description = "\n".join(
                f"<@{row['user']}> — {row['rank']} — "
                f"**{row['points']}/{row['required']}**"
                for row in batch
            ) or "لا يوجد أعضاء في هذه القائمة."

            embed = discord.Embed(
                title=label,
                color=0x22C55E if passed else 0xEF4444,
                description=description,
                timestamp=dt.datetime.fromtimestamp(
                    audit["created"],
                    dt.timezone.utc,
                ),
            )

            embed.add_field(
                name="المسؤول",
                value=f"<@{audit['actor']}>",
            )

            if audit["reset"]:
                embed.add_field(
                    name="التصفير",
                    value="حُفظ الجرد ثم صُفرت جميع الأرصدة.",
                    inline=False,
                )

            key = f"{'pass' if passed else 'fail'}:{number}"

            embed.set_footer(
                text=f"الجرد: {audit['id']}:{key}"
            )

            view = None

            if (
                not passed
                and number == len(batches) - 1
                and rows
            ):
                view = AuditView(audit["id"])

            output.append((key, embed, view))

    return output


class WarningButton(discord.ui.Button):
    def __init__(self, audit_id):
        super().__init__(
            label="أنزل إنذار",
            style=discord.ButtonStyle.danger,
            custom_id=f"milan_warn:{audit_id}",
        )
        self.audit_id = audit_id

    async def callback(self, interaction):
        if not admin(interaction):
            return

        audit = load(self.audit_id, "audits")

        if interaction.channel_id != AUDIT_CHANNEL or not audit:
            return

        if audit.get("warnings_requested"):
            return await reply(
                interaction,
                "سبق طلب تنبيهات هذا الجرد. لن تتكرر.",
            )

        # يحفظ الطلب قبل أي انتظار، لمنع الضغط المزدوج.
        audit["warnings_requested"] = True
        audit["warning_actor"] = interaction.user.id
        save(audit, "audits")

        await interaction.response.edit_message(
            view=AuditView(self.audit_id, True)
        )

        await interaction.followup.send(
            "تم تسجيل طلب التنبيهات. "
            "ستُنشر رسائل نصية في روم التنبيهات."
        )


class AuditView(discord.ui.View):
    def __init__(self, audit_id, disabled=False):
        super().__init__(timeout=None)

        button = WarningButton(audit_id)
        button.disabled = disabled
        self.add_item(button)


async def audit_command(interaction, reset=False):
    if not admin(interaction):
        return

    if interaction.channel_id != AUDIT_CHANNEL:
        return await reply(
            interaction,
            f"الجرد والتصفير في <#{AUDIT_CHANNEL}> فقط.",
        )

    if not bot.ready:
        return await reply(
            interaction,
            "البوت يجهز الآن.",
        )

    await interaction.response.defer(thinking=True)

    try:
        members = [
            member
            async for member in interaction.guild.fetch_members(
                limit=None
            )
        ]

        audit = create_audit(
            members,
            interaction.user.id,
            interaction.id,
            reset,
        )

        text = (
            f"تم حفظ الجرد **{audit['id']}**. "
            "ستظهر قائمتا المكتمل وغير المكتمل هنا."
        )

        text += (
            " صُفرت الأرصدة بعد حفظها."
            if reset
            else " لم تتغير النقاط."
        )

        await interaction.edit_original_response(
            content=text
        )

    except Exception as error:
        error_log(error)

        existing = load(interaction.id, "audits")

        text = (
            "الجرد محفوظ. سيعاد إرسال نتائجه تلقائيًا."
            if existing
            else (
                "تعذر قراءة الأعضاء. "
                "تأكد من تفعيل Server Members Intent؛ "
                "لم تتغير النقاط."
            )
        )

        await interaction.edit_original_response(
            content=text
        )


# ======================================================
# إرسال المهام واللوقات والتنبيهات المحفوظة
# ======================================================

async def process_jobs():
    for task in records():
        try:
            if task["status"] == "publishing":
                target_channel = await channel(task["channel"])

                retry = task.get("publish_attempted", False)
                task["publish_attempted"] = True
                save(task)

                message = await send_once(
                    target_channel,
                    ref(task, "task"),
                    retry=retry,
                    view=task_view(dict(task, status="pending")),
                    files=files(task),
                )

                task.update(
                    status="pending",
                    message=message.id,
                )
                save(task)

                bot.add_view(
                    task_view(task),
                    message_id=message.id,
                )

            if task["status"] not in ("accepted", "rejected"):
                continue

            await notify(task)

            if not task.get("updated"):
                try:
                    target_channel = await channel(task["channel"])
                    message = await target_channel.fetch_message(
                        task["message"]
                    )

                    await message.edit(
                        view=task_view(task),
                        attachments=files(task),
                    )

                    task["updated"] = True
                    save(task)

                except discord.NotFound:
                    task["updated"] = True
                    save(task)

                except Exception as error:
                    error_log(error)

            if not task.get("log_message"):
                retry = task.get("log_attempted", False)
                task["log_attempted"] = True
                save(task)

                message = await send_once(
                    await channel(LOG_CHANNEL),
                    ref(task, "log"),
                    retry=retry,
                    embed=decision_embed(task),
                )

                task["log_message"] = message.id
                save(task)

        except Exception as error:
            error_log(error)

    for event in records("events"):
        if event.get("message"):
            continue

        try:
            if event.get("kind") == "reset":
                embed = discord.Embed(
                    title="تصفير النقاط",
                    color=0xEF4444,
                    description=(
                        f"**المسؤول:** <@{event['actor']}>\n"
                        f"**الأرصدة المصفرة:** {event['count']}\n"
                        f"**النقاط المسحوبة:** {event['removed']}\n"
                        f"**روم الجرد:** <#{AUDIT_CHANNEL}>"
                    ),
                )

            else:
                embed = discord.Embed(
                    title=(
                        "➕ زيادة نقاط"
                        if event["delta"] > 0
                        else "➖ سحب نقاط"
                    ),
                    color=0x5865F2,
                    description=(
                        f"**الشخص:** <@{event['user']}>\n"
                        f"**المسؤول:** <@{event['actor']}>\n"
                        f"**العدد:** {abs(event['delta'])}\n"
                        f"**المجموع بعد العملية:** {event['balance']}"
                    ),
                )

            embed.timestamp = dt.datetime.fromtimestamp(
                event["at"],
                dt.timezone.utc,
            )

            embed.set_footer(
                text=f"تعديل: {event['id']}"
            )

            retry = event.get("attempted", False)
            event["attempted"] = True
            save(event, "events")

            message = await send_once(
                await channel(LOG_CHANNEL),
                f"تعديل: {event['id']}",
                retry=retry,
                embed=embed,
            )

            event["message"] = message.id
            save(event, "events")

        except Exception as error:
            error_log(error)

    for audit in records("audits"):
        try:
            for key, embed, view in audit_pages(audit):
                if key in audit["reports"]:
                    continue

                message = await send_once(
                    await channel(AUDIT_CHANNEL),
                    f"الجرد: {audit['id']}:{key}",
                    retry=True,
                    embed=embed,
                    view=view,
                )

                audit["reports"][key] = message.id
                save(audit, "audits")

            if audit.get("warnings_requested"):
                for row in audit["rows"]:
                    user_key = str(row["user"])

                    if (
                        row["passed"]
                        or user_key in audit["warning_messages"]
                    ):
                        continue

                    # رسالة نصية عادية، بدون Embed.
                    text = (
                        "تنبيه إداري :\n"
                        f"<@{row['user']}>\n"
                        f"لم تكمل متطلب رتبة {row['rank']}. "
                        f"نقاطك: {row['points']} من {row['required']}.\n"
                        f"الجرد: {audit['id']} — العضو: {row['user']}"
                    )

                    message = await send_once(
                        await channel(WARNING_CHANNEL),
                        f"الجرد: {audit['id']} — العضو: {row['user']}",
                        retry=True,
                        content=text,
                        allowed_mentions=discord.AllowedMentions(
                            users=[
                                discord.Object(id=row["user"])
                            ],
                            roles=False,
                            everyone=False,
                        ),
                    )

                    audit["warning_messages"][user_key] = message.id
                    save(audit, "audits")

        except Exception as error:
            error_log(error)


# ======================================================
# تشغيل البوت والأزرار الدائمة
# ======================================================

class MilanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        self.ready = False
        self.worker = None

    async def setup_hook(self):
        for task in records():
            if task["status"] in (
                "draft",
                "pending",
                "accepted",
                "rejected",
            ):
                self.add_view(task_view(task))

        for audit in records("audits"):
            self.add_view(
                AuditView(
                    audit["id"],
                    audit.get("warnings_requested", False),
                )
            )

        await self.tree.sync(
            guild=discord.Object(id=GUILD_ID)
        )

        self.worker = asyncio.create_task(
            self.jobs()
        )

    async def jobs(self):
        await self.wait_until_ready()

        while not self.is_closed():
            if self.ready:
                try:
                    await process_jobs()
                except Exception as error:
                    error_log(error)

            await asyncio.sleep(5)

    async def close(self):
        if self.worker:
            self.worker.cancel()

            try:
                await self.worker
            except asyncio.CancelledError:
                pass

        await super().close()


bot = MilanBot()
SERVER = discord.Object(id=GUILD_ID)


# ======================================================
# أوامر السلاش
# ======================================================

@bot.tree.command(
    name="اضافة_صورة",
    description="إضافة مهمة بالصور والبيانات",
    guild=SERVER,
)
async def add_task(interaction: discord.Interaction):
    if interaction.guild_id != GUILD_ID:
        return

    if interaction.channel_id not in TASK_CHANNELS:
        return await reply(
            interaction,
            "هذا الأمر داخل رومات المهام فقط.",
        )

    if not bot.ready:
        return await reply(
            interaction,
            "البوت يجهز الآن.",
        )

    count = sum(
        task["user"] == interaction.user.id
        and task["status"] == "draft"
        and now().timestamp() - task["created"] < 86400
        for task in records()
    )

    if count >= 5:
        return await reply(
            interaction,
            "أكمل أو ألغِ مسوداتك السابقة أولًا.",
        )

    task = {
        "id": uuid.uuid4().hex[:20],
        "user": interaction.user.id,
        "channel": interaction.channel_id,
        "status": "draft",
        "created": now().timestamp(),
        "fields": {},
        "images": [],
    }

    save(task)

    await interaction.response.send_modal(
        UploadModal(task)
    )


@bot.tree.command(
    name="نقاط",
    description="عرض مجموع نقاطك",
    guild=SERVER,
)
async def points(interaction: discord.Interaction):
    if interaction.channel_id not in POINTS_CHANNELS:
        return await reply(
            interaction,
            "عرض النقاط في "
            + " أو ".join(
                f"<#{channel_id}>"
                for channel_id in sorted(POINTS_CHANNELS)
            ),
        )

    embed = discord.Embed(
        description=(
            f"**مجموع نقاطك: {balance(interaction.user.id)}**"
        ),
        color=0x22C55E,
    )

    await interaction.response.send_message(
        content=interaction.user.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            users=[interaction.user]
        ),
    )


withdraw = app_commands.Group(
    name="سحب",
    description="سحب نقاط إداري",
)

increase = app_commands.Group(
    name="زيادة",
    description="زيادة نقاط إداري",
)


@withdraw.command(
    name="نقاط",
    description="اختر الشخص وعدد النقاط",
)
@app_commands.rename(person="الشخص", count="العدد")
async def withdraw_points(
    interaction: discord.Interaction,
    person: discord.Member,
    count: app_commands.Range[int, 1, 100000],
):
    await adjust_command(
        interaction,
        person,
        count,
        -1,
    )


@increase.command(
    name="نقاط",
    description="اختر الشخص وعدد النقاط",
)
@app_commands.rename(person="الشخص", count="العدد")
async def increase_points(
    interaction: discord.Interaction,
    person: discord.Member,
    count: app_commands.Range[int, 1, 100000],
):
    await adjust_command(
        interaction,
        person,
        count,
        1,
    )


bot.tree.add_command(
    withdraw,
    guild=SERVER,
)

bot.tree.add_command(
    increase,
    guild=SERVER,
)


@bot.tree.command(
    name="الجرد",
    description="عرض المكتمل وغير المكتمل بدون تغيير النقاط",
    guild=SERVER,
)
async def audit(interaction: discord.Interaction):
    await audit_command(interaction)


@bot.tree.command(
    name="تصفير",
    description="حفظ جرد ثم تصفير جميع النقاط",
    guild=SERVER,
)
async def reset(interaction: discord.Interaction):
    await audit_command(interaction, True)


@bot.tree.error
async def command_error(interaction, error):
    if (
        interaction.command
        and interaction.command.qualified_name in {
            "الجرد",
            "تصفير",
            "سحب نقاط",
            "زيادة نقاط",
        }
        and not admin(interaction)
    ):
        return

    error_log(error)

    await reply(
        interaction,
        "تعذر تنفيذ الأمر الآن. تحقق من الإعدادات.",
    )


# ======================================================
# التحقق من الرومات والصلاحيات
# ======================================================

@bot.event
async def on_ready():
    if bot.ready:
        return

    try:
        guild = bot.get_guild(GUILD_ID)

        if not guild:
            raise ValueError(
                "البوت غير موجود في السيرفر المحدد."
            )

        me = guild.me or await guild.fetch_member(bot.user.id)

        channel_ids = (
            set(TASK_CHANNELS)
            | POINTS_CHANNELS
            | {
                LOG_CHANNEL,
                AUDIT_CHANNEL,
                WARNING_CHANNEL,
            }
        )

        for channel_id in channel_ids:
            target_channel = await channel(channel_id)

            if (
                not isinstance(target_channel, discord.TextChannel)
                or target_channel.guild.id != GUILD_ID
            ):
                raise ValueError(
                    f"الروم غير صالح: {channel_id}"
                )

            permissions = target_channel.permissions_for(me)

            required = [
                "view_channel",
                "send_messages",
                "embed_links",
                "read_message_history",
            ]

            if channel_id in TASK_CHANNELS:
                required.append("attach_files")

            if not all(
                getattr(permissions, name)
                for name in required
            ):
                raise ValueError(
                    f"صلاحيات ناقصة في الروم: {channel_id}"
                )

        bot.ready = True

        print(
            f"✅ {BOT_NAME} جاهز: {bot.user}",
            flush=True,
        )

    except Exception as error:
        print(
            f"فشل الإعداد: {error}",
            flush=True,
        )
        await bot.close()


# ======================================================
# صفحة الاستضافة
# ======================================================

def web():
    from flask import Flask

    app = Flask(__name__)

    @app.get("/")
    def home():
        return {
            "service": BOT_NAME,
            "discord_ready": bot.ready and bot.is_ready(),
        }

    Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    ).start()


# ======================================================
# التشغيل
# ======================================================

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "أضف MILAN_BOT_TOKEN في Environment."
        )

    web()

    try:
        bot.run(TOKEN)
    finally:
        DB.close()
