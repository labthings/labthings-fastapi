"""
This tests Things that depend on other Things
"""

import os
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import HTTPStatusError
from pydantic_core import PydanticSerializationError
import pytest
import labthings_fastapi as lt
from labthings_fastapi.client.outputs import ClientBlobOutput
from labthings_fastapi.testing import create_thing_without_server


class TextBlob(lt.blob.Blob):
    media_type: str = "text/plain"


class ThingOne(lt.Thing):
    ACTION_ONE_RESULT = b"Action one result!"

    def __init__(self, thing_server_interface):
        super().__init__(thing_server_interface=thing_server_interface)
        self._temp_directory = TemporaryDirectory()

    @lt.thing_action
    def action_one(self) -> TextBlob:
        """An action that makes a blob response from bytes"""
        return TextBlob.from_bytes(self.ACTION_ONE_RESULT)

    @lt.thing_action
    def action_two(self) -> TextBlob:
        """An action that makes a blob response from a file and tempdir"""
        td = TemporaryDirectory()
        with open(os.path.join(td.name, "serverside"), "wb") as f:
            f.write(self.ACTION_ONE_RESULT)
        return TextBlob.from_temporary_directory(td, "serverside")

    @lt.thing_action
    def action_three(self) -> TextBlob:
        """An action that makes a blob response from a file"""
        fpath = os.path.join(self._temp_directory.name, "serverside")
        with open(fpath, "wb") as f:
            f.write(self.ACTION_ONE_RESULT)
        return TextBlob.from_file(fpath)

    @lt.thing_action
    def passthrough_blob(self, blob: TextBlob) -> TextBlob:
        """An action that passes through a blob response"""
        return blob


class ThingTwo(lt.Thing):
    thing_one: ThingOne = lt.thing_slot()

    @lt.thing_action
    def check_both(self) -> bool:
        """An action that checks the output of ThingOne"""
        check_actions(self.thing_one)
        return True

    @lt.thing_action
    def check_passthrough(self) -> bool:
        """An action that checks the passthrough of ThingOne"""
        output = self.thing_one.action_one()
        passthrough = self.thing_one.passthrough_blob(blob=output)
        assert passthrough.content == ThingOne.ACTION_ONE_RESULT
        return True


@pytest.fixture
def client():
    """Yield a test client connected to a ThingServer."""
    server = lt.ThingServer(
        {
            "thing_one": ThingOne,
            "thing_two": ThingTwo,
        }
    )
    with TestClient(server.app) as client:
        yield client


def test_blobdata_protocol():
    """Check the definition of the blobdata protocol, and the implementations."""

    class BadBlob(lt.blob.BlobData):
        pass

    bad_blob = BadBlob()

    assert not isinstance(bad_blob, lt.blob.ServerSideBlobData)

    with pytest.raises(NotImplementedError):
        _ = bad_blob.media_type
    with pytest.raises(NotImplementedError):
        _ = bad_blob.content


@pytest.mark.filterwarnings("ignore:.*removed in v0.0.13.*:DeprecationWarning")
def test_blob_type():
    """Check we can't put dodgy values into a blob output model"""
    with pytest.raises(ValueError):
        lt.blob.blob_type(media_type="text/plain\\'DROP TABLES")
    M = lt.blob.blob_type(media_type="text/plain")
    assert M.from_bytes(b"").media_type == "text/plain"


def test_blob_creation():
    """Check that blobs can be created in three ways"""
    TEXT = b"Test input"
    # Create a blob from a file in a temporary directory
    td = TemporaryDirectory()
    with open(os.path.join(td.name, "test_input"), "wb") as f:
        f.write(TEXT)
    # This creates the blob from only a file. It won't preserve
    # the temporary directory.
    blob = TextBlob.from_file(os.path.join(td.name, "test_input"))
    assert blob.content == TEXT
    # This will preserve the temporary directory, as it's
    # saved in the underlying BlobData object (asserted below).
    blob = TextBlob.from_temporary_directory(td, "test_input")
    assert blob.content == TEXT
    assert blob.data._temporary_directory is td
    # Using a filename that does not exist should generate an error.
    with pytest.raises(IOError):
        _ = TextBlob.from_file(os.path.join(td.name, "nonexistent"))
    with pytest.raises(IOError):
        _ = TextBlob.from_temporary_directory(td, "nonexistent")

    # Finally, check we can make a blob from a bytes object, no file.
    blob = TextBlob.from_bytes(TEXT)
    assert blob.content == TEXT


