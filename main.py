import discord
from discord.ext import commands, tasks
import sqlite3, requests, os, random, asyncio

# ===== CONFIG =====
CASINO_NAME = "7Flip"
EMBED_COLOR = 0x6A0DAD
LOG_CHANNEL_ID = 1524925387354669097

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
PUBLIC_ADDRESS = os.getenv("PUBLIC_ADDRESS")

MIN_DEPOSIT = 0.001

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# ===== DB =====
conn = sqlite3.connect("casino.db")
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    deposit_address TEXT
)""")

conn.commit()

# ===== BALANCE =====
def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def get_balance(user_id):
    user = get_user(user_id)
    return user[1] if user else 0

def update_balance(user_id, amt):
    if not get_user(user_id):
        c.execute("INSERT INTO users VALUES (?,?,?)",(user_id,0,None))
    bal = get_balance(user_id)
    c.execute("UPDATE users SET balance=? WHERE user_id=?",(bal+amt,user_id))
    conn.commit()

# ===== LOG =====
async def log(bot, text):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    await ch.send(text)

# ===== DEPOSIT =====
@bot.command()
async def deposit(ctx):
    user = get_user(ctx.author.id)

    if user and user[2]:
        return await ctx.send(f"Your deposit address:\n```{user[2]}```")

    r = requests.post(f"https://api.blockcypher.com/v1/ltc/main/addrs?token={BLOCKCYPHER_TOKEN}").json()
    addr = r["address"]

    c.execute("INSERT OR REPLACE INTO users VALUES (?,?,?)",(ctx.author.id,0,addr))
    conn.commit()

    await ctx.send(f"💰 Send LTC here:\n```{addr}```")

# ===== CHECK DEPOSITS =====
@tasks.loop(seconds=30)
async def check_deposits():
    c.execute("SELECT user_id, deposit_address FROM users")
    for uid, addr in c.fetchall():
        if not addr: continue

        data = requests.get(f"https://api.blockcypher.com/v1/ltc/main/addrs/{addr}").json()
        bal = data.get("final_balance",0)/1e8

        if bal >= MIN_DEPOSIT:
            update_balance(uid, bal)

# ===== WITHDRAW =====
@bot.command()
async def withdraw(ctx, address, amount: float):
    if get_balance(ctx.author.id) < amount:
        return await ctx.send("❌ Not enough balance")

    satoshi = int(amount * 1e8)

    tx = {
        "inputs":[{"addresses":[PUBLIC_ADDRESS]}],
        "outputs":[{"addresses":[address],"value":satoshi}]
    }

    r = requests.post(
        f"https://api.blockcypher.com/v1/ltc/main/txs/new?token={BLOCKCYPHER_TOKEN}",
        json=tx
    ).json()

    # ⚠️ SIMPLIFIED (real signing needed in production)

    update_balance(ctx.author.id, -amount)

    await ctx.send(f"💸 Sent {amount} LTC")

# ===== CHECK PLAY =====
def can_play(user_id):
    return get_balance(user_id) >= MIN_DEPOSIT

# ===== SLOTS =====
@bot.command()
async def slots(ctx, bet: float):
    if not can_play(ctx.author.id):
        return await ctx.send("❌ Deposit at least 0.001 LTC")

    if get_balance(ctx.author.id) < bet:
        return await ctx.send("❌ Not enough balance")

    emojis = ["🍒","🍋","💎","7️⃣"]
    msg = await ctx.send("🎰 Spinning...")

    for _ in range(3):
        spin = [random.choice(emojis) for _ in range(3)]
        await msg.edit(content=" | ".join(spin))
        await asyncio.sleep(0.6)

    if len(set(spin)) == 1:
        win = bet * 3
        update_balance(ctx.author.id, win)
        await log(bot, f"{ctx.author} WON {win} LTC")
    else:
        update_balance(ctx.author.id, -bet)
        await log(bot, f"{ctx.author} LOST {bet} LTC")

# ===== START =====
@bot.event
async def on_ready():
    print("7Flip ONLINE")
    check_deposits.start()

bot.run(DISCORD_TOKEN)
