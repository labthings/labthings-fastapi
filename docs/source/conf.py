# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'labthings-fastapi'
copyright = '2024, Richard Bowman'
author = 'Richard Bowman'
release = '0.0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx.ext.intersphinx",
    #"sphinx.ext.napoleon",
    "autodoc2",
    "sphinx_rtd_theme",
]

templates_path = ['_templates']
exclude_patterns = []

autodoc2_packages = ["../../src/labthings_fastapi"]
autodoc2_render_plugin = "myst"

#autoapi_dirs = ["../../src/labthings_fastapi"]
#autoapi_ignore = []
#autoapi_generate_api_docs = True
#autoapi_keep_files = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
}