def test_blob_serialisation():
    """Check that blobs may be serialised."""
    blob = TextBlob.from_bytes(b"Some data")
    # Can't serialise a blob (with data) without a BlobDataManager
    with pytest.raises(PydanticSerializationError):
        blob.model_dump()
    # Fake the required context variable, and it should work
    try:
        token = lt.outputs.blob.blobdata_to_url_ctx.set(lambda b: "https://example/")
        data = blob.model_dump()
        assert data["href"] == "https://example/"
        assert data["media_type"] == "text/plain"
    finally:
        lt.outputs.blob.blobdata_to_url_ctx.reset(token)

    # Blobs that already refer to a remote URL should serialise without error
    # though there's currently no way to create one on the server.
    remoteblob = TextBlob.model_construct(
        media_type="text/plain",
        href="https://example/",
    )
    data = remoteblob.model_dump()
    assert data["href"] == "https://example/"
    assert data["media_type"] == "text/plain"


def test_blob_output_client(client):
    """Test that blob outputs work as expected when used over HTTP."""
    tc = lt.ThingClient.from_url("/thing_one/", client=client)
    check_actions(tc)


def test_blob_output_direct():
    """Check blob outputs work correctly when we use a Thing directly in Python."""
    thing = create_thing_without_server(ThingOne)
    check_actions(thing)


def test_blob_output_inserver(client):
    """Test that the blob output works the same when used via a `.thing_slot`."""
    tc = lt.ThingClient.from_url("/thing_two/", client=client)
    output = tc.check_both()
    assert output is True


def check_blob(output, expected_content: bytes):
    """Test that a BlobOutput can be retrieved in three ways"""
    print(f"Testing blob output {output} which has attributes {output.__dict__}")
    assert output.content == expected_content
    with TemporaryDirectory() as dir:
        output.save(os.path.join(dir, "test_output"))
        with open(os.path.join(dir, "test_output"), "rb") as f:
            assert f.read() == expected_content
    with output.open() as f:
        assert f.read() == expected_content


def check_actions(thing):
    """Check that both action_one and action_two work.

    This should work if called on a ThingOne directly, or a DirectThingClient,
    or an HTTP ThingClient.
    """
    for action in (thing.action_one, thing.action_two, thing.action_three):
        output = action()
        check_blob(output, ThingOne.ACTION_ONE_RESULT)


def test_blob_input(client):
    """Check that blobs can be used as input."""
    tc = lt.ThingClient.from_url("/thing_one/", client=client)
    output = tc.action_one()
    print(f"Output is {output}")
    assert output is not None

    # Check that the blob can be passed from one action to another,
    # via the client
    passthrough = tc.passthrough_blob(blob=output)
    print(f"Output is {passthrough}")
    assert passthrough.content == ThingOne.ACTION_ONE_RESULT

    # Check that a bad URL results in an error.
    # This URL is not totally bad - it follows the right form, but the
    # UUID is not found on the server.
    bad_blob = ClientBlobOutput(
        media_type="text/plain", href=f"http://nonexistent.local/blob/{uuid4()}"
    )
    with pytest.raises(LookupError):
        tc.passthrough_blob(blob=bad_blob)
    # Try again with a totally bogus URL
    bad_blob = ClientBlobOutput(
        media_type="text/plain", href="http://nonexistent.local/totally_bogus"
    )
    with pytest.raises(HTTPStatusError, match="404 Not Found"):
        tc.passthrough_blob(blob=bad_blob)

    # Check that the same thing works on the server side
    tc2 = lt.ThingClient.from_url("/thing_two/", client=client)
    assert tc2.check_passthrough() is True
