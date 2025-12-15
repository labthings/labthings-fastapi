"""A module that can't be imported due to a runtimeerror.

This is to help test ImportString error handling.
See test_server_config_model.py.
"""

raise RuntimeError("This module should not be importable!")
