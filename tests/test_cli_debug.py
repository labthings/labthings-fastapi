import logging
from labthings_fastapi.server.cli import serve_from_cli
from labthings_fastapi.logs import THING_LOGGER


def test_cli_debug_flag():
    """
    Test that using the --debug flag sets the logger level to DEBUG,
    and that not using it leaves the logger level at INFO.
    """
    # Reset logger level to NOTSET
    THING_LOGGER.setLevel(logging.NOTSET)

    # Run without --debug
    # We use dry_run=True to avoid starting uvicorn
    # We need a dummy config
    dummy_json = '{"things": {}}'
    serve_from_cli(["--json", dummy_json], dry_run=True)

    assert THING_LOGGER.level == logging.INFO

    # Reset logger level
    THING_LOGGER.setLevel(logging.NOTSET)

    # Run with --debug
    serve_from_cli(["--json", dummy_json, "--debug"], dry_run=True)

    assert THING_LOGGER.level == logging.DEBUG

    # Reset logger level to NOTSET
    THING_LOGGER.setLevel(logging.NOTSET)
