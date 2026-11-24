"""Generate client code for the example Things.

This file regenerates the example client code.
Keeping the expected client code in the repository ensures that any changes
to the generated code get noticed.
"""

from pathlib import Path

import thing_with_simple_types

from labthings_fastapi.code_generation import write_client_module
from labthings_fastapi.testing import create_thing_without_server

if __name__ == "__main__":
    here = Path(__file__).parent
    thing = create_thing_without_server(thing_with_simple_types.SimpleTypeThing)
    td = thing.thing_description()
    write_client_module(td, str(here / "thing_with_simple_types_client_ruff.py"))
    write_client_module(
        td, str(here / "thing_with_simple_types_client_noruff.py"), use_ruff=False
    )
