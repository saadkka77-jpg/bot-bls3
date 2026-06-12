import discord
from discord.ext import commands
import os
import threading
import http.server
import socketserver

# --- حيلة فتح البورت لـ Render (Web Service) ---
def run_web_server():
    class MyHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("البوت شغال تمام ويا جبل ما يهزك ريح!".encode('utf-8'))

    # ريندر يعطي البوت بورت تلقائي في المتغير PORT، وإذا ما لقى يحط 8080
    port = int(os.environ.get("PORT", 8080))
    server = socketserver.TCPServer(("0.0.0.0", port), MyHandler)
    print(f"=== تم فتح بورت الخدعة بنجاح على البورت: {port} ===")
    server.serve_forever()

# تشغيل سيرفر الويب في خلفية الكود عشان ريندر ما يقفل الخدمة
threading.Thread(target=run_web_server, daemon=True).start()


# --- تشغيل مكتبة الذكاء الاصطناعي بشكل يضمن عدم حدوث خطأ ---
# بنستخدم مكتبة google-generativeai كبديل أسهل في التثبيت أحياناً داخل السيرفرات
try:
    import google.generativeai as genai
except ModuleNotFoundError:
    import os
    os.system('pip install google-generativeai')
    import google.generativeai as genai

# إعداد وتجهيز المفاتيح
DISCORD_TOKEN = "ضع_توكن_ديسكورد_هنا"
GEMINI_API_KEY = "ضع_مفتاح_جيميني_هنا"
ALLOWED_CHANNEL_ID = 1514885534336417902

genai.configure(api_key=GEMINI_API_KEY)
# استخدام نموذج الفلاش السريع والخفيف للردود العامية
ai_model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    system_instruction="""
أنت عضو رهيب ومطنوخ ومصقّط في هذا السيرفر بالديسكورد.
قوانينك الصارمة في الرد:
1. رد بالعامية والشرقاوية أو النجدية أو الحجازية (اللهجة البيضاء القريبة للشباب وفلة الديسكورد).
2. ممنوع نهائياً تتكلم فصحى (لا تقل "أهلاً بك" بل قل "هلا والله" أو "أرحب").
3. طقطق وسولف مع الأعضاء كأنك خوي جالس معهم في القهوة، واستخدم رياكشنات وإيموجيات مناسبة لجو الكلام.
4. استخدم السياق والمحادثات السابقة المرفقة لك عشان تفهم وش السالفة بالسيرفر وتعرف وش يتكلمون عنه الأعضاء، وتكتشف الجو بنفسك.
"""
)

intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"البوت الذكي شغال وجاهز للاكتشاف في الروم المحدد باسم: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if message.channel.id != ALLOWED_CHANNEL_ID and not is_dm:
        return

    if bot.user.mentioned_in(message) or is_dm:
        async with message.channel.typing():
            try:
                context_messages = []
                async for msg in message.channel.history(limit=30):
                    if msg.id != message.id:
                        context_messages.append(f"{msg.author.display_name}: {msg.content}")
                
                context_messages.reverse()
                room_context = "\n".join(context_messages)
                current_user_input = f"{message.author.display_name}: {message.content.replace(f'<@{bot.user.id}>', '').strip()}"
                
                full_prompt = f"هذه السوالف الأخيرة اللي صارت في الروم عشان تفهم الجو:\n{room_context}\n\nالرسالة الجديدة الموجهة لك الآن:\n{current_user_input}\n\nرد عليها بناءً على جو السيرفر وبالعامية:"

                response = ai_model.generate_content(full_prompt)
                await message.reply(response.text)
                
            except Exception as e:
                print(f"خطأ في الاكتشاف أو الرد: {e}")
                await message.reply("سلك لي يا بعدي، مخي علق ثانية وجاي!")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
