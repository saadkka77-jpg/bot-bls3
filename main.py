import discord
from discord.ext import commands
import os
import threading
import http.server
from http.server import ThreadingHTTPServer

# --- 1️⃣ قراءة التوكن بأمان من موقع Render ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

# --- 2️⃣ حيلة فتح البورت لـ Render لضمان البقاء صاحي 24/7 ---
def run_web_server():
    class MyHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("البوت شغال تمام وبأعلى كفاءة!".encode('utf-8'))

        def log_message(self, format, *args):
            return

    port = int(os.environ.get("PORT", 8080))
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), MyHandler)
        server.serve_forever()
    except Exception as e:
        print(f"خطأ في سيرفر الويب: {e}")

threading.Thread(target=run_web_server, daemon=True).start()

# --- 3️⃣ إعدادات تشغيل بوت الديسكورد وتفعيل الصلاحيات الكاملة ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# الـ ID الجديد للروم المطلوب والمسموح له فقط بالعمل
TARGET_CHANNEL_ID = 1495546233018908813

@bot.event
async def on_ready():
    print(f"تم تشغيل البوت المصلح بنجاح باسم: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # التحقق الصارم: إذا لم تكن الرسالة في الروم المحدد، يتجاهلها البوت تماماً
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    # الرد التلقائي داخل الروم المحدد فقط (إذا لم يكن أمراً)
    if not message.content.startswith("!"):
        try:
            await message.channel.send("نادر غدار و سعد تاج راسه")
        except Exception as e:
            print(f"مشكلة في إرسال الرسالة التلقائية: {e}")

    # السماح للأوامر بالعمل داخل الروم المحدد فقط
    await bot.process_commands(message)


# --- 4️⃣ أمر إرسال القوانين بنفس شكل الصورة (Embed) ---
@bot.command(name="setup")
@commands.has_permissions(administrator=True) # للأدمن فقط
async def send_rules(ctx):
    # تحقق إضافي للأمر للتأكد أنه يعمل في نفس الروم فقط
    if ctx.channel.id != TARGET_CHANNEL_ID:
        return

    # إنشاء الـ Embed وتحديد اللون الأحمر الجانبي كالموجود بالصورة
    embed = discord.Embed(
        title="📜 قوانين وإرشادات سيرفر BLS",
        description="نرجو من جميع الأعضاء الالتزام التام بالقوانين التالية للحفاظ على مجتمع آمن ومحترم للجميع.\n\n"
                    "⚖️ المادة الأولى: القذف والتشهير\n"
                    "يمنع منعاً باتاً ممارسة القذف أو الإساءة اللفظية تجاه أي عضو، كما يُحظر أي محاولة للتشهير بالأشخاص. الهدف الأسمى هو الارتقاء بالمجتمع والحفاظ على الاحترام المتبادل كقاعدة أساسية.\n"
                    "العقوبة: الحظر النهائي من المجتمع دون نقاش.\n\n"
                    "المادة الثانية: المقدسات والأديان\n"
                    "يُحظر تماماً الاستهزاء بالأديان أو الإساءة للمقدسات والقيم الدينية بكافة أشكالها وصورها.\n"
                    "العقوبة: الحظر النهائي والمباشر.\n\n"
                    "المادة الثالثة: النشر والإزعاج\n"
                    "يُمنع النشر العشوائي وتكرار الرسائل بصورة مزعجة، كما يُحظر إرسال الروابط الخارجية دون الحصول على إذن رسمي من الإدارة لضمان تنظيم المحادثات.\n"
                    "العقوبة: الطرد أو الحظر المباشر.\n\n"
                    "تنويه هام إلى جميع أعضاء السيرفر الكرام\n"
                    "لاحظنا مؤخراً قيام بعض الأشخاص بإرسال روابط داخل قنوات السيرفر العامة، سواء كانت روابط مواقع أو روابط سيارات لمحاكي أو أي نوع آخر من الروابط.\n\n"
                    "وحفاظاً على أمن وحماية السيرفر وسلامة الجميع، يُمنع منعاً باتاً نشر أي رابط بجميع أشكاله داخل القنوات العامة. إذا كنت ترغب في مشاركة رابط معين مع شخص، يرجى إرساله له في الخاص وليس داخل السيرفر لتجنب المخالفة وعقوبة التايم آوت.\n\n"
                    "جرى التنبيه لإخلاء المسؤولية ونرجو من الجميع الالتزام لتجنب العقوبات والحفاظ على مجتمعنا آمناً. شاكرين لكم تفهمكم وتعاونكم الدائم.\n\n"
                    "(نظام الحماية متواجد من بداية السيرفر لكن التنويه من أجل تجنب التايم آوت من البوت بس)\n\n"
                    "المادة الخامسة: القنوات الصوتية والعامة\n"
                    "تُخصص القنوات العامة للدردشة الهادئة فقط، ويُمنع افتعال الفوضى أو إصدار أصوات تسبب الإزعاج للمتواجدين.",
        color=discord.Color.from_rgb(231, 76, 60) # اللون الأحمر المميز للحد الجانبي
    )
    
    # إضافة الحقوق أسفل الرسالة كما في الصورة
    embed.set_footer(text="إدارة سيرفر BLS • الاحترام أساس مجتمعنا")
    
    # إرسال الرسالة وحذف أمر العضو ليكون المظهر نظيفاً جداً
    await ctx.message.delete()
    await ctx.send(embed=embed)


# تشغيل البوت
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("خطأ: لم يتم العثور على التوكن DISCORD_TOKEN في إعدادات Render!")
