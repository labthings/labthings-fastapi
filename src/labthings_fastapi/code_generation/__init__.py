from inspect import cleandoc
import re
from typing import Sequence

from labthings_fastapi.thing_description.model import (
    DataSchema,
    ThingDescription,
    Type,
)


def title_to_snake_case(title: str) -> str:
    """Convert text to snake_case"""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "_".join(words)


def snake_to_camel_case(snake: str) -> str:
    """Convert snake_case to CamelCase"""
    words = snake.split("_")
    return "".join(word.capitalize() for word in words)


def title_to_camel_case(title: str) -> str:
    """Convert text to CamelCase"""
    return snake_to_camel_case(title_to_snake_case(title))


def clean_code(code: str, prefix: str = "") -> str:
    """Clean up code by removing leading/trailing whitespace and empty lines"""
    lines = cleandoc(code).split("\n")
    return "\n".join([prefix + l for l in lines])


def quoted_docstring(docstring: str, indent: int = 4) -> str:
    """Wrap a docstring in triple quotes"""
    prefix = " " * indent
    lines = docstring.split("\n")
    lines[0] = f'"""{lines[0]}'
    lines.append('"""')
    return "".join([f"{prefix}{line}\n" for line in lines])


def dataschema_to_type(schema: DataSchema) -> str:
    """Convert a DataSchema to a Python type"""
    if isinstance(schema.oneOf, Sequence) and len(schema.oneOf) > 0:
        types = [dataschema_to_type(s) for s in schema.oneOf]
        return f"Union[{", ".join(types)}]"
    if schema.type == Type.string:
        return "str"
    elif schema.type == Type.integer:
        return "int"
    elif schema.type == Type.number:
        return "float"
    elif schema.type == Type.boolean:
        return "bool"
    elif schema.type == Type.array:
        if schema.items is None:
            return "list"
        return f"list[{dataschema_to_type(schema.items)}]"
    elif schema.type == Type.object:
        return "dict[str, Any]"
    else:
        return "Any"

def property_to_argument(
        name: str,
        property: DataSchema,
    ) -> str:
    """Convert a property to a function argument"""
    dtype = dataschema_to_type(property)
    arg = f"{name}: {dtype}"
    if "default" in property.model_fields_set:
        if property.default is None:
            arg += " = None"
        elif isinstance(property.default, str):
            arg += f' = "{property.default}"'
        elif (
            isinstance(property.default, bool)
            or isinstance(property.default, int)
            or isinstance(property.default, float)
        ):
            arg += f" = {property.default}"
        else:
            raise NotImplementedError(f"Unsupported default value: {property.default}")
    return arg


def input_model_to_arguments(model: DataSchema) -> list[str]:
    """Convert an input model to a list of arguments"""
    if model.type is None:
        return []
    if model.type != Type.object:
        print(f"model.type: {model.type}")
        raise NotImplementedError("Only object models are supported")
    if not model.properties:
        return []
    args = []
    if model.required:
        for name in model.required:
            property = model.properties[name]
            args.append(
                property_to_argument(name, property)
            )
    for name, property in model.properties.items():
        if model.required and name in model.required:
            continue
        args.append(property_to_argument(name, property))
        if "=" not in args[-1]:
            args[-1] += " = ..."
    return args


def generate_client(thing_description: ThingDescription) -> str:
    """Generate a client from a Thing Description"""
    code = (
        "from labthings_fastapi.client import ThingClient\n"
        "from typing import Any, Union\n"
        "\n"
    )
    class_name = title_to_camel_case(thing_description.title)
    code += f"class {class_name}Client(ThingClient):\n"
    code += f'    """A client for the {thing_description.title} Thing"""\n\n'
    for name, property in thing_description.properties.items():
        pname = title_to_snake_case(name)
        dtype = dataschema_to_type(property)
        code += "    @property\n"
        code += f"    def {pname}(self) -> {dtype}:\n"
        code += quoted_docstring(property.description, indent=8)
        code += f'        return self.get_property("{name}")\n\n'

        if not property.readOnly:
            code += clean_code(
                f'''
                @{pname}.setter
                def {pname}(self, value: {dtype}):
                    self.set_property("{name}", value)
                ''',
                prefix = "    ",
            ) + "\n\n"
    
    for name, action in thing_description.actions.items():
        aname = title_to_snake_case(name)
        args = input_model_to_arguments(action.input)
        output_type = dataschema_to_type(action.output)
        code += f"    def {aname}(\n"
        code += "        self,\n"
        for arg in args:
            code += f"        {arg},\n"
        code += "        **kwargs\n"
        code += f"    ) -> {output_type}:\n"
        code += quoted_docstring(action.description, indent=8)
        for arg in args:
            k = arg.split(":")[0].strip()
            if arg.endswith("..."):
                code += clean_code(
                    f"""
                    if {k} is not ...:
                        kwargs[{k}] = {k}
                    """,
                    prefix = "        ",
                ) + "\n"
            else:
                code += f"        kwargs[{k}] = {k}\n"
        code += f'        return self.invoke_action("{name}", **kwargs)\n\n'

    return code

