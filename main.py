#!/usr/bin/env python3

import discord
from discord.ext import commands
import os
import json
from dotenv import load_dotenv
import re
import asyncio
import base64

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

database_file = "database.json"

owner = int(os.getenv("OWNER"))
whitelist = set()

@commands.check
def owner_check(ctx):
    return ctx.author.id == owner

@commands.check
def is_whitelisted(ctx):
    return ctx.author.id in whitelist

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command()
@commands.check(owner_check)
async def whitelist(ctx, user: discord.User):
    if user.id in whitelist:
        await ctx.send(f"{user.name} is already whitelisted.")
    else:
        whitelist.add(user.id)
        await ctx.send(f"{user.name} has been whitelisted.")

@bot.command()
@commands.check(owner_check)
async def blacklist(ctx, user: discord.User):
    if user.id not in whitelist:
        await ctx.send(f"{user.name} is already blacklisted.")
    else:
        whitelist.discard(user.id)
        await ctx.send(f"{user.name} has been blacklisted.")

def entry_exists(json_entry):
    if not os.path.isfile(database_file):
        return False

    with open(database_file, "r") as database:
        for line in database:
            try:
                entry = json.loads(line.strip())
                if entry == json_entry:
                    return True
            except json.JSONDecodeError:
                continue
    return False

async def send_file_content_as_messages(ctx, file_path, guild, category):
    with open(file_path, 'rb') as file:
        content = base64.b64encode(file.read()).decode('utf-8')

    channel_name = f"split-{sanitize_channel_name(get_filename(file_path))}"
    channel = await get_or_create_channel(guild, channel_name, category)

    for i in range(0, len(content), 2000):
        await channel.send(content[i:i + 2000])

    return channel_name

@bot.command()
@commands.check_any(owner_check, is_whitelisted)
async def split(ctx, file_name: str):
    file_path = os.path.join(os.getcwd(), file_name)

    if not os.path.isfile(file_path):
        await ctx.send(f"File '{file_name}' not found.")
        return

    guild = ctx.guild
    guild_data = {
        "guild_id": str(guild.id),
        "guild_name": guild.name
    }
    category = await get_or_create_category(guild, "split_files")

    channel_name = await send_file_content_as_messages(ctx, file_path, guild, category)

    json_entry = {
        "file_name": get_filename(file_name),
        "channel_name": channel_name,
        "guild_data": guild_data
    }

    if not entry_exists(json_entry):
        with open(database_file, "a") as database:
            database.write(json.dumps(json_entry) + "\n")

    json_str = json.dumps(json_entry, indent=4)
    await ctx.send(f"```json\n{json_str}\n```")
    await ctx.send(f"File '{file_name}' split into messages in channel '{channel_name}'. JSON entry created.")

@bot.command()
@commands.check_any(owner_check, is_whitelisted)
async def rebuild(ctx, entry: str):
    try:
        entry = json.loads(entry)
    except json.JSONDecodeError:
        await ctx.send("Invalid JSON entry.")
        return

    channel_name = entry["channel_name"]
    channel = discord.utils.get(ctx.guild.channels, name=channel_name)

    if channel is None:
        await ctx.send(f"Channel '{channel_name}' not found.")
        return

    messages = await channel.history(limit=None, oldest_first=True).flatten()
    base64_content = ''.join([msg.content for msg in messages if msg.author == bot.user])

    try:
        decoded_content = base64.b64decode(base64_content)
    except (base64.binascii.Error, ValueError):
        await ctx.send("Error in decoding base64 content.")
        return

    output_file_path = os.path.join(os.getcwd(), entry["file_name"])
    with open(output_file_path, 'wb') as file:
        file.write(decoded_content)

    await ctx.send(f"File rebuilt: {entry['file_name']}")

@bot.command()
@commands.check_any(owner_check, is_whitelisted)
async def list(ctx):
    embed = discord.Embed(title="Command List", description="List of available commands:", color=discord.Color.blue())

    embed.add_field(name="!split <file_name>", value="Splits a file into parts and sends them as messages in the created channel.")
    embed.add_field(name="!rebuild", value="Rebuilds a file from split messages using the `database.json`.")
    embed.add_field(name="!list", value="Lists all the commands and their descriptions.")
    embed.add_field(name="!whitelist @USER", value="Whitelists users so they can run bot commands too.")
    embed.add_field(name="!blacklist @USER", value="Removes users from whitelists.")
    await ctx.send(embed=embed)

async def get_or_create_category(guild, name):
    category = discord.utils.get(guild.categories, name=name)
    if not category:
        category = await guild.create_category(name)
    return category


async def get_or_create_channel(guild, name, category):
    channel_name = sanitize_channel_name(name)
    channel = discord.utils.get(guild.channels, name=channel_name, category=category)
    if not channel:
        channel = await category.create_text_channel(channel_name)
    return channel

def get_filename(file_path):
    return os.path.basename(file_path)

def sanitize_channel_name(name):
    sanitized_name = re.sub(r"[/\\.:]+", "", name)
    return sanitized_name

# Create the database file if it doesn't exist
if not os.path.isfile(database_file):
    with open(database_file, "w") as database:
        pass

bot.run(os.getenv("TOKEN"))
