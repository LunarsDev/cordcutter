from __future__ import annotations

import asyncio
import datetime
import functools
from collections import defaultdict
from inspect import iscoroutinefunction
from logging import getLogger
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional, Union

from discord.ext import commands as _ext_commands

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

    from discord import Interaction
    from discord.app_commands import AppCommandError, Command, CommandTree, ContextMenu
    from discord.app_commands.commands import CommandCallback as _CommandCallback
    from discord.app_commands.commands import ContextMenuCallback as _ContextMenuCallback
    from discord.ext.commands.hybrid import HybridAppCommand as _HybridAppCommand  # type: ignore[reportMissingTypeStubs] # not gonna create stubs for this one thing

    _HybridAppCommandCallback: TypeAlias = Callable[[_ext_commands.Context[Any]], Any]
    CommandCallbackT: TypeAlias = Union[
        _CommandCallback[Any, ..., Any],
        _ContextMenuCallback,
        _HybridAppCommandCallback,
    ]
    AppCommand: TypeAlias = Union[Command[Any, ..., Any], ContextMenu, _HybridAppCommand[Any, ..., Any]]
    BreakerCallbackT: TypeAlias = Callable[[Interaction[Any]], Coroutine[Any, Any, Any]]


logger = getLogger(__name__)


class Cordcutter:
    """Cordcutter implements the circuit breaker design pattern for discord.py bot using application commands.

    Parameters
    -----------
    command_tree: :class:`~discord.app_commands.CommandTree`
        The Command Tree instance to get application command information from.
    threshold: :class:`int`
        How many errors may occur before the command breaker trips. Defaults to ``3``.
    reset_after: Union[:class:`datetime.timedelta`, int]
        After what time the command breaker should reset. Defaults to ``timedelta(minutes=1)``.
        Integer is passed to ``timedelta(minutes=)``
    trip_callback: Optional[Callable[:class:`~discord.Interaction`, Coroutine[Any, Any, Any]]]
        The function to call when the command breaker is tripped.
        This can also be set via the ``on_tripped_call`` decorator.

    Attributes
    -----------
    threshold: :class:`int`
        How many errors may occur before the command breaker trips.
    tripped_at: Optional[:class:`datetime.datetime`]
        The time the breaker tripped at.

    """

    def __init__(
        self,
        command_tree: CommandTree[Any],
        *,
        threshold: int = 3,
        reset_after: Optional[Union[int, datetime.timedelta]] = None,
        trip_callback: Optional[BreakerCallbackT] = None,
        hybrid_app_command: bool = True,
    ) -> None:
        self._original_tree_on_error = command_tree.on_error
        command_tree.on_error = self._tree_on_error

        self._original_on_command_error = None
        if hybrid_app_command:
            if issubclass(command_tree.client.__class__, _ext_commands.Bot):
                self._original_on_command_error = command_tree.client.on_command_error
                command_tree.client.on_command_error = self._on_hybridcommand_on_error
            else:
                logger.debug("hybrid_app_command is True, but client is not a discord.ext.commands.Bot. Ignoring...")

        self.threshold: int = threshold
        self.reset_after = reset_after
        self.trip_callback = trip_callback
        self.errors: defaultdict[AppCommand, int] = defaultdict(int)

        self.tripped_at: Optional[datetime.datetime] = None

    @property
    def reset_after(self) -> datetime.timedelta:
        """:class:`datetime.timedelta`: After what time the command breaker should reset."""
        return self._reset_after

    @reset_after.setter
    def reset_after(self, time: Optional[Union[datetime.timedelta, int]]) -> None:
        if time is None:
            self._reset_after = datetime.timedelta(minutes=1)
        elif not isinstance(time, datetime.timedelta):
            self._reset_after = datetime.timedelta(minutes=time)
        else:
            self._reset_after = time

    @property
    def trip_callback(self) -> Optional[BreakerCallbackT]:
        """The function to call when the breaker is tripped."""
        return self._trip_callback

    @trip_callback.setter
    def trip_callback(self, callback: Optional[BreakerCallbackT]) -> None:
        if callback is None:
            return

        if not iscoroutinefunction(callback):
            raise TypeError("Callback must be a coroutine function.")

        self._trip_callback = callback

    async def _tree_on_error(self, interaction: Interaction[Any], error: AppCommandError) -> None:
        # call the handler
        await self.handle_cutter(interaction, error)
        # call the original handler
        return await self._original_tree_on_error(interaction, error)

    async def _on_hybridcommand_on_error(
        self,
        ctx: _ext_commands.Context[Any],
        error: _ext_commands.HybridCommandError,
    ) -> None:
        # check if hybrid app command callback
        if (interaction := ctx.interaction) is not None:
            # call the handler
            await self.handle_cutter(interaction, error)

        # call the original handler
        if self._original_on_command_error:
            return await self._original_on_command_error(ctx, error)

        return None

    # This hack seems to fix the CommandSignatureMismatch error from being raised by discord.py
    def __wrap_trip_callback(self, command_callback: CommandCallbackT, binding: Optional[Any], /) -> Callable[..., Any]:
        @functools.wraps(command_callback)  # type: ignore[PylancereportGeneralTypeIssues]
        async def wrapper(*args: Any, **_: Any) -> None:
            interaction_arg: Union[Interaction, _ext_commands.Context[Any]] = args[0] if binding else args[1]
            if isinstance(interaction_arg, _ext_commands.Context):
                if not (interaction := interaction_arg.interaction):
                    raise TypeError("Only application commands are supported.")

                interaction_arg = interaction

            if self.trip_callback:
                return await self.trip_callback(interaction_arg)
            return None

        return wrapper

    async def handle_cutter(
        self,
        interaction: Union[Interaction[Any], _ext_commands.Context[Any]],
        error: Union[AppCommandError, _ext_commands.HybridCommandError],  # noqa: ARG002
    ) -> None:
        """The handler for CordCutter.

        Parameters
        -----------
        interaction: :class:`~discord.Interaction`
            The interaction that is being handled.
        error: :exc:`AppCommandError`
            The exception that was raised.
        """
        if isinstance(interaction, _ext_commands.Context):
            if (ctx_interaction := interaction.interaction) is None:
                raise TypeError("Only application commands are supported.")

            interaction = ctx_interaction

        command = interaction.command
        if not command:
            return

        # Breaker has already tripped
        if self.errors.get(command, 0) >= self.threshold:
            return

        self.errors[command] += 1

        if self.errors[command] >= self.threshold:
            await self.tripped_breaker(command)

    async def tripped_breaker(self, command: AppCommand) -> None:
        """Trips a command breaker.

        Parameters
        ----------
        command: Union[:class:`discord.app_commands.Command`, :class:`discord.app_commands.ContextMenu`]
            The command to trip the breaker for.
        """
        logger.warning("[cordcutter] 🔌 Breaker tripped for %s!", command.qualified_name)

        if not self.trip_callback:
            logger.warning("[cordcutter] An on_tripped_call cannot be found. Doing nothing.")
            return

        self.tripped_at = datetime.datetime.now(tz=datetime.timezone.utc)
        original_callback: CommandCallbackT = command.callback
        command._callback = self.__wrap_trip_callback(  # noqa: SLF001 # type: ignore[ReportPrivateUsage] # can't do anything about this
            original_callback,
            getattr(command, "binding", None),
        )

        asyncio.get_event_loop().call_later(
            self.reset_after.total_seconds(),
            self.reset_breaker,
            command,
            original_callback,
        )

    def reset_breaker(self, command: AppCommand, original_callback: CommandCallbackT) -> None:
        """Reset the breaker for a command.

        Parameters
        ----------
        command: Union[:class:`discord.app_commands.Command`, :class:`discord.app_commands.ContextMenu`]
            The command to reset the breaker for.
        original_callback: Any
            The original callback of the command.
        """
        logger.warning("[cordcutter] 🔌 Breaker reset for %s!", command.qualified_name)

        self.tripped_at = None
        command._callback = original_callback  # type: ignore[reportGeneralTypeIssues] # noqa: SLF001
        self.errors.pop(command, None)

    def on_tripped_call(self, callback: BreakerCallbackT) -> BreakerCallbackT:
        """The callback to call when a command breaker trips.

        Parameters
        ----------
        callback: Callable[:class:`~discord.Interaction`, Coroutine[Any, Any, Any]]
            The callback to call.

        Returns
        -------
        Callable[:class:`~discord.Interaction`, Coroutine[Any, Any, Any]]
            The callback that was passed in.
        """
        self.trip_callback = callback
        return callback
