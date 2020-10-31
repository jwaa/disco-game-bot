# bot.py

# TODO # - !suggest
# TODO # - welcome

import functools
import os
import random
import math
import re
import string
import sys
import time

import pandas as pd
import sqlite3

from discord.utils import get
from matplotlib import pyplot as plt
from discord import Activity, ActivityType, File, Intents, DiscordException
from dotenv import load_dotenv
from discord.ext import commands

# General settings
from matplotlib.ticker import StrMethodFormatter

COMMAND_PREFIX = "!"
IGNORE_EXISTING_DB = True

# Setting variables
load_dotenv()
DB_PATH = os.getenv('SQLITE_DB')
TOKEN = os.getenv('DISCORD_TOKEN')
ALLOWED_GUILDS = []

# Create disco game bot
intents = Intents.all()  # (guild_reactions=True, members=True)
disco = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# Create data storage
sql_connection = None

# Constant column names
user_id_col = "user_id"
user_name_col = "user_name"
game_col = "game"

# Some discord colors
discord_blue = "#7087E4"
discord_gray = "#36393F"
discord_white = "#FFFFFB"

# Emojis
em_wave = ":wave:"
em_smile = ":smiley_cat:"
em_sad = ":crying_cat_face:"

# ASCII emojis
em_throw_table = "(╯°□°）╯︵ ┻━┻"
em_put_table = "┬──┬◡ﾉ(° -°ﾉ)"
em_play_game = "{\\\__/}\n" \
               "(●_●)\n" \
               "( >🎮 Play game?"
em_panda_face = "(◉ܫ◉)"
em_game_on = "(ง •̀_•́)ง"
em_dance = "(~‾▿‾)~"
rnd_emotes = [em_panda_face, em_game_on, em_dance]

# A place to store any exceptions that occurred for a certain server
exceptions = {}


#######################
# Some helper methods #
#######################
# Transform a guild name to its SQL table name
def guild_sql_table(guild_name):
    return f"{guild_name}".replace(" ", "_")


# Text formatting
def style(txt):
    return f"```diff\n{txt}\n```"


# Status decorator and checks
def status_update(func):
    @functools.wraps(func)  # Important to preserve name because `command` uses it
    async def wrapper(*args, **kwargs):
        if "ctx" in kwargs.keys():
            ctx = kwargs["ctx"]
        else:
            ctx = args[0]

        # Check if the guild/server is allowed
        guild_name = ctx.guild.name
        if guild_name not in ALLOWED_GUILDS:
            raise ValueError(f"The guild {guild_name} is not allowed to run this bot.")

        # Show that the bot is busy
        with ctx.channel.typing():
            # Set status
            await disco.change_presence(activity=Activity(type=ActivityType.watching, name="the data"))

            # Call function
            result = await func(*args, **kwargs)

            # Set status
            await disco.change_presence(activity=Activity(type=ActivityType.listening, name="cyberspace"))

            return result

    return wrapper


# Plot a pandas series in a histogram
def plot_hist(counts):
    with plt.style.context("seaborn-dark"):
        # First plot its unique values in a horizontal bar graph
        ax = counts.plot.barh(color=discord_blue)

        # Despine
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['top'].set_visible(True)
        ax.spines['left'].set_color(discord_blue)
        ax.spines['left'].set_linewidth(2)

        # Set background colors
        ax.set_facecolor(discord_gray)
        ax.get_figure().patch.set_facecolor(discord_gray)

        # Set tick colors and size
        ax.tick_params(colors=discord_white, labelsize=12)

        # Set yticks to whole numbers (integers)
        xint = range(min(counts), math.ceil(max(counts)) + 1)
        ax.set_xticks(xint)

        # Draw vertical axis lines
        vals = ax.get_xticks()
        for tick in vals:
            ax.axvline(x=tick, linestyle='dashed', alpha=0.4, color=discord_blue, zorder=1)

        # Set x-axis label
        ax.set_xlabel("Games", labelpad=20, weight='bold', size=12, color=discord_white)

        # Set y-axis label
        ax.set_ylabel("# Registered", labelpad=20, weight='bold', size=12, color=discord_white)

        # Tight layout
        plt.tight_layout()

        # Store as a figure to a random file for sending over discord
        fig = ax.get_figure()
        fn = ''.join(random.choice(string.ascii_lowercase) for _ in range(16)) + ".png"  # random filename
        fn = os.path.join("db", fn)
        fig.savefig(fn)

        # Clear all figures
        plt.clf()

    # Return the file such that it can be send and deleted
    return fn


