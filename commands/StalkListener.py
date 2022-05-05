import discord


class StalkListener(discord.ext.commands.Cog, name="StalkListen"):
    def __init__(self, bot):
        self.bot = bot

    @discord.ext.commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        embed = None
        # channel = .utils.get(self.bot.guild.text_channels, name="StalkingLogs")
        # if channel is None:
        #    channel = await self.bot.guild.create_text_channel("StalkingLogs")

        if before.display_name != after.display_name:
            embed = discord.Embed(title=f"Changed Name")
            embed.add_field(name='User', value=before.mention)
            embed.add_field(name="Before", value=before.display_name)
            embed.add_field(name="After", value=after.display_name)
        if before.avatar != after.avatar:
            embed = discord.Embed(title=f"Changed Avatar")
            embed.add_field(name='User', value=before.mention)
            embed.add_field(
                name="Before",
                value=before.name).set_image(
                before.avatar)
            embed.add_field(
                name="After",
                value=after.name).set_image(
                after.avatar)
        if before.name != after.name:
            embed = discord.Embed(title=f"Changed Name")
            embed.add_field(name='User', value=before.mention)
            embed.add_field(name="Before", value=before.name)
            embed.add_field(name="After", value=after.name)

        # await channel.send(embed=embed)
        await self.bot.get_user(self, id=241821259434950657).send(embed=embed)
