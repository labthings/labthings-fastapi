"""A module that fails to import because of a missing import.

This is to help test ImportString error handling.
See test_server_config_model.py.
"""

from missing_module import missing_submodule

missing_submodule.missing_function()  # Stop Ruff flagging an unused import.
