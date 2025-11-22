import logging
import labthings_fastapi
import importlib.metadata

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "labthings-fastapi"
copyright = "2025, Richard Bowman"
author = "Richard Bowman"
release = importlib.metadata.version("labthings-fastapi")

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.intersphinx",
    # "sphinx.ext.napoleon",
    # "autodoc2",
    "autoapi.extension",
    "sphinx_rtd_theme",
    "sphinx_toolbox.decorators",
]

templates_path = ["_templates"]
exclude_patterns = []

default_role = "py:obj"

# autodoc2_packages = ["../../src/labthings_fastapi"]
# autodoc2_render_plugin = "myst"
# autodoc2_class_docstring = "both"

autoapi_dirs = ["../../src/labthings_fastapi"]
autoapi_generate_api_docs = True
autoapi_keep_files = True
autoapi_python_class_content = "both"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
# html_static_path = ["_static"]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
    "anyio": ("https://anyio.readthedocs.io/en/stable/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "jsonschema": ("https://python-jsonschema.readthedocs.io/en/stable/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}

# The next section deals with skipping names. Because various modules import
# symbols with `from x import y`, those symbols are duplicated by apidoc.
# The logic below defines a function that skips functions we've pulled into
# the public API, and functions that are used elsewhere, to ensure they
# are documented exactly once, at the fully qualified name specified.

skipper_log = logging.getLogger("skipper")
skipper_log.addHandler(logging.FileHandler("./skipper.log", mode="w"))
skipper_log.setLevel(logging.DEBUG)

convenience_modules = {
    "labthings_fastapi": labthings_fastapi.__all__,
    "labthings_fastapi.deps": labthings_fastapi.deps.__all__,
}
canonical_fq_names = [
    "labthings_fastapi.descriptors.action.ActionDescriptor",
    "labthings_fastapi.outputs.blob.BlobDataManager",
    "labthings_fastapi.invocations.InvocationModel",
    "labthings_fastapi.outputs.MJPEGStream",
    "labthings_fastapi.outputs.MJPEGStreamDescriptor",
    "labthings_fastapi.outputs.blob.BlobIOContextDep",
    "labthings_fastapi.actions.ActionManager",
    "labthings_fastapi.descriptors.endpoint.EndpointDescriptor",
    "labthings_fastapi.dependencies.invocation.invocation_logger",
    "labthings_fastapi.utilities.introspection.EmptyObject",
]


def unqual(name):
    if "." in name:
        return name.split(".")[-1]
    return name


canonical_names = {unqual(n): n for n in canonical_fq_names}

skipper_log.info("Convenience modules: %s.", convenience_modules)


def skip_public_api(app, what, name: str, obj, skip, options):
    """Skip documenting members that are re-exported from the public API."""
    parts = name.split(".")
    unqual = parts[-1]
    if unqual in canonical_names and name != canonical_names[unqual]:
        skip = True
        return skip
    for conv, all in convenience_modules.items():
        if unqual in all and name != f"{conv}.{unqual}":
            skipper_log.warning(f"skipping {name}")
            skip = True
    return skip


def setup(sphinx):
    sphinx.connect("autoapi-skip-member", skip_public_api)
