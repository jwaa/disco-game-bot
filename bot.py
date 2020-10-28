# bot.py
import os
import re

import pandas as pd
import sqlite3

from discord import utils, Activity, ActivityType
from dotenv import load_dotenv
from discord.ext import commands

# General settings
COMMAND_PREFIX = "!"
IGNORE_EXISTING_DB = True

# Setting variables
load_dotenv()
DB_PATH = os.getenv('SQLITE_DB')
TOKEN = os.getenv('DISCORD_TOKEN')
ALLOWED_GUILDS = []

# Create disco game bot
disco = commands.Bot(command_prefix=COMMAND_PREFIX)

# Create data storage
sql_connection = None

# Some helper lambdas
guild_sql_table = lambda g: f"{g}".replace(" ", "_")

# Constant column names
user_id_col = "user_id"
user_name_col = "user_name"
game_col = "game"


# Listen to events
@disco.event
async def on_ready():
    # Set status
    await disco.change_presence(activity=Activity(type=ActivityType.watching, name="the data"))

    # Check if we have an existing database
    global sql_connection
    if os.path.exists(DB_PATH) and not IGNORE_EXISTING_DB:
        sql_connection = sqlite3.connect(DB_PATH)
        loaded_db = True
    else:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        sql_connection = sqlite3.connect(DB_PATH)
        loaded_db = False

    # Prep database using Pandas and SQLite (because I suck at SQL)
    for g in ALLOWED_GUILDS:
        guild_df = pd.DataFrame(columns=[user_id_col, user_name_col, game_col])
        guild_df.to_sql(guild_sql_table(g), sql_connection, if_exists="replace", index=False)

    # Print connection
    if loaded_db:
        print(f'{disco.user.name} has connected to Discord and loaded the database!')
    else:
        print(f'{disco.user.name} has connected to Discord and created a new database!')

    # Set status
    await disco.change_presence(activity=Activity(type=ActivityType.listening, name="cyberspace"))


#####################
# Listen to commands
#####################
# View someone's games
@disco.command("view")
async def view_games(ctx, user_name):
    # Get the channel in which the command was used
    channel = ctx.message.channel

    # Set as typing, as visual feedback that we are doing something (as retrieving data from the DB might be slow
    # given the server this bots runs on)
    with channel.typing():
        # Set status
        await disco.change_presence(activity=Activity(type=ActivityType.watching, name="the data"))

        # Get the games data
        guild_name = ctx.guild.name
        if guild_name not in ALLOWED_GUILDS:
            raise ValueError(f"The guild {guild_name} is not allowed to run this bot.")
        guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

        # Get the listed games of the requested user if given, otherwise get all listed games
        if user_name is not None:
            # Get either the author's ID or the requested user ID
            if user_name == "me":
                user_id = ctx.author.id
            else:
                user_id = [user.id for user in ctx.guild.members if user.name == user_name]
                # If no user has this user name, send a message and return
                if len(user_id) == 0:
                    await channel.send(f"It seems I cannot find {user_name} in this server. Did you spell it alright?")
                    return

                else:
                    if len(user_id) > 1:
                        # Multiple users have this name, which the handles by sending a message and picking the first
                        await channel.send(f"It seems I found more people with the name {user_name} in this server. "
                                           f"Sadly, I don't know how to handle this so I just pick the first one.")

                    # We pick the first user with this user name
                    user_id = user_id[0]

            # Get the user's games
            game_data = guild_df[guild_df[user_id_col] == str(user_id)]
            listed_games = list(game_data[game_col].values)

        # No user name was given, so we show a server summary
        else:
            # Get all server games
            listed_games = list(guild_df[game_col].values)

        # Get the histogram of how popular these games are in the server
        hist = guild_df[game_col].groupby(listed_games).count()

        # Wrap the game data in a pretty format
        pass

        # Send the message
        pass


# The add games command
@disco.command("add")
async def add_games(ctx, game_list=None):
    # Get the channel in which the command was used
    channel = ctx.message.channel

    # If no games were provided send a help message
    if game_list is None:
        await channel.send("If you want to add some games to your profile, you should tell me which. For example; "
                           "'!add pubg, World of Warcraft, Minecraft'.")
        return

    # Get the accompanying game names (separated by comma's if there are more)
    games = re.split(", |,", game_list)

    # Set as typing, as visual feedback that we are doing something (as retrieving data from the DB might be slow
    # given the server this bots runs on)
    with channel.typing():
        # Set status
        await disco.change_presence(activity=Activity(type=ActivityType.watching, name="the data"))

        # Get the games data
        guild_name = ctx.guild.name
        if guild_name not in ALLOWED_GUILDS:
            raise ValueError(f"The guild {guild_name} is not allowed to run this bot.")
        guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

        # Get the author, as a Member or User, and use its unique ID to get its game data (can be empty)
        author = ctx.author
        user_id = author.id
        game_data = guild_df[guild_df[user_id_col] == str(user_id)]

        # Check which games are new to add
        to_add = []
        for game in games:
            if len(game_data[game_data[game_col] == game]) == 0:
                to_add.append(game)

        # If no games can be added, send a message with this result and be done
        if len(to_add) == 0:
            await channel.send(f"It seems all of these games are already added to your list!")
            return

        # If games need to be added, we do so
        user_name = author.name
        for g in to_add:
            guild_df = guild_df.append({user_id_col: user_id, user_name_col: user_name, game_col: g}, ignore_index=True)

        # Update SQL table
        guild_df.to_sql(guild_sql_table(guild_name), sql_connection, if_exists="append", index=False)

        # Send a message back with the successful result, a bit contextual to those who were already added
        if len(to_add) == len(games):
            if len(to_add) > 1:
                await channel.send('Done! I added these games to your profile.')
            else:
                await channel.send("Done! I added this game to your profile.")
        else:
            already_added = set(games).difference(set(to_add))
            if len(already_added) < 6:  # only list the added games if less then 6
                already_added = "\n- ".join([g for g in already_added])
                already_added = "- " + already_added
                await channel.send(f'Done! I added some of these games, as some of these games were already stored for '
                                   f'you:\n{already_added}')
            else:
                await channel.send(f'Done! I added {len(to_add)} new games, as {len(already_added)} were already added.')

    # Set status
    await disco.change_presence(activity=Activity(type=ActivityType.listening, name="cyberspace"))


def run_bot(test_mode=True):
    global ALLOWED_GUILDS
    if test_mode:
        guild_var = 'DISCORD_TEST_GUILDS'
    else:
        guild_var = 'DISCORD_GUILDS'
    ALLOWED_GUILDS = os.getenv(guild_var).split(",")

    disco.run(TOKEN)
