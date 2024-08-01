from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.file_manager import FileManagerDep
from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from temp_client import poll_task, get_link


class FileThing(Thing):
    @thing_action
    def write_message_file(
        self,
        file_manager: FileManagerDep,
        message: str = "Hello World",
    ) -> dict[str, str]:
        """Write a message to a file."""
        # We should be able to call actions as normal Python functions
        with open(file_manager.path("message.txt", rel="message_file"), "w") as f:
            f.write(message)
        with open(file_manager.path("message2.txt"), "w") as f:
            f.write(message)
        return {"filename": "message.txt"}


thing = FileThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def test_td_validates():
    thing.validate_thing_description()


def test_action_output():
    client = TestClient(server.app)
    r = client.post("/thing/write_message_file", json={})
    invocation = poll_task(client, r.json())
    assert invocation["status"] == "completed"
    assert invocation["output"] == {"filename": "message.txt"}
    r = client.get(get_link(invocation, "message_file")["href"])
    assert r.status_code == 200
    assert r.text == "Hello World"


if __name__ == "__main__":
    test_td_validates()
    test_action_output()
