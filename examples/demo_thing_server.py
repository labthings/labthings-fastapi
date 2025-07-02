import logging
import time
from typing import Optional, Annotated
from pydantic import Field
from fastapi.responses import HTMLResponse

import labthings_fastapi as lt

logging.basicConfig(level=logging.INFO)


class MyThing(lt.Thing):
    @lt.thing_action
    def anaction(
        self,
        repeats: Annotated[
            int, Field(description="The number of times to try the action")
        ],
        undocumented: int,
        title: Annotated[
            str, Field(description="the title of the invocation")
        ] = "Untitled",
        attempts: Annotated[
            Optional[list[str]],
            Field(
                description="Names for each attempt - I suggest final, Final, FINAL."
            ),
        ] = None,
    ) -> dict[str, str]:
        """Quite a complicated action

        This action has lots of parameters and is designed to confuse my schema
        generator. I hope it doesn't!

        I might even use some Markdown here:

        * If this renders, it supports lists
        * With at east two items.
        """
        # We should be able to call actions as normal Python functions
        self.increment_counter()
        return "finished!!"

    @lt.thing_action
    def increment_counter(self):
        """Increment the counter property

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @lt.thing_action
    def slowly_increase_counter(self):
        """Increment the counter slowly over a minute"""
        for i in range(60):
            time.sleep(1)
            self.increment_counter()

    counter = lt.ThingProperty[int](
        initial_value=0, readonly=True, description="A pointless counter"
    )

    foo = lt.ThingProperty[str](
        initial_value="Example",
        description="A pointless string for demo purposes.",
    )


thing_server = lt.ThingServer()
my_thing = MyThing()
td = my_thing.thing_description()
my_thing.validate_thing_description()
thing_server.add_thing(my_thing, "/my_thing")

app = thing_server.app


html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/my_thing/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""

"""
{"messageType":"addPropertyObservation","data":{"foo":true, "counter":true}}
{"messageType":"addActionObservation","data":{"increment_counter":true}}
"""


@app.get("/wsclient", tags=["websockets"])
async def get():
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
