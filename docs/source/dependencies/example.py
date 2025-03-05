from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.dependencies.thing import direct_thing_client_dependency
from labthings_fastapi.example_things import MyThing
from labthings_fastapi.server import ThingServer

MyThingDep = direct_thing_client_dependency(MyThing, "/mything/")

class TestThing(Thing):
    """A test thing with a counter property and a couple of actions"""

    @thing_action
    def increment_counter(self, my_thing: MyThingDep) -> None:
        """Increment the counter on another thing"""
        my_thing.increment_counter()

server = ThingServer()
server.add_thing(MyThing(), "/mything/")
server.add_thing(TestThing(), "/testthing/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(server.app, port=5000)