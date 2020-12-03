import contextlib
import asyncio
import discord
from discord.ext.commands import BadArgument, Converter
from ssl import CertificateError
from aiohttp import ClientConnectorError
import logging
import yaml

log = logging.getLogger(__name__)

with open("config-default.yml", encoding="UTF-8") as f:
    _CONFIG_YAML = yaml.safe_load(f)

class YAMLGetter(type):
    """
    Implements a custom metaclass used for accessing
    configuration data by simply accessing class attributes.
    Supports getting configuration from up to two levels
    of nested configuration through `section` and `subsection`.

    `section` specifies the YAML configuration section (or "key")
    in which the configuration lives, and must be set.

    `subsection` is an optional attribute specifying the section
    within the section from which configuration should be loaded.

    Example Usage:

        # config.yml
        bot:
            prefixes:
                direct_message: ''
                guild: '!'

        # config.py
        class Prefixes(metaclass=YAMLGetter):
            section = "bot"
            subsection = "prefixes"

        # Usage in Python code
        from config import Prefixes
        def get_prefix(bot, message):
            if isinstance(message.channel, PrivateChannel):
                return Prefixes.direct_message
            return Prefixes.guild
    """

    subsection = None

    def __getattr__(cls, name):
        name = name.lower()

        try:
            if cls.subsection is not None:
                return _CONFIG_YAML[cls.section][cls.subsection][name]
            return _CONFIG_YAML[cls.section][name]
        except KeyError:
            dotted_path = '.'.join(
                (cls.section, cls.subsection, name)
                if cls.subsection is not None else (cls.section, name)
            )
            log.critical(f"Tried accessing configuration variable at `{dotted_path}`, but it could not be found.")
            raise

    def __getitem__(cls, name):
        return cls.__getattr__(name)

    def __iter__(cls):
        """Return generator of key: value pairs of current constants class' config values."""
        for name in cls.__annotations__:
            yield name, getattr(cls, name)

class RedirectOutput(metaclass=YAMLGetter):
    section = 'redirect_output'

    delete_invocation: bool
    delete_delay: int

class ValidPythonIdentifier(Converter):
    """
    A converter that checks whether the given string is a valid Python identifier.
    
    This is used to have package names that correspond to how you would use the package in your
    code, e.g. `import package`.
    
    Raises `BadArgument` if the argument is not a valid Python identifier, and simply passes through
    the given argument otherwise.
    """

    @staticmethod
    async def convert(ctx: Context, argument: str) -> str:
        """Checks whether the given string is a valid Python identifier."""
        if not argument.isidentifier():
            raise BadArgument(f"`{argument}` is not a valid Python identifier")
        return argument

class ValidURL(Converter):
    """
    Represents a valid webpage URL.
  
    This converter checks whether the given URL can be reached and requesting it returns a status
    code of 200. If not, `BadArgument` is raised.
  
    Otherwise, it simply passes through the given URL.
    """

    @staticmethod
    async def convert(ctx: Context, url: str) -> str:
        """This converter checks whether the given URL can be reached with a status code of 200."""
        try:
            async with ctx.bot.session.get(url) as resp:
                if resp.status != 200:
                    raise BadArgument(
                        f"HTTP GET on `{url}` returned status `{resp.status}`, expected 200"
                    )
        except CertificateError:
            if url.startswith('https'):
                raise BadArgument(
                    f"Got a `CertificateError` for URL `{url}`. Does it support HTTPS?"
                )
            raise BadArgument(f"Got a `CertificateError` for URL `{url}`.")
        except ValueError:
            raise BadArgument(f"`{url}` doesn't look like a valid hostname to me.")
        except ClientConnectorError:
            raise BadArgument(f"Cannot connect to host with URL `{url}`.")
        return url

async def wait_for_deletion(bot, message, user_ids, deletion_emojis=('<:trashcan:780486554266501194>',), timeout=60 * 5, attach_emojis=True,):
    """
    Wait for up to `timeout` seconds for a reaction by any of the specified `user_ids` to delete the message.
    An `attach_emojis` bool may be specified to determine whether to attach the given
    `deletion_emojis` to the message in the given `context`.
    """
    if message.guild is None:
        raise ValueError("Message must be sent on a guild")

    if attach_emojis:
        for emoji in deletion_emojis:
            try:
                await message.add_reaction(emoji)
            except discord.NotFound:
                log.trace(f"Aborting wait_for_deletion: message {message.id} deleted prematurely.")
                return

    def check(reaction: discord.Reaction, user: discord.Member) -> bool:
        """Check that the deletion emoji is reacted by the appropriate user."""
        return (
            reaction.message.id == message.id
            and str(reaction.emoji) in deletion_emojis
            and user.id in user_ids
        )

    with contextlib.suppress(asyncio.TimeoutError):
        await bot.wait_for('reaction_add', check=check, timeout=timeout)
        await message.delete()