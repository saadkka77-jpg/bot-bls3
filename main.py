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
            self.wfile.write("البوت شغال تمام في كل الرومات!".encode('utf-8'))

        def log_message(self, format, *args):
            return

    port = int(os.environ.get("PORT", 8080))
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), MyHandler)
        print(f"=== تم فتح بورت الخدعة بنجاح على البورت: {port} ===")
        server.serve_forever()
    except Exception as e:
        print(f"خطأ في تشغيل سيرفر الويب: {e}")

threading.Thread(target=run_web_server, daemon=True).start()

# --- 3️⃣ إعدادات تشغيل بوت الديسكورد ---
intents = discord.Intents.default()
intents.message_content = True  # تفعيل خاصية قراءة محتوى الرسائل
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"البوت الإداري شغال وجاهز لخدمة سيرفر BLS في كل الرومات باسم: {bot.user.name}")

@bot.event
async def on_message(message):
    # تجنب رد البوت على نفسه
    if message.author == bot.user:
        return

    # تنظيف النص وجعله كلمات صغيرة وإزالة علامة التعجب
    content = message.content.strip().lower().replace("!", "")

    # ==================== أمر: قوانين ====================
    if "قوانين" in content:
        embed = discord.Embed(
            title="📜 قوانين وإرشادات سيرفر BLS",
            description="نرجو من جميع الأعضاء الالتزام التام بالقوانين التالية للحفاظ على مجتمع آمن ومحترم للجميع.",
            color=discord.Color.red()
        )
        
        if message.guild and message.guild.icon:
            embed.set_thumbnail(url=message.guild.icon.url)
        else:
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else "")

        embed.add_field(
            name="⚖️ المادة الأولى: القذف والتشهير",
            value="يُمنع منعاً باتاً ممارسة القذف أو الإساءة اللفظية تجاه أي عضو، كما يُحظر أي محاولة للتشهير بالأشخاص. الهدف الأسمى هو الارتقاء بالمجتمع والحفاظ على الاحترام المتبادل كقاعدة أساسية.\n**العقوبة:** الحظر النهائي من المجتمع دون نقاش.",
            inline=False
        )
        embed.add_field(
            name="🕌 المادة الثانية: المقدسات والأديان",
            value="يُحظر تماماً الاستهزاء بالأديان أو الإساءة للمقدسات والقيم الدينية بكافة أشكالها وصورها.\n**العقوبة:** الحظر النهائي والمباشر.",
            inline=False
        )
        embed.add_field(
            name="📢 المادة الثالثة: النشر والإزعاج",
            value="يُمنع النشر العشوائي وتكرار الرسائل بصورة مزعجة، كما يُحظر إرسال الروابط الخارجية دون الحصول على إذن رسمي من الإدارة لضمان تنظيم المحادثات.\n**العقوبة:** الطرد أو الحظر المباشر.",
            inline=False
        )
        embed.add_field(
            name="🔊 المادة الرابعة: القنوات الصوتية والعامة",
            value="تُخصص القنوات العامة للدردشة الهادئة فقط، ويُمنع افتعال الفوضى أو إصدار أصوات تسبب الإزعاج للمتواجدين.",
            inline=False
        )
        embed.add_field(
            name="⚠️ تنويه هام إلى جميع أعضاء السيرفر الكرام (المادة الرابعة)",
            value="لاحظنا مؤخراً قيام بعض الأشخاص بإرسال روابط داخل قنوات السيرفر العامة، سواء كانت روابط مواقع أو روابط سيارات لمحاكي أو أي نوع آخر من الروابط.\n\nوحفاظاً على أمن وحماية السيرفر وسلامة الجميع، **يُمنع منعاً باتاً نشر أي رابط بجميع أشكاله داخل القنوات العامة**. إذا كنت ترغب في مشاركة رابط معين مع شخص، يرجى إرساله له في الخاص وليس داخل السيرفر لتجنب المخالفة وعقوبة التايم آوت.\n\nجرى التنبيه لإخلاء المسؤولية ونرجو من الجميع الالتزام لتجنب العقوبات والحفاظ على مجتمعنا آمناً. شاكرين لكم تفهمكم وتعاونكم الدائم.\n\n*(نظام الحماية متواجد من بداية السيرفر لكن التنويه من أجل تجنب التايم أوت من البوت بس)*",
            inline=False
        )
        
        embed.set_footer(text="إدارة سيرفر BLS • الاحترام أساس مجتمعنا", icon_url=bot.user.avatar.url if bot.user.avatar else "")
        await message.channel.send(content="|| @everyone ||", embed=embed)

    # ==================== أمر: رانك ====================
    elif "رانك" in content:
        embed = discord.Embed(
            title="🎮 الـــرتـــب الــمــتــاحـــة لـلــرانــكــا",
            description="نظام الرتب (الرانك) هو نظام مخصص لتحسين اللعب ورفع المستويات بحيث تلعب مع أشخاص بمثل مستواك أو أقل إذا رغبت في ذلك. وفرنا هذا نظام لجعل تجربتك في الألعاب أفضل ولتطوير مهاراتك. لكل رتبة دور (Role) محدد وقنوات صوتية وكتابية خاصة بها، بعيداً عن الدردشة العامة للعبة.",
            color=discord.Color.blue()
        )
        
        if message.guild and message.guild.icon:
            embed.set_thumbnail(url=message.guild.icon.url)
        else:
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else "")

        embed.add_field(
            name="⚽ [ رانـــك روكـــت لـــيـــق ]",
            value="<@&1479223202336084230>\n<@&1479240455974686791>\n<@&1479240650435068085>\n<@&1479240876810174595>\n<@&1479240916601667604>\n<@&1479240999346638978>\n<@&1479241080326066296>\n<@&1479241114811629680>",
            inline=False
        )
        embed.add_field(
            name="🛡️ [ رانـــك أوفر واتش ]",
            value="<@&1479253167836499978>\n<@&1479928984711204946>\n<@&1480017625772986468>\n<@&1479537667577348137>\n<@&1479537820740751402>\n<@&1479539094999531522>\n<@&1479538006145761542>\n<@&1479538137960022018>\n<@&1479539783142477934>\n\n*رانك أوفر واتش لمنصة الحاسب منفصل عن منصة السوني، كما وفرنا قناة مشتركة إذا كنت ترغب في اللعب مع أصدقائك من منصات مختلفة. توجد رتبة خاصة لمستخدِمي البي سي ورتبة خاصة لمستخدِمي السوني وذلك لأن نظام التصنيف في أوفر واتش يختلف عن باقي الألعاب.*",
            inline=False
        )
        embed.add_field(
            name="💥 [ مــارفــل ريــفــلــز ]",
            value="<@&1480079573797437490>\n<@&1480079673722409143>\n<@&1480079726709182616>\n<@&1480079933794549910>\n<@&1480080104494469121>\n<@&1480080178754617467>",
            inline=False
        )
        embed.add_field(
            name="🔫 [ رانــك كــود ]",
            value="<@&1480081751299723344>\n<@&1480082094427471882>\n<@&1480082355459850240>\n<@&1480082585760698368>\n<@&1480082810155958343>\n<@&1480082979798651033>\n<@&1480083149605179473>",
            inline=False
        )
        embed.add_field(
            name="🚀 ابدأ رحلتك الآن",
            value="اختر رتبتك الآن وابدأ رحلتك نحو القمة! للحصول على الرتبة يرجى فتح تذكرة في [ <#1481127399042322582> ] الدعم الفني.",
            inline=False
        )
        
        embed.set_footer(text="سيرفر BLS • نحو القمة دائماً", icon_url=bot.user.avatar.url if bot.user.avatar else "")
        await message.channel.send(content="|| @everyone ||", embed=embed)

    # ==================== أمر: متجر ====================
    elif "متجر" in content:
        embed = discord.Embed(
            title="🏪 اتفاقية وقوانين التعامل مع المتجر",
            description="***بمجرد تعاملك مع المتجر أو دخولك للمزاد، فإنك تقر بموافقتك التامة على الشروط والسياسات التالية:***",
            color=discord.Color.gold()
        )
        
        if message.guild and message.guild.icon:
            embed.set_thumbnail(url=message.guild.icon.url)
        else:
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else "")

        # تم تقسيم البنود هنا لحل مشكلة الـ 1024 حرفاً (القسم الأول 1-5)
        embed.add_field(
            name="💳 الشروط والبنود الرسمية (الجزء الأول):",
            value=(
                "`1-` **بمجرد تحويل المبلغ ووصول رسالة التأكيد إلينا، سيتم تسليمك الحساب فوراً.**\n"
                "`2-` تخضع جميع عمليات البيع لسياسة عدم الاسترجاع أو الاستبدال بعد إتمام الدفع أو التسليم، إلا في حال وجود عيب فني مثبت من طرف إدارة المتجر.\n"
                "`3-` يخلي المتجر مسؤوليته الكاملة عن أي إغلاق أو حظر للحسابات ناتج عن مخالفة سياسات الشركة المصنعة للعبة أو سوء استخدام العميل للحساب بعد استلامه وتغيير بياناته.\n"
                "`4-` تعتبر المشاركة في المزاد التزاماً قطعياً بالشراء، ويُمنع منعاً باتاً حذف السومة أو التراجع عنها لأي سبب كان.\n"
                "`5-` في حال الفوز بالمزاد، يجب إتمام الدفع خلال المدة المحددة من قِبل الإدارة."
            ),
            inline=False
        )

        # القسم الثاني (6-10) لضمان عدم تخطي الليميت
        embed.add_field(
            name="💳 الشروط والبنود الرسمية (الجزء الثاني):",
            value=(
                "`6-` أي محاولة للتراجع أو حذف السومة أو التلاعب بالأسعار أو عدم الدفع بعد الفوز ستؤدي إلى حظر نهائي من السيرفر فوراً ودون نقاش.\n"
                "`7-` يتحمل العميل مسؤولية قراءة وصف الحساب والمنتج بدقة قبل الشراء، حيث لا يتحمل المتجر مسؤولية خطأ العميل في الاختيار.\n"
                "`8-` أي محاولة تلاعب في إيصالات التحويل أو الادعاء الكاذب بالدفع تؤدي إلى حظر نهائي وإلغاء الطلب فوراً.\n"
                "`9-` **الاحترام متبادل بين العميل والإدارة، وأي تجاوز لفظي أو استنقاص من السلع يعطي المتجر الحق في حظر العميل وإلغاء التعامل معه.**\n"
                "`10-` **يؤكد المتجر بأنه غير مسؤول نهائياً عن أي منتج يتم بيعه أو تداوله بين الأعضاء خارج إشراف الإدارة المباشر، ولا يتحمل أي تبعات قانونية أو تقنية تتعلق بصفقات تتم بصفة شخصية بين المستخدمين.**"
            ),
            inline=False
        )

        embed.add_field(
            name="💡 إعلان صريح ومهم",
            value="***بشرائك من المتجر أو مشاركتك في المزاد، أنت تعلن صراحةً اطلاعك على هذه القوانين وموافقتك عليها. الإدارة غير ملزمة بتنبيهك قبل تنفيذ العقوبة في حال ارتكاب أي مخالفة لهذه البنود.***",
            inline=False
        )
        embed.add_field(
            name="💰 طرق الدفع المعتمدة :",
            value="**` البنوك السعوديه `**\n*موضحة في الصورة أدناه*",
            inline=False
        )
        
        # الروابط الجديدة الصحيحة اللي أرسلتها
        img_banks = "https://cdn.discordapp.com/attachments/1479654263620898897/1509660121217892384/8af69cb5-adc4-4416-ac2a-126d7b5b586c.png"
        embed.set_image(url=img_banks)
        embed.set_footer(text="متجر BLS الرسمي", icon_url=bot.user.avatar.url if bot.user.avatar else "")

        # إرسال الرسالة الأولى للمتجر بعد الإصلاح
        await message.channel.send(content="|| @everyone ||", embed=embed)

        # رسالة الصورة الثانية التوضيحية
        embed_info = discord.Embed(
            description="***هذا توضيح كامل لكل شيء ممكن يواجهك في أي حساب مشترك الرجاء مراجعة قوانين المتجر من الجميع قبل أي شراء***",
            color=discord.Color.gold()
        )
        img_info = "https://cdn.discordapp.com/attachments/1479654263620898897/1512939354350293133/2169675d-38fd-48db-be9f-8b137f641d25.jpg"
        embed_info.set_image(url=img_info)
        
        await message.channel.send(embed=embed_info)

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
