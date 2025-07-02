import labthings_fastapi as lt
from labthings_fastapi.example_things import MyThing

MyThingDep = lt.deps.direct_thing_client_dependency(MyThing, "/mything/")


class TestThing(lt.Thing):
    """A test thing with a counter property and a couple of actions"""

    @lt.thing_action
    def increment_counter(self, my_thing: MyThingDep) -> None:
        """Increment the counter on another thing"""
        my_thing.increment_counter()


server = lt.ThingServer()
server.add_thing(MyThing(), "/mything/")
server.add_thing(TestThing(), "/testthing/")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(server.app, port=5000)
