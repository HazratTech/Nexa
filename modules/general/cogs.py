import discord
import requests
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @commands.hybrid_command(name="youtube", description="search video")
    async def youtube(self, interaction: commands.Context, search: str):
        response = requests.get(f"https://youtube.com/results?search_query={search}")
        html = response.text
        index = html.find("/watch?v=")
        url = "https://www.youtube.com" + html[index : index + 20]
        await interaction.send(url)


    @app_commands.command(name="botemoji", description="Display all bot emojis")
    async def app_emoji(self, interaction: discord.Interaction):
        emojis = await self.bot.fetch_application_emojis()
        if not emojis:
            await interaction.response.send_message("No bot emojis available.")
            return

        await interaction.response.send_message(f"{", ".join(f"<:{emoji.name}:{emoji.id}>" for emoji in emojis)}")


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
