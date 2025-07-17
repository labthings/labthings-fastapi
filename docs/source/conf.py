# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "labthings-fastapi"
copyright = "2024, Richard Bowman"
author = "Richard Bowman"
release = "0.0.10"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.intersphinx",
    # "sphinx.ext.napoleon",
    # "autodoc2",
    "autoapi.extension",
    "sphinx_rtd_theme",
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

canonical_fq_names = [
    "labthings_fastapi.Thing",
    "labthings_fastapi.ThingProperty",
    "labthings_fastapi.ThingSetting",
    "labthings_fastapi.thing_property",
    "labthings_fastapi.thing_setting",
    "labthings_fastapi.thing_action",
    "labthings_fastapi.fastapi_endpoint",
    "labthings_fastapi.deps.outputs",
    "labthings_fastapi.deps.blob",
    "labthings_fastapi.deps.ThingServer",
    "labthings_fastapi.deps.cli",
    "labthings_fastapi.deps.ThingClient",
    "labthings_fastapi.deps.get_blocking_portal",
    "labthings_fastapi.deps.BlockingPortal",
    "labthings_fastapi.deps.InvocationID",
    "labthings_fastapi.deps.InvocationLogger",
    "labthings_fastapi.deps.CancelHook",
    "labthings_fastapi.deps.GetThingStates",
    "labthings_fastapi.deps.raw_thing_dependency",
    "labthings_fastapi.deps.direct_thing_client_dependency",
    "labthings_fastapi.deps.direct_thing_client_class",
    "labthings_fastapi.deps.DirectThingClient",
    "labthings_fastapi.descriptors.action.ActionDescriptor",
    "labthings_fastapi.outputs.blob.BlobDataManager",
    "labthings_fastapi.actions.invocation_model.InvocationModel",
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


def skip_public_api(app, what, name: str, obj, skip, options):
    """Skip documenting members that are re-exported from the public API."""
    parts = name.split(".")
    unqual = parts[-1]
    if unqual in canonical_names and name != canonical_names[unqual]:
        skip = True
        return skip
    return skip


def setup(sphinx):
    sphinx.connect("autoapi-skip-member", skip_public_api)