# Get games of some user
async def get_games(ctx, user_name, n_games):
    # Get the channel
    channel = ctx.channel

    # Get the games data
    guild_name = ctx.guild.name
    guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

    # Get the listed games of the requested user if given, otherwise get all listed games
    if user_name is not None and user_name != "all":
        # Get either the author's ID or the requested user ID
        if user_name == "me":
            user_id = ctx.author.id
            mssg = "These are the games you have registered:\n"
        else:
            user_id = [user.id for user in ctx.guild.members if user.name == user_name]
            mssg = f"These are all the games I know for {user_name}:\n"

            # If no user has this user name, send a message and return
            if len(user_id) == 0:
                await channel.send(style(f"It seems I cannot find {user_name} in this server. Did you spell it "
                                         f"correctly?"))
                return None, None, None

            else:
                if len(user_id) > 1:
                    # Multiple users have this name, which the bot handles by sending a message and pick the first
                    await channel.send(style(f"It seems I found more people with the name {user_name} in this server. "
                                             f"Sadly, I don't know how to handle this so I just pick the first one."))

                # We pick the first user with this user name
                user_id = user_id[0]

        # Get the user's games
        game_data = guild_df[guild_df[user_id_col] == user_id]
        listed_games = list(game_data[game_col].values)

    # No user name was given, so we show a server summary
    else:
        # Get all unique server games
        listed_games = list(set(list(guild_df[game_col].values)))
        mssg = f"These are all the games I know:\n"

        # No user id available
        user_id = None

    # If we have no listed games for that user or server
    if len(listed_games) == 0:
        if user_name is None:
            await channel.send(
                style(f"It seems nobody in this server registered any games yet. Be the first! You can do "
                      f"so with !add, for example '!add pubg, minecraft'."))
            return None, None, None
        elif user_name == "me":
            await channel.send(
                style(f"It seems you did not register any games yet. You can do so with !add, for example "
                      f"'!add pubg, minecraft'."))
            return None, None, None
        else:
            await channel.send(
                style(f"It seems that {user_name} did not yet register any games with me. {user_name} can "
                      f"do so for themself with !add, for example '!add pubg, minecraft'."))
            return None, None, None

    # Get the histogram of how popular these games are in the server
    hist = guild_df[game_col].value_counts()

    # Only keep the counts of listed games
    hist = hist.loc[listed_games]

    # Sort them
    hist = hist.sort_values(ascending=True)

    # Get the first n games
    n_games = max(1, min(n_games, len(hist)))
    hist = hist.iloc[len(hist) - n_games:]

    return mssg, hist, user_id


####################
# Listen to events #
####################
# When the bot is ready
@disco.event
async def on_ready():
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


# When an error/exception occurs
@disco.event
async def on_command_error(ctx, error):
    # Still print it to the console
    print(error, file=sys.stderr)

    # Get the server on which the erroneous event occurred
    guild_name = guild_sql_table(ctx.message.guild.name)

    # Check if it was a unknown command error
    if "is not found" in str(error):
        cmd = ctx.message.content
        mssg = f"I don't know the command {cmd} {em_sad}\nYou can type !help if you need some help."
        await ctx.message.channel.send(mssg)

    # If an exception is found, we prep the exceptions storage for this server if need be
    if guild_name not in exceptions.keys():
        exceptions[guild_name] = []

    # We create our 'exception data' dict
    exc = {"error": error, "context": ctx}

    # If an exception occurred we store it
    exceptions[guild_name].append(exc)


