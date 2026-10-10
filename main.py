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


BOT_NAME = "ميلان بوت"
GUILD_ID = 1556038627170066463
TOKEN = os.getenv("MILAN_BOT_TOKEN", "").strip()

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

# تُحسب أعلى رتبة فقط، ولا تُجمع المتطلبات.
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

# True يسمح للإداري بمراجعة مهمته بنفسه.
ALLOW_SELF_REVIEW = False


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
        CREATE TABLE IF NOT EXISTS {table}(
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )

DB.execute(
    """
    CREATE TABLE IF NOT EXISTS ledger(
        ref TEXT PRIMARY KEY,
        user INTEGER NOT NULL,
        delta INTEGER NOT NULL,
        at REAL NOT NULL
    )
    """
)

# نقل النقاط من النسخة السابقة مرة واحدة.
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
        ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
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
    row = DB.execute(
        f"SELECT payload FROM {table} WHERE id=?",
        (str(item_id),),
    ).fetchone()

    return json.loads(row[0]) if row else None


def records(table="tasks"):
    rows = DB.execute(
        f"SELECT payload FROM {table}"
    ).fetchall()

    return [json.loads(row[0]) for row in rows]


def balance(user_id):
    return DB.execute(
        """
        SELECT COALESCE(SUM(delta), 0)
        FROM ledger
        WHERE user=?
        """,
        (user_id,),
    ).fetchone()[0]


def clean(value):
    return discord.utils.escape_markdown(
        discord.utils.escape_mentions(str(value))
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
        f"خطأ: {type(error).__name__} | "
        f"code={getattr(error, 'code', '-')}",
        flush=True,
    )


