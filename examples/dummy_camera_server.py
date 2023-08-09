import logging
import time
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.thing_server import ThingServer
from labthings_fastapi.descriptors import PropertyDescriptor

logging.basicConfig(level=logging.INFO)

class DummyCamera(Thing):
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

    counter = PropertyDescriptor(int, 0, readonly=True, description="A counter")

    
thing_server = ThingServer()
my_thing = DummyCamera()
print(my_thing.validate_thing_description())
thing_server.add_thing(my_thing, "/camera")

app = thing_server.app