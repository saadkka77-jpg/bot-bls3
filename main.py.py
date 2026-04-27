SAAD
ws0w
Online

This is the start of the #👑〢برمجة-بس private channel. 
𝐁𝐋 | 𝐒𝐀𝐀𝐃Role icon, 𝐎𝐖𝐍𝐄𝐑 ♚ — 4/25/2026 2:31 AM
رابط الموقع الرسمي لمنصة Render هو:

https://render.com/
Render
Render | The cloud for builders
Deploy and scale any app or agent from your first user to your billionth. Build faster on intuitive cloud infrastructure for the modern web.
Render | The cloud for builders
https://github.com/saadkka77-jpg/bls-bot/blob/main/bot.py
GitHub
bls-bot/bot.py at main · saadkka77-jpg/bls-bot
Contribute to saadkka77-jpg/bls-bot development by creating an account on GitHub.
bls-bot/bot.py at main · saadkka77-jpg/bls-bot
https://dashboard.uptimerobot.com/monitors
UptimeRobot
A place to manage all your important monitors. Get 50 monitors for FREE!
𝐁𝐋 | 𝐒𝐀𝐀𝐃Role icon, 𝐎𝐖𝐍𝐄𝐑 ♚ — 4/25/2026 3:23 AM
https://chatgpt.com/c/69ec06e1-ff84-83eb-9f34-b301952771aa
𝐁𝐋 | 𝐒𝐀𝐀𝐃Role icon, 𝐎𝐖𝐍𝐄𝐑 ♚ — Yesterday at 1:54 PM
import discord
from discord.ext import commands
import datetime
import json
import os

message.txt
8 KB
𝐁𝐋 | 𝐒𝐀𝐀𝐃Role icon, 𝐎𝐖𝐍𝐄𝐑 ♚ — Yesterday at 10:10 PM
require('dotenv').config();
const {
  Client, GatewayIntentBits, EmbedBuilder,
  ActionRowBuilder, ButtonBuilder, ButtonStyle
} = require('discord.js');
const db = require('quick.db');

message.txt
7 KB
https://chatgpt.com/?utm_source=google&utm_medium=paid_search&utm_campaign=GOOG_C_SEM_GBR_Core_CHT_BAU_ACQ_PER_MIX_ALL_EMEA_SA_AR_021425&c_id=22239765515&c_agid=176486813898&c_crid=783932789945&c_kwid=kwd-1928885899585&c_ims=&c_pms=9076780&c_nw=g&c_dvc=c&gad_source=1&gad_campaignid=22239765515&gbraid=0AAAAA-I0E5fLReC2kLjT57IfHX0HzcbLV&gclid=EAIaIQobChMIzarwnpiMlAMVman9BR2lFygzEAAYASAAEgJHR_D_BwE
﻿
require('dotenv').config();
const {
  Client, GatewayIntentBits, EmbedBuilder,
  ActionRowBuilder, ButtonBuilder, ButtonStyle
} = require('discord.js');
const db = require('quick.db');

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]
});

const TOKEN = process.env.TOKEN;

// 🎯 الرومات
const PROPERTY_ROOM = '1498037416672493829';
const ADMIN_ROOM = '1498037576538259556';

// 🧠 إنشاء مستخدم
function createUser(id) {
  if (!db.get(`user_${id}`)) {
    db.set(`user_${id}`, {
      money: 1000,
      stocks: 3,
      properties: [],
      firstWin: true,
      lastCommand: 0,
      banned: false
    });
  }
}

// ⏱️ كولداون
function cooldown(user) {
  let now = Date.now();
  if (now - user.lastCommand < 3000) return false;
  user.lastCommand = now;
  return true;
}

// 🚀 تشغيل
client.once('ready', () => {
  console.log(`✅ شغال: ${client.user.tag}`);
});

