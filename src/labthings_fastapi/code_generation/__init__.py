from inspect import cleandoc
import re
from typing import Optional, Sequence

from labthings_fastapi.thing_description.model import (
    DataSchema,
    ThingDescription,
    Type,
)


def title_to_snake_case(title: str) -> str:
    """Convert text to snake_case"""
    # First, look for CamelCase so it doesn't get ignored:
    uncameled = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", title)
    words = re.findall(r"[a-zA-Z0-9]+", uncameled)
    return "_".join(w.lower() for w in words)


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


def quoted_docstring(docstring: Optional[str], indent: int = 4) -> str:
    """Wrap a docstring in triple quotes"""
    if docstring is None:
        return ""
    prefix = " " * indent
    lines = docstring.split("\n")
    lines[0] = f'"""{lines[0]}'
    lines.append('"""')
    return "".join([f"{prefix}{line}\n" for line in lines])


def dataschema_to_type(schema: DataSchema, models: dict[str, str], name: str = "anonymous") -> str:
    """Convert a DataSchema to a Python type"""
    if isinstance(schema.oneOf, Sequence) and len(schema.oneOf) > 0:
        types = [dataschema_to_type(s, models) for s in schema.oneOf]
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
        if isinstance(schema.items, Sequence):
            types = [dataschema_to_type(s, models) for s in schema.items]
            return f"tuple[{', '.join(types)}]"
        return f"list[{dataschema_to_type(schema.items, models)}]"
    elif schema.type == Type.object:
        # If the object has no properties, return a generic dict
        if not schema.properties:
            return "dict[str, Any]"
        # Objects with properties are converted to Pydantic models
        if schema.title:
            model_name = title_to_camel_case(schema.title + "_model")
        else:
            model_name = snake_to_camel_case(name + "_model")
        if model_name in models:
            i = 0
            while f"{model_name}_{i}" in models:
                i += 1
            model_name = f"{model_name}_{i}"
        models[model_name] = "# placeholder"
        models[model_name] = dataschema_to_model(schema, models, model_name)
        return model_name
    else:
        return "Any"
    
def dataschema_to_model(schema: DataSchema, models: dict[str, str], name: str) -> str:
    """Convert a DataSchema to a Pydantic model"""
    code = f"class {name}(BaseModel):\n"
    for pname, property in schema.properties.items():
        code += "    " + property_to_argument(pname, property, models) + "\n"
    code += (
        "\n"
        "    class Config:\n"
        "        extra = 'allow'\n"
    )
    return code


def property_to_argument(
        name: str,
        property: DataSchema,
        models: dict[str, str] = None,
    ) -> str:
    """Convert a property to a function argument"""
    dtype = dataschema_to_type(property, models, name)
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


def input_model_to_arguments(model: DataSchema, models) -> list[str]:
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
                property_to_argument(name, property, models)
            )
    for name, property in model.properties.items():
        if model.required and name in model.required:
            continue
        args.append(property_to_argument(name, property, models))
        if "=" not in args[-1]:
            args[-1] += " = ..."
    return args


def generate_client(thing_description: ThingDescription) -> str:
    """Generate a client from a Thing Description"""
    code = (
        "from labthings_fastapi.client import ThingClient\n"
        "from typing import Any, Union\n"
        "from pydantic import BaseModel\n"
        "\n"
        "\n"
        "# Model definitions\n"  # will be replaced at the end
        "\n"
        "\n"
    )
    models: dict[str, str] = {}
    class_name = title_to_camel_case(thing_description.title)
    code += f"class {class_name}Client(ThingClient):\n"
    code += f'    """A client for the {thing_description.title} Thing"""\n\n'
    for name, property in thing_description.properties.items():
        pname = title_to_snake_case(name)
        dtype = dataschema_to_type(property, models=models)
        code += "    @property\n"
        code += f"    def {pname}(self) -> {dtype}:\n"
        code += quoted_docstring(property.description, indent=8)
        code += f"        val = self.get_property(\"{name}\")\n"
        if dtype in models:
            # If we've defined a model, convert it
            code += f"        return {dtype}(**val)\n\n"
        else:
            code += "        return val\n\n"

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
        args = input_model_to_arguments(action.input, models)
        output_type = dataschema_to_type(action.output, models)
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
        code += f'        result = self.invoke_action("{name}", **kwargs)\n'
        if output_type in models:
            code += f"        return {output_type}(**result)\n\n"
        else:
            code += "        return result\n\n"

    # Include the model definitions
    code = code.replace("# Model definitions", "\n\n".join(models.values()))

    return code

