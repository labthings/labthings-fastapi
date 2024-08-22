from argparse import ArgumentParser, Namespace
from typing import Optional
import json

from labthings_fastapi.utilities.object_reference_to_object import (
    object_reference_to_object,
)
import uvicorn

from . import ThingServer, server_from_config


def parse_args(argv: Optional[list[str]] = None) -> Namespace:
    """Process command line arguments for the server"""
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
    args = parser.parse_args(argv)
    return args


def config_from_args(args: Namespace) -> dict:
    """Process arguments and return a config dictionary"""
    if args.config:
        try:
            with open(args.config) as f:
                config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Could not find configuration file {args.config}")
    else:
        config = {}
    if args.json:
        config.update(json.loads(args.json))

    if len(config) == 0:
        raise RuntimeError("No configuration (or empty configuration) provided")

    return config


def serve_from_cli(argv: Optional[list[str]] = None, dry_run=False):
    """Start the server from the command line"""
    args = parse_args(argv)
    try:
        config, server = None, None
        config = config_from_args(args)
        server = server_from_config(config)
        assert isinstance(server, ThingServer)
        if dry_run:
            return server
        uvicorn.run(server.app, host=args.host, port=args.port)
    except BaseException as e:
        if args.fallback:
            print(f"Error: {e}")
            fallback_server = "labthings_fastapi.server.fallback:app"
            print(f"Starting fallback server {fallback_server}.")
            app = object_reference_to_object(fallback_server)
            app.labthings_config = config
            app.labthings_server = server
            app.labthings_error = e
            uvicorn.run(app, host=args.host, port=args.port)
        else:
            raise e
