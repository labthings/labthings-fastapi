"""Command-line interface to the `.ThingServer`.

This module provides a command-line interface that is provided as
`labthings-server`. It exposes various functions that may be useful to
projects based on LabThings, if they wish to expose their own CLI.

.. note::

    In principle, LabThings may be run as an ASGI application wrapped
    by a more advanced HTTP server providing HTTPS or other features.
    This generally requires configuration via environment variables
    rather than command-line flags.

    Environment variables are not yet supported, but may supplement
    or replace the command line interface in the future.

For examples of how to run the server from the command line, see
the tutorial page :ref:`tutorial_running`.
"""

from argparse import ArgumentParser, Namespace
import sys
from typing import Optional

from pydantic import ValidationError
import uvicorn

from . import ThingServer
from . import fallback
from .config_model import ThingServerConfig, ThingImportFailure


def get_default_parser() -> ArgumentParser:
    """Return the default CLI parser for LabThings.

    This can be used to add more arguments, for custom CLIs that make use of
    LabThings.

    :return: an `argparse.ArgumentParser` set up with the options for
        ``labthings-server``.
    """
    parser = ArgumentParser()
    parser.add_argument("-c", "--config", type=str, help="Path to configuration file")
    parser.add_argument("-j", "--json", type=str, help="Configuration as JSON string")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Serve an error page instead of exiting, if we can't start.",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Bind socket to this host"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Bind socket to this port. If 0, an available port will be picked.",
    )
    return parser


def parse_args(argv: Optional[list[str]] = None) -> Namespace:
    r"""Process command line arguments for the server.

    The arguments are defined in `.get_default_parser`\ .

    :param argv: command line arguments (defaults to arguments supplied
        to the current command).

    :return: a namespace with the extracted options.
    """
    parser = get_default_parser()
    # Use parser to parse CLI arguments and return the namespace with attributes set.
    return parser.parse_args(argv)


def config_from_args(args: Namespace) -> ThingServerConfig:
    """Load the configuration from a supplied file or JSON string.

    This function will first attempt to load a JSON file specified in the
    command line argument. It will then look for JSON configuration supplied
    as a string.

    If both a file and a string are specified, the JSON string will be used
    to ``update`` the configuration loaded from file, i.e. it will overwrite
    keys in the file.

    :param args: Parsed arguments from `.parse_args`.

    :return: the server configuration.

    :raise FileNotFoundError: if the configuration file specified is missing.
    :raise RuntimeError: if neither a config file nor a string is provided.
    """
    if args.config:
        if args.json:
            raise RuntimeError("Can't use both --config and --json simultaneously.")
        try:
            with open(args.config) as f:
                return ThingServerConfig.model_validate_json(f.read())
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Could not find configuration file {args.config}"
            ) from e
    elif args.json:
        return ThingServerConfig.model_validate_json(args.json)
    else:
        raise RuntimeError("No configuration (or empty configuration) provided")


def serve_from_cli(
    argv: Optional[list[str]] = None, dry_run: bool = False
) -> ThingServer | None:
    r"""Start the server from the command line.

    This function will parse command line arguments, load configuration,
    set up a server, and start it. It calls `.parse_args`,
    `.config_from_args` and `.ThingServer.from_config` to get a server, then
    starts `uvicorn` to serve on the specified host and port.

    If the ``fallback`` argument is specified, errors that stop the
    LabThings server from starting will be handled by starting a simple
    HTTP server that shows an error page. This behaviour may be helpful
    if ``labthings-server`` is being run on a headless server, where
    an HTTP error page is more useful than no response.

    If ``fallback`` is not specified, we will print the error and exit.

    :param argv: command line arguments (defaults to arguments supplied
        to the current command).
    :param dry_run: may be set to ``True`` to terminate after the server
        has been created. This tests set-up code and verifies all of the
        Things specified can be correctly loaded and instantiated, but
        does not start `uvicorn`\ .

    :return: the `.ThingServer` instance created, if ``dry_run`` is ``True``.

    :raise BaseException: if the server cannot start, and the ``fallback``
        option is not specified.
    """
    args = parse_args(argv)
    try:
        config, server = None, None
        config = config_from_args(args)
        server = ThingServer.from_config(config)
        if dry_run:
            return server
        uvicorn.run(server.app, host=args.host, port=args.port)
    except BaseException as e:
        if args.fallback:
            print(f"Error: {e}")
            print("Starting fallback server.")
            app = fallback.app
            app.labthings_config = config
            app.labthings_server = server
            app.labthings_error = e
            uvicorn.run(app, host=args.host, port=args.port)
        else:
            if isinstance(e, (ValidationError, ThingImportFailure)):
                print(f"Error reading LabThings configuration:\n{e}")
                sys.exit(3)
            else:
                raise e
    return None  # This is required as we sometimes return the server
