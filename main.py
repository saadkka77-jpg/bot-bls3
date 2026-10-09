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
from discord.ext import commands


# ======================================================
# ميلان بوت — الإعدادات
# ======================================================

BOT_NAME = "ميلان بوت"

# التوكن يقرأ من Environment ولا يكتب داخل الكود.
TOKEN = os.getenv("MILAN_BOT_TOKEN", "").strip()

# آيدي السيرفر يقرأ من Environment.
GUILD_RAW = os.getenv("DISCORD_GUILD_ID", "").strip()
VALUE: 1556038627170066463

if not TOKEN:
    raise SystemExit(
        "ناقص MILAN_BOT_TOKEN في Environment: "
        "ضع توكن البوت الحقيقي كقيمة."
    )

if not GUILD_RAW.isdecimal() or not 17 <= len(GUILD_RAW) <= 20:
    raise SystemExit(
        "ناقص DISCORD_GUILD_ID أو قيمته غير صالحة: "
        "ضع آيدي السيرفر فقط."
    )

GUILD_ID = int(GUILD_RAW)

# أضف آيديات رتب المراجعين بين الأقواس.
# مثال: REVIEWER_ROLE_IDS = {123456789012345678}
# إذا تركتها فارغة، المراجعة لأصحاب:
# Administrator أو Manage Server.
REVIEWER_ROLE_IDS = set()

# منع الشخص من قبول أو رفض مهمته بنفسه.
ALLOW_SELF_REVIEW = False

# حد حجم الصورة بالميجابايت.
MAX_IMAGE_MB = 10

# صفحة ويب للاستضافة على Render.
ENABLE_WEB = os.getenv("ENABLE_WEB", "true").lower() == "true"

# روم القرارات ولوحة إحصائيات الإداريين.
LOG_CHANNEL_ID = 1556039742485827707

# /نقاط يعمل في هذين الرومين فقط.
POINTS_CHANNEL_IDS = {
    1556039842230566949,
    1556039678774214768,
}

SCENARIO_CHANNEL_ID = 1556039764996522074

# points = النقاط المضافة عند قبول المهمة.
TASK_CHANNELS = {
    1556039749360422922: {
        "name": "مهام الباند",
        "points": 1,
    },
    1556039753344753754: {
        "name": "مهام التعويض",
        "points": 1,
    },
    1556039757866344489: {
        "name": "مهام الدعم الفني",
        "points": 1,
    },
    1556039761893003386: {
        "name": "مهام الادمن منجر",
        "points": 1,
    },
    1556039764996522074: {
        "name": "مراقبة السيناريوهات",
        "points": 1,
    },
}


# ======================================================
# التحقق من المكتبة والإعدادات
# ======================================================

if not hasattr(discord.ui, "FileUpload"):
    raise RuntimeError(
        'حدّث المكتبة: python -m pip install -U "discord.py>=2.7,<3"'
    )

if not 1 <= MAX_IMAGE_MB <= 20:
    raise ValueError("MAX_IMAGE_MB يجب أن يكون بين 1 و20")

for section in TASK_CHANNELS.values():
    if type(section["points"]) is not int or section["points"] < 0:
        raise ValueError(
            "نقاط الأقسام يجب أن تكون أعدادًا صحيحة غير سالبة"
        )


# ======================================================
# حفظ المهام والصور
# ======================================================

# يمكن تغيير مكان التخزين بمتغير MILAN_DATA_DIR.
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

DB.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        payload TEXT NOT NULL
    )
""")

DB.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
""")

DB.commit()

LOCKS = {}


def now():
    return dt.datetime.now(dt.timezone.utc)


def save(task):
    DB.execute(
        """
        INSERT INTO tasks VALUES (?, ?)
        ON CONFLICT(id)
        DO UPDATE SET payload=excluded.payload
        """,
        (task["id"], json.dumps(task, ensure_ascii=False)),
    )
    DB.commit()


def load(task_id):
    result = DB.execute(
        "SELECT payload FROM tasks WHERE id=?",
        (task_id,),
    ).fetchone()

    return json.loads(result[0]) if result else None


def all_tasks():
    records = DB.execute(
        "SELECT payload FROM tasks"
    ).fetchall()

    return [json.loads(record[0]) for record in records]


