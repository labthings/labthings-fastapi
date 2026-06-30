import ast
import importlib.util
import os
import tempfile

from pydantic import BaseModel

import labthings_fastapi as lt
import labthings_fastapi.code_generation as cg
from labthings_fastapi.code_generation import (
    generate_client_ast,
    generate_client_class,
)
from labthings_fastapi.example_things import MyThing
from labthings_fastapi.testing import create_thing_without_server


def test_title_to_snake_case():
    assert cg.title_to_snake_case("CamelCase") == "camel_case"
    assert cg.title_to_snake_case("Camel") == "camel"
    assert cg.title_to_snake_case("camel") == "camel"
    assert cg.title_to_snake_case("CAMEL") == "camel"
    assert cg.title_to_snake_case("CamelCASE") == "camel_case"


def test_snake_to_camel_case():
    assert cg.snake_to_camel_case("snake_case") == "SnakeCase"
    assert cg.snake_to_camel_case("snake") == "Snake"
    assert cg.snake_to_camel_case("SNAKE") == "Snake"
    assert cg.snake_to_camel_case("snakeCASE_word") == "SnakecaseWord"


def generate_and_verify(thing):
    td = create_thing_without_server(thing).thing_description()
    cls_name, tree = generate_client_ast(td)
    ast.fix_missing_locations(tree)
    code = ast.unparse(tree)
    with tempfile.TemporaryDirectory() as d:
        fname = os.path.join(d, "client.py")
        with open(fname, "w") as f:
            f.write(code)
        spec = importlib.util.spec_from_file_location(
            f"labthings_fastapi.generated_client.{cls_name}", f.name
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    assert cls_name in dir(module)
    cls = getattr(module, cls_name)
    assert issubclass(cls, lt.ThingClient)


def test_mything_generation():
    generate_and_verify(MyThing)


class SimpleModel(BaseModel):
    a: int
    b: str


class NestedModel(BaseModel):
    c: SimpleModel


class ThingWithModels(lt.Thing):
    @lt.property
    def prop1(self) -> SimpleModel:
        return SimpleModel(a=1, b="test")

    @lt.action
    def action1(self, arg1: SimpleModel) -> SimpleModel:
        return arg1

    @lt.property
    def prop2(self) -> NestedModel:
        return NestedModel(c=SimpleModel(a=1, b="test"))


def test_with_models():
    generate_and_verify(ThingWithModels)


if __name__ == "__main__":
    td = create_thing_without_server(ThingWithModels).thing_description()
    print("Thing Description:")
    print(td.model_dump_json(indent=2, exclude_unset=True))
    print("\nGenerated AST:")
    _, ast_module = generate_client_ast(td)
    print(ast.dump(ast_module, indent=4))
    print("\nGenerated module:")
    print(ast.unparse(ast_module))
    with open("scratch/generated_client_test.py", "w") as f:
        f.write(ast.unparse(ast_module))
    cls = generate_client_class(td)
