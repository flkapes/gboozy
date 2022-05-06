import discord
from client.gboozy_client import GboozyClient
from commands.CommandErrorHandler import CommandErrHandler
from commands.Music import Music
from commands.StalkListener import StalkListener


def main():
    token = "OTcwMzg4OTk0MTEyMjMzNTky.Ym7PLQ.z8SsiIcQpwQ0vdsVXwv1RNJGZK4"

    intents = discord.Intents.default()
    intents.members = True

    bot = GboozyClient(
        command_prefix="$",
        intents=intents
    )

    bot.add_cog(StalkListener(bot))
    bot.add_cog(Music(bot))
    bot.add_cog(CommandErrHandler(bot))

    bot.run(token)


if __name__ == "__main__":
    main()
