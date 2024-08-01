"""
This tests Things that depend on other Things
"""

import os
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
import pytest
from labthings_fastapi.server import ThingServer
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.dependencies.thing import direct_thing_client_dependency
from labthings_fastapi.outputs.blob import BlobOutput, blob_output_model
from labthings_fastapi.client import ThingClient


class TestBlobOutput(BlobOutput):
    media_type = "text/plain"


class ThingOne(Thing):
    ACTION_ONE_RESULT = b"Action one result!"

    def __init__(self):
        self._temp_directory = TemporaryDirectory()

    @thing_action
    def action_one(self) -> TestBlobOutput:
        """An action that makes a blob response from bytes"""
        return TestBlobOutput.from_bytes(self.ACTION_ONE_RESULT)

    @thing_action
    def action_two(self) -> TestBlobOutput:
        """An action that makes a blob response from a file and tempdir"""
        td = TemporaryDirectory()
        with open(os.path.join(td.name, "serverside"), "wb") as f:
            f.write(self.ACTION_ONE_RESULT)
        return TestBlobOutput.from_temporary_directory(td, "serverside")

    @thing_action
    def action_three(self) -> TestBlobOutput:
        """An action that makes a blob response from a file"""
        fpath = os.path.join(self._temp_directory.name, "serverside")
        with open(fpath, "wb") as f:
            f.write(self.ACTION_ONE_RESULT)
        return TestBlobOutput.from_file(fpath)


ThingOneDep = direct_thing_client_dependency(ThingOne, "/thing_one/")


class ThingTwo(Thing):
    @thing_action
    def check_both(self, thing_one: ThingOneDep) -> bool:
        """An action that checks the output of ThingOne"""
        check_actions(thing_one)
        return True


def test_blob_output_model():
    """Check we can't put dodgy values into a blob output model"""
    with pytest.raises(ValueError):
        blob_output_model(media_type="text/plain\\'DROP TABLES")
    M = blob_output_model(media_type="text/plain")
    assert M(href="http://example/").media_type == "text/plain"


def test_blob_output_client():
    """Test that a Thing can depend on another Thing

    This uses the internal thing client mechanism.
    """
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    with TestClient(server.app) as client:
        tc = ThingClient.from_url("/thing_one/", client=client)
        check_actions(tc)


def test_blob_output_direct():
    """This should mirror `test_blob_output_inserver` but with helpful errors"""
    thing = ThingOne()
    check_actions(thing)


def test_blob_output_inserver():
    """Test that the blob output works the same when used directly"""
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    server.add_thing(ThingTwo(), "/thing_two")
    with TestClient(server.app) as client:
        tc = ThingClient.from_url("/thing_two/", client=client)
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
    """Check that both action_one and action_two work"""
    for action in (thing.action_one, thing.action_two, thing.action_three):
        output = action()
        check_blob(output, ThingOne.ACTION_ONE_RESULT)
