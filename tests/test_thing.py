from typing import Optional
from labthings_fastapi.thing import Thing

class MyThing:

    def anaction(self, repeats: int, title: str="Untitled", attempts: Optional[list[str]] = None) -> str:
        return "finished!!"