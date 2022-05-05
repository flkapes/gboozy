from discord.ext import commands
import logging


class GboozyClient(commands.Bot):
    async def onReady(self):
        print("gBoozy has successfully connected!")
        print("Username: {0.name}".format(self.user))
