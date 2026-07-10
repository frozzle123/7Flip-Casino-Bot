import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import random, asyncio, sqlite3, requests, os

# ===== CONFIG =====
CASINO_NAME = "7Flip"
EMBED_COLOR = 0x6A0DAD
LOGO_URL = "https://cdn.discordapp.com/attachments/1416711940025090082/1524925387354669097/1000035905.png"
LOG_CHANNEL_ID = 1524925387354669097

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# ===== DATABASE =====
conn = sqlite3.connect("casino.db")
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)""")

c.execute("""CREATE TABLE IF NOT EXISTS deposits (
    address TEXT,
    user_id INTEGER,
    credited INTEGER DEFAULT 0
)""")

c.execute("""CREATE TABLE IF NOT EXISTS withdraws (
    user_id INTEGER,
    address TEXT,
    amount REAL,
    status TEXT
)""")

conn.commit()

# ===== BALANCE =====
def get_balance(uid):
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users VALUES (?,0)", (uid,))
        conn.commit()
        return 0
    return row[0]

def update_balance(uid, amt):
    bal = get_balance(uid)
    c.execute("UPDATE users SET balance=? WHERE user_id=?", (bal+amt, uid))
    conn.commit()

# ===== LOG =====
async def log(title, desc):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    embed = discord.Embed(title=title, description=desc, color=EMBED_COLOR)
    embed.set_thumbnail(url=LOGO_URL)
    await ch.send(embed=embed)

# ===== DEPOSIT =====
@bot.command()
async def deposit(ctx):
    r = requests.post(f"https://api.blockcypher.com/v1/ltc/main/addrs?token={BLOCKCYPHER_TOKEN}").json()
    addr = r["address"]

    c.execute("INSERT INTO deposits (address,user_id) VALUES (?,?)",(addr,ctx.author.id))
    conn.commit()

    await ctx.send(f"Send LTC to:\n```{addr}```")

# ===== CHECK DEPOSITS =====
@tasks.loop(seconds=30)
async def check_deposits():
    c.execute("SELECT address,user_id FROM deposits WHERE credited=0")
    for addr,uid in c.fetchall():
        data = requests.get(f"https://api.blockcypher.com/v1/ltc/main/addrs/{addr}").json()
        if data.get("final_balance",0)>0:
            amt = data["final_balance"]/1e8
            update_balance(uid, amt)
            c.execute("UPDATE deposits SET credited=1 WHERE address=?",(addr,))
            conn.commit()

# ===== WITHDRAW REQUEST =====
@bot.command()
async def withdraw(ctx, address, amount:float):
    if get_balance(ctx.author.id) < amount:
        return await ctx.send("Not enough balance")

    update_balance(ctx.author.id, -amount)

    c.execute("INSERT INTO withdraws VALUES (?,?,?,?)",(ctx.author.id,address,amount,"PENDING"))
    conn.commit()

    await ctx.send("✅ Withdraw request sent")

    await log("💸 Withdraw Request",
              f"{ctx.author.mention}\nAmount: {amount} LTC\nAddress: {address}")

# ===== SLOTS =====
@bot.command()
async def slots(ctx, bet:float):
    if get_balance(ctx.author.id)<bet:
        return await ctx.send("No balance")

    emojis=["🍒","🍋","💎","7️⃣"]
    msg=await ctx.send("🎰 Spinning...")

    for _ in range(3):
        spin=[random.choice(emojis) for _ in range(3)]
        await msg.edit(content=" | ".join(spin))
        await asyncio.sleep(0.6)

    if len(set(spin))==1:
        win=bet*3
        update_balance(ctx.author.id,win)
        await log("🎰 WIN",f"{ctx.author.mention} won {win} LTC")
    else:
        update_balance(ctx.author.id,-bet)
        await log("🎰 LOSS",f"{ctx.author.mention} lost {bet} LTC")

# ===== CRASH =====
@bot.command()
async def crash(ctx, bet:float):
    if get_balance(ctx.author.id)<bet:
        return await ctx.send("No balance")

    multi=1.0
    msg=await ctx.send("🚀 1.0x")

    while True:
        multi+=0.2
        await msg.edit(content=f"🚀 {round(multi,2)}x")
        if random.random()<0.1:
            update_balance(ctx.author.id,-bet)
            await log("💥 Crash",f"{ctx.author.mention} lost {bet} LTC")
            break
        await asyncio.sleep(0.5)

# ===== START =====
@bot.event
async def on_ready():
    print("7Flip running")
    check_deposits.start()

bot.run(DISCORD_TOKEN)