async def reply(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(
            text,
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            text,
            ephemeral=True,
        )


def draft(task, interaction):
    if not bot.ready or interaction.guild_id != GUILD_ID:
        raise ValueError("البوت غير جاهز الآن.")

    if (
        not task
        or task["user"] != interaction.user.id
        or task["channel"] != interaction.channel_id
        or task["status"] != "draft"
    ):
        raise ValueError("المهمة غير متاحة لك أو سبق إرسالها.")

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

    if (
        not ALLOW_SELF_REVIEW
        and task["user"] == interaction.user.id
    ):
        raise ValueError("لا يمكنك مراجعة مهمتك بنفسك.")

    if task["status"] != "pending":
        raise ValueError(
            "سبق اتخاذ قرار للمهمة. لم تُحتسب نقاط إضافية."
        )


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
    # مرجع داخلي فقط، لا يظهر في الرسائل الجديدة.
    return f"مرجع: {task['id']}:{kind}"


def task_view(task):
    view = discord.ui.LayoutView(timeout=None)

    states = {
        "draft": "📝 معاينة",
        "pending": "⏳ بانتظار المراجعة",
        "accepted": "✅ مقبولة",
        "rejected": "❌ مرفوضة",
    }

    text = (
        f"## {TASK_CHANNELS[task['channel']]}\n"
        f"**الإداري:** <@{task['user']}>\n"
        f"**الحالة:** {states[task['status']]}\n"
    )

    fields = task["fields"]

    if fields.get("description"):
        text += (
            f"**التفاصيل:** {clean(fields['description'])}\n"
        )

    if fields.get("start"):
        text += (
            f"**وقت البداية:** {clean(fields['start'])}\n"
            f"**وقت النهاية:** {clean(fields['end'])}\n"
        )

    # دعم بيانات المهام المسجلة بالنسخة السابقة.
    for key, title in (
        ("police", "آيديات العسكر"),
        ("criminals", "آيديات المجرمين"),
        ("winner", "الفائز"),
    ):
        if fields.get(key):
            text += f"**{title}:** {clean(fields[key])}\n"

    text += (
        f"**تاريخ الإرسال:** <t:{int(task['created'])}:F>\n"
    )

    if task.get("reviewer"):
        text += f"**المسؤول:** <@{task['reviewer']}>\n"

    color = (
        0x22C55E
        if task["status"] == "accepted"
        else 0xEF4444
        if task["status"] == "rejected"
        else 0x5865F2
    )

    container = discord.ui.Container(accent_colour=color)
    container.add_item(discord.ui.TextDisplay(text))

    if task["images"]:
        gallery = discord.ui.MediaGallery()

        for index, name in enumerate(task["images"]):
            caption = (
                "بداية التفاوض — عسكران ومجرمان"
                if index == 0
                else "نهاية السيناريو"
            )

            gallery.add_item(
                media=f"attachment://{name}",
                description=caption,
            )

        container.add_item(gallery)

    if task["status"] == "draft":
        # دعم مسودات النسخة السابقة.
        options = [
            ("add", "+ تعديل الصور", 2, False),
            ("form", "كتابة البيانات", 1, False),
            (
                "send",
                "إرسال",
                3,
                not bool(fields.get("start")),
            ),
            ("cancel", "إلغاء", 4, False),
        ]
    else:
        options = [
            (
                "accept",
                "قبول",
                3,
                task["status"] != "pending",
            ),
            (
                "reject",
                "رفض",
                4,
                task["status"] != "pending",
            ),
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

    container.add_item(row)
    view.add_item(container)
    return view


class TaskButton(discord.ui.Button):
    def __init__(self, task_id, action, label, style, disabled):
        super().__init__(
            label=label,
            style=discord.ButtonStyle(style),
            custom_id=f"task:{action}:{task_id}",
            disabled=disabled,
        )

        self.tid = task_id
        self.action = action

    async def callback(self, interaction):
        if self.action in ("accept", "reject"):
            if not admin(interaction):
                return

        try:
            task = load(self.tid)

            if self.action in ("accept", "reject"):
                review(task, interaction)

                if self.action == "reject":
                    await interaction.response.send_modal(
                        RejectModal(self.tid)
                    )
                else:
                    await decide(
                        interaction,
                        self.tid,
                        "accepted",
                    )

                return

            lock = LOCKS.setdefault(
                self.tid,
                asyncio.Lock(),
            )

            if lock.locked():
                raise ValueError("انتظر العملية الحالية.")

            async with lock:
                task = load(self.tid)
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
                    if self.action == "send":
                        incomplete = (
                            not task["images"]
                            or not task["fields"].get("start")
                            or (
                                task["channel"] == SCENARIO_CHANNEL
                                and len(task["images"]) != 2
                            )
                        )

                        if incomplete:
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
            title="إرسال المهمة",
            timeout=900,
        )

        self.tid = task["id"]

        self.first = discord.ui.FileUpload(
            min_values=1,
            max_values=1,
            required=True,
        )

        self.second = discord.ui.FileUpload(
            min_values=1,
            max_values=1,
            required=True,
        )

        self.add_item(
            discord.ui.Label(
                text="صورة بداية التفاوض — عسكران ومجرمان",
                component=self.first,
            )
        )

        self.add_item(
            discord.ui.Label(
                text="صورة نهاية السيناريو",
                component=self.second,
            )
        )

        self.description = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1200,
            placeholder=(
                "سرقة محل الأسلحة؛ العسكر: ...؛ "
                "المجرمون: ...؛ الفائز: ..."
            ),
        )

        self.start = discord.ui.TextInput(
            required=True,
            max_length=5,
            placeholder="21:30",
        )

        self.end = discord.ui.TextInput(
            required=True,
            max_length=5,
            placeholder="22:00",
        )

        self.add_item(
            discord.ui.Label(
                text="وصف المهمة والآيديات والفائز",
                component=self.description,
            )
        )

        self.add_item(
            discord.ui.Label(
                text="وقت البداية",
                component=self.start,
            )
        )

        self.add_item(
            discord.ui.Label(
                text="وقت النهاية",
                component=self.end,
            )
        )

    async def on_submit(self, interaction):
        lock = LOCKS.setdefault(
            self.tid,
            asyncio.Lock(),
        )

        if lock.locked():
            return await reply(
                interaction,
                "انتظر العملية الحالية.",
            )

        async with lock:
            try:
                task = load(self.tid)
                draft(task, interaction)

                values = {
                    "description": self.description.value.strip(),
                    "start": self.start.value.strip(),
                    "end": self.end.value.strip(),
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

                await interaction.response.defer(
                    thinking=True,
                    ephemeral=True,
                )

                names = []

                attachments = (
                    list(self.first.values)
                    + list(self.second.values)
                )

                for index, attachment in enumerate(attachments):
                    if attachment.size > MAX_IMAGE_MB * 1024 * 1024:
                        raise ValueError(
                            f"ارفع صورة لا تتجاوز "
                            f"{MAX_IMAGE_MB} ميجابايت."
                        )

                    data = await asyncio.wait_for(
                        attachment.read(),
                        timeout=30,
                    )

                    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
                        raise ValueError("الصورة كبيرة.")

                    name = (
                        f"{task['id']}-{index}-"
                        f"{uuid.uuid4().hex}."
                        f"{image_extension(data)}"
                    )

                    (IMAGES / name).write_bytes(data)
                    names.append(name)

                if len(names) != 2:
                    raise ValueError(
                        "أرفق صورة البداية وصورة النهاية."
                    )

                task.update(
                    images=names,
                    fields=values,
                    status="publishing",
                )

                save(task)

                await interaction.edit_original_response(
                    content="✅ تم إرسال المهمة للمراجعة."
                )

            except ValueError as error:
                if interaction.response.is_done():
                    await interaction.edit_original_response(
                        content=str(error)
                    )
                else:
                    await reply(interaction, str(error))


class DetailsModal(SafeModal):
    # دعم مسودات النسخة القديمة فقط.
    def __init__(self, task):
        super().__init__(
            title="بيانات المهمة",
            timeout=900,
        )

        self.tid = task["id"]
        self.fields = {}

        specification = [
            ("start", "وقت البداية فقط — مثال 21:30", 5),
            ("end", "وقت النهاية فقط — مثال 22:00", 5),
        ]

        if task["channel"] == SCENARIO_CHANNEL:
            specification += [
                ("police", "آيديات العسكر", 350),
                ("criminals", "آيديات المجرمين", 350),
                ("winner", "الفائز", 100),
            ]
        else:
            specification += [
                ("description", "تفاصيل المهمة", 1000),
            ]

        for key, title, maximum in specification:
            default = task["fields"].get(key)

            if default and len(default) > maximum:
                default = None

            field = discord.ui.TextInput(
                required=True,
                max_length=maximum,
                default=default,
                style=(
                    discord.TextStyle.paragraph
                    if maximum > 100
                    else discord.TextStyle.short
                ),
            )

            self.fields[key] = field

            self.add_item(
                discord.ui.Label(
                    text=title,
                    component=field,
                )
            )

    async def on_submit(self, interaction):
        try:
            lock = LOCKS.setdefault(
                self.tid,
                asyncio.Lock(),
            )

            if lock.locked():
                raise ValueError("انتظر العملية الحالية.")

            async with lock:
                task = load(self.tid)
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

                await interaction.response.defer(
                    thinking=True,
                    ephemeral=True,
                )

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

        self.tid = task_id

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
                self.tid,
                "rejected",
                reason,
            )

        except ValueError as error:
            await reply(interaction, str(error))


