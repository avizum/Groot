from utils._type import *

import asyncio
import datetime
import random
import discord
import json

from discord.ext import commands
from humanize.time import precisedelta
from PIL import Image, ImageDraw, ImageFont
from typing import Union
from utils.useful import Embed, detect, get_grole
from wonderwords import RandomSentence, RandomWord


class Utilities(commands.Cog, description="Handy dandy utils"):
    def __init__(self, bot):
        self.bot = bot
        self.index = 0
        self.snipe_cache = {}
        self.esnipe_cache = {}

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        message = after
        if message.author.bot:
            return
        
        try:
            cache = self.esnipe_cache[message.channel.id]
        except KeyError:
            cache = self.esnipe_cache[message.channel.id] = []
        
        cache.append({"author": before.author, "before_content": before.content, "after_content": message.content, "message_obj": message})
        await asyncio.sleep(300)
        del cache[cache.index({"author": before.author, "before_content": before.content, "after_content": message.content})]

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        try:
            cache = self.snipe_cache[message.channel.id]
        except KeyError:
            cache = self.snipe_cache[message.channel.id] = []
        
        cache.append(message)

        await asyncio.sleep(300)
        del cache[cache.index(message)]

    @commands.command(name="snipe", brief="Retrieves a recent deleted message")
    async def snipe(self, ctx: customContext, index=1):
        """
        Acts like a message log, but for channel specific and command only.\n
        Only returns the most recent message.
        A bot's deleted message is ignored.
        """
        try:
            cache = self.snipe_cache[ctx.channel.id]
        except KeyError:
            raise commands.BadArgument("There's nothing to snipe here.")

        try:
            message = cache[index-1]
        except IndexError:
            raise commands.BadArgument("There's nothing to snipe here.")

        em = Embed(
            title=f"Last deleted message in #{ctx.channel.name}",
            description=message.content,
            timestamp=datetime.datetime.utcnow(),
            colour=discord.Color.random(),
            url=message.jump_url
        )
        em.set_author(
            name=message.author,
            icon_url=message.author.avatar_url
        )
        em.set_footer(text=f"Sniped by: {ctx.author} | Index {index}/{len(cache)}")
        await ctx.send(embed=em)

    @commands.command(name="editsnipe", brief="Retrieves a recently edited message")
    async def editsnipe(self, ctx: customContext, index=1):
        """
        Same as `snipe`, but for edited messages.
        A bot's edited message is ignored.
        """
        try:
            cache = self.esnipe_cache[ctx.channel.id]
        except KeyError:
            raise commands.BadArgument("There's nothing to snipe here.")

        try:
            message = cache[index-1]
        except IndexError:
            raise commands.BadArgument("There's nothing to snipe here.")

        em = Embed(
            title=f"Last edited message in #{ctx.channel.name}",
            description="**Before:**\n"
            f"+ {message['before_content']}\n"
            f"\n**After:**\n- {message['after_content']}",
            timestamp=datetime.datetime.utcnow(),
            colour=discord.Color.random(),
            url=message['message_obj'].jump_url
        )
        em.set_author(
            name=message['author'],
            icon_url=message['author'].avatar_url
        )

        em.set_footer(text=f"Sniped by: {ctx.author} | Index {index}/{len(cache)}")
        await ctx.send(embed=em)

    @commands.command(name="choose")
    async def choose(self, ctx: customContext, *, choice):
        choicelist = choice.split(" ")
        await ctx.send(random.choice(choicelist))

    @commands.command(
        name="ui", aliases=["info", "whois"], brief="Displays an user's information"
    )
    async def ui(self, ctx: customContext, member: discord.Member = None):
        """
        Shows all the information about the specified user.\n
        If none is specified, it defaults to the author.
        """
        member = member if member else ctx.author
        guild = ctx.guild
        status = member.raw_status
        
        def format_dt(dt: datetime.datetime, style=None):
            if style is None:
                return f'<t:{int(dt.timestamp())}>'
            return f'<t:{int(dt.timestamp())}:{style}>'
        em = Embed(
            title="",
            description=f"{member.mention}",
            timestamp=datetime.datetime.utcnow(),
        )
        em.add_field(
            name="Joined at", value=f"{format_dt(member.joined_at)} ({format_dt(member.joined_at, 'R')})"
        )
        em.add_field(
            name="Created at", value=f"{format_dt(member.created_at)} ({format_dt(member.created_at, 'R')})"
        )
        roles = member.roles[1:30]

        if roles:
            em.add_field(
                name=f"Roles [{len(member.roles) -1}]",
                value=" ".join(f"{role.mention}" for role in roles),
                inline=False,
            )
        else:
            em.add_field(
                name=f"Roles [{len(member.roles) -1}]",
                value="This member has no roles",
                inline=False,
            )



        em.add_field(name=f"Status:", value=f"{self.bot.icons[status]} {status.capitalize()}")

        # Activity
        activity = member.activity or "No activity currently"
        if isinstance(activity, discord.BaseActivity):
            em.add_field(name="Activity:", value=activity.name, inline=False)
        else:
            em.add_field(name="Activity:", value="No activity currently", inline=False)
        em.set_thumbnail(url=member.avatar_url)
        em.set_author(name=f"{member}", icon_url=member.avatar_url)
        em.set_footer(text=f"User ID: {member.id}")
        await ctx.send(embed=em)

    @commands.command(name="avatar", aliases=["av"], brief="Displays a member's avatar")
    async def avatar(self, ctx: customContext, member: discord.Member = None):
        """
        Displays a 1024 pixel sized image of the given member's avatar.
        If no member is specified, it defaults to the author's avatar.
        """
        member = member if member else ctx.author
        if member:
            em = Embed(
                title=f"Avatar for {member}",
                description=f'Link as\n[png]({member.avatar_url_as(format="png",size=1024)}) | [jpg]({member.avatar_url_as(format="jpg",size=1024)}) | [webp]({member.avatar_url_as(format="webp",size=1024)})',
                colour=discord.Color.blurple(),
            )
            em.set_image(url=member.avatar_url)
            await ctx.send(embed=em)

    @commands.command(name="archive", aliases=['save', 'arch'])
    async def _archive(self, ctx, *, message: typing.Optional[discord.Message]):
        """
        Archive a message to your DM's by either
        supplying a message ID or replying to one.
        """

        if not message:
            message = getattr(ctx.message.reference, "resolved", None)
        
        if not message:
            raise commands.BadArgument(f"{self.bot.icons['redTick']} | You must either reply to a message, or pass in a message ID/jump url")

        # Resort message
        content = message.content or "_No content_"
        em = Embed(title="You archived a message!", url=message.jump_url, description=content, timestamp=datetime.datetime.utcnow())
        em.set_author(name=message.author, icon_url=message.author.avatar_url)
        try:
            msg = await ctx.author.send(embed=em)
            await msg.pin()
            await ctx.send(f"Archived the message in your DMs!\n{msg.jump_url}")
        except discord.Forbidden:
            await ctx.send("Oops! I couldn't send you a message. Are you sure your DMs are on?")

    @commands.command(name="rickroll", brief="Detects rickroll from given link")
    async def _rickroll(self, ctx: customContext, *, link):
        """
        Detects if the given link is a rickroll.\n
        The link must start with https://.\n
        """
        i = link.replace("<", "").replace(">", "")
        if "https://" in link:
            if await detect().find(i):
                await ctx.message.reply("Rickroll detected :eyes:")
            else:
                await ctx.message.reply("That website is safe :>")
        else:
            await ctx.send(link + " is not a valid URL...")

    
    @commands.command(name="id", usage="<channel | emoji | user>")
    async def _get_id(self, ctx: customContext, arg: Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.CategoryChannel, discord.Emoji, discord.User]):
        """
        Gets the ID from either a channel, an emoji or a user
        The emoji can **not** be a default emoji (they don't have ID's)
        """
        if not isinstance(arg, discord.Emoji):
            await ctx.send(f"\\{arg.mention}", allowed_mentions=discord.AllowedMentions(users=False))
        else:
            await ctx.send(f"\\<:{arg.name}:{arg.id}>")
    
    @commands.command(name="embed")
    async def _send_embed(self, ctx: customContext, *, embed: str):
        """
        Takes an embed dictionary as args and sends the embed.
        For more information see the documentation on Discord's official website.
        """
        em = discord.Embed.from_dict(json.loads(embed))
        await ctx.send(embed=em)

def setup(bot):
    bot.add_cog(Utilities(bot), cat_name="Utilities")
