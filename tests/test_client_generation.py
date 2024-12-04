import os
import tempfile
import importlib.util

from labthings_fastapi.code_generation import generate_client
from labthings_fastapi.example_things import MyThing


def test_client_generation():
    td = MyThing().thing_description()
    code = generate_client(td)
    with tempfile.TemporaryDirectory() as d:
        fname = os.path.join(d,"client.py")
        with open(fname, "w") as f:
            f.write(code)
        spec = importlib.util.spec_from_file_location("client", f.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    assert "MyThingClient" in dir(module)
    
if __name__ == "__main__":
    td = MyThing().thing_description()
    print("Thing Description:")
    print(td.model_dump_json(indent=2, exclude_unset=True))
    print("\nGenerated Client:")
    print(generate_client(td))
