import datetime
import itertools
import logging
import operator
import os
import re
from pathlib import Path

import aiohttp
import aiosqlite
import discord

from ext.category import Category
from discord.ext import commands, ipc

from utils.cache import CacheManager
from utils.subclasses import customContext
from utils.useful import (Cooldown, ListCall, call, currencyData,
                          print_exception)
from utils.json_loader import read_json

to_call = ListCall()


class GrootBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(self.get_prefix, **kwargs)
        self.icons = {}
        self.non_sync = ["music", "core"]
        self.data = currencyData(self)
        self.token = kwargs.pop("token", None)
        self.session = aiohttp.ClientSession()
        self.maintenance = False
        self.cache = CacheManager()
        self.ipc = ipc.Server(
            self, host="0.0.0.0", secret_key="GrootBotAdmin"
        )
        self.categories = {}
        self.config = dict(os.environ)
        self.testers = [396805720353275924]

    async def after_db(self):
        """Runs after the db is connected"""
        await to_call.call(self)

    def add_command(self, command):
        """Overwrite add_command to add a default cooldown to every command"""
        super().add_command(command)
        command.cooldown_after_parsing = True

        if (
            discord.utils.find(lambda c: isinstance(c, Cooldown), command.checks)
            is None
        ):
            command.checks.append(Cooldown(1, 3, 1, 1, commands.BucketType.user))

    @property
    def cwd(self):
        return str(Path(__file__).parents[0])

    @property
    def owner(self):
        """Gets the discord.User of the owner"""
        return self.get_user(396805720353275924)

    @property
    def log_channel(self):
        """Gets the error channel for the bot to log."""
        return self.owner

    @to_call.append
    def loading_emojis(self):
        emojis = {
            "greenTick": "<:greenTick:814504388139155477>",
            "redTick": "<:redTick:814774960852566026>",
            "plus": "<:plus:854044237556351006>",
            "minus": "<:minus:854046724497604649>",
            "save": "<:save:854038370735882260>",
            'online': '<:online:808613541774360576>', 
            'offline': '<:offline:817034738014879845>', 
            'idle': '<:idle:817035319165059102>',
            'dnd': '<:dnd:817035352925536307>',
            'boosters': '<:Boosters:814930829461553152>',
            'typing': '<a:typing:826939777290076230>',
            'database': '<:database:857553072909189191>',
            'groot': '<:Groot:829361863807860756>',
            'loading': '<a:loading:856978168476205066>'
        }

        self.icons = emojis
        return self.icons

    @to_call.append
    def loading_cogs(self):
        """Loads the cogs"""
        cogs = ()
        for file in os.listdir(f"{self.cwd}/cogs"):
            if file.endswith(".py"):
                cogs += (file[:-3],)

        cogs += ("jishaku", )
        for cog in cogs:
            ext = "cogs." if cog != "jishaku" else ""
            if error := call(self.load_extension, f"{ext}{cog}", ret=True):
                print_exception(
                    "Ignoring exception while loading up {}:".format(cog), error
                )

    @to_call.append
    async def fill_cache(self):
        """Loading up the blacklisted users."""
        query = 'SELECT * FROM (SELECT guild_id AS snowflake_id, blacklisted  FROM guild_config  UNION ALL SELECT user_id AS snowflake_id, blacklisted  FROM users_data) WHERE blacklisted="TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        ## BETA
        self.cache["blacklisted_users"] = {r[0] for r in data} or set()
        # self.blacklist = {r[0] for r in data} or set()

        """Loading up premium users."""
        query = 'SELECT * FROM (SELECT guild_id AS snowflake_id, premium  FROM guild_config  UNION ALL SELECT user_id AS snowflake_id, premium  FROM users_data) WHERE premium="TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        ## BETA
        self.cache["premium_users"] = {r[0] for r in data} or set()
        # self.premiums = {r[0] for r in data} or set()

        """Loading up users that have tips enabled"""

        query = 'SELECT user_id FROM users_data WHERE tips = "TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        ## BETA
        self.cache["tips_are_on"] = {r[0] for r in data} or set()
        # self.tips_on_cache = {r[0] for r in data} or set()

        """Loads up all disabled_commands"""
        query = "SELECT command_name, snowflake_id FROM disabled_commands ORDER BY command_name"
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        ## BETA
        self.cache["disabled_commands"] = {
            cmd: [r[1] for r in _group]
            for cmd, _group in itertools.groupby(data, key=operator.itemgetter(0))
        }
        # self.cached_disabled = {
        #   cmd: [r[1] for r in _group]
        #   for cmd, _group in itertools.groupby(data, key=operator.itemgetter(0))
        #}
        self.cache["users"] = {}

    async def get_prefix(self, message):
        """Handles custom prefixes, this function is invoked every time process_command method is invoke thus returning
        the appropriate prefixes depending on the guild."""
        if message.author == self.owner:
            return ["g.", "", self.cache["prefix"].get(getattr(message.guild, "id", message.author.id))]
        query = "SELECT prefix FROM guild_config WHERE guild_id=?"
        snowflake_id = getattr(message.guild, "id", message.author.id)
        self.cache.setdefault("prefix", {})
        if not (prefix := self.cache["prefix"].get(snowflake_id)):
            cur = await self.db.execute(query, (snowflake_id,))
            data = await cur.fetchone()
            data = data if data else ["g."]
            prefix = self.cache["prefix"].setdefault(snowflake_id, data[0])

        comp = re.compile(f"^({re.escape(prefix)}).*", flags=re.I)
        match = comp.match(message.content)
        if match is not None:
            return match.group(1)
        return prefix

    def add_cog(self, cog: commands.Cog, cat_name: str = "Unlisted"):
        category = self.get_category(cat_name)

        if not category:
            category = Category(cat_name)
            self.categories[category.name] = category

        category.add_cog(cog)
        super().add_cog(cog)

    def get_message(self, message_id):
        """Gets the message from the cache"""
        return self._connection._get_message(message_id)

    def get_category(self, name):
        """Gets the category with the given name."""
        return self.categories.get(name)

    async def get_context(self, message, *, cls=None):
        """Override get_context to use a custom Context"""
        context = await super().get_context(message, cls=customContext)
        return context

    async def process_commands(self, message):
        """Override process_commands to check, and call typing every invoke"""
        if message.author.bot:
            return

        # Checks etc for blacklist ...
        ctx = await self.get_context(message)
        if message.author.id == self.owner.id:
            await self.invoke(ctx)
            return

        if self.maintenance and ctx.valid:
            await message.channel.send("Bot is in maintenance. Please try again later.")
            return

        if (message.author.id in self.cache["blacklisted_users"] or getattr(message.guild, "id", None) in self.cache["blacklisted_users"]):
            return

        if ctx.valid and ctx.command.name in self.cache["disabled_commands"].keys():
            if (
                ctx.valid
                and message.channel.id in self.cache["disabled_commands"][ctx.command.name]
                or ctx.valid
                and message.guild.id in self.cache["disabled_commands"][ctx.command.name]
            ):
                return
        
        # Trigger typing every invoke
        if ctx.valid and getattr(ctx.cog, "qualified_name", None) != "Jishaku":
            await ctx.trigger_typing()
        await self.invoke(ctx)

    def starter(self):
        """Starts the bot properly"""
        try:
            db = self.loop.run_until_complete(
                aiosqlite.connect(f"{self.cwd}/data/main.sqlite3")
            )
        except Exception as e:
            print_exception("Could not connect to database:", e)

        else:
            self.launch_time = datetime.datetime.utcnow()
            self.db = db
            self.loop.run_until_complete(self.after_db())
            try:
                self.ipc.start()
            except Exception as e:
                logging.warning("Couldn't connect to IPC:", e)
            self.run(self.token)

    # Events
    async def on_ready(self):
        logging.warning(f"Logged in as {self.user}, SQLite3 database initialized.")
        print(f"Logged in as {self.user}")

        # Edit restart message
        data = read_json('config')
        channel = self.get_channel(data['messages']['lastChannel'])
        msg = await channel.fetch_message(data['messages']['lastMessage'])
        if msg is not None:
            await msg.edit(content=f"Back online {self.owner.mention}!")

    async def on_ipc_error(self, endpoint, error):
        logging.warning(f"{endpoint} raised {error}")
        