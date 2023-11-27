import io
from typing import Optional
import httpx


class ClientBlobOutput:
    """An output from LabThings best returned as a file

    This object is returned by a client when the output is not serialised to JSON.
    It may be either retrieved to memory using `.content`, or saved to a file using
    `.save_to_file()`.
    """

    media_type: str
    download_url: str

    def __init__(
        self, media_type: str, download_url: str, client: Optional[httpx.Client] = None
    ):
        self.media_type = media_type
        self.download_url = download_url
        self.client = client or httpx.Client()

    @property
    def content(self) -> bytes:
        """Return the the output as a `bytes` object"""
        return self.client.get(self.download_url).content

    def save_to_file(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory, though for now it
        simply retrieves the output into memory, then writes it to a file.
        """
        if hasattr(self, "_bytes"):
            with open(filepath, "wb") as f:
                f.write(self.content)

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object."""
        return io.BytesIO(self.content)
