require("dotenv").config();
const { Client, GatewayIntentBits, EmbedBuilder } = require("discord.js");
const mongoose = require("mongoose");

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent],
});

// اتصال قاعدة البيانات
mongoose.connect(process.env.MONGO_URI).then(() => {
  console.log("✅ MongoDB Connected");
});

// سكيمة اللاعب
const userSchema = new mongoose.Schema({
  userId: String,
  money: { type: Number, default: 1000 },
  gold: { type: Number, default: 0 },
  diamonds: { type: Number, default: 0 },
  lands: { type: Number, default: 0 },
  lastInvest: { type: Number, default: 0 },
  lastTrade: { type: Number, default: 0 },
  lastSteal: { type: Number, default: 0 }
});

const User = mongoose.model("User", userSchema);

// جلب مستخدم
async function getUser(id) {
  let user = await User.findOne({ userId: id });
  if (!user) user = await User.create({ userId: id });
  return user;
}

// Embed جاهز
function embed(title, desc, color = "#2b2d31") {
  return new EmbedBuilder()
    .setTitle(title)
    .setDescription(desc)
    .setColor(color)
    .setFooter({ text: "نظام الاقتصاد" })
    .setTimestamp();
}

client.on("messageCreate", async (msg) => {
  if (msg.author.bot) return;

  const args = msg.content.split(" ");
  const cmd = args[0];

  const user = await getUser(msg.author.id);

  // 📊 ممتلكاتي
  if (cmd === "ممتلكاتي") {
    return msg.reply({
      embeds: [embed("📊 ممتلكاتك", `
💵 الفلوس: **${user.money}**
🥇 الذهب: **${user.gold}**
💎 الماس: **${user.diamonds}**
🏝️ الأراضي: **${user.lands}**
      `, "#00bcd4")]
    });
  }

  // 📈 استثمار
  if (cmd === "استثمار") {
    const now = Date.now();
    if (now - user.lastInvest < 180000)
      return msg.reply({ embeds: [embed("⏳", "انتظر 3 دقايق")] });

    let amount = args[1] === "كل" ? user.money : parseInt(args[1]);
    if (!amount || amount <= 0)
      return msg.reply({ embeds: [embed("❌", "اكتب مبلغ صحيح")] });

    if (user.money < amount)
      return msg.reply({ embeds: [embed("❌", "ما عندك المبلغ")] });

    user.money -= amount;
    user.lastInvest = now;

    let win = Math.random() < 0.5;
    let change = Math.floor(amount * (Math.random() * 0.5));

    if (win) {
      user.money += amount + change;
      msg.reply({ embeds: [embed("📈 استثمار ناجح", `ربحت **${change}** 💰`, "#4caf50")] });
    } else {
      msg.reply({ embeds: [embed("📉 استثمار فاشل", `خسرت **${change}**`, "#f44336")] });
    }

    await user.save();
  }

  // 📊 تداول
  if (cmd === "تداول") {
    const now = Date.now();
    if (now - user.lastTrade < 180000)
      return msg.reply({ embeds: [embed("⏳", "انتظر 3 دقايق")] });

    let amount = args[1] === "كل" ? user.money : parseInt(args[1]);

    if (!amount || amount <= 0)
      return msg.reply({ embeds: [embed("❌", "اكتب مبلغ صحيح")] });

    if (user.money < amount)
      return msg.reply({ embeds: [embed("❌", "ما عندك")] });

    user.money -= amount;
    user.lastTrade = now;

    let win = Math.random() < 0.5;
    let change = Math.floor(amount * (Math.random() * 0.7));

    if (win) {
      user.money += amount + change;
      msg.reply({ embeds: [embed("💹 تداول ناجح", `كسبت **${change}**`, "#4caf50")] });
    } else {
      msg.reply({ embeds: [embed("📉 تداول خاسر", `خسرت **${change}**`, "#f44336")] });
    }

    await user.save();
  }

  // 🎰 روليت
  if (cmd === "روليت") {
    let rand = Math.floor(Math.random() * 4);

    if (rand === 0) {
      let x = Math.floor(Math.random() * 500);
      user.gold += x;
      msg.reply({ embeds: [embed("🎰 روليت", `🥇 حصلت **${x} ذهب**`, "#ffd700")] });
    }

    if (rand === 1) {
      let x = Math.floor(Math.random() * 300);
      user.diamonds += x;
      msg.reply({ embeds: [embed("🎰 روليت", `💎 حصلت **${x} ماس**`, "#00e5ff")] });
    }

    if (rand === 2) {
      let x = Math.floor(Math.random() * 3);
      user.lands += x;
      msg.reply({ embeds: [embed("🎰 روليت", `🏝️ حصلت **${x} أرض**`, "#8bc34a")] });
    }

    if (rand === 3) {
      let x = Math.floor(Math.random() * 1000);
      user.money += x;
      msg.reply({ embeds: [embed("🎰 روليت", `💵 حصلت **${x} فلوس**`, "#4caf50")] });
    }

    await user.save();
  }

  // 🕵️ سرقة (نهب + منشن)
  if (cmd === "سرقة") {
    const target = msg.mentions.users.first();
    if (!target) return msg.reply("من تبي تنهب؟");

    const now = Date.now();
    if (now - user.lastSteal < 300000)
      return msg.reply({ embeds: [embed("⏳", "انتظر 5 دقايق")] });

    const victim = await getUser(target.id);

    if (victim.money <= 0)
      return msg.reply({ embeds: [embed("❌", "الشخص لا يملك مال")] });

    let stolen = Math.floor(Math.random() * victim.money);

    victim.money -= stolen;
    user.money += stolen;
    user.lastSteal = now;

    await victim.save();
    await user.save();

    msg.reply({
      content: `🚨 ${target}`,
      embeds: [embed("🕵️ نهب!", `تم نهب **${stolen}** 💰 من ${target}\nيا حرامي وش اليد الخفيفة هذي 😈`, "#ff9800")]
    });
  }

  // 💰 بيع
  if (cmd === "بيع") {
    let type = args[2];
    if (!["gold", "diamonds", "lands"].includes(type))
      return msg.reply("اكتب: gold / diamonds / lands");

    let amount;
    if (args[1] === "كل") amount = user[type];
    else if (args[1] === "نص") amount = Math.floor(user[type] / 2);
    else amount = parseInt(args[1]);

    if (!amount || user[type] < amount)
      return msg.reply({ embeds: [embed("❌", "ما عندك الكمية")] });

    let price = Math.floor(Math.random() * 100);

    user[type] -= amount;
    user.money += amount * price;

    await user.save();

    msg.reply({
      embeds: [embed("💰 بيع ناجح", `بعت **${amount} ${type}** بسعر **${price}**`, "#4caf50")]
    });
  }
});

// تشغيل
client.login(process.env.DISCORD_TOKEN);
