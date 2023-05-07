# syncing is not included in this example.

import discord
from discord.ext import commands

from cordcutter import Cordcutter

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=discord.Intents(messages=True, guilds=True))
# Initialise the Cordcutter class
# the constructor takes one required argument, the CommandTree
# and four optional ones...
# threshold (default: 3) - After how many errors it should trigger the breaker.
# reset_after (default: 1 minutes) - The time after it should reset the break.
# trip_callback (default: None) - The function it should call when the threshold is reached -
# - you can also use the on_tripped_call decorator.
# hybrid_app_command (default: True) - Whether to also use the breaker for hybrid app commands.

# Let's change the reset time to 5 minutes instead of 1
# reset_after=datetime.timedelta(minutes=5) works too.
cordcutter = Cordcutter(bot.tree, reset_after=5)


# Define a test hybrid command
@bot.hybrid_command(name="test")
async def test_command(ctx: commands.Context):  # noqa: ANN201
    # since only application commands are supported, we need to check if the command was invoked by a slash command
    # if it was invoked by a slash command, ctx.interaction will be set, else it will be None
    if ctx.interaction is not None:
        raise RuntimeError("This command always fails!")

    # if it was not invoked by a slash command, we can just continue as normal
    await ctx.send("Prefix command invoked!")


# Let's set this function as the trip callback using the decorator
@cordcutter.on_tripped_call
async def on_tripped(interaction: discord.Interaction) -> None:
    # In a classic circuit breaker, this is where you would show the user a message,
    # that lets them know that the command is temporarily disabled.

    # You should avoid accessing a database or any other external resources here,
    # as that might be the reason why the breaker tripped in the first place.

    breaker_embed = discord.Embed(
        title="⚡ Breaker tripped!",
        description="This command is temporarily disabled due to encountering too many errors.",
        color=discord.Color.red(),
    )
    # Check if we can use interaction.response else followup
    # This is not part of cordcutter thus not required...
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=breaker_embed)
    else:
        await interaction.followup.send(embed=breaker_embed)


bot.run("...")
