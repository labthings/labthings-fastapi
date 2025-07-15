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
    "myst_parser",
    "sphinx.ext.intersphinx",
    # "sphinx.ext.napoleon",
    "autodoc2",
    "sphinx_rtd_theme",
]

templates_path = ["_templates"]
exclude_patterns = []

default_role = "py:obj"

autodoc2_packages = ["../../src/labthings_fastapi"]
# autodoc2_render_plugin = "myst"
autodoc2_class_docstring = "both"

# autoapi_dirs = ["../../src/labthings_fastapi"]
# autoapi_ignore = []
# autoapi_generate_api_docs = True
# autoapi_keep_files = True

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
}

myst_enable_extensions = ["fieldlist"]
