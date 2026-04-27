import discord
from discord.ext import commands
import os

# إعداد الصلاحيات (Intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# إعداد البوت
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is now online!')

@bot.command()
async def ping(ctx):
    await ctx.send('🏓 Pong!')

# هنا ينادي التوكن اللي أنت حطيته في Render باسم DISCORD_TOKEN
token = os.getenv('DISCORD_TOKEN')

if token:
    bot.run(token)
else:
    print("❌ Error: DISCORD_TOKEN not found in Environment Variables!")