# When a new member joins
@disco.event
async def on_member_join(member):
    # Get the general channel of the server
    channel = get(member.guild.channels, name="general")

    # Welcome the new member
    await channel.send(f"Welcome {member.name}! {em_wave}")
    time.sleep(0.2)
    await channel.send(f"I am Disco, and I track what games everyone plays. This way it becomes a lot "
                       f"easier to see what is popular and who has the same games as you.")
    time.sleep(0.2)
    await channel.send("To add games you can use the command `!add`. For example; `!add pubg, Minecraft`. Which adds "
                       "the games PUBG and Minecraft to your profile. To view or list registered games use `!view` or "
                       "`!list` respectively. To view who plays a certain game use `!whoplays`. See `!help` for a "
                       "complete explanation of everything I can do.")

#####################
# Listen to commands
#####################
# View someone's games
@disco.command("view")
@status_update
async def view_games(ctx, user_name=None, show_n_games=10):
    """ [<user_name>|me] [<N>] Shows the games for either the entire server or a single user.

    This command will show a histogram of the games registered to me on the entire server ("!view") or a specific user
    ("!view <user_name>"). You can also only request the top-N games for the entire server ("!view all <N>") or a
    specific user ("!view <user_name> <N>"). As default N=10, showing only the top-10 games. If you want to view how
    popular your own games are in the server you can use the shortcut "!view me".
    """

    # Get the channel in which the command was used
    channel = ctx.message.channel

    # Get the games
    mssg, hist, _ = await get_games(ctx, user_name, show_n_games)

    # If no games were retrieved we end here
    if mssg is None and hist is None:
        return

    # Wrap the game data in a pretty figure
    fn = plot_hist(hist)

    # Send the message and figure
    await channel.send(content=style(mssg), file=File(fn))

    # Remove figure
    os.remove(fn)


# List someone's games
@disco.command("list")
@status_update
async def list_games(ctx, user_name=None):
    """ [<user_name>|me] Shows a list of games registered in the entire server of for a specific user

    Prints a list of the games registered in the entire server ("!list") or for a specific user ("!list <user_name>").
    If you want view the list of games you registered you can also type "!list me".

    :param ctx:
    :param user_name:
    :return:
    """

    # Get all of the (user's) games
    mssg, hist, _ = await get_games(ctx, user_name, n_games=854775807)

    # If no games were retrieved we end here
    if mssg is None and hist is None:
        return

    # Print all games
    game_list = "\n+ ".join(list(hist.index.values))
    game_list = "+ " + game_list

    # Get the channel in which the command was used
    channel = ctx.message.channel

    # Send message
    await channel.send(style(mssg + game_list))


# Remove someone's games
@disco.command("remove")
@status_update
async def remove_games(ctx, *, game_list=None):
    """ all|<game>[, <game>, ...]  Removes one or more games you have registered.

    This can be used to remove all games you have registered (!remove all) or just a few (!remove <game_1>, <game_2>,
    ...). On completion it provides an !add command to redo the removal if need be. Multiple games need to be
    comma-separated.
    """

    # Get all of the user's games
    _, hist, user_id = await get_games(ctx, user_name="me", n_games=854775807)
    registered_games = list(hist.index.values)

    # If the game list is None, we remove all games for that user
    if game_list == "all":
        games = registered_games

    # Else, we parse the games list (separated by comma's if there are more)
    else:
        # Split them
        games = re.split(", |,", game_list)

        # As title case, as this is how they are stored
        games = [g.title() for g in games]

    # Get the channel in which the command was used
    channel = ctx.message.channel

    # Check which games are present for this user
    to_remove = [g for g in games if g in registered_games]

    # If no games can be removed, we send a message and return
    if len(to_remove) == 0:
        await channel.send(style(f"It seems none of these games are registered for you, so I cannot unregister them."))
        return

    # Get this guilds/servers data
    guild_name = ctx.guild.name
    guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

    # Remove each game we can remove
    for g in to_remove:
        user_indices = guild_df[guild_df[user_id_col] == user_id].index
        game_indices = guild_df[guild_df[game_col] == g].index
        indices = list(set(user_indices).intersection(set(game_indices)))

        guild_df.drop(indices, inplace=True)

    # Update the database
    guild_df.to_sql(guild_sql_table(guild_name), sql_connection, if_exists="replace", index=False)

    # Create message telling what we did
    if len(to_remove) == len(hist):
        # We removed all
        add_list = ", ".join(to_remove)
        mssg = f"I removed all the registered games for you. To add them back you can use:\n " \
               f"!add {add_list}"

    elif len(to_remove) == 1 and len(games) == 1:
        # We removed one
        mssg = f"I removed {to_remove[0]} for you, to add it back you can use: !add " \
               f"{to_remove[0]}"
    else:
        # We removed some games but not all
        remove_list = "\n- ".join(to_remove)
        remove_list = "- " + remove_list
        add_list = ", ".join(to_remove)
        mssg = f"I removed {len(to_remove)} games for you:" \
               f"\n{remove_list}\n " \
               f"To add them back, you can use: !add {add_list}"

    # Send message
    await channel.send(style(mssg))


