from argparse import ArgumentParser, Namespace
import json

import uvicorn

from . import ThingServer, server_from_config


def parse_args(argv: list[str] | None = None) -> Namespace:
    """Process command line arguments for the server"""
    parser = ArgumentParser()
    parser.add_argument("-c", "--config", type=str, help="Path to configuration file")
    parser.add_argument("-j", "--json", type=str, help="Configuration as JSON string")
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


def serve_from_cli(argv: list[str] | None = None, dry_run=False):
    """Start the server from the command line"""
    args = parse_args(argv)
    config = config_from_args(args)
    server = server_from_config(config)
    assert isinstance(server, ThingServer)
    if dry_run:
        return server
    uvicorn.run(server.app, host=args.host, port=args.port)
