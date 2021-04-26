import random
import datetime
import os
import re
import time
from os import environ, getenv
from os.path import dirname, join
from pathlib import Path
import aiosqlite
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from utils.useful import *
from utils.subclasses import customContext
import itertools
import operator
import logging


to_call = ListCall()

class GrootBot(commands.Bot):
    def __init__(self, **kwargs):
        self.existing_prefix = {}
        self.greenTick = "<:greenTick:814504388139155477>"
        self.redTick = "<:redTick:814774960852566026>"
        self.data = currencyData(self)
        self.token = kwargs.pop("token", None)
        self.db = None
        self.session = aiohttp.ClientSession()
        self.premiums = set()
        self.blacklist = set()
        self.cached_users = {}
        self.cached_disabled = {}
        self.tips_on_cache = set()
        
        super().__init__(self.get_prefix, **kwargs)

    async def after_db(self):
        """Runs after the db is connected"""
        await to_call.call(self)

    def add_command(self, command):
        super().add_command(command)
        command.cooldown_after_parsing = True
        
        if discord.utils.find(lambda c:isinstance(c, grootCooldown), command.checks) is None:
            command.checks.append(grootCooldown(1, 3, 1, 1, commands.BucketType.user))

    @property
    def cwd(self):
        return str(Path(__file__).parents[0])

    @property
    def owner(self):
        """Gets the discord.User of the owner"""
        return self.get_user(396805720353275924)
    
    @property
    def error_channel(self):
        """Gets the error channel for the bot to log."""
        return self.get_guild(int(environ.get("SUPPORT_SERVER"))).get_channel(int(environ.get("ERROR_LOG_CHANNEL")))
        
    @to_call.append
    def loading_cog(self):
        """Loads the cog"""
        cogs = ()
        for file in os.listdir(f"{self.cwd}/cogs"):
            if file.endswith(".py"):
                cogs += (file[:-3],)

        cogs += ("jishaku",)
        
        for cog in cogs:
            ext = "cogs." if cog != "jishaku" else ""
            if error := call(self.load_extension, f"{ext}{cog}", ret=True):
                print_exception('Ignoring exception while loading up {}:'.format(cog), error)

    @to_call.append
    async def fill_blacklist(self):
        """Loading up the blacklisted users."""
        query = 'SELECT * FROM (SELECT guild_id AS snowflake_id, blacklisted  FROM guild_config  UNION ALL SELECT user_id AS snowflake_id, blacklisted  FROM users_data) WHERE blacklisted="TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        self.blacklist = {r[0] for r in data} or set()
    
    @to_call.append
    async def fill_premiums(self):
        """Loading up premium users."""
        query = 'SELECT * FROM (SELECT guild_id AS snowflake_id, premium  FROM guild_config  UNION ALL SELECT user_id AS snowflake_id, premium  FROM users_data) WHERE premium="TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        self.premiums = {r[0] for r in data} or set()
    
    @to_call.append
    async def fill_tips_on(self):
        """Loading up users that have tips enabled"""

        query = 'SELECT user_id FROM users_data WHERE tips = "TRUE"'
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        self.tips_on_cache = {r[0] for r in data} or set()
    
    @to_call.append
    async def fill_disabled_commands(self):
        """Loads up all disabled_commands"""
        query = "SELECT command_name, snowflake_id FROM disabled_commands ORDER BY command_name"
        cur = await self.db.execute(query)
        data = await cur.fetchall()
        self.cached_disabled = {
            cmd: [r[1] for r in _group]
            for cmd, _group in itertools.groupby(data,
                key=operator.itemgetter(0))
        }

    async def get_prefix(self, message):
        """Handles custom prefixes, this function is invoked every time process_command method is invoke thus returning
        the appropriate prefixes depending on the guild."""
        query = "SELECT prefix FROM guild_config WHERE guild_id=?"
        snowflake_id = message.guild.id if message.guild else message.author.id

        if not (prefix := self.existing_prefix.get(snowflake_id)):
            cur = await self.db.execute(query, (snowflake_id,))
            data = await cur.fetchone()
            data = data if data else ["g."]
            prefix = self.existing_prefix.setdefault(snowflake_id, data[0])

        comp = re.compile(f"^({re.escape(prefix)}).*", flags=re.I)
        match = comp.match(message.content)
        if match is not None:
            return match.group(1)
        return prefix

    def get_message(self, message_id):
        """Gets the message from the cache"""
        return self._connection._get_message(message_id)

    async def get_context(self, message, *, cls=None):
        """Override get_context to use a custom Context"""
        context = await super().get_context(message, cls=customContext)
        return context

    
    async def close(self):
        """Override close to close bot.session"""
        return await self.session.close()
    
    async def logout(self):
        return await super().close()

    def starter(self):
        """Starts the bot properly"""
        try:
            loop = asyncio.get_event_loop()
            db = loop.run_until_complete(aiosqlite.connect(f"{self.cwd}/data/main.sqlite3"))

        except Exception as e:
            print_exception("Could not connect to database:", e)

        else:
            self.launch_time = datetime.datetime.utcnow()
            self.db = db
            self.loop.run_until_complete(self.after_db())
            self.run(self.token)