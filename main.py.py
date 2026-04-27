import discord
from discord.ext import commands
import os

# إعداد الصلاحيات
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

# هنا نستخدم os.getenv عشان الاستضافة تسحب التوكن بأمان
token = os.getenv('DISCORD_TOKEN')
bot.run(token)