"""A client-side implementation of `.Blob`.

.. note::

    In the future, both client and server code are planned to use `.Blob` to
    represent binary data, or data held in a file.

When a `.ThingClient` returns data to a client that matches the schema of a `.Blob`
(specifically, it needs an `href` and a `media_type`), we convert it into a
`.ClientBlobOutput` object. This is a work-a-like for `.Blob`, meaning it can
be saved to a file or have its contents accessed in the same ways.
"""

import io
from typing import Optional
import httpx


class ClientBlobOutput:
    """An output from LabThings best returned as a file.

    This object is returned by a client when the output is not serialised to JSON.
    It may be either retrieved to memory using `.ClientBlobOutput.content`, or
    saved to a file using `.ClientBlobOutput.save`.

    .. note::

        In the future, it is planned to replace this with `.Blob` as used on
        server-side code. The ``.content`` and ``.save()`` methods should be
        identical between the two.
    """

    media_type: str
    download_url: str

    def __init__(
        self, media_type: str, href: str, client: Optional[httpx.Client] = None
    ) -> None:
        """Create a ClientBlobOutput to wrap a link to a downloadable file.

        :param media_type: the MIME type of the remote file.
        :param href: the URL where it may be downloaded.
        :param client: if supplied, this `httpx.Client` will be used to
            download the data.
        """
        self.media_type = media_type
        self.href = href
        self.client = client or httpx.Client()

    @property
    def content(self) -> bytes:
        """The binary data, as a `bytes` object."""
        return self.client.get(self.href).content

    def save(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory, though for now it
        simply retrieves the output into memory, then writes it to a file.

        :param filepath: the file will be saved at this location.
        """
        with open(filepath, "wb") as f:
            f.write(self.content)

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object.

        Internally, this will download the file to memory, and wrap the
        resulting `bytes` object in an `io.BytesIO` object to allow it to
        function as a file-like object.

        To work with the data on disk, use `.ClientBlobOutput.save` instead.

        :return: a file-like object containing the downloaded data.
        """
        return io.BytesIO(self.content)