# The add games command
@disco.command("add")
@status_update
async def add_games(ctx, *, game_list=None):
    """ <game>[, <game>, ...] Add one or more games.

    Adds or registers one (!add <game>) or more games (!add <game>, <game>, ...). Multiple games need to be
    comma-separated.
    """

    # Get the channel in which the command was used
    channel = ctx.message.channel

    # If no games were provided send a help message
    if game_list is None:
        await channel.send(
            style("If you want to add some games to your profile, you should tell me which. For example; "
                  "'!add pubg, World of Warcraft, Minecraft'."))
        return

    # Get the accompanying game names (separated by comma's if there are more)
    games = re.split(", |,", game_list)
    games = [g.title() for g in games]

    # Get the games data
    guild_name = ctx.guild.name
    if guild_name not in ALLOWED_GUILDS:
        raise ValueError(f"The guild {guild_name} is not allowed to run this bot.")
    guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

    # Get the author, as a Member or User, and use its unique ID to get its game data (can be empty)
    author = ctx.author
    user_id = author.id
    game_data = guild_df[guild_df[user_id_col] == user_id]

    # Check which games are new to add
    to_add = []
    for game in games:
        if len(game_data[game_data[game_col] == game.title()]) == 0:
            to_add.append(game.title())

    # If no games can be added, send a message with this result and be done
    if len(to_add) == 0:
        await channel.send(style(f"It seems all of these games are already added to your list!"))
        return

    # If games need to be added, we do so
    user_name = author.name
    for g in to_add:
        guild_df = guild_df.append({user_id_col: user_id, user_name_col: user_name, game_col: g}, ignore_index=True)

    # Update SQL table
    guild_df.to_sql(guild_sql_table(guild_name), sql_connection, if_exists="replace", index=False)

    # Send a message back with the successful result, a bit contextual to those who were already added
    if len(to_add) == len(games):
        if len(to_add) > 1:
            await channel.send(style('Done! I added these games to your profile.'))
        else:
            await channel.send(style("Done! I added this game to your profile."))
    else:
        already_added = set(games).difference(set(to_add))
        if len(already_added) < 6:  # only list the added games if less then 6
            already_added = "\n- ".join([g for g in already_added])
            already_added = "- " + already_added
            await channel.send(style(f'Done! I added some of these games, as some of these games were already stored '
                                     f'for you:\n{already_added}'))
        else:
            await channel.send(style(
                f'Done! I added {len(to_add)} new games, as {len(already_added)} were already added.'))


