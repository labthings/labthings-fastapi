import logging
import time
from typing import Optional, Annotated
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.thing_server import ThingServer
from labthings_fastapi.descriptors import PropertyDescriptor
from pydantic import Field

logging.basicConfig(level=logging.INFO)

class DummyCamera(Thing):
    @thing_action
    def anaction(
        self, 
        repeats: Annotated[int, Field(description="The number of times to try the action")], 
        title: Annotated[str, Field(description="the title of the invocation - not to be confused with the action!")] = "Untitled", 
        attempts: Annotated[Optional[list[str]], Field(description="Names for each attempt - I suggest final, Final, FINAL, last-ditch.")] = None
    ) -> dict[str, str]:
        """Quite a complicated action
        
        This action has lots of parameters and is designed to confuse my schema generator. I hope
        it doesn't!
        
        I might even use some Markdown here:
        
        * If this renders, it supports lists
        * With at east two items.
        """
        self.increment_counter() # We should be able to call actions as normal Python functions
        return "finished!!"
    
    @thing_action
    def increment_counter(self):
        """Increment the counter property
        
        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the 
        `counter` property).
        """
        self.counter += 1

    @thing_action
    def slowly_increase_counter(self):
        """Increment the counter slowly over a minute"""
        for i in range(60):
            time.sleep(1)
            self.increment_counter()

    counter = PropertyDescriptor(int, 0, readonly=True, description="A pointless counter")

    foo = PropertyDescriptor(str, "Example", description="A pointless string for demo purposes.")
    
thing_server = ThingServer()
my_thing = MyThing()
print(my_thing.validate_thing_description())
thing_server.add_thing(my_thing, "/my_thing")

app = thing_server.app