async def decide(
    interaction,
    task_id,
    status,
    reason="",
):
    if not admin(interaction):
        return

    try:
        # حفظ القرار والنقاط قبل أي انتظار.
        DB.execute("BEGIN IMMEDIATE")

        task = load(task_id)
        review(task, interaction)

        task.update(
            status=status,
            reason=reason,
            reviewer=interaction.user.id,
            reviewed=now().timestamp(),
            awarded=(
                POINTS_PER_TASK
                if status == "accepted"
                else 0
            ),
            accept_count=(
                1 if status == "accepted" else 0
            ),
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

    # إقرار صامت؛ لا تُرسل رسالة قبول أو رفض في روم المهام.
    await interaction.response.defer()


def decision_embed(task, private=False):
    accepted = task["status"] == "accepted"

    embed = discord.Embed(
        title=(
            "✅ تم قبول المهام"
            if accepted
            else "❌ تم رفض المهام"
        ),
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
                f"\n**مجموع نقاطك:** "
                f"{task['points_at_decision']}"
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

    embed.set_footer(text=BOT_NAME)
    return embed


async def channel(channel_id):
    return (
        bot.get_channel(channel_id)
        or await bot.fetch_channel(channel_id)
    )


async def send_once(
    destination,
    reference,
    retry=False,
    since=None,
    **kwargs,
):
    try:
        if retry:
            after = (
                dt.datetime.fromtimestamp(
                    since,
                    dt.timezone.utc,
                )
                if since
                else None
            )

            async for message in destination.history(
                limit=200,
                after=after,
            ):
                if message.author.id != bot.user.id:
                    continue

                body = message.content

                body += json.dumps(
                    [
                        embed.to_dict()
                        for embed in message.embeds
                    ],
                    ensure_ascii=False,
                )

                body += json.dumps(
                    [
                        component.to_dict()
                        for component in message.components
                    ],
                    ensure_ascii=False,
                )

                # دعم الرسائل القديمة التي احتوت مراجع.
                if reference in body:
                    return message

                expected = kwargs.get("embed")

                if expected and any(
                    embed.to_dict() == expected.to_dict()
                    for embed in message.embeds
                ):
                    return message

                if (
                    kwargs.get("content")
                    and message.content == kwargs["content"]
                ):
                    return message

                if reference.endswith(":task"):
                    task_id = (
                        reference
                        .removeprefix("مرجع: ")
                        .removesuffix(":task")
                    )

                    if any(
                        attachment.filename.startswith(
                            task_id + "-"
                        )
                        for attachment in message.attachments
                    ):
                        return message

        return await destination.send(**kwargs)

    finally:
        for attachment in kwargs.get("files", []):
            attachment.close()


async def notify(task):
    if task.get("dm_state") in ("sent", "closed"):
        return

    try:
        user = (
            bot.get_user(task["user"])
            or await bot.fetch_user(task["user"])
        )

        destination = (
            user.dm_channel
            or await user.create_dm()
        )

        retry = task.get("dm_attempted", False)
        task["dm_attempted"] = True
        save(task)

        await send_once(
            destination,
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


def adjustment(
    user_id,
    amount,
    actor,
    operation_id,
):
    try:
        DB.execute("BEGIN IMMEDIATE")

        existing = DB.execute(
            "SELECT 1 FROM ledger WHERE ref=?",
            (f"adjust:{operation_id}",),
        ).fetchone()

        if existing:
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
            "لا يمكن استخدام هذا الأمر هنا.",
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

        action = (
            "➕ تمت زيادة"
            if sign > 0
            else "➖ تم سحب"
        )

        await reply(
            interaction,
            f"{action} {count} نقطة لـ <@{person.id}>. "
            f"المجموع: **{result}**.",
        )

    except ValueError as error:
        await reply(interaction, str(error))


def requirement(role_ids):
    # القائمة مرتبة من الأعلى للأقل.
    # أول تطابق فقط يُحسب، والباقي يُتجاهل.
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
                points = balance(member.id)

                rows.append(
                    {
                        "user": member.id,
                        "rank": name,
                        "required": target,
                        "points": points,
                        "passed": points >= target,
                    }
                )

        audit = {
            "id": str(audit_id),
            "actor": actor,
            "created": now().timestamp(),
            "reset": reset,
            "rows": sorted(
                rows,
                key=lambda row: row["user"],
            ),
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

            for user_id, points in balances:
                DB.execute(
                    "INSERT INTO ledger VALUES (?, ?, ?, ?)",
                    (
                        f"reset:{audit_id}:{user_id}",
                        user_id,
                        -points,
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
                    "removed": sum(
                        value
                        for _, value in balances
                    ),
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

    for passed, label in (
        (True, "✅ أكملوا المتطلب"),
        (False, "❌ لم يكملوا المتطلب"),
    ):
        rows = [
            row
            for row in audit["rows"]
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
            )

            embed = discord.Embed(
                title=label,
                color=0x22C55E if passed else 0xEF4444,
                description=(
                    description
                    or "لا يوجد أعضاء في هذه القائمة."
                ),
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
                    value=(
                        "حُفظ الجرد ثم صُفرت جميع الأرصدة."
                    ),
                    inline=False,
                )

            key = (
                f"{'pass' if passed else 'fail'}:{number}"
            )

            view = None

            if (
                not passed
                and number == len(batches) - 1
                and rows
            ):
                view = AuditView(
                    audit["id"],
                    audit.get("warnings_requested", False),
                )

            output.append((key, embed, view))

    return output


class WarningButton(discord.ui.Button):
    def __init__(self, audit_id):
        super().__init__(
            label="أنزل إنذار",
            style=discord.ButtonStyle.danger,
            custom_id=f"milan_warn:{audit_id}",
        )

        self.aid = audit_id

    async def callback(self, interaction):
        if not admin(interaction):
            return

        audit = load(self.aid, "audits")

        if (
            interaction.channel_id != AUDIT_CHANNEL
            or not audit
        ):
            return

        if audit.get("warnings_requested"):
            return await reply(
                interaction,
                "سبق طلب تنبيهات هذا الجرد. لن تتكرر.",
            )

        audit["warnings_requested"] = True
        audit["warning_actor"] = interaction.user.id
        save(audit, "audits")

        await interaction.response.edit_message(
            view=AuditView(self.aid, True)
        )

        await interaction.followup.send(
            "تم إرسال طلب التنبيهات.",
            ephemeral=True,
        )


class AuditView(discord.ui.View):
    def __init__(self, audit_id, disabled=False):
        super().__init__(timeout=None)

        button = WarningButton(audit_id)
        button.disabled = disabled
        self.add_item(button)


async def audit_command(
    interaction,
    reset=False,
):
    if not admin(interaction):
        return

    if interaction.channel_id != AUDIT_CHANNEL:
        return await reply(
            interaction,
            "لا يمكن استخدام هذا الأمر هنا.",
        )

    if not bot.ready:
        return await reply(
            interaction,
            "البوت يجهز الآن.",
        )

    # النتيجة نفسها رد عام مباشر على الأمر.
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

        audit["delivery_until"] = now().timestamp() + 120
        save(audit, "audits")

        for index, (key, embed, view) in enumerate(
            audit_pages(audit)
        ):
            if index == 0:
                message = await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=view,
                )
            else:
                message = await interaction.followup.send(
                    embed=embed,
                    view=view,
                    wait=True,
                )

            current = load(audit["id"], "audits")
            current["reports"][key] = message.id
            save(current, "audits")

        current = load(audit["id"], "audits")
        current["delivery_until"] = 0
        save(current, "audits")

    except Exception as error:
        error_log(error)

        existing = load(
            interaction.id,
            "audits",
        )

        if existing:
            existing["delivery_until"] = 0
            save(existing, "audits")
        else:
            await interaction.delete_original_response()

        text = (
            "تعذر عرض بعض النتائج الآن. "
            "سيعاد إرسال النتائج المحفوظة تلقائيًا."
            if existing
            else (
                "تعذر قراءة الأعضاء. تأكد من تفعيل "
                "Server Members Intent."
            )
        )

        await interaction.followup.send(
            text,
            ephemeral=True,
        )


async def process_jobs():
    for task in records():
        try:
            if task["status"] == "publishing":
                destination = await channel(task["channel"])

                retry = task.get(
                    "publish_attempted",
                    False,
                )

                task["publish_attempted"] = True
                save(task)

                message = await send_once(
                    destination,
                    ref(task, "task"),
                    retry=retry,
                    view=task_view(
                        dict(task, status="pending")
                    ),
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

            if task["status"] not in (
                "accepted",
                "rejected",
            ):
                continue

            await notify(task)

            if not task.get("updated"):
                try:
                    destination = await channel(
                        task["channel"]
                    )

                    message = await destination.fetch_message(
                        task["message"]
                    )

                    # تحديث البطاقة الموجودة فقط.
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
                retry = task.get(
                    "log_attempted",
                    False,
                )

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
                        f"**الأرصدة المصفرة:** "
                        f"{event['count']}\n"
                        f"**النقاط المسحوبة:** "
                        f"{event['removed']}\n"
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
                        f"**المجموع بعد العملية:** "
                        f"{event['balance']}"
                    ),
                )

            embed.timestamp = dt.datetime.fromtimestamp(
                event["at"],
                dt.timezone.utc,
            )

            embed.set_footer(text=BOT_NAME)

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
        if (
            audit.get("delivery_until", 0)
            > now().timestamp()
        ):
            continue

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

                audit = load(audit["id"], "audits")
                audit["reports"][key] = message.id
                save(audit, "audits")

            if audit.get("warnings_requested"):
                for row in audit["rows"]:
                    user_key = str(row["user"])

                    if (
                        row["passed"]
                        or user_key
                        in audit["warning_messages"]
                    ):
                        continue

                    text = (
                        "تنبيه إداري :\n"
                        f"<@{row['user']}>\n"
                        f"لم تكمل متطلب رتبة {row['rank']}. "
                        f"نقاطك: {row['points']} "
                        f"من {row['required']}."
                    )

                    reference = (
                        f"الجرد: {audit['id']} — "
                        f"العضو: {row['user']}"
                    )

                    message = await send_once(
                        await channel(WARNING_CHANNEL),
                        reference,
                        retry=True,
                        since=audit["created"],
                        content=text,
                        allowed_mentions=discord.AllowedMentions(
                            users=[
                                discord.Object(
                                    id=row["user"]
                                )
                            ],
                            roles=False,
                            everyone=False,
                        ),
                    )

                    audit = load(
                        audit["id"],
                        "audits",
                    )

                    audit["warning_messages"][user_key] = (
                        message.id
                    )

                    save(audit, "audits")

        except Exception as error:
            error_log(error)


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
                    audit.get(
                        "warnings_requested",
                        False,
                    ),
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


@bot.tree.command(
    name="اضافة_صورة",
    description="إرسال مهمة بالصور والوصف والوقت",
    guild=SERVER,
)
async def add_task(interaction: discord.Interaction):
    if interaction.guild_id != GUILD_ID:
        return

    if interaction.channel_id not in TASK_CHANNELS:
        return await reply(
            interaction,
            "لا يمكن استخدام هذا الأمر هنا.",
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
            "لا يمكن استخدام هذا الأمر هنا.",
        )

    embed = discord.Embed(
        description=(
            f"**مجموع نقاطك: "
            f"{balance(interaction.user.id)}**"
        ),
        color=0x22C55E,
    )

    await interaction.response.send_message(
        content=interaction.user.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            users=[interaction.user],
            roles=False,
            everyone=False,
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
@app_commands.rename(
    person="الشخص",
    count="العدد",
)
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
@app_commands.rename(
    person="الشخص",
    count="العدد",
)
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


bot.tree.add_command(withdraw, guild=SERVER)
bot.tree.add_command(increase, guild=SERVER)


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
    await audit_command(
        interaction,
        reset=True,
    )


@bot.tree.error
async def command_error(interaction, error):
    restricted = {
        "الجرد",
        "تصفير",
        "سحب نقاط",
        "زيادة نقاط",
    }

    if (
        interaction.command
        and interaction.command.qualified_name
        in restricted
        and not admin(interaction)
    ):
        return

    error_log(error)

    await reply(
        interaction,
        "تعذر تنفيذ الأمر الآن. تحقق من الإعدادات.",
    )


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

        member = (
            guild.me
            or await guild.fetch_member(bot.user.id)
        )

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
            destination = await channel(channel_id)

            if (
                not isinstance(
                    destination,
                    discord.TextChannel,
                )
                or destination.guild.id != GUILD_ID
            ):
                raise ValueError(
                    f"الروم غير صالح: {channel_id}"
                )

            permissions = destination.permissions_for(
                member
            )

            required_permissions = [
                "view_channel",
                "send_messages",
                "embed_links",
                "read_message_history",
            ]

            if channel_id in TASK_CHANNELS:
                required_permissions.append(
                    "attach_files"
                )

            if not all(
                getattr(permissions, name)
                for name in required_permissions
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


def web():
    from flask import Flask

    app = Flask(__name__)

    @app.get("/")
    def home():
        return {
            "service": BOT_NAME,
            "discord_ready": (
                bot.ready and bot.is_ready()
            ),
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
