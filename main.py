import discord
from discord.ext import commands
from google import genai

# إعداد وتجهيز المفاتيح
DISCORD_TOKEN = "ضع_توكن_ديسكورد_هنا"
GEMINI_API_KEY = "ضع_مفتاح_جيميني_هنا"

# الـ ID الخاص بالروم المسموح للبوت بالرد فيه
ALLOWED_CHANNEL_ID = 1514885534336417902

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True  # ضروري جداً يقرأ الرسائل عشان يكتشف السيرفر
bot = commands.Bot(command_prefix="!", intents=intents)

# التوجيهات الصارمة للبوت ليتحدث بالعامية ويتأقلم مع الجو
SYSTEM_INSTRUCTION = """
أنت عضو رهيب ومطنوخ ومصقّط في هذا السيرفر بالديسكورد.
قوانينك الصارمة في الرد:
1. رد بالعامية والشرقاوية أو النجدية أو الحجازية (اللهجة البيضاء القريبة للشباب وفلة الديسكورد).
2. ممنوع نهائياً تتكلم فصحى (لا تقل "أهلاً بك" بل قل "هلا والله" أو "أرحب").
3. طقطق وسولف مع الأعضاء كأنك خوي جالس معهم في القهوة، واستخدم رياكشنات وإيموجيات مناسبة لجو الكلام.
4. استخدم السياق والمحادثات السابقة المرفقة لك عشان تفهم وش السالفة بالسيرفر وتعرف وش يتكلمون عنه الأعضاء، وتكتشف الجو بنفسك.
"""

@bot.event
async def on_ready():
    print(f"البوت الذكي شغال وجاهز للاكتشاف في الروم المحدد باسم: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # التحقق: إذا كانت الرسالة ليست في الروم المحدد وليست في الخاص (DM)، يتجاهلها فوراً
    is_dm = isinstance(message.channel, discord.DMChannel)
    if message.channel.id != ALLOWED_CHANNEL_ID and not is_dm:
        return

    # الرد إذا تم منشنة البوت أو إذا أرسل له أحد في الخاص
    if bot.user.mentioned_in(message) or is_dm:
        async with message.channel.typing():
            try:
                # 🧠 البوت يكتشف السيرفر عبر قراءة آخر 30 رسالة في هذا الروم عشان يفهم الجو
                context_messages = []
                async for msg in message.channel.history(limit=30):
                    if msg.id != message.id: # نتخطى رسالة المنشن الحالية عشان نرتبها بالنهاية
                        context_messages.append(f"{msg.author.display_name}: {msg.content}")
                
                # ترتيب الرسائل من الأقدم للأحدث
                context_messages.reverse()
                
                # دمج سوالف الروم السابقة مع رسالة المستخدم الجديدة
                room_context = "\n".join(context_messages)
                current_user_input = f"{message.author.display_name}: {message.content.replace(f'<@{bot.user.id}>', '').strip()}"
                
                # صياغة الطلب الكامل للذكاء الاصطناعي
                full_prompt = f"هذه السوالف الأخيرة اللي صارت في الروم عشان تفهم الجو:\n{room_context}\n\nالرسالة الجديدة الموجهة لك الآن:\n{current_user_input}\n\nرد عليها بناءً على جو السيرفر وبالعامية:"

                # إرسال البيانات لجيميني
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=full_prompt,
                    config={"system_instruction": SYSTEM_INSTRUCTION}
                )
                
                # الرد المباشر بالعامية
                await message.reply(response.text)
                
            except Exception as e:
                print(f"خطأ في الاكتشاف أو الرد: {e}")
                await message.reply("سلك لي يا بعدي، مخي علق ثانية وجاي!")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
