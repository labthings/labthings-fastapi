from typing import Optional

class MyThing:
    def anaction(self, repeats: int, title: str="Untitled", attempts: Optional[list[str]] = None) -> str:
        return "finished!!"