# The get error command
@disco.command("wazzup")
@status_update
async def get_error(ctx, forget=None):
    """ [forget] Show or forget the current status of the Disco bot

    Lists potential caught exceptions in this server. Can also be used to clear all stored caught exceptions
    (!wazzup forget)
    """

    # Get guild name
    guild_name = guild_sql_table(ctx.message.guild.name)

    # See if there are any exceptions raised since last get_error request
    excs = []
    if guild_name in exceptions.keys():
        if len(exceptions[guild_name]):
            excs = exceptions[guild_name]

    # See if we need to clear all errors
    if forget is not None and forget.lower() == "forget":
        # Create message based on if there were exceptions
        mssg = f"I'm good, nothing to forget! {em_smile}"
        if len(excs) >= 1:
            issue_str = "issue" if len(excs) == 1 else "issues"
            mssg = f"Few... I just forgot about {len(excs)} {issue_str} in the world!\n{em_put_table}"

        # Clear all errors/exceptions
        exceptions[guild_name] = []

        # Send message
        await ctx.channel.send(mssg)

        return

    # If none were found, send that the bot is all good and return
    if len(excs) == 0:
        mssg = f"I'm all good! {em_smile}"
        await ctx.message.channel.send(mssg)
        return

    # Else, format the errors and send them
    mssg = f"Since you ask... I did run into some issues!\n{em_throw_table}"
    await ctx.message.channel.send(mssg)
    mssg = "The following exceptions were caught:"
    for exc in excs:
        # Get some exception data
        err = exc["error"]
        ctx = exc["context"]
        err_name = str(err).split(": ")
        if len(err_name) > 1:
            err_name = " ".join(err_name[1:])
        author = ctx.author.name
        cmd = ctx.message.content
        time = ctx.message.created_at.strftime("%m/%d/%Y, %H:%M:%S")

        # Format message to send
        mssg += f"\n- {err_name} was raised when {author} used {cmd} at {time}"

    await ctx.message.channel.send(style(mssg))


# Get a list of people who play a certain game
@disco.command("whoplays")
@status_update
async def get_members(ctx, *, game):
    """ <game>  Lists the server members who registered a game.

    It lists all of the people in this server who registered the given game (e.g. !whoplays Minecraft). Only one game
    can be queried at a time, though it is not case sensitive.
    """

    # Get the channel
    channel = ctx.message.channel

    # Format the game name
    game = game.title()

    # Get the guild data
    guild_name = ctx.guild.name
    guild_df = pd.read_sql_query(f"SELECT * from {guild_sql_table(guild_name)}", sql_connection)

    # Get all of the member ID's who registered that game
    ids = guild_df[guild_df[game_col] == game]
    names = list(ids[user_name_col].values)

    # Get the message's author
    author = ctx.message.author.name

    # Create opening if no one registered the game,
    if len(names) == 0:
        # send message and return
        mssg = f"Sadly none have registered {game} to me {em_sad}"
        await channel.send(mssg)
        return

    # only the author registered it
    elif len(names) == 1 and names[0] == author:
        # send message and return
        mssg = f"It seems only you have registered {game} to me."
        await channel.send(mssg)
        return

    # Others have this game registered
    else:

        if author in names:
            # Remove self from the names
            names.remove(author)

            # Create name list message
            names_mssg = "The following people have this game: " + ", ".join(names) + "\n"

            # Create message
            others_str = "others" if len(names) > 1 else "other"
            mssg = f"{len(names)} {others_str} also registered {game} to me beside you!\n"
            mssg += names_mssg

            # Send messages
            await channel.send(mssg)
            time.sleep(0.2)
            await channel.send(f".\n{em_play_game.replace('game', game)}")

        else:
            # Create message
            others_str = "others" if len(names) > 1 else "other"
            mssg = f"{len(names)} {others_str} have registered {game} to me! Do you also play this game? If so you" \
                   f" can register it to me with !add {game}."

            # Send message
            await channel.send(mssg)


def run_bot(test_mode=False, reset_databases=False):
    global ALLOWED_GUILDS, IGNORE_EXISTING_DB
    IGNORE_EXISTING_DB = reset_databases
    if test_mode:
        guild_var = 'DISCORD_TEST_GUILDS'
    else:
        guild_var = 'DISCORD_GUILDS'
    ALLOWED_GUILDS = os.getenv(guild_var).split(",")

    disco.run(TOKEN)


if __name__ == "__main__":
    run_bot(test_mode=True, reset_databases=False)