// 💬 أوامر
client.on('messageCreate', async (msg) => {
  if (msg.author.bot) return;

  createUser(msg.author.id);
  let user = db.get(`user_${msg.author.id}`);

  if (user.banned) return;

  if (!cooldown(user)) return;

  // 📊 رصيد
  if (msg.content === '/رصيدي') {
    return msg.reply(`💰 رصيدك: ${user.money}`);
  }

  // 📊 المحفظة
  if (msg.content === '/محفظتي') {
    const embed = new EmbedBuilder()
      .setTitle('📊 | حسابك')
      .addFields(
        { name: '💰 الرصيد', value: `${user.money}` },
        { name: '🏠 العقارات', value: `${user.properties.length}` }
      );
    return msg.reply({ embeds: [embed] });
  }

  // 🏠 شراء (فقط في روم العقار)
  if (msg.content === '/شراء') {
    if (msg.channel.id !== PROPERTY_ROOM)
      return msg.reply('❌ هذا الأمر فقط في روم العقارات');

    let price = Math.floor(Math.random() * 500) + 500;

    if (user.money < price)
      return msg.reply('❌ فلوسك ما تكفي');

    user.money -= price;

    user.properties.push({
      id: Date.now(),
      price: price
    });

    db.set(`user_${msg.author.id}`, user);

    msg.reply(`✅ اشتريت عقار بـ ${price}`);

    // نتيجة
    setTimeout(() => {
      let result;

      if (user.firstWin) {
        result = 'ربح';
        user.firstWin = false;
      } else {
        let r = Math.random();
        if (r < 0.4) result = 'ربح';
        else if (r < 0.8) result = 'خسارة';
        else result = 'ثبات';
      }

      if (result === 'ربح') {
        user.money += Math.floor(Math.random() * 300);
      }

      if (result === 'خسارة' && Math.random() < 0.3) {
        user.properties.pop();
      }

      db.set(`user_${msg.author.id}`, user);

      msg.author.send(`📩 نتيجة الاستثمار: ${result}`).catch(()=>{});
    }, 600000);
  }

  // 💸 بيع
  if (msg.content === '/بيع') {
    if (msg.channel.id !== PROPERTY_ROOM)
      return;

    if (user.properties.length < 100)
      return msg.reply('❌ تحتاج 100 عقار');

    let p = user.properties.pop();
    user.money += p.price;

    db.set(`user_${msg.author.id}`, user);

    msg.reply('✅ تم البيع');
  }

  // 🏎️ مزاد
  if (msg.content === '/مزاد') {

    let price = Math.floor(Math.random() * 2000) + 3000;

    let row = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('bid')
        .setLabel('مزايدة')
        .setStyle(ButtonStyle.Primary)
    );

    let embed = new EmbedBuilder()
      .setTitle('🏎️ مزاد')
      .setDescription(`السعر: ${price}`);

    let auction = await msg.reply({ embeds: [embed], components: [row] });

    let highest = price;
    let winner = null;
    let lastBidTime = Date.now();

    const collector = auction.createMessageComponentCollector({ time: 600000 });

    collector.on('collect', i => {
      createUser(i.user.id);
      let bidder = db.get(`user_${i.user.id}`);

      if (bidder.money < highest + 200)
        return i.reply({ content: '❌ فلوسك ما تكفي', ephemeral: true });

      highest += 200;
      winner = i.user;
      lastBidTime = Date.now();

      i.reply({ content: `🔥 السعر صار ${highest}`, ephemeral: true });
    });

    // ⛔ إلغاء إذا ما فيه تفاعل 10 دقائق
    let interval = setInterval(() => {
      if (Date.now() - lastBidTime > 600000) {
        collector.stop('no_bids');
      }
    }, 10000);

    collector.on('end', (collected, reason) => {
      clearInterval(interval);

      if (!winner) {
        return msg.channel.send('❌ تم إلغاء المزاد (ما فيه تفاعل)');
      }

      let winUser = db.get(`user_${winner.id}`);
      winUser.money -= highest;
      db.set(`user_${winner.id}`, winUser);

      msg.channel.send(`🏆 الفائز: <@${winner.id}> بسعر ${highest}`);
    });
  }

  // ================= ADMIN =================

  if (msg.channel.id === ADMIN_ROOM) {

    // 💰 إضافة فلوس
    if (msg.content.startsWith('/اضافة')) {
      let userId = msg.mentions.users.first()?.id;
      let amount = parseInt(msg.content.split(' ')[2]);

      if (!userId || !amount) return;

      createUser(userId);
      let u = db.get(`user_${userId}`);

      u.money += amount;
      db.set(`user_${userId}`, u);

      msg.reply('✅ تم الإضافة');
    }

    // ❌ خصم
    if (msg.content.startsWith('/خصم')) {
      let userId = msg.mentions.users.first()?.id;
      let amount = parseInt(msg.content.split(' ')[2]);

      if (!userId || !amount) return;

      let u = db.get(`user_${userId}`);
      u.money -= amount;

      db.set(`user_${userId}`, u);

      msg.reply('✅ تم الخصم');
    }

    // 🚫 حظر
    if (msg.content.startsWith('/حظر')) {
      let userId = msg.mentions.users.first()?.id;
      let u = db.get(`user_${userId}`);
      u.banned = true;
      db.set(`user_${userId}`, u);
      msg.reply('🚫 تم الحظر');
    }

    // 🔓 فك حظر
    if (msg.content.startsWith('/فك')) {
      let userId = msg.mentions.users.first()?.id;
      let u = db.get(`user_${userId}`);
      u.banned = false;
      db.set(`user_${userId}`, u);
      msg.reply('✅ تم فك الحظر');
    }

    // 🔄 تصفير
    if (msg.content === '/تصفير') {
      db.deleteAll();
      msg.reply('⚠️ تم تصفير الاقتصاد');
    }

  }

});

client.login(TOKEN);
