import discord
from discord.ext import commands, tasks
import sqlite3
import random
import asyncio
import os
import time
from threading import Thread
from flask import Flask
from PIL import Image, ImageDraw

# ----------------- إعدادات سيرفر الويب للـ UptimeRobot -----------------
app = Flask('')

@app.route('/')
def home():
    return "Kingdom War Bot is Alive and Running 24/7!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ----------------- إعدادات البوت والـ Intents -----------------
intents = discord.Intents.default()
intents.message_content = True
# تم تغيير البريفكس ليصبح سادة بدون علامة تعجب
bot = commands.Bot(command_prefix="", intents=intents)

# الروم الموحد المخصص للعب والبيع وكل شيء
GAME_CHANNEL_ID = 1515267885201625150

# ----------------- إعدادات قاعدة البيانات SQLITE -----------------
conn = sqlite3.connect('kingdom_war.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    kingdom_name TEXT,
    gold INTEGER DEFAULT 0,
    coal INTEGER DEFAULT 0,
    diamonds INTEGER DEFAULT 0,
    wood INTEGER DEFAULT 0,
    stone INTEGER DEFAULT 0,
    iron INTEGER DEFAULT 0,
    soldiers INTEGER DEFAULT 6,
    citizens INTEGER DEFAULT 10,
    builders INTEGER DEFAULT 1,
    wooden_houses INTEGER DEFAULT 1,
    stone_houses INTEGER DEFAULT 0,
    iron_houses INTEGER DEFAULT 0,
    wall_level TEXT DEFAULT 'لا يوجد',
    spies INTEGER DEFAULT 0,
    miners INTEGER DEFAULT 0,
    last_tax_day TEXT,
    cooldown_challenge REAL DEFAULT 0,
    cooldown_attack REAL DEFAULT 0,
    cooldown_steal REAL DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS alliances (
    leader_id INTEGER PRIMARY KEY,
    member_id INTEGER
)
''')
conn.commit()

# ----------------- أنظمة وميزات اللعبة الداخلية -----------------
current_market_items = {}
last_market_update = 0  # لتتبع وقت تحديث السوق تلقائياً كل 15 دقيقة

def generate_market_items():
    global current_market_items, last_market_update
    items = {
        "فحم": {"price": random.randint(15, 30), "stock": random.randint(5, 15)},
        "الماس": {"price": random.randint(100, 200), "stock": random.randint(1, 3)},
        "خشب": {"price": random.randint(10, 20), "stock": random.randint(10, 30)},
        "حجر": {"price": random.randint(12, 25), "stock": random.randint(10, 25)},
        "حديد": {"price": random.randint(25, 50), "stock": random.randint(5, 15)},
        "بناء إضافي": {"price": 1500, "stock": 1}
    }
    # تم تقليل عدد الأغراض المعروضة إلى 2 فقط لتصبح الأغراض قليلة جداً
    selected_keys = random.sample(list(items.keys()), 2)
    current_market_items = {k: items[k] for k in selected_keys}
    last_market_update = time.time()

def draw_kingdom_map():
    img = Image.new('RGB', (800, 800), color='#1e3f20')
    canvas = ImageDraw.Draw(img)
    
    for i in range(0, 800, 100):
        canvas.line([(i, 0), (i, 800)], fill='#2d5a30', width=1)
        canvas.line([(0, i), (800, i)], fill='#2d5a30', width=1)
        
    cursor.execute("SELECT kingdom_name, user_id FROM players WHERE kingdom_name IS NOT NULL")
    kingdoms = cursor.fetchall()
    
    random.seed(42)
    positions = [(x, y) for x in range(50, 750, 150) for y in range(50, 750, 150)]
    
    for idx, kingdom in enumerate(kingdoms):
        if idx >= len(positions): break
        pos = positions[idx]
        canvas.rectangle([pos[0]-30, pos[1]-30, pos[0]+30, pos[1]+30], fill='#8b0000', outline='#ffffff', width=2)
        canvas.text((pos[0]-25, pos[1]-45), f"[{kingdom[0]}]", fill='#ffffff')
        
    img.save('map.png')

# ----------------- الـ Loops التلقائية المتبقية -----------------
@tasks.loop(minutes=20)
async def miners_production_loop():
    cursor.execute("SELECT user_id, miners FROM players WHERE miners > 0")
    players = cursor.fetchall()
    
    for player in players:
        uid, m_count = player[0], player[1]
        cycles = 1
        if m_count >= 10:
            cycles = 10
        elif m_count >= 5:
            cycles = 4
            
        produced_wood, produced_stone, produced_iron, produced_coal, produced_diamonds = 0, 0, 0, 0, 0
        
        for _ in range(cycles * m_count):
            roll = random.random()
            if roll <= 0.05:
                produced_diamonds += random.randint(1, 10)
            elif roll <= 0.15:
                produced_coal += random.randint(1, 5)
            else:
                res = random.choice(['wood', 'stone', 'iron'])
                if res == 'wood': produced_wood += random.randint(2, 8)
                elif res == 'stone': produced_stone += random.randint(2, 8)
                else: produced_iron += random.randint(1, 5)
                
        cursor.execute('''
            UPDATE players SET 
            wood = wood + ?, stone = stone + ?, iron = iron + ?, coal = coal + ?, diamonds = diamonds + ?
            WHERE user_id = ?
        ''', (produced_wood, produced_stone, produced_iron, produced_coal, produced_diamonds, uid))
    conn.commit()

@tasks.loop(minutes=30)
async def half_hour_tax_loop():
    if random.choice([True, False]):
        cursor.execute("SELECT user_id, citizens FROM players WHERE kingdom_name IS NOT NULL")
        players = cursor.fetchall()
        for player in players:
            uid, citizens = player[0], player[1]
            earnings = int((citizens / 100) * 6)
            if earnings < 1:
                earnings = random.randint(1, 3)
                
            cursor.execute("SELECT * FROM alliances WHERE leader_id = ? OR member_id = ?", (uid, uid))
            if cursor.fetchone():
                earnings = int(earnings * 1.25)
                
            cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (earnings, uid))
        conn.commit()

@tasks.loop(hours=5)
async def iron_house_bonus_loop():
    cursor.execute("SELECT user_id, iron_houses FROM players WHERE iron_houses > 0")
    players = cursor.fetchall()
    for player in players:
        uid, iron_houses = player[0], player[1]
        bonus_citizens = iron_houses * 10
        
        cursor.execute("SELECT * FROM alliances WHERE leader_id = ? OR member_id = ?", (uid, uid))
        if cursor.fetchone():
            bonus_citizens += int(bonus_citizens * 0.2)
            
        cursor.execute("UPDATE players SET citizens = citizens + ? WHERE user_id = ?", (bonus_citizens, uid))
    conn.commit()

# ----------------- أحداث البوت -----------------
@bot.event
async def on_ready():
    print(f"👑 تم تشغيل البوت بنجاح باسم: {bot.user}")
    generate_market_items() # توليد أول بضاعة عند التشغيل
    miners_production_loop.start()
    half_hour_tax_loop.start()
    iron_house_bonus_loop.start()

def is_game_channel():
    async def predicate(ctx):
        if ctx.channel.id != GAME_CHANNEL_ID:
            await ctx.send(f"⚠️ **عذراً الملك، الأوامر الاستراتيجية تنفذ فقط في الروم المخصص: <#{GAME_CHANNEL_ID}>**")
            return False
        return True
    return commands.check(predicate)

# ----------------- أوامر البوت المعدلة بدون علامات -----------------
@bot.command(name="انشان_ارض", aliases=["انشاء_ارض"])
@is_game_channel()
async def create_land(ctx, *, name: str):
    uid = ctx.author.id
    cursor.execute("SELECT kingdom_name FROM players WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    
    if row and row[0] is not None:
        return await ctx.send("❌ **أنت تمتلك مملكة مسجلة بالفعل في أراضي الحرب العظمى!**")
        
    if row:
        cursor.execute("UPDATE players SET kingdom_name = ? WHERE user_id = ?", (name, uid))
    else:
        cursor.execute('''
            INSERT INTO players (user_id, kingdom_name, gold, coal, diamonds, wood, stone, iron, soldiers, citizens, builders)
            VALUES (?, ?, 1000, 10, 2, 200, 200, 100, 6, 10, 1, 1)
        ''', (uid, name))
    conn.commit()
    
    embed = discord.Embed(title="🏰 تأسيس المملكة العظمى", color=discord.Color.green())
    embed.description = f"تم بنجاح تسجيل مملكتك باسم **【 {name} 】** في الخرائط الملكية!\n\n**🎁 هدايا التأسيس الملكية:**\n⚔️ جنود: `6` | 👥 سكان: `10` | 👷 بناؤون: `1` | 🪵 بيت خشب: `1`"
    await ctx.send(embed=embed)

@bot.command(name="مملكتي")
@is_game_channel()
async def info_kingdom(ctx):
    uid = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    
    if not p or p[1] is None:
        return await ctx.send("❌ **لا تملك أرضاً بعد! اكتب: `انشاء_ارض [اسم الأرض]` لبدء مسيرتك.**")
        
    embed = discord.Embed(title=f"🏰 مملكة 【 {p[1]} 】 -- الحاكم {ctx.author.name}", color=discord.Color.dark_red())
    embed.add_field(name="💰 الخزينة والعملات", value=f"🪙 الذهب: `{p[2]}`\n💎 الألماس: `{p[4]}`\n🔥 الفحم: `{p[3]}`", inline=True)
    embed.add_field(name="🪵 الموارد الخام", value=f"🪵 الخشب: `{p[5]}`\n🪨 الحجر: `{p[6]}`\n⛓️ الحديد: `{p[7]}`", inline=True)
    embed.add_field(name="👥 القوة البشرية", value=f"⚔️ الجنود: `{p[8]}`\n👥 السكان: `{p[9]}`\n👷 البناؤون: `{p[10]}`", inline=True)
    embed.add_field(name="🏘️ العقارات والحماية", value=f"🪵 بيوت خشب: `{p[11]}`\n🪨 بيوت حجر: `{p[12]}`\n⛓️ بيوت حديد: `{p[13]}`\n🛡️ السور: `[{p[14]}]`", inline=True)
    embed.add_field(name="🕵️ الأجهزة السرية", value=f"🕵️ الجواسيس: `{p[15]}`\n⛏️ المنقبين: `{p[16]}/10 [Max]`", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="بائع", aliases=["البائع", "سوق", "المتجر"])
@is_game_channel()
async def show_market(ctx):
    global current_market_items, last_market_update
    # التحقق مما إذا مرت 15 دقيقة (900 ثانية) لتحديث السوق عشوائياً تلقائياً
    if time.time() - last_market_update > 900:
        generate_market_items()

    embed = discord.Embed(title="🏪 متجر الممالك المتنقل - البضائع المتاحة!", color=discord.Color.gold())
    embed.description = "وصل التاجر المتجول لساحة الحرب وحمل معه بضائع محدودة جداً! يتغير السوق تلقائياً كل 15 دقيقة."
    for item, info in current_market_items.items():
        embed.add_field(name=f"📦 {item}", value=f"السعر: `{info['price']}` ذهبة\nالكمية المتاحة: `{info['stock']}`", inline=True)
    
    embed.set_footer(text="للشراء اكتب: شراء [اسم_الغرض] [الكمية]")
    await ctx.send(embed=embed)

@bot.command(name="شراء")
@is_game_channel()
async def buy_market(ctx, item_name: str, quantity: int = 1):
    global current_market_items
    if time.time() - last_market_update > 900:
        generate_market_items()
        
    if item_name not in current_market_items: 
        return await ctx.send("❌ هذا الغرض غير متوفر في بضائع التاجر الحالية، اكتب `بائع` لرؤية المتاح.")
    
    uid = ctx.author.id
    info = current_market_items[item_name]
    if info['stock'] < quantity: 
        return await ctx.send(f"❌ الكمية المطلوبة غير متوفرة! المتاح هو `{info['stock']}` فقط.")
    
    total_cost = info['price'] * quantity
    cursor.execute("SELECT gold FROM players WHERE user_id = ?", (uid,))
    p_gold = cursor.fetchone()[0]
    if p_gold < total_cost: 
        return await ctx.send(f"❌ ذهبك غير كافٍ. تحتاج `{total_cost}` ذهبة لشراء هذه الكمية.")
    
    current_market_items[item_name]['stock'] -= quantity
    res_map = {"فحم": "coal", "الماس": "diamonds", "خشب": "wood", "حجر": "stone", "حديد": "iron"}
    if item_name in res_map:
        db_col = res_map[item_name]
        cursor.execute(f"UPDATE players SET gold = gold - ?, {db_col} = {db_col} + ? WHERE user_id = ?", (total_cost, quantity, uid))
    elif item_name == "بناء إضافي":
        cursor.execute("UPDATE players SET gold = gold - ?, builders = builders + ? WHERE user_id = ?", (total_cost, quantity, uid))
        
    conn.commit()
    await ctx.send(f"🛍️ **تمت عملية الشراء بنجاح! اشتريت `{quantity}` من [{item_name}] بسعر إجمالي ناهز `{total_cost}` ذهبة.**")

@bot.command(name="تطوير_بيت")
@is_game_channel()
async def upgrade_house(ctx, type_house: str, quantity: int = 1):
    if quantity <= 0: return await ctx.send("❌ **الكمية يجب أن تكون أكبر من صفر!**")
    uid = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    
    if not p or p[1] is None: return await ctx.send("❌ ليس لديك مملكة.")
    
    wood_discount = (p[5] // 100) * 0.25
    stone_discount = (p[6] // 100) * 0.25
    iron_discount = (p[7] // 100) * 0.25

    if type_house == "خشب":
        cost = max(1, int((100 - wood_discount) * quantity))
        if p[2] < cost: return await ctx.send(f"❌ الذهب غير كافٍ. تحتاج `{cost}` ذهبة.")
        if p[10] < quantity: return await ctx.send(f"❌ ليس لديك بناؤون كافيين (`{quantity}`) للقيام بالعملية دفعة واحدة.")
        cursor.execute("UPDATE players SET gold = gold - ?, wooden_houses = wooden_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity*10, uid))
        
    elif type_house == "حجر":
        if p[11] < quantity: return await ctx.send("❌ يجب أن تمتلك بيوت خشب كافية أولاً لتطويرها إلى حجر!")
        cost = max(1, int((200 - stone_discount) * quantity))
        if p[2] < cost: return await ctx.send(f"❌ الذهب غير كافٍ. تحتاج `{cost}` ذهبة.")
        if p[10] < quantity: return await ctx.send(f"❌ البناؤون مشغولون، تحتاج `{quantity}` من البنائين.")
        cursor.execute("UPDATE players SET gold = gold - ?, wooden_houses = wooden_houses - ?, stone_houses = stone_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity, quantity*20, uid))
        
    elif type_house == "حديد":
        if p[12] < quantity: return await ctx.send("❌ يجب أن تمتلك بيوت حجر كافية أولاً لتطويرها إلى حديد!")
        cost = max(1, int((350 - iron_discount) * quantity))
        if p[2] < cost: return await ctx.send(f"❌ الذهب غير كافٍ. تحتاج `{cost}` ذهبة.")
        if p[10] < quantity: return await ctx.send(f"❌ البناؤون مشغولون، تحتاج `{quantity}` من البنائين.")
        cursor.execute("UPDATE players SET gold = gold - ?, stone_houses = stone_houses - ?, iron_houses = iron_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity, quantity*70, uid))
    else:
        return await ctx.send("❓ **نوع البيت غير معروف. اختر: (خشب، حجر، حديد)**")

    conn.commit()
    wait_time = 180 if quantity >= 10 else 60
    await ctx.send(f"👷 **بدأ البناؤون في تشييد وتطوير العقارات الملكية... انتظر القائد `{wait_time}` ثانية لاتمام البناء.**")
    await asyncio.sleep(wait_time)
    await ctx.send(f"🎉 **تهانينا يا {ctx.author.mention}! تم الانتهاء من تطوير `{quantity}` بيت من لفل {type_house} وازداد عدد سكانك وقوة قريتك.**")

@bot.command(name="تطوير_سور")
@is_game_channel()
async def upgrade_wall(ctx, type_wall: str):
    uid = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    current_wall = p[14]
    
    if type_wall == "خشب":
        if current_wall != "لا يوجد": return await ctx.send("❌ سورك الحالي أقوى أو مساوٍ للخشب بالفعل!")
        if p[2] < 500: return await ctx.send("❌ تحتاج 500 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 500, wall_level = 'خشب' WHERE user_id = ?", (uid,))
    elif type_wall == "حجر":
        if current_wall != "خشب": return await ctx.send("❌ يجب ترقية السور إلى خشب أولاً!")
        if p[2] < 1000: return await ctx.send("❌ تحتاج 1000 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 1000, wall_level = 'حجر' WHERE user_id = ?", (uid,))
    elif type_wall == "حديد":
        if current_wall != "حجر": return await ctx.send("❌ يجب ترقية السور إلى حجر أولاً!")
        if p[2] < 3000: return await ctx.send("❌ تحتاج 3000 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 3000, wall_level = 'حديد' WHERE user_id = ?", (uid,))
    else:
        return await ctx.send("❓ **أنواع الأسوار المتاحة للتطوير بالترتيب: (خشب، حجر، حديد)**")
        
    conn.commit()
    await ctx.send(f"🛡️ **تم تعزيز وتطوير سور مملكتك بنجاح ليكون من الـ {type_wall}!**")

@bot.command(name="تدريب_جنود")
@is_game_channel()
async def train_soldiers(ctx, quantity_groups: int = 1):
    uid = ctx.author.id
    cursor.execute("SELECT gold, citizens FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    
    needed_gold = quantity_groups * 10
    needed_citizens = quantity_groups * 5
    
    if p[0] < needed_gold: return await ctx.send(f"❌ لا تملك الذهب الكافي. تحتاج `{needed_gold}` ذهبة.")
    if p[1] < needed_citizens: return await ctx.send(f"❌ ليس لديك سكان كافيين للتحويل. تحتاج `{needed_citizens}` مواطن.")
    
    cursor.execute('''
        UPDATE players SET gold = gold - ?, citizens = citizens - ?, soldiers = soldiers + ?
        WHERE user_id = ?
    ''', (needed_gold, needed_citizens, quantity_groups * 5, uid))
    conn.commit()
    await ctx.send(f"⚔️ **تم إرسال `{needed_citizens}` مواطن لثكنات التدريب الحربية، وحصلت على `{quantity_groups * 5}` جندياً جديداً لحماية العرش!**")

class ChallengeView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ **هذا التحدي ملك لحاكم آخر، اكتب `تحدي` للحصول على تحدياتك الخاصة!**", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ غارة الغابة", style=discord.ButtonStyle.danger)
    async def c1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_challenge(interaction, "غارة الغابة المكثفة", random.randint(1, 3))

    @discord.ui.button(label="⛏️ تأمين منجم منهار", style=discord.ButtonStyle.secondary)
    async def c2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_challenge(interaction, "تأمين المناجم القديمة", random.randint(1, 3))

    @discord.ui.button(label="📦 حماية القافلة الملكية", style=discord.ButtonStyle.success)
    async def c3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_challenge(interaction, "حماية قافلة الذهب المتنقلة", random.randint(2, 3))

    async def process_challenge(self, interaction, name, gold_reward):
        uid = interaction.user.id
        cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold_reward, uid))
        conn.commit()
        await interaction.response.send_message(f"🏆 **نجحت في تحدي [{name}]! منحتك القيادة العليا مكافأة برصيد `{gold_reward}` عملة ذهبية.**", ephemeral=False)
        self.stop()

@bot.command(name="تحدي")
@is_game_channel()
async def challenge(ctx):
    view = ChallengeView(ctx.author)
    embed = discord.Embed(title="⚔️ قائمة التحديات الاستراتيجية للممالك", description="اختر أحد التحديات المتاحة لقيادة قواتك، المكافأة القصوى للتحدي هي **3 عملات ذهبية**.", color=discord.Color.blue())
    await ctx.send(embed=embed, view=view)

@bot.command(name="توظيف_جاسوس")
@is_game_channel()
async def hire_spy(ctx):
    uid = ctx.author.id
    cursor.execute("SELECT citizens, soldiers FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if p[0] < 10 or p[1] < 3: return await ctx.send("❌ **المتطلبات غير متوفرة! تحتاج لتوفير التضحية التالية: (10 سكان و 3 جنود) لتوظيف جاسوس سري.**")
    cursor.execute("UPDATE players SET citizens = citizens - 10, soldiers = soldiers - 3, spies = spies + 1 WHERE user_id = ?", (uid,))
    conn.commit()
    await ctx.send("🕵️ **تمت التضحية بالموارد البشرية وتجنيد جاسوس محترف في جهازك السري للسرقة والاستطلاع!**")

@bot.command(name="توظيف_منقب")
@is_game_channel()
async def hire_miner(ctx):
    uid = ctx.author.id
    cursor.execute("SELECT citizens, soldiers, miners FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if p[2] >= 10: return await ctx.send("❌ **لقد وصلت للحد الأقصى لعدد المنقبين في مملكتك (10 منقبين - لفل ماكس)!**")
    if p[0] < 3 or p[1] < 1: return await ctx.send("❌ **لا تملك تضحية كافية. تحتاج (3 سكان و 1 جندي).**")
    cursor.execute("UPDATE players SET citizens = citizens - 3, soldiers = soldiers - 1, miners = miners + 1 WHERE user_id = ?", (uid,))
    conn.commit()
    await ctx.send(f"⛏️ **تم توظيف منقب جديد بنجاح! عدد منقبيك الحالي هو `{p[2] + 1}/10`. كلما زادوا زادت سرعة استخراج المواد.**")

@bot.command(name="سرقة")
@is_game_channel()
async def steal_gold(ctx, target: discord.Member):
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكنك سرقة نفسك أيها الحاكم!")
    
    cursor.execute("SELECT spies, gold FROM players WHERE user_id = ?", (uid,))
    p_thief = cursor.fetchone()
    cursor.execute("SELECT spies, gold FROM players WHERE user_id = ?", (tid,))
    p_target = cursor.fetchone()
    
    if not p_thief or p_thief[0] < 1: return await ctx.send("❌ **لا تمتلك جواسيس! وظف جاسوس أولاً عبر أمر: `توظيف_جاسوس`.**")
    if not p_target or p_target[1] <= 0: return await ctx.send("❌ **خزينة هذا الحاكم خالية تماماً من الذهب حالياً.**")
    
    await ctx.send(f"🕵️‍♂️ **تسلل جاسوسك متوجهاً لخزائن {target.mention}... جاري تنفيذ العملية السرية!**")
    
    if p_target[0] > 0 and random.random() < 0.25:
        cursor.execute("UPDATE players SET spies = spies - 1 WHERE user_id = ?", (uid,))
        conn.commit()
        return await ctx.send(f"💀 **أمر كارثي! تم كشف جاسوسك في نفس الثانية بواسطة الدفاعات السرية للمملكة المستهدفة، وتم إعدامه فوراً!**")
        
    stolen_gold = random.randint(1, min(10, p_target[1]))
    cursor.execute("UPDATE players SET gold = gold - ? WHERE user_id = ?", (stolen_gold, tid))
    cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (stolen_gold, uid))
    conn.commit()
    await ctx.send(f"💰 **نجحت السرقة! عاد الجاسوس محملاً بـ `{stolen_gold}` عملة ذهبية من خزائن الخصم.**")

@bot.command(name="تحالف")
@is_game_channel()
async def ally(ctx, target: discord.Member):
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكنك إقامة تحالف مع نفسك!")
    
    cursor.execute("SELECT * FROM alliances WHERE leader_id = ? OR member_id = ? OR leader_id = ? OR member_id = ?", (uid, uid, tid, tid))
    if cursor.fetchone(): return await ctx.send("❌ **أحد الطرفين أو كلاهما منضم بالفعل في تحالف قائم! يجب فسخ التحالف السابق أولاً.**")
    
    await ctx.send(f"🤝 **يا {target.mention}، يعرض عليك الملك {ctx.author.mention} إقامة تحالف استراتيجي لدمج الممالك! هل تقبل؟ اكتب (موافق/ارفض)**")
    
    def check(m):
        return m.author == target and m.channel == ctx.channel and m.content in ['موافق', 'ارفض']
        
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content == 'موافق':
            cursor.execute("INSERT INTO alliances (leader_id, member_id) VALUES (?, ?)", (uid, tid))
            conn.commit()
            await ctx.send(f"🎉 **تم توقيع معاهدة السلام العظمى! أصبحت مملكة {ctx.author.mention} ومملكة {target.mention} دولة واحدة قوية وحليفة من الآن فصاعداً!**")
        else:
            await ctx.send(f"❌ **تم رفض طلب التحالف من قِبل الحاكم المستهدف.**")
    except asyncio.TimeoutError:
        await ctx.send("⏳ **انتهى وقت الاستجابة لطلب التحالف الملكي.**")

@bot.command(name="فسخ_التحالف")
@is_game_channel()
async def break_ally(ctx, target: discord.Member):
    uid = ctx.author.id
    tid = target.id
    cursor.execute("DELETE FROM alliances WHERE (leader_id = ? AND member_id = ?) OR (leader_id = ? AND member_id = ?)", (uid, tid, tid, uid))
    conn.commit()
    await ctx.send(f"💔 **تم فسخ المعاهدة وإعلان إنهاء التحالف رسمياً بين مملكتك ومملكة {target.mention}.**")

@bot.command(name="هجوم")
@is_game_channel()
async def attack(ctx, target: discord.Member):
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكن الهجوم على نفسك!")
    
    cursor.execute("SELECT kingdom_name, soldiers, gold, coal, diamonds, wood, stone, iron FROM players WHERE user_id = ?", (uid,))
    p_att = cursor.fetchone()
    cursor.execute("SELECT kingdom_name, soldiers, gold, coal, diamonds, wood, stone, iron FROM players WHERE user_id = ?", (tid,))
    p_def = cursor.fetchone()
    
    if not p_att or p_att[0] is None: return await ctx.send("❌ لا تملك مملكة لتهجم بها.")
    if not p_def or p_def[0] is None: return await ctx.send("❌ الطرف المستهدف لا يمتلك مملكة قائمة.")
    
    att_soldiers = p_att[1]
    def_soldiers = p_def[1]
    
    if att_soldiers == 0: return await ctx.send("❌ **جيشك فارغ تماماً! لا يمكنك إرسال غزو بدون جنود.**")
    
    await ctx.send("⚔️ ⚔️ **[ جاري الهجوم والزحف العسكري.. انتظر دقيقة كاملة لمعرفة نتائج المعركة الطاحنة! ]** ⚔️ ⚔️")
    await asyncio.sleep(60)
    
    win = False
    diff = att_soldiers - def_soldiers
    
    if att_soldiers >= 2000: win = True
    elif diff >= 1000: win = True
    elif diff >= 300:
        if random.random() <= 0.40: win = True
    else:
        if random.randint(0, att_soldiers + def_soldiers) < att_soldiers: win = True
            
    if win:
        cursor.execute('''
            UPDATE players SET 
            gold = gold + ?, coal = coal + ?, diamonds = diamonds + ?, wood = wood + ?, stone = stone + ?, iron = iron + ?
            WHERE user_id = ?
        ''', (p_def[2], p_def[3], p_def[4], p_def[5], p_def[6], p_def[7], uid))
        cursor.execute("UPDATE players SET gold=0, coal=0, diamonds=0, wood=0, stone=0, iron=0 WHERE user_id = ?", (tid,))
        conn.commit()
        
        embed = discord.Embed(title="🔥 انتصار ساحق ومجيد! 🔥", color=discord.Color.gold())
        embed.description = f"اكتسحت قوات الحاكم {ctx.author.mention} حصون مملكة {target.mention} ونُهبت جميع ثرواتها ومواردها بالكامل وضُمت إلى خزائن النصر!"
        await ctx.send(embed=embed)
    else:
        cursor.execute("UPDATE players SET soldiers = 0 WHERE user_id = ?", (uid,))
        conn.commit()
        
        embed = discord.Embed(title="💀 هزيمة نكراء وانكسار للجيش 💀", color=discord.Color.red())
        embed.description = f"فشلت جحافل الحاكم {ctx.author.mention} في اختراق دفاعات الصمود لمملكة {target.mention}.. تم إبادة جيش المهاجم بالكامل وتشتيت شملهم!"
        await ctx.send(embed=embed)

@bot.command(name="بيع")
@is_game_channel()
async def sell_resources(ctx, resource_name: str, quantity: int = 1):
    uid = ctx.author.id
    res_map = {"فحم": "coal", "الماس": "diamonds", "خشب": "wood", "حجر": "stone", "حديد": "iron"}
    if resource_name not in res_map: return await ctx.send("❌ نوع المورد المكتوب للبيع غير صحيح. اختر من الموارد المتوفرة.")
    
    db_col = res_map[resource_name]
    cursor.execute(f"SELECT {db_col} FROM players WHERE user_id = ?", (uid,))
    p_res = cursor.fetchone()[0]
    if p_res < quantity: return await ctx.send(f"❌ أنت لا تمتلك هذه الكمية من الـ {resource_name} لبيعها.")
    
    gold_per_unit = random.randint(1, 10)
    total_gains = gold_per_unit * quantity
    
    cursor.execute(f"UPDATE players SET {db_col} = {db_col} - ?, gold = gold + ? WHERE user_id = ?", (quantity, total_gains, uid))
    conn.commit()
    await ctx.send(f"💰 **تم بيع الموارد الفائضة بنجاح! استبدلت `{quantity}` حبة من [{resource_name}] بـ `{total_gains}` عملة ذهبية عشوائية السعر.**")

@bot.command(name="خريطة")
@is_game_channel()
async def show_map(ctx):
    draw_kingdom_map()
    file = discord.File("map.png", filename="map.png")
    embed = discord.Embed(title="🗺️ الخريطة الإستراتيجية الكبرى للممالك", color=discord.Color.dark_green())
    embed.description = "توضح هذه اللوحة الرسمية مواقع الممالك والحدود الجغرافية المشيدة حالياً لملوك السيرفر:"
    embed.set_image(url="attachment://map.png")
    await ctx.send(file=file, embed=embed)

@bot.command(name="توب_الملوك")
@is_game_channel()
async def leaderboard(ctx):
    cursor.execute("SELECT kingdom_name, soldiers FROM players WHERE kingdom_name IS NOT NULL ORDER BY soldiers DESC LIMIT 10")
    top_players = cursor.fetchall()
    if not top_players: return await ctx.send("📊 لا توجد ممالك مسجلة في قائمة الصدارة حالياً.")
    
    embed = discord.Embed(title="👑 تصنيف توب الملوك - القوى العظمى في الحرب", color=discord.Color.gold())
    desc = ""
    for idx, player in enumerate(top_players, 1):
        crown = "👑 " if idx == 1 else "⚔️ "
        desc += f"{idx}. {crown}**{player[0]}** -- قوة الجيش: `{player[1]}` جندي\n"
    embed.description = desc
    await ctx.send(embed=embed)

# تشغيل خادم الويب للحفاظ على الاتصال حياً 
keep_alive()

# استدعاء التوكن بشكل آمن تماماً من الـ Environment Variables
bot.run(os.getenv('DISCORD_TOKEN'))