def setting(key, value=None):
    if value is not None:
        DB.execute(
            """
            INSERT INTO settings VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (key, str(value)),
        )
        DB.commit()
        return value

    result = DB.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,),
    ).fetchone()

    return result[0] if result else None


def clean(value):
    return discord.utils.escape_markdown(
        discord.utils.escape_mentions(str(value))
    ).strip()


def error_log(error):
    print(
        f"خطأ: {type(error).__name__} "
        f"| code={getattr(error, 'code', '-')}"
    )


async def tell(interaction, text):
    if not interaction.response.is_done():
        await interaction.response.send_message(
            text,
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            text,
            ephemeral=True,
        )


# ======================================================
# الصلاحيات
# ======================================================

def reviewer(member):
    return isinstance(member, discord.Member) and (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or any(role.id in REVIEWER_ROLE_IDS for role in member.roles)
    )


def check_context(interaction):
    if (
        interaction.guild_id != GUILD_ID
        or not isinstance(interaction.user, discord.Member)
    ):
        raise ValueError(
            "هذا البوت يعمل داخل السيرفر المحدد فقط."
        )

    if not bot.initialized:
        raise ValueError(
            "البوت يجهز الآن. أعد المحاولة بعد قليل."
        )


def check_draft(task, interaction):
    check_context(interaction)

    if (
        not task
        or task["user"] != interaction.user.id
        or task["channel"] != interaction.channel_id
        or task["status"] != "draft"
    ):
        raise ValueError(
            "المعاينة غير متاحة لك أو سبق إرسالها."
        )

    if now().timestamp() - task["created"] > 86400:
        raise ValueError(
            "انتهت صلاحية المسودة. استخدم الأمر من جديد."
        )


def check_review(task, interaction):
    check_context(interaction)

    if not task or task["channel"] != interaction.channel_id:
        raise ValueError("المهمة غير متاحة.")

    if (
        interaction.message
        and interaction.message.id != task.get("message")
    ):
        raise ValueError("بطاقة المهمة غير صالحة.")

    if not reviewer(interaction.user):
        raise ValueError(
            "ليس لديك صلاحية مراجعة المهام."
        )

    if not ALLOW_SELF_REVIEW and task["user"] == interaction.user.id:
        raise ValueError(
            "لا يمكنك مراجعة مهمتك بنفسك."
        )

    if task["status"] != "pending":
        raise ValueError(
            "تم اتخاذ قرار لهذه المهمة مسبقًا."
        )


# ======================================================
# حساب النقاط والإحصائيات
# ======================================================

def submitted():
    return [
        task
        for task in all_tasks()
        if task["status"] in ("pending", "accepted", "rejected")
    ]


def user_stats(user_id, records=None):
    records = submitted() if records is None else records

    own = [
        task for task in records
        if task["user"] == user_id
    ]

    accepted = [
        task for task in own
        if task["status"] == "accepted"
    ]

    return {
        "user": user_id,
        "total": len(own),
        "accepted": len(accepted),
        "rejected": sum(
            task["status"] == "rejected" for task in own
        ),
        "pending": sum(
            task["status"] == "pending" for task in own
        ),
        "points": sum(
            task.get("awarded", 0) for task in accepted
        ),
        "categories": {
            channel_id: sum(
                task["channel"] == channel_id
                for task in accepted
            )
            for channel_id in TASK_CHANNELS
        },
    }


def ranking():
    records = submitted()

    result = [
        user_stats(user_id, records)
        for user_id in {task["user"] for task in records}
    ]

    return sorted(
        result,
        key=lambda stats: (
            -stats["points"],
            -stats["accepted"],
            -stats["total"],
            stats["user"],
        ),
    )


def points_embed(user_id):
    stats = user_stats(user_id)

    embed = discord.Embed(
        title=f"{BOT_NAME} • ⭐ نقاطك ومهامك",
        description=f"الإداري: <@{user_id}>",
        color=0x5865F2,
    )

    for name, key in [
        ("مجموع النقاط", "points"),
        ("جميع المرسلة", "total"),
        ("المقبولة", "accepted"),
        ("المرفوضة", "rejected"),
        ("بانتظار المراجعة", "pending"),
    ]:
        embed.add_field(
            name=name,
            value=str(stats[key]),
            inline=True,
        )

    embed.add_field(
        name="المقبولة حسب القسم",
        value="\n".join(
            f"{section['name']}: **{stats['categories'][channel_id]}**"
            for channel_id, section in TASK_CHANNELS.items()
        ),
        inline=False,
    )

    embed.set_footer(
        text=f"{BOT_NAME} • النقاط للمهام المقبولة فقط"
    )

    return embed


def stats_embed(page=0):
    rows = ranking()

    pages = max(1, (len(rows) + 9) // 10)
    page = max(0, min(page, pages - 1))

    embed = discord.Embed(
        title=f"{BOT_NAME} • 📊 إحصائيات مهام الإداريين",
        color=0x5865F2,
        timestamp=now(),
        description=(
            f"الإداريون: **{len(rows)}**\n"
            f"مجموع المهام المرسلة: "
            f"**{sum(s['total'] for s in rows)}**\n"
            f"مجموع المهام المقبولة: "
            f"**{sum(s['accepted'] for s in rows)}**\n"
            f"مجموع النقاط: "
            f"**{sum(s['points'] for s in rows)}**\n\n"
            "أعداد الأقسام أدناه تخص المهام المقبولة."
        ),
    )

    for index, stats in enumerate(
        rows[page * 10:page * 10 + 10],
        start=page * 10 + 1,
    ):
        counts = "\n".join(
            f"{section['name']}: {stats['categories'][channel_id]}"
            for channel_id, section in TASK_CHANNELS.items()
        )

        embed.add_field(
            name=f"الإداري رقم {index}",
            inline=False,
            value=(
                f"<@{stats['user']}> | ⭐ **{stats['points']}** نقطة\n"
                f"📨 المرسلة: {stats['total']} | "
                f"✅ المقبولة: {stats['accepted']}\n"
                f"❌ المرفوضة: {stats['rejected']} | "
                f"⏳ الانتظار: {stats['pending']}\n"
                f"{counts}"
            ),
        )

    if not rows:
        embed.add_field(
            name="لا توجد مهام",
            value="تظهر الإحصائيات بعد إرسال أول مهمة.",
        )

    embed.set_footer(
        text=f"{BOT_NAME} • صفحة {page + 1} من {pages}"
    )

    return embed


class StatsButton(discord.ui.Button):
    def __init__(self, delta, label):
        super().__init__(
            label=label,
            custom_id=f"task_stats:{delta}",
            style=discord.ButtonStyle.secondary,
        )
        self.delta = delta

    async def callback(self, interaction):
        try:
            check_context(interaction)

            if not reviewer(interaction.user):
                raise ValueError(
                    "الإحصائيات متاحة للمراجعين فقط."
                )

            page = 0

            if interaction.message and interaction.message.embeds:
                footer = (
                    interaction.message.embeds[0].footer.text or ""
                )
                match = re.search(r"صفحة (\d+)", footer)

                if match:
                    page = int(match.group(1)) - 1

            await interaction.response.edit_message(
                embed=stats_embed(page + self.delta),
                view=StatsView(),
            )

        except ValueError as error:
            await tell(interaction, str(error))

        except Exception as error:
            error_log(error)
            await tell(
                interaction,
                "تعذر تحديث الإحصائيات الآن.",
            )


class StatsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for delta, label in [
            (-1, "السابق"),
            (0, "تحديث"),
            (1, "التالي"),
        ]:
            self.add_item(StatsButton(delta, label))


# ======================================================
# الصور والبطاقات
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

    raise ValueError(
        "ارفع صورة PNG أو JPG أو GIF أو WEBP."
    )


def files_for(task):
    return [
        discord.File(IMAGES / name, filename=name)
        for name in task["images"]
    ]


def marker(task, kind):
    return f"مرجع: {task['id']}:{kind}"


def task_text(task, log=False):
    fields = task["fields"]

    status = {
        "draft": "📝 معاينة",
        "pending": "⏳ بانتظار المراجعة",
        "accepted": "✅ مقبولة",
        "rejected": "❌ مرفوضة",
    }[task["status"]]

    text = (
        f"## {BOT_NAME} • {TASK_CHANNELS[task['channel']]['name']}\n"
        f"**رقم المهمة:** {task['id']}\n"
        f"**الإداري:** <@{task['user']}>\n"
        f"**الحالة:** {status}\n"
    )

    if fields.get("description"):
        text += (
            f"**التفاصيل:** {clean(fields['description'])}\n"
        )

    if fields.get("start"):
        text += (
            f"**البداية:** {clean(fields['start'])}\n"
            f"**النهاية:** {clean(fields['end'])}\n"
        )

    if fields.get("police"):
        text += (
            f"**آيديات العسكر:** {clean(fields['police'])}\n"
            f"**آيديات المجرمين:** {clean(fields['criminals'])}\n"
            f"**الفائز:** {clean(fields['winner'])}\n"
        )

    if task.get("reviewer"):
        text += (
            f"**المراجع:** <@{task['reviewer']}>\n"
            f"**وقت القرار:** <t:{int(task['reviewed'])}:F>\n"
        )

    if task["status"] == "accepted":
        text += (
            f"**نقاط المهمة:** +{task['awarded']}\n"
        )

    # سبب الرفض لا يظهر في الرومات أو اللوقات.
    # يُرسل لصاحب المهمة بالخاص فقط.

    if log:
        stats = user_stats(task["user"])

        text += (
            "\n### مجموع مهام الإداري\n"
            f"**المرسلة:** {stats['total']} | "
            f"**المقبولة:** {stats['accepted']}\n"
            f"**المرفوضة:** {stats['rejected']} | "
            f"**الانتظار:** {stats['pending']}\n"
            f"**مجموع النقاط:** {stats['points']}\n"
            "**المهمة الأصلية:** "
            f"https://discord.com/channels/{GUILD_ID}/"
            f"{task['channel']}/{task['message']}\n"
        )

    text += (
        f"\n-# {marker(task, 'log' if log else 'task')}"
    )

    return text


class ActionButton(discord.ui.Button):
    def __init__(
        self,
        task_id,
        action,
        label,
        style,
        disabled=False,
    ):
        super().__init__(
            custom_id=f"task:{action}:{task_id}",
            label=label,
            style=style,
            disabled=disabled,
        )
        self.task_id = task_id
        self.action = action

    async def callback(self, interaction):
        await handle_action(
            interaction,
            self.task_id,
            self.action,
        )


def task_view(task, log=False):
    view = discord.ui.LayoutView(timeout=None)

    color = (
        0x22C55E if task["status"] == "accepted"
        else 0xEF4444 if task["status"] == "rejected"
        else 0x5865F2
    )

    box = discord.ui.Container(accent_colour=color)

    box.add_item(
        discord.ui.TextDisplay(task_text(task, log))
    )

    if task["images"]:
        gallery = discord.ui.MediaGallery()

        for name in task["images"]:
            gallery.add_item(
                media=f"attachment://{name}"
            )

        box.add_item(gallery)

    if not log:
        if task["status"] == "draft":
            options = [
                (
                    "add",
                    "+ تعديل / إضافة صورة",
                    discord.ButtonStyle.secondary,
                    False,
                ),
                (
                    "form",
                    "كتابة البيانات",
                    discord.ButtonStyle.primary,
                    False,
                ),
                (
                    "send",
                    "إرسال المهمة",
                    discord.ButtonStyle.success,
                    not bool(task["fields"].get("start")),
                ),
                (
                    "cancel",
                    "إلغاء",
                    discord.ButtonStyle.danger,
                    False,
                ),
            ]

        else:
            options = [
                (
                    "accept",
                    "قبول",
                    discord.ButtonStyle.success,
                    task["status"] != "pending",
                ),
                (
                    "reject",
                    "رفض",
                    discord.ButtonStyle.danger,
                    task["status"] != "pending",
                ),
            ]

        actions = discord.ui.ActionRow()

        for action, label, style, disabled in options:
            actions.add_item(
                ActionButton(
                    task["id"],
                    action,
                    label,
                    style,
                    disabled,
                )
            )

        box.add_item(actions)

    view.add_item(box)
    return view


async def show_preview(interaction, task):
    await interaction.edit_original_response(
        content=None,
        embeds=[],
        attachments=files_for(task),
        view=task_view(task),
    )


# ======================================================
# حقول بيانات المهام
# ======================================================

def details_spec(task):
    if task["channel"] == SCENARIO_CHANNEL_ID:
        return [
            ("start", "وقت بداية السيناريو (التاريخ والوقت)", 80, False),
            ("end", "وقت نهاية السيناريو (التاريخ والوقت)", 80, False),
            ("police", "آيديات العسكر", 350, True),
            ("criminals", "آيديات المجرمين", 350, True),
            ("winner", "من فاز؟", 100, False),
        ]

    return [
        ("description", "تفاصيل المهمة", 1000, True),
        ("start", "وقت بداية المهمة (التاريخ والوقت)", 80, False),
        ("end", "وقت نهاية المهمة (التاريخ والوقت)", 80, False),
    ]


# ======================================================
# نماذج رفع الصور والبيانات وسبب الرفض
# ======================================================

class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction, error):
        error_log(error)

        await tell(
            interaction,
            "تعذر إتمام العملية الآن. أعد المحاولة.",
        )


class UploadModal(SafeModal):
    def __init__(self, task_id):
        super().__init__(
            title="إضافة صور المهمة",
            timeout=900,
        )
        self.task_id = task_id

        self.upload = discord.ui.FileUpload(
            min_values=1,
            max_values=2,
            required=True,
        )

        self.add_item(
            discord.ui.Label(
                text="اختر صورة أو صورتين",
                description=(
                    "لإضافة صورتين حددهما معًا. "
                    "الحفظ يستبدل الصور السابقة."
                ),
                component=self.upload,
            )
        )

    async def on_submit(self, interaction):
        lock = LOCKS.setdefault(
            self.task_id,
            asyncio.Lock(),
        )

        if lock.locked():
            return await tell(
                interaction,
                "انتظر حتى تكتمل العملية الحالية.",
            )

        async with lock:
            try:
                task = load(self.task_id)
                check_draft(task, interaction)

                await interaction.response.defer(
                    ephemeral=True,
                    thinking=True,
                )

                if not 1 <= len(self.upload.values) <= 2:
                    raise ValueError(
                        "اختر صورة أو صورتين."
                    )

                names = []

                for index, attachment in enumerate(
                    self.upload.values
                ):
                    content_type = attachment.content_type or ""

                    if (
                        not content_type.startswith("image/")
                        or attachment.size
                        > MAX_IMAGE_MB * 1024 * 1024
                    ):
                        raise ValueError(
                            "ارفع صورة بحجم لا يتجاوز "
                            f"{MAX_IMAGE_MB} ميجابايت."
                        )

                    data = await asyncio.wait_for(
                        attachment.read(),
                        timeout=30,
                    )

                    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
                        raise ValueError(
                            "الصورة أكبر من الحد المسموح."
                        )

                    extension = image_extension(data)

                    name = (
                        f"{task['id']}-{index}-"
                        f"{uuid.uuid4().hex}.{extension}"
                    )

                    (IMAGES / name).write_bytes(data)
                    names.append(name)

                task["images"] = names
                save(task)

                await show_preview(interaction, task)

            except ValueError as error:
                if interaction.response.is_done():
                    await interaction.edit_original_response(
                        content=str(error)
                    )
                else:
                    await tell(
                        interaction,
                        str(error),
                    )


class DetailsModal(SafeModal):
    def __init__(self, task):
        super().__init__(
            title=TASK_CHANNELS[task["channel"]]["name"],
            timeout=900,
        )
        self.task_id = task["id"]
        self.fields = {}

        for key, label, maximum, paragraph in details_spec(task):
            item = discord.ui.TextInput(
                required=True,
                max_length=maximum,
                style=(
                    discord.TextStyle.paragraph
                    if paragraph
                    else discord.TextStyle.short
                ),
                default=task["fields"].get(key),
            )

            self.fields[key] = item

            self.add_item(
                discord.ui.Label(
                    text=label,
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
                return await tell(
                    interaction,
                    "انتظر حتى تكتمل العملية الحالية.",
                )

            async with lock:
                task = load(self.task_id)
                check_draft(task, interaction)

                values = {
                    key: item.value.strip()
                    for key, item in self.fields.items()
                }

                if not all(values.values()):
                    raise ValueError(
                        "أكمل جميع الحقول."
                    )

                task["fields"] = values
                save(task)

                await interaction.response.defer(
                    ephemeral=True,
                    thinking=True,
                )

                await show_preview(
                    interaction,
                    task,
                )

        except ValueError as error:
            await tell(
                interaction,
                str(error),
            )


class RejectModal(SafeModal):
    def __init__(self, task_id):
        super().__init__(
            title="رفض المهمة",
            timeout=900,
        )
        self.task_id = task_id

        self.reason = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=700,
        )

        self.add_item(
            discord.ui.Label(
                text="اكتب سبب الرفض",
                description="يرسل لصاحب المهمة بالخاص فقط.",
                component=self.reason,
            )
        )

    async def on_submit(self, interaction):
        try:
            task = load(self.task_id)
            check_review(task, interaction)

            reason = self.reason.value.strip()

            if not reason:
                raise ValueError(
                    "اكتب سبب الرفض."
                )

            await decide(
                interaction,
                task,
                "rejected",
                reason,
            )

        except ValueError as error:
            await tell(
                interaction,
                str(error),
            )


# ======================================================
# حفظ القرار والنقاط
# ======================================================

async def decide(
    interaction,
    task,
    status,
    reason="",
):
    check_review(task, interaction)

    # حفظ القرار قبل أول await يمنع المراجعة المزدوجة.
    task.update(
        status=status,
        reason=reason,
        reviewer=interaction.user.id,
        reviewed=now().timestamp(),
        awarded=(
            TASK_CHANNELS[task["channel"]]["points"]
            if status == "accepted"
            else 0
        ),
        dm_state="pending",
    )

    save(task)

    stats = user_stats(task["user"])

    task.update(
        points_at_decision=stats["points"],
        accepted_at_decision=stats["accepted"],
    )

    save(task)

    if status == "accepted":
        text = (
            f"✅ تم القبول وإضافة {task['awarded']} نقطة."
        )
    else:
        text = (
            "❌ تم الرفض. السبب يرسل لصاحب المهمة "
            "بالخاص فقط."
        )

    await tell(interaction, text)


# ======================================================
# معالجة أزرار المهام
# ======================================================

async def handle_action(
    interaction,
    task_id,
    action,
):
    try:
        task = load(task_id)

        if action in ("accept", "reject"):
            check_review(task, interaction)

            if action == "reject":
                await interaction.response.send_modal(
                    RejectModal(task_id)
                )
            else:
                await decide(
                    interaction,
                    task,
                    "accepted",
                )
            return

        lock = LOCKS.setdefault(
            task_id,
            asyncio.Lock(),
        )

        if lock.locked():
            return await tell(
                interaction,
                "انتظر حتى تكتمل العملية الحالية.",
            )

        async with lock:
            task = load(task_id)
            check_draft(task, interaction)

            if action == "add":
                await interaction.response.send_modal(
                    UploadModal(task_id)
                )

            elif action == "form":
                if not task["images"]:
                    raise ValueError(
                        "أضف صورة أولًا."
                    )

                await interaction.response.send_modal(
                    DetailsModal(task)
                )

            elif action in ("cancel", "send"):
                if action == "send" and (
                    not task["images"]
                    or not task["fields"].get("start")
                ):
                    raise ValueError(
                        "أضف الصور وأكمل البيانات أولًا."
                    )

                task["status"] = (
                    "cancelled"
                    if action == "cancel"
                    else "publishing"
                )

                save(task)

                view = discord.ui.LayoutView(
                    timeout=None
                )

                text = (
                    "تم إلغاء المهمة."
                    if action == "cancel"
                    else (
                        "✅ تم استلام المهمة. "
                        "يجري نشرها في الروم للمراجعة."
                    )
                )

                view.add_item(
                    discord.ui.TextDisplay(text)
                )

                await interaction.response.edit_message(
                    view=view,
                    attachments=[],
                )

    except ValueError as error:
        await tell(
            interaction,
            str(error),
        )

    except Exception as error:
        error_log(error)
        await tell(
            interaction,
            "تعذر إتمام العملية الآن. أعد المحاولة.",
        )


# ======================================================
# إرسال المهام واللوقات والاستعادة
# ======================================================

async def get_channel(channel_id):
    channel = bot.get_channel(channel_id)

    return channel or await bot.fetch_channel(
        channel_id
    )


async def send_once(
    channel,
    reference,
    retry=False,
    **kwargs,
):
    # عند إعادة المحاولة نفحص آخر 200 رسالة
    # لتقليل تكرار الإرسال بعد توقف مفاجئ.

    try:
        if retry:
            async for message in channel.history(limit=200):
                if message.author.id != bot.user.id:
                    continue

                data = json.dumps(
                    [
                        component.to_dict()
                        for component in message.components
                    ],
                    ensure_ascii=False,
                )

                data += json.dumps(
                    [
                        embed.to_dict()
                        for embed in message.embeds
                    ],
                    ensure_ascii=False,
                )

                if reference in data:
                    return message

        return await channel.send(**kwargs)

    finally:
        for file in kwargs.get("files", []):
            file.close()


# ======================================================
# إشعارات الخاص
# ======================================================

async def notify_owner(task):
    if task.get("dm_state") in ("sent", "closed"):
        return

    try:
        user = (
            bot.get_user(task["user"])
            or await bot.fetch_user(task["user"])
        )

        channel = (
            user.dm_channel
            or await user.create_dm()
        )

        accepted = task["status"] == "accepted"

        description = (
            f"**رقم المهمة:** {task['id']}\n"
            f"**القسم:** "
            f"{TASK_CHANNELS[task['channel']]['name']}\n"
        )

        if accepted:
            description += (
                f"**نقاط المهمة:** +{task['awarded']}\n"
                f"**مجموع نقاطك وقت القبول:** "
                f"{task['points_at_decision']}\n"
                f"**مهامك المقبولة وقت القبول:** "
                f"{task['accepted_at_decision']}\n\n"
                "استخدم `/نقاط` لعرض مجموعك الحالي."
            )
        else:
            description += (
                f"**سبب الرفض:** {clean(task['reason'])}\n"
                f"**نقاطك وقت القرار:** "
                f"{task['points_at_decision']}"
            )

        description += (
            "\n\n"
            f"https://discord.com/channels/{GUILD_ID}/"
            f"{task['channel']}/{task['message']}"
        )

        embed = discord.Embed(
            title=(
                "✅ تم قبول مهمتك"
                if accepted
                else "❌ تم رفض مهمتك"
            ),
            description=description,
            color=0x22C55E if accepted else 0xEF4444,
            timestamp=dt.datetime.fromtimestamp(
                task["reviewed"],
                dt.timezone.utc,
            ),
        )

        embed.set_footer(
            text=f"{BOT_NAME} • {marker(task, 'dm')}"
        )

        retry = task.get(
            "dm_attempted",
            False,
        )

        task["dm_attempted"] = True
        save(task)

        await send_once(
            channel,
            marker(task, "dm"),
            retry=retry,
            embed=embed,
        )

        task["dm_state"] = "sent"
        save(task)

    except discord.Forbidden:
        task["dm_state"] = "closed"
        save(task)

        print(
            f"تعذر إرسال الخاص للمهمة {task['id']}: "
            "الخاص غير متاح."
        )

    except Exception as error:
        error_log(error)


# ======================================================
# لوحة الإحصائيات داخل روم اللوقات
# ======================================================

async def update_dashboard():
    signature = json.dumps(
        sorted(
            (
                task["id"],
                task["status"],
                task.get("awarded", 0),
            )
            for task in submitted()
        )
    )

    message_id = setting("dashboard_id")

    if (
        message_id
        and setting("dashboard_signature") == signature
    ):
        return

    channel = await get_channel(
        LOG_CHANNEL_ID
    )

    if message_id:
        try:
            message = await channel.fetch_message(
                int(message_id)
            )

            await message.edit(
                embed=stats_embed(),
                view=StatsView(),
            )

        except discord.NotFound:
            message_id = None

    if not message_id:
        message = await channel.send(
            embed=stats_embed(),
            view=StatsView(),
        )

        setting(
            "dashboard_id",
            message.id,
        )

    setting(
        "dashboard_signature",
        signature,
    )


# ======================================================
# المهام المتعثرة وإعادة المحاولة
# ======================================================

async def process_jobs():
    for task in all_tasks():
        try:
            if task["status"] == "publishing":
                channel = await get_channel(
                    task["channel"]
                )

                pending = dict(
                    task,
                    status="pending",
                )

                retry = task.get(
                    "publish_attempted",
                    False,
                )

                task["publish_attempted"] = True
                save(task)

                message = await send_once(
                    channel,
                    marker(task, "task"),
                    retry=retry,
                    view=task_view(pending),
                    files=files_for(task),
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

            await notify_owner(task)

            if not task.get("updated"):
                try:
                    channel = await get_channel(
                        task["channel"]
                    )

                    message = await channel.fetch_message(
                        task["message"]
                    )

                    await message.edit(
                        view=task_view(task),
                        attachments=files_for(task),
                    )

                    task["updated"] = True
                    save(task)

                except discord.NotFound:
                    task["updated"] = True
                    save(task)

                except Exception as error:
                    error_log(error)

            if not task.get("log_message"):
                channel = await get_channel(
                    LOG_CHANNEL_ID
                )

                retry = task.get(
                    "log_attempted",
                    False,
                )

                task["log_attempted"] = True
                save(task)

                message = await send_once(
                    channel,
                    marker(task, "log"),
                    retry=retry,
                    view=task_view(task, log=True),
                    files=files_for(task),
                )

                task["log_message"] = message.id
                save(task)

        except Exception as error:
            error_log(error)

    await update_dashboard()


# ======================================================
# البوت والأزرار الدائمة
# ======================================================

class TasksBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        self.initialized = False
        self.worker = None

    async def setup_hook(self):
        self.add_view(StatsView())

        for task in all_tasks():
            if task["status"] in (
                "draft",
                "pending",
                "accepted",
                "rejected",
            ):
                self.add_view(
                    task_view(task)
                )

        await self.tree.sync(
            guild=discord.Object(id=GUILD_ID)
        )

        self.worker = asyncio.create_task(
            self.worker_loop()
        )

    async def worker_loop(self):
        await self.wait_until_ready()

        while not self.is_closed():
            if self.initialized:
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


bot = TasksBot()

SERVER = discord.Object(id=GUILD_ID)


# ======================================================
# /اضافة_صورة
# ======================================================

@bot.tree.command(
    name="اضافة_صورة",
    description="إضافة مهمة بالصور والبيانات للمراجعة",
    guild=SERVER,
)
async def add_task(interaction: discord.Interaction):
    try:
        check_context(interaction)

        if interaction.channel_id not in TASK_CHANNELS:
            raise ValueError(
                "هذا الأمر يعمل داخل رومات المهام الخمسة فقط."
            )

        count = sum(
            task["user"] == interaction.user.id
            and task["status"] in ("draft", "publishing")
            and now().timestamp() - task["created"] < 86400
            for task in all_tasks()
        )

        if count >= 5:
            raise ValueError(
                "لديك 5 مسودات. أكملها أو ألغِها أولًا."
            )

        task = {
            "id": uuid.uuid4().hex[:20],
            "user": interaction.user.id,
            "channel": interaction.channel_id,
            "status": "draft",
            "created": now().timestamp(),
            "images": [],
            "fields": {},
        }

        save(task)

        await interaction.response.send_modal(
            UploadModal(task["id"])
        )

    except ValueError as error:
        await tell(interaction, str(error))


# ======================================================
# /نقاط — محصور في الرومين المحددين
# ======================================================

@bot.tree.command(
    name="نقاط",
    description="عرض مجموع نقاطك ومهامك",
    guild=SERVER,
)
async def my_points(interaction: discord.Interaction):
    try:
        check_context(interaction)

        if interaction.channel_id not in POINTS_CHANNEL_IDS:
            raise ValueError(
                "عرض النقاط متاح فقط في:\n"
                + "\n".join(
                    f"<#{channel_id}>"
                    for channel_id in sorted(POINTS_CHANNEL_IDS)
                )
            )

        await interaction.response.send_message(
            embed=points_embed(interaction.user.id),
            ephemeral=True,
        )

    except ValueError as error:
        await tell(interaction, str(error))


# ======================================================
# /لوقات — إحصائيات جميع الإداريين
# ======================================================

@bot.tree.command(
    name="لوقات",
    description="عرض إحصائيات جميع الإداريين للمراجعين",
    guild=SERVER,
)
async def logs_command(interaction: discord.Interaction):
    try:
        check_context(interaction)

        if not reviewer(interaction.user):
            raise ValueError(
                "هذا الأمر متاح للمراجعين فقط."
            )

        await interaction.response.send_message(
            embed=stats_embed(),
            view=StatsView(),
            ephemeral=True,
        )

    except ValueError as error:
        await tell(interaction, str(error))


@bot.tree.error
async def command_error(interaction, error):
    error_log(error)

    await tell(
        interaction,
        "تعذر تنفيذ الأمر الآن. أعد المحاولة.",
    )


# ======================================================
# التحقق من صلاحيات الرومات
# ======================================================

@bot.event
async def on_ready():
    if bot.initialized:
        return

    try:
        guild = bot.get_guild(GUILD_ID)

        if guild is None:
            raise ValueError(
                "البوت غير موجود في السيرفر المحدد."
            )

        me = (
            guild.me
            or await guild.fetch_member(bot.user.id)
        )

        channel_ids = (
            set(TASK_CHANNELS)
            | POINTS_CHANNEL_IDS
            | {LOG_CHANNEL_ID}
        )

        for channel_id in channel_ids:
            channel = await get_channel(channel_id)

            if (
                not isinstance(channel, discord.TextChannel)
                or channel.guild.id != GUILD_ID
            ):
                raise ValueError(
                    f"الروم غير صالح: {channel_id}"
                )

            permissions = channel.permissions_for(me)

            required = [
                "view_channel",
                "send_messages",
                "embed_links",
                "read_message_history",
            ]

            if (
                channel_id in TASK_CHANNELS
                or channel_id == LOG_CHANNEL_ID
            ):
                required.append("attach_files")

            if not all(
                getattr(permissions, name)
                for name in required
            ):
                raise ValueError(
                    "صلاحيات البوت ناقصة في الروم: "
                    f"{channel_id}"
                )

        bot.initialized = True

        print(
            f"✅ {BOT_NAME} جاهز ومتصل بدسكورد: {bot.user}",
            flush=True,
        )

        print(
            "الأوامر: /اضافة_صورة — /نقاط — /لوقات",
            flush=True,
        )

    except Exception as error:
        print(
            f"فشل الإعداد: {error}",
            flush=True,
        )

        await bot.close()


# ======================================================
# صفحة Flask للاستضافة
# ======================================================

def keep_alive():
    if not ENABLE_WEB:
        return

    from flask import Flask

    app = Flask(__name__)

    @app.get("/")
    def home():
        return {
            "service": BOT_NAME,
            "discord_ready": (
                bot.initialized and bot.is_ready()
            ),
        }

    def run_web():
        app.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            debug=False,
            use_reloader=False,
        )

    Thread(
        target=run_web,
        daemon=True,
    ).start()


# ======================================================
# التشغيل
# ======================================================

if __name__ == "__main__":
    keep_alive()

    try:
        bot.run(TOKEN)
    finally:
        DB.close()
