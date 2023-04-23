# 🔌 Cordcutter

> ❗ This is a fork of a similar extension for Nextcord by [teaishealthy](https://github.com/teaishealthy)
> - [To Nextcord alternative](https://github.com/teaishealthy/cordcutter)

Cordcutter is a discord.py extension that implements the circuit breaker design pattern for application commands.

Cordcutter works by watching for errors in your application commands and once the error threshold is reached _(breaker tripped)_, it will disable the command for a set period of time. Once the cool-down period is over, the command will be re-enabled _(breaker reset)_.

Cordcutter currently does not implement an semi-stable circuit breaker (half-open / half-tripped state), but this is a planned feature.

For more information on the circuit breaker design pattern, see [this wikipedia article](https://en.wikipedia.org/wiki/Circuit_breaker_design_pattern).

## Installation

Cordcutter is currently in development and is not yet available on PyPI. You can install it from Git using pip:

```bash
python -m pip install git+https://github.com/LunarsDev/cordcutter.git
```

## Usage

Simply import the `Cordcutter` class from `cordcutter` and pass your `app_commands.CommandTree` instance to it.

```py
from cordcutter import Cordcutter
# <snip>
# tree: app_commands.CommandTree =...
cordcutter = Cordcutter(tree)
```
And set a callback for the breaker

```py
import discord

@cordcutter.on_tripped_call
async def trip_callback(interaction: discord.Interaction):
    ...
```

### Configuration

You can configure when the breaker trips and how long it stays tripped by passing the `threshold` and `reset_after` parameters to the `Cordcutter` constructor:

```py
Cordcutter(
    tree,
    threshold = 3,
    reset_after = timedelta(minutes=5)
)
```
See the [example.py](/example.py) file for more.
