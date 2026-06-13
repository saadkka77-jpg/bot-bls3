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
intents = discord.Intents.all()  # تفعيل كل الصلاحيات لضمان عدم تجاهل الروم
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"تم تشغيل البوت المصلح بنجاح باسم: {bot.user.name}")

@bot.event
async def on_message(message):
    # تجنب رد البوت على نفسه عشان ما يكرر الكلام
    if message.author == bot.user:
        return

    # التحقق من الـ ID الصحيح للروم المطلوب كـ رقم (Integer)
    TARGET_CHANNEL_ID = 1514885534336417902

    if message.channel.id == TARGET_CHANNEL_ID:
        try:
            # الرد المباشر بطلبك
            await message.channel.send("نادر غدار و سعد تاج راسه")
        except Exception as e:
            print(f"مشكلة في إرسال الرسالة: {e}")

    # السماح للأوامر الأخرى بالعمل إن وجدت
    await bot.process_commands(message)

# تشغيل البوت
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("خطأ: لم يتم العثور على التوكن DISCORD_TOKEN في إعدادات Render!")
