import discord
import sys
import traceback
from discord.ext import commands


class CommandErrHandler(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, discord.ext.commands.CommandNotFound):
            await ctx.send('Sorry, that command does not exist!')
        else:
            print(
                'Ignoring exception in command {}:'.format(
                    ctx.command),
                file=sys.stderr)
            traceback.print_exception(
                type(error),
                error,
                error.__traceback__,
                file=sys.stderr)
