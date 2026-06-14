import discord
from discord.ext import commands, tasks
import sqlite3
import random
import asyncio
import os
import time
from threading import Thread
from flask import Flask

# ----------------- إعدادات سيرفر الويب للـ UptimeRobot -----------------
app = Flask('')

@app.route('/')
def home():
    return "BLS Kingdom War Bot is Fully Operational!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ----------------- إعدادات البوت والـ Intents -----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# دعم البريفكس المباشر والمساحة لمنع أي تعليق
bot = commands.Bot(command_prefix=["", " "], intents=intents, help_command=None)

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
    miners INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS alliances (
    leader_id INTEGER PRIMARY KEY,
    member_id INTEGER
)
''')
conn.commit()

current_market_items = {}
last_market_update = 0

def generate_market_items():
    global current_market_items, last_market_update
    items = {
        "فحم": {"price": random.randint(15, 30), "stock": random.randint(5, 15)},
        "الماس": {"price": random.randint(100, 200), "stock": random.randint(1, 3)},
        "خشب": {"price": random.randint(10, 20), "stock": random.randint(10, 30)},
        "حجر": {"price": random.randint(12, 25), "stock": random.randint(10, 25)},
        "حديد": {"price": random.randint(25, 50), "stock": random.randint(5, 15)},
        "بناء": {"price": 1500, "stock": 1}
    }
    selected_keys = random.sample(list(items.keys()), 2)
    current_market_items = {k: items[k] for k in selected_keys}
    last_market_update = time.time()

# ----------------- فلاتر التحقق والتحكم -----------------
async def is_game_channel_check(ctx):
    if ctx.channel.id != GAME_CHANNEL_ID:
        embed = discord.Embed(
            description=f"⚠️ **عذراً أيها الحاكم، الأوامر الإستراتيجية تُنفذ فقط في ساحة المعركة: <#{GAME_CHANNEL_ID}>**",
            color=0x2b2d31
        )
        await ctx.send(embed=embed)
        return False
    return True

# ----------------- أحداث البوت -----------------
@bot.event
async def on_ready():
    print(f"👑 تم تشغيل النظام الملكي لـ BLS بنجاح: {bot.user}")
    generate_market_items()
    if not miners_production_loop.is_running(): miners_production_loop.start()
    if not half_hour_tax_loop.is_running(): half_hour_tax_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message)

# ----------------- الأوامر الإستراتيجية المختصرة والفخمة -----------------

@bot.command(name="انشاء")
async def create_land(ctx, *, name: str = None):
    if not await is_game_channel_check(ctx): return
    if not name: return await ctx.send("❌ **يرجى تحديد اسم لمملكتك! مثال: `انشاء العظمى`**")
    
    uid = ctx.author.id
    cursor.execute("SELECT kingdom_name FROM players WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    if row and row[0] is not None: return await ctx.send("❌ **أنت تمتلك مملكة مسجلة بالفعل!**")
        
    if row:
        cursor.execute("UPDATE players SET kingdom_name = ? WHERE user_id = ?", (name, uid))
    else:
        cursor.execute('''
            INSERT INTO players (user_id, kingdom_name, gold, coal, diamonds, wood, stone, iron, soldiers, citizens, builders)
            VALUES (?, ?, 1000, 10, 2, 200, 200, 100, 6, 10, 1)
        ''', (uid, name))
    conn.commit()
    
    embed = discord.Embed(title="🏰 لوحة التأسيس الملكية", color=0x2b2d31)
    embed.description = f"تم تسجيل ممتلكاتك باسم **【 {name} 】** بنجاح!\n\n**🎁 هدايا الدعم العسكري الأولية:**\n🪙 الذهب: `1000` | ⚔️ الجنود: `6` | 👥 السكان: `10` | 👷 بناؤون: `1`"
    embed.set_footer(text="BLS Economy")
    await ctx.send(embed=embed)

@bot.command(name="مملكتي")
async def info_kingdom(ctx):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if not p or p[1] is None: return await ctx.send("❌ **لا تملك أرضاً بعد! اكتب: `انشاء [الاسم]` لبدء مسيرتك.**")
        
    embed = discord.Embed(title="📋 لوحة ممتلكاتك الإستراتيجية", color=0x2b2d31)
    embed.description = f"🏰 اسم الأرض: **{p[1]}**"
    embed.add_field(name="🪙 الخزينة والعملات", value=f"🪙 الذهب: `{p[2]}`\n💎 الألماس: `{p[4]}`\n🔥 الفحم: `{p[3]}`", inline=True)
    embed.add_field(name="🪵 الموارد الخام", value=f"🪵 الخشب: `{p[5]}`\n🪨 الحجر: `{p[6]}`\n⛓️ الحديد: `{p[7]}`", inline=True)
    embed.add_field(name="👥 القوة البشرية", value=f"⚔️ الجنود: `{p[8]}`\n👥 السكان: `{p[9]}`\n👷 البناؤون: `{p[10]}`", inline=False)
    embed.add_field(name="🏘️ العقارات والحصون", value=f"🪵 بيوت خشب: `{p[11]}`\n🪨 بيوت حجر: `{p[12]}`\n⛓️ بيوت حديد: `{p[13]}`\n🛡️ السور: `[{p[14]}]`", inline=True)
    embed.add_field(name="🕵️ الأجهزة السرية", value=f"🕵️ الجواسيس: `{p[15]}`\n⛏️ المنقّبين: `{p[16]}/10`", inline=True)
    embed.set_footer(text="BLS Economy")
    await ctx.send(embed=embed)

@bot.command(name="سوق")
async def show_market(ctx):
    if not await is_game_channel_check(ctx): return
    global current_market_items, last_market_update
    if time.time() - last_market_update > 900: generate_market_items()

    embed = discord.Embed(title="🏪 متجر الممالك المتنقل", color=0x2b2d31)
    for item, info in current_market_items.items():
        embed.add_field(name=f"📦 {item}", value=f"السعر: `{info['price']}` ذهبة | المتاح: `{info['stock']}`", inline=True)
    embed.set_footer(text="للشراء اكتب: شراء [اسم_الغرض] [الكمية]")
    await ctx.send(embed=embed)

@bot.command(name="شراء")
async def buy_market(ctx, item_name: str, quantity: int = 1):
    if not await is_game_channel_check(ctx): return
    global current_market_items
    if item_name not in current_market_items: return await ctx.send("❌ **هذا الغرض غير متوفر في السوق حالياً.**")
        
    uid = ctx.author.id
    info = current_market_items[item_name]
    if info['stock'] < quantity: return await ctx.send(f"❌ **الكمية المتاحة: `{info['stock']}` فقط.**")
        
    total_cost = info['price'] * quantity
    cursor.execute("SELECT gold, builders FROM players WHERE user_id = ?", (uid,))
    p_data = cursor.fetchone()
    
    if p_data[0] < total_cost: return await ctx.send(f"❌ **ذهبك غير كافٍ! تحتاج `{total_cost}` ذهبة.**")
        
    current_market_items[item_name]['stock'] -= quantity
    if item_name == "بناء":
        cursor.execute("UPDATE players SET gold = gold - ?, builders = builders + ? WHERE user_id = ?", (total_cost, quantity, uid))
    else:
        res_map = {"فحم": "coal", "الماس": "diamonds", "خشب": "wood", "حجر": "stone", "حديد": "iron"}
        db_col = res_map[item_name]
        cursor.execute(f"UPDATE players SET gold = gold - ?, {db_col} = {db_col} + ? WHERE user_id = ?", (total_cost, quantity, uid))
    
    conn.commit()
    await ctx.send(f"🛍️ **تمت العملية! اشتريت `{quantity}` من [{item_name}] بسعر `{total_cost}` ذهبة.**")

@bot.command(name="بيع")
async def sell_resources(ctx, resource_name: str, quantity: int = 1):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    res_map = {"فحم": "coal", "الماس": "diamonds", "خشب": "wood", "حجر": "stone", "حديد": "iron"}
    if resource_name not in res_map: return await ctx.send("❌ **المورد غير صحيح! اختر: (فحم، الماس، خشب، حجر، حديد)**")
    
    db_col = res_map[resource_name]
    cursor.execute(f"SELECT {db_col} FROM players WHERE user_id = ?", (uid,))
    p_res = cursor.fetchone()[0]
    if p_res < quantity: return await ctx.send(f"❌ **لا تمتلك هذه الكمية من الـ {resource_name} لبيعها.**")
    
    gold_per_unit = random.randint(5, 15)
    total_gains = gold_per_unit * quantity
    
    cursor.execute(f"UPDATE players SET {db_col} = {db_col} - ?, gold = gold + ? WHERE user_id = ?", (quantity, total_gains, uid))
    conn.commit()
    await ctx.send(f"💰 **تم بيع الموارد! استبدلت `{quantity}` [{resource_name}] بـ `{total_gains}` عملة ذهبية.**")

@bot.command(name="بيت")
async def upgrade_house(ctx, type_house: str, quantity: int = 1):
    if not await is_game_channel_check(ctx): return
    if quantity <= 0: return
    uid = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if not p or p[1] is None: return await ctx.send("❌ لا تملك مملكة.")
    if p[10] < quantity: return await ctx.send(f"❌ **البناؤون مشغولون! تحتاج إلى `{quantity}` بناؤون أحرار لتنفيذ العملية.**")
    
    if type_house == "خشب":
        cost = 100 * quantity
        if p[2] < cost: return await ctx.send(f"❌ تحتاج `{cost}` ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - ?, wooden_houses = wooden_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity*10, uid))
    elif type_house == "حجر":
        if p[11] < quantity: return await ctx.send("❌ يجب أن تمتلك بيوت خشب كافية أولاً لتطويرها!")
        cost = 200 * quantity
        if p[2] < cost: return await ctx.send(f"❌ تحتاج `{cost}` ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - ?, wooden_houses = wooden_houses - ?, stone_houses = stone_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity, quantity*20, uid))
    elif type_house == "حديد":
        if p[12] < quantity: return await ctx.send("❌ يجب أن تمتلك بيوت حجر كافية أولاً لتطويرها!")
        cost = 350 * quantity
        if p[2] < cost: return await ctx.send(f"❌ تحتاج `{cost}` ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - ?, stone_houses = stone_houses - ?, iron_houses = iron_houses + ?, citizens = citizens + ? WHERE user_id = ?", (cost, quantity, quantity, quantity*70, uid))
    else:
        return await ctx.send("❓ **الأنواع المتاحة: (خشب، حجر، حديد)**")

    conn.commit()
    await ctx.send(f"👷 **بناء وتطوير العقارات جارٍ الآن بقوة عمالك... انتظر 10 ثوانٍ.**")
    await asyncio.sleep(10)
    await ctx.send(f"🎉 **{ctx.author.mention} تم الانتهاء من ترقية البيوت إلى لفل [{type_house}] بنجاح!**")

@bot.command(name="سور")
async def upgrade_wall(ctx, type_wall: str):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    cursor.execute("SELECT gold, wall_level FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    current_wall = p[1]
    
    if type_wall == "خشب":
        if current_wall != "لا يوجد": return await ctx.send("❌ سورك الحالي مكافئ أو أقوى!")
        if p[0] < 500: return await ctx.send("❌ ترقيتك تتطلب 500 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 500, wall_level = 'خشب' WHERE user_id = ?", (uid,))
    elif type_wall == "حجر":
        if current_wall != "خشب": return await ctx.send("❌ يجب بناء سور خشب أولاً!")
        if p[0] < 1000: return await ctx.send("❌ ترقيتك تتطلب 1000 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 1000, wall_level = 'حجر' WHERE user_id = ?", (uid,))
    elif type_wall == "حديد":
        if current_wall != "حجر": return await ctx.send("❌ يجب ترقية السور لحجر أولاً!")
        if p[0] < 3000: return await ctx.send("❌ ترقيتك تتطلب 3000 ذهبة.")
        cursor.execute("UPDATE players SET gold = gold - 3000, wall_level = 'حديد' WHERE user_id = ?", (uid,))
    else:
        return await ctx.send("❓ **الخيارات المتاحة بالترتيب: (خشب، حجر، حديد)**")
        
    conn.commit()
    await ctx.send(f"🛡️ **تم تعزيز خطوط الدفاع وسور المملكة بنجاح لـ [{type_wall}]!**")

@bot.command(name="جنود")
async def train_soldiers(ctx, quantity_groups: int = 1):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    cursor.execute("SELECT gold, citizens FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    
    needed_gold = quantity_groups * 10
    needed_citizens = quantity_groups * 5
    if p[0] < needed_gold: return await ctx.send(f"❌ الذهب غير كافٍ. تحتاج `{needed_gold}` ذهبة.")
    if p[1] < needed_citizens: return await ctx.send(f"❌ السكان غير كافيين. تحتاج `{needed_citizens}` مواطنين.")
    
    cursor.execute('''
        UPDATE players SET gold = gold - ?, citizens = citizens - ?, soldiers = soldiers + ?
        WHERE user_id = ?
    ''', (needed_gold, needed_citizens, quantity_groups * 5, uid))
    conn.commit()
    await ctx.send(f"⚔️ **تم تدريب المواطنين بنجاح، وحصلت على `{quantity_groups * 5}` جنود حاميين للعرش.**")

@bot.command(name="جاسوس")
async def hire_spy(ctx):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    cursor.execute("SELECT citizens, soldiers FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if p[0] < 10 or p[1] < 3: return await ctx.send("❌ **المتطلبات ناقصة! تحتاج إلى (10 سكان و 3 جنود) لتجنيد جاسوس.**")
    cursor.execute("UPDATE players SET citizens = citizens - 10, soldiers = soldiers - 3, spies = spies + 1 WHERE user_id = ?", (uid,))
    conn.commit()
    await ctx.send("🕵️ **تم تدريب وتوظيف جاسوس محترف في جهازك السري للسرقة والاستطلاع العسكري بنجاح!**")

@bot.command(name="منقب")
async def hire_miner(ctx):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    cursor.execute("SELECT citizens, soldiers, miners FROM players WHERE user_id = ?", (uid,))
    p = cursor.fetchone()
    if p[2] >= 10: return await ctx.send("❌ **وصلت للحد الأقصى لعدد المنقبين في مملكتك (10 منقبين - لفل ماكس)!**")
    if p[0] < 3 or p[1] < 1: return await ctx.send("❌ **المتطلبات ناقصة! تحتاج إلى (3 سكان و 1 جندي) لتوظيف منقب.**")
    cursor.execute("UPDATE players SET citizens = citizens - 3, soldiers = soldiers - 1, miners = miners + 1 WHERE user_id = ?", (uid,))
    conn.commit()
    await ctx.send(f"⛏️ **تم توظيف منقب جديد! المنقبين الحاليين بمملكتك: `{p[2] + 1}/10`.**")

@bot.command(name="سرقة")
async def steal_gold(ctx, target: discord.Member):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكنك سرقة نفسك!")
    
    cursor.execute("SELECT spies, gold FROM players WHERE user_id = ?", (uid,))
    p_thief = cursor.fetchone()
    cursor.execute("SELECT spies, gold FROM players WHERE user_id = ?", (tid,))
    p_target = cursor.fetchone()
    
    if not p_thief or p_thief[0] < 1: return await ctx.send("❌ **لا تمتلك جواسيس أحرار! وظف جاسوساً أولاً عبر أمر: `جاسوس`.**")
    if not p_target or p_target[1] <= 0: return await ctx.send("❌ **خزينة هذا الحاكم خالية من الذهب تماماً حالياً.**")
    
    await ctx.send(f"🕵️‍♂️ **يتسلل جاسوسك متوجهاً لخزائن {target.mention}... ترقب النتيجة.**")
    await asyncio.sleep(4)
    
    if p_target[0] > 0 and random.random() < 0.25:
        cursor.execute("UPDATE players SET spies = spies - 1 WHERE user_id = ?", (uid,))
        conn.commit()
        return await ctx.send(f"💀 **كارثة! الدفاعات السرية للخصم كشفت جاسوسك وتم إعدامه فوراً!**")
        
    stolen_gold = random.randint(5, min(30, p_target[1]))
    cursor.execute("UPDATE players SET gold = gold - ? WHERE user_id = ?", (stolen_gold, tid))
    cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (stolen_gold, uid))
    conn.commit()
    await ctx.send(f"💰 **نجحت العملية السرية! عاد الجاسوس محملاً بـ `{stolen_gold}` عملة ذهبية من خزائن الخصم.**")

@bot.command(name="تحالف")
async def ally(ctx, target: discord.Member):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكنك التحالف مع نفسك!")
    
    cursor.execute("SELECT * FROM alliances WHERE leader_id = ? OR member_id = ? OR leader_id = ? OR member_id = ?", (uid, uid, tid, tid))
    if cursor.fetchone(): return await ctx.send("❌ **أحد الممالك منضمة بالفعل في تحالف قائم!**")
    
    await ctx.send(f"🤝 **يا {target.mention}، يعرض عليك الملك {ctx.author.mention} معاهدة تحالف استراتيجي! اكتب (موافق/ارفض)**")
    
    def check(m): return m.author == target and m.channel == ctx.channel and m.content in ['موافق', 'ارفض']
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content == 'موافق':
            cursor.execute("INSERT INTO alliances (leader_id, member_id) VALUES (?, ?)", (uid, tid))
            conn.commit()
            await ctx.send(f"🎉 **تم توقيع معاهدة السلام العظمى! أصبحت الممالك حليفة رسمياً من الآن فصاعداً!**")
        else:
            await ctx.send(f"❌ **تم رفض طلب التحالف الملكي.**")
    except asyncio.TimeoutError:
        await ctx.send("⏳ **انتهى وقت الاستجابة للمعاهدة الملكية.**")

@bot.command(name="فسخ")
async def break_ally(ctx, target: discord.Member):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    tid = target.id
    cursor.execute("DELETE FROM alliances WHERE (leader_id = ? AND member_id = ?) OR (leader_id = ? AND member_id = ?)", (uid, tid, tid, uid))
    conn.commit()
    await ctx.send(f"💔 **تم فسخ المعاهدة وإعلان إنهاء التحالف رسمياً مع مملكة {target.mention}.**")

class ChallengeView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ **هذا التحدي مخصص لحاكم آخر! اكتب `تحدي` الخاص بك.**", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ غارة الغابة", style=discord.ButtonStyle.danger)
    async def c1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_challenge(interaction, "غارة الغابة", random.randint(10, 40))

    @discord.ui.button(label="📦 حماية القافلة", style=discord.ButtonStyle.success)
    async def c2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_challenge(interaction, "حماية قافلة الذهب", random.randint(20, 60))

    async def process_challenge(self, interaction, name, gold_reward):
        uid = interaction.user.id
        cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (gold_reward, uid))
        conn.commit()
        await interaction.response.send_message(f"🏆 **نجحت في تحدي [{name}] وعُدت بغنائم تقدر بـ `{gold_reward}` عملة ذهبية!**")
        self.stop()

@bot.command(name="تحدي")
async def challenge(ctx):
    if not await is_game_channel_check(ctx): return
    view = ChallengeView(ctx.author)
    embed = discord.Embed(title="⚔️ قائمة التحديات والغزوات الإستراتيجية", description="اختر أحد التحديات المتاحة لقيادة قواتك وجمع الغنائم الملكية والذهب:", color=0x2b2d31)
    await ctx.send(embed=embed, view=view)

@bot.command(name="هجوم")
async def attack(ctx, target: discord.Member):
    if not await is_game_channel_check(ctx): return
    uid = ctx.author.id
    tid = target.id
    if uid == tid: return await ctx.send("❌ لا يمكن مهاجمة نفسك!")
    
    cursor.execute("SELECT kingdom_name, soldiers, gold, coal, diamonds, wood, stone, iron FROM players WHERE user_id = ?", (uid,))
    p_att = cursor.fetchone()
    cursor.execute("SELECT kingdom_name, soldiers, gold, coal, diamonds, wood, stone, iron FROM players WHERE user_id = ?", (tid,))
    p_def = cursor.fetchone()
    
    if not p_att or p_att[0] is None: return await ctx.send("❌ لا تملك مملكة لتهجم بها.")
    if not p_def or p_def[0] is None: return await ctx.send("❌ الخصم لا يمتلك مملكة مسجلة.")
    if p_att[1] == 0: return await ctx.send("❌ جيشك خالٍ تماماً من الجنود!")
    
    await ctx.send("⚔️ **[ زحف عسكري حاشد... ترقبوا صدور تقرير المعركة بعد 10 ثوانٍ! ]**")
    await asyncio.sleep(10)
    
    win = random.randint(0, p_att[1] + p_def[1]) < p_att[1]
            
    if win:
        cursor.execute('''
            UPDATE players SET 
            gold = gold + ?, coal = coal + ?, diamonds = diamonds + ?, wood = wood + ?, stone = stone + ?, iron = iron + ?
            WHERE user_id = ?
        ''', (p_def[2], p_def[3], p_def[4], p_def[5], p_def[6], p_def[7], uid))
        cursor.execute("UPDATE players SET gold=0, coal=0, diamonds=0, wood=0, stone=0, iron=0 WHERE user_id = ?", (tid,))
        conn.commit()
        
        embed = discord.Embed(title="🔥 انتصار ملكي ساحق! 🔥", color=0x2b2d31)
        embed.description = f"اكتسحت قوات الحاكم {ctx.author.mention} حصون {target.mention} ونُهبت ثرواته بالكامل وضُمت لبلادنا!"
        await ctx.send(embed=embed)
    else:
        cursor.execute("UPDATE players SET soldiers = 0 WHERE user_id = ?", (uid,))
        conn.commit()
        
        embed = discord.Embed(title="💀 انكسار جيش الممالك 💀", color=0x2b2d31)
        embed.description = f"فشلت جحافل الحاكم {ctx.author.mention} في اختراق دفاعات الصمود لـ {target.mention}.. وتمت إبادة القوة المهاجمة بالكامل!"
        await ctx.send(embed=embed)

@bot.command(name="توب")
async def leaderboard(ctx):
    if not await is_game_channel_check(ctx): return
    cursor.execute("SELECT kingdom_name, soldiers FROM players WHERE kingdom_name IS NOT NULL ORDER BY soldiers DESC LIMIT 10")
    top_players = cursor.fetchall()
    if not top_players: return await ctx.send("📊 لا توجد ممالك مسجلة حالياً.")
    
    embed = discord.Embed(title="👑 تصنيف قوى الملوك العظمى في السيرفر", color=0x2b2d31)
    desc = ""
    for idx, player in enumerate(top_players, 1):
        crown = "👑 " if idx == 1 else "⚔️ "
        desc += f"{idx}. {crown}**{player[0]}** -- الجيش: `{player[1]}` جندي\n"
    embed.description = desc
    embed.set_footer(text="BLS Economy")
    await ctx.send(embed=embed)

# ----------------- Loops الإنتاج والضرائب التلقائية -----------------
@tasks.loop(minutes=20)
async def miners_production_loop():
    await bot.wait_until_ready()
    cursor.execute("SELECT user_id, miners FROM players WHERE miners > 0")
    players = cursor.fetchall()
    for player in players:
        uid, m_count = player[0], player[1]
        cursor.execute("UPDATE players SET wood = wood + ?, stone = stone + ? WHERE user_id = ?", (m_count * 4, m_count * 2, uid))
    conn.commit()

@tasks.loop(minutes=30)
async def half_hour_tax_loop():
    await bot.wait_until_ready()
    cursor.execute("SELECT user_id, citizens FROM players WHERE kingdom_name IS NOT NULL")
    players = cursor.fetchall()
    for player in players:
        uid, citizens = player[0], player[1]
        earnings = max(5, int((citizens / 10)))
        cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (earnings, uid))
    conn.commit()

# تشغيل الـ Keep Alive والـ Bot Token
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
