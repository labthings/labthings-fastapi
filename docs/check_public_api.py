"""Check public API for completeness.

This module loads the intersphinx inventory, and checks that all the symbols from the
top-level module are present. This should prevent that page from going out of date.
"""

import sphobjinv as soi

import labthings_fastapi as lt

if __name__ == "__main__":
    inventory = soi.Inventory("build/html/objects.inv")

    if not inventory.project == "labthings-fastapi":
        raise AssertionError(f"The inventory is for {inventory.project} not LabThings!")

    published_lt_namespace = {}

    for object in inventory.objects:
        if object.name.startswith("lt.") and object.domain == "py":
            published_lt_namespace[object.name] = object

    missing = []

    for name in lt.__all__:
        if f"lt.{name}" not in published_lt_namespace:
            missing.append(name)

    if missing:
        msg = "Failure: the following symbols are missing from the `lt` namespace: \n\n"
        msg += "\n".join(missing)
        raise AssertionError(msg)
