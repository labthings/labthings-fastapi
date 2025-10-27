"""Test the thing_connection module."""

from collections.abc import Mapping
import gc
import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient

from labthings_fastapi.exceptions import ThingConnectionError


class ThingOne(lt.Thing):
    """A class that will cause chaos if it can."""

    other_thing: "ThingTwo" = lt.thing_connection()
    n_things: "Mapping[str, ThingThree]" = lt.thing_connection()
    optional_thing: "ThingThree | None" = lt.thing_connection()


class ThingTwo(lt.Thing):
    """A class that relies on ThingOne."""

    other_thing: ThingOne = lt.thing_connection()


class ThingN(lt.Thing):
    """A class that emulates ThingOne and ThingTwo more generically."""

    other_thing: "ThingN" = lt.thing_connection(None)


class ThingThree(lt.Thing):
    """A Thing that has no other attributes."""

    pass


class ThingThatMustBeConfigured(lt.Thing):
    """A Thing that has a default that won't work."""

    other_thing: lt.Thing = lt.thing_connection(None)


class Dummy:
    """A dummy thing-like class."""

    def __init__(self, name):
        """Set the dummy Thing's name."""
        self.name = name


class Dummy1(Dummy):
    """A subclass of Dummy."""


class Dummy2(Dummy):
    """A different subclass of Dummy."""


class ThingWithManyConnections:
    """A class with lots of ThingConnections.

    This class is not actually meant to be used - it is a host for
    the thing_connection attributes. It's not a Thing, to simplify
    testing. The "thing" types it depends on are also not Things,
    again to simplify testing.
    """

    name = "thing"

    single_no_default: Dummy1 = lt.thing_connection()
    optional_no_default: Dummy1 | None = lt.thing_connection()
    multiple_no_default: Mapping[str, Dummy1] = lt.thing_connection()

    single_default_none: Dummy1 = lt.thing_connection(None)
    optional_default_none: Dummy1 | None = lt.thing_connection(None)
    multiple_default_none: Mapping[str, Dummy1] = lt.thing_connection(None)

    single_default_str: Dummy1 = lt.thing_connection("dummy_a")
    optional_default_str: Dummy1 | None = lt.thing_connection("dummy_a")
    multiple_default_str: Mapping[str, Dummy1] = lt.thing_connection("dummy_a")

    single_default_seq: Dummy1 = lt.thing_connection(["dummy_a", "dummy_b"])
    optional_default_seq: Dummy1 | None = lt.thing_connection(["dummy_a", "dummy_b"])
    multiple_default_seq: Mapping[str, Dummy1] = lt.thing_connection(
        ["dummy_a", "dummy_b"]
    )


class ThingWithFutureConnection:
    """A class with a ThingConnection in the future."""

    name = "thing"

    single: "DummyFromTheFuture" = lt.thing_connection()
    optional: "DummyFromTheFuture | None" = lt.thing_connection()
    multiple: "Mapping[str, DummyFromTheFuture]" = lt.thing_connection()


class DummyFromTheFuture(Dummy):
    """A subclass of the dummy Thing defined after the dependent class."""


def dummy_things(names, cls=Dummy1):
    """Turn a list or set of names into a dict of Things."""
    return {n: cls(n) for n in names}


def names_set(thing_or_mapping):
    """Given a mapping or a Thing, return a set of names."""
    if thing_or_mapping is None:
        return set()
    if isinstance(thing_or_mapping, str):
        return {thing_or_mapping}
    else:
        return {t.name for t in thing_or_mapping.values()}


@pytest.fixture
def mixed_things():
    """A list of Things with two different types."""
    return {
        **dummy_things({"thing1_a", "thing1_b"}, Dummy1),
        **dummy_things({"thing2_a", "thing2_b"}, Dummy2),
    }


CONN_TYPES = ["single", "optional", "multiple"]
DEFAULTS = ["no_default", "default_none", "default_str", "default_seq"]


@pytest.mark.parametrize("conn_type", CONN_TYPES)
@pytest.mark.parametrize("default", DEFAULTS)
def test_type_analysis(conn_type, default):
    """Check the type of things and thing connections is correctly determined."""
    attr = getattr(ThingWithManyConnections, f"{conn_type}_{default}")

    # All the attributes use the same type of Thing, Dummy1
    assert attr.thing_type == (Dummy1,)
    assert attr.is_optional is (conn_type == "optional")
    assert attr.is_mapping is (conn_type == "multiple")


@pytest.mark.parametrize("conn_type", CONN_TYPES)
def test_type_analysis_strings(conn_type):
    """Check connection types still work with stringified annotations."""
    attr = getattr(ThingWithFutureConnection, f"{conn_type}")

    # All the attributes use the same type of Thing, Dummy1
    assert attr.thing_type == (DummyFromTheFuture,)
    assert attr.is_optional is (conn_type == "optional")
    assert attr.is_mapping is (conn_type == "multiple")


def test_pick_things(mixed_things):
    r"""Test the logic that picks things from the server.

    Note that ``_pick_things`` depends only on the ``thing_type`` of the connection,
    not on whether it's optional or a mapping. Those are dealt with in ``connect``\ .
    """
    attr = ThingWithManyConnections.single_no_default

    def picked_names(things, target):
        return {t.name for t in attr._pick_things(things, target)}

    # If the target is None, we always get an empty list.
    for names in [[], ["thing1_a"], ["thing1_a", "thing1_b"]]:
        assert picked_names(dummy_things(names), None) == set()

    # If there are no other Things, picking by class returns nothing.
    assert picked_names({}, ...) == set()

    # If there are other Things, they should be filtered by type.
    for names1 in [[], ["thing1_a"], ["thing1_a", "thing1_b"]]:
        for names2 in [[], ["thing2_a"], ["thing2_a", "thing2_b"]]:
            mixed_things = {
                **dummy_things(names1, Dummy1),
                **dummy_things(names2, Dummy2),
            }
            assert picked_names(mixed_things, ...) == set(names1)

    # If a string is specified, it works when it exists and it's the right type.
    for target in ["thing1_a", "thing1_b"]:
        assert picked_names(mixed_things, target) == {target}
    # If a sequence of strings is specified, it should also check existence and type.
    # The targets below all exist and have the right type.
    for target in [[], ["thing1_a"], ["thing1_a", "thing1_b"]]:
        assert picked_names(mixed_things, target) == set(target)
    # Any iterable will do - a set is not a sequence, but it is an iterable.
    # This checks sets are OK as well.
    for target in [set(), {"thing1_a"}, {"thing1_a", "thing1_b"}]:
        assert picked_names(mixed_things, target) == target

    # Check for the error if we specify the wrong type (for string and sequence)
    # Note that only one thing of the wrong type will still cause the error.
    for target in ["thing2_a", ["thing2_a"], ["thing1_a", "thing2_a"]]:
        with pytest.raises(ThingConnectionError) as excinfo:
            picked_names(mixed_things, target)
        assert "wrong type" in str(excinfo.value)

    # Check for a KeyError if we specify a missing Thing. This is converted to
    # a ThingConnectionError by `connect`.
    for target in ["something_else", {"thing1_a", "something_else"}]:
        with pytest.raises(KeyError):
            picked_names(mixed_things, target)

    # Check for a TypeError if the target is the wrong type.
    with pytest.raises(TypeError):
        picked_names(mixed_things, True)


def test_connect(mixed_things):
    """Test connecting different attributes produces the right result"""
    cls = ThingWithManyConnections  # This is just to save typing!

    # A default of None means no things should be returned by default
    # This is OK for optional connections and mappings, but not for
    # connections typed as a Thing: these must always have a value.
    for names in [set(), {"thing_a"}, {"thing_a", "thing_b"}]:
        obj = cls()
        cls.optional_default_none.connect(obj, dummy_things(names))
        assert obj.optional_default_none is None
        cls.multiple_default_none.connect(obj, dummy_things(names))
        assert names_set(obj.multiple_default_none) == set()
        # single should fail, as it requires a Thing
        with pytest.raises(ThingConnectionError) as excinfo:
            cls.single_default_none.connect(obj, dummy_things(names))
        assert "must be set" in str(excinfo.value)

    # We should be able to override this by giving names.
    # Note that a sequence with one element and a single string are equivalent.
    for target in ["thing1_a", ["thing1_a"]]:
        obj = cls()
        cls.single_default_none.connect(obj, mixed_things, target)
        assert obj.single_default_none.name == "thing1_a"
        cls.optional_default_none.connect(obj, mixed_things, target)
        assert obj.optional_default_none.name == "thing1_a"
        cls.multiple_default_none.connect(obj, mixed_things, target)
        assert names_set(obj.multiple_default_none) == {"thing1_a"}

    # A default of `...` (i.e. no default) picks by class.
    # Different types have different constraints on how many are allowed.

    # If there are no matching Things, optional and multiple are OK,
    # but a single connection fails, as it can't be None.
    no_matches = {n: Dummy2(n) for n in ["one", "two"]}
    obj = cls()
    with pytest.raises(ThingConnectionError) as excinfo:
        cls.single_no_default.connect(obj, no_matches)
    assert "no matching Thing" in str(excinfo.value)
    cls.optional_no_default.connect(obj, no_matches)
    assert obj.optional_no_default is None
    cls.multiple_no_default.connect(obj, no_matches)
    assert obj.multiple_no_default == {}

    # If there's exactly one matching Thing, everything works.
    match = Dummy1("three")
    one_match = {"three": match, **no_matches}
    obj = cls()
    cls.single_no_default.connect(obj, one_match)
    assert obj.single_no_default is match
    cls.optional_no_default.connect(obj, one_match)
    assert obj.optional_no_default is match
    cls.multiple_no_default.connect(obj, one_match)
    assert obj.multiple_no_default == {"three": match}

    # If we have more than one match, only the multiple connection
    # is OK.
    match2 = Dummy1("four")
    two_matches = {"four": match2, **one_match}
    obj = cls()
    with pytest.raises(ThingConnectionError) as excinfo:
        cls.single_no_default.connect(obj, two_matches)
    assert "multiple Things" in str(excinfo.value)
    assert "Things by type" in str(excinfo.value)
    with pytest.raises(ThingConnectionError) as excinfo:
        cls.optional_no_default.connect(obj, two_matches)
    assert "multiple Things" in str(excinfo.value)
    assert "Things by type" in str(excinfo.value)
    cls.multiple_no_default.connect(obj, two_matches)
    assert obj.multiple_no_default == {"three": match, "four": match2}

    # _pick_things raises KeyErrors for invalid names.
    # Check KeyErrors are turned back into ThingConnectionErrors
    obj = cls()
    with pytest.raises(ThingConnectionError) as excinfo:
        cls.single_default_str.connect(obj, mixed_things)
    assert "not the name of a Thing" in str(excinfo.value)
    assert f"{obj.name}.single_default_str" in str(excinfo.value)
    assert "not configured, and used the default" in str(excinfo.value)
    # The error message changes if a target is specified.
    obj = cls()
    with pytest.raises(ThingConnectionError) as excinfo:
        cls.single_default_str.connect(obj, mixed_things, "missing")
    assert "not the name of a Thing" in str(excinfo.value)
    assert f"{obj.name}.single_default_str" in str(excinfo.value)
    assert "configured to connect to 'missing'" in str(excinfo.value)


def test_readonly():
    """Test that thing connections are read-only."""
    obj = ThingWithManyConnections()
    with pytest.raises(AttributeError, match="read-only"):
        obj.single_default_none = Dummy("name")


def test_referenceerror():
    """Check an error is raised by premature deletion."""
    obj = ThingWithManyConnections()
    things = {"name": Dummy1("name")}
    ThingWithManyConnections.single_no_default.connect(obj, things)
    del things
    gc.collect()
    with pytest.raises(ReferenceError):
        _ = obj.single_no_default


# The tests below use real Things and a real ThingServer to do more
# realistic tests. These are not as exhaustive as the tests above,
# but I think there's no harm in taking both approaches.
def test_type_analysis_thingone():
    """Check the correct properties are inferred from the type hints."""
    assert ThingOne.other_thing.is_optional is False
    assert ThingOne.other_thing.is_mapping is False
    assert ThingOne.other_thing.thing_type == (ThingTwo,)

    assert ThingOne.n_things.is_optional is False
    assert ThingOne.n_things.is_mapping is True
    assert ThingOne.n_things.thing_type == (ThingThree,)

    assert ThingOne.optional_thing.is_optional is True
    assert ThingOne.optional_thing.is_mapping is False
    assert ThingOne.optional_thing.thing_type == (ThingThree,)


CONNECTIONS = {
    "thing_one": {"other_thing": "thing_two"},
    "thing_two": {"other_thing": "thing_one"},
}


@pytest.mark.parametrize(
    ("cls_1", "cls_2", "connections"),
    [
        (ThingOne, ThingTwo, {}),
        (ThingOne, ThingTwo, CONNECTIONS),
        (ThingN, ThingN, CONNECTIONS),
    ],
)
def test_circular_connection(cls_1, cls_2, connections) -> None:
    """Check that two things can connect to each other.

    Note that this test includes a circular dependency, which is fine.
    No checks are made for infinite loops: that's up to the author of the
    Thing classes. Circular dependencies should not cause any problems for
    the LabThings server.
    """
    server = lt.ThingServer(
        things={
            "thing_one": lt.ThingConfig(
                cls=cls_1, thing_connections=connections.get("thing_one", {})
            ),
            "thing_two": lt.ThingConfig(
                cls=cls_2, thing_connections=connections.get("thing_two", {})
            ),
        }
    )
    things = [server.things[n] for n in ["thing_one", "thing_two"]]

    with TestClient(server.app) as _:
        # The things should be connected as the server is now running
        for thing, other in zip(things, reversed(things), strict=True):
            assert thing.other_thing is other


@pytest.mark.parametrize(
    ("connections", "error"),
    [
        ({}, "must be set"),
        ({"thing_one": {"other_thing": "non_thing"}}, "not the name of a Thing"),
        ({"thing_one": {"other_thing": "thing_three"}}, "wrong type"),
        (
            {
                "thing_one": {"other_thing": "thing_one"},
                "thing_two": {"other_thing": "thing_one"},
            },
            None,
        ),
    ],
)
def test_connections_none_default(connections, error):
    """Check error conditions for a connection with a default of None.

    Note that we only catch the first error - that's why we only need
    to specify connections for 'thing_two' in the last case - because
    that's the only one where 'thing_one' connects successfully.
    """
    things = {
        "thing_one": lt.ThingConfig(
            cls=ThingN, thing_connections=connections.get("thing_one", {})
        ),
        "thing_two": lt.ThingConfig(
            cls=ThingN, thing_connections=connections.get("thing_two", {})
        ),
        "thing_three": lt.ThingConfig(
            cls=ThingThree, thing_connections=connections.get("thing_three", {})
        ),
    }

    if error is None:
        server = lt.ThingServer(things)
        with TestClient(server.app):
            thing_one = server.things["thing_one"]
            assert isinstance(thing_one, ThingN)
            assert thing_one.other_thing is thing_one
        return

    with pytest.raises(ThingConnectionError, match=error):
        server = lt.ThingServer(things)


def test_optional_and_empty():
    """Check that an optional or mapping connection can be None/empty."""
    server = lt.ThingServer({"thing_one": ThingOne, "thing_two": ThingTwo})

    with TestClient(server.app):
        thing_one = server.things["thing_one"]
        assert isinstance(thing_one, ThingOne)
        assert thing_one.optional_thing is None
        assert len(thing_one.n_things) == 0


def test_mapping_and_multiple():
    """Check that a mapping connection can pick up several Things.

    This also tests the expected error if multiple things match a
    single connection.
    """
    things = {
        "thing_one": ThingOne,
        "thing_two": ThingTwo,
        "thing_3": ThingThree,
        "thing_4": ThingThree,
        "thing_5": ThingThree,
    }
    # We can't set up a server like this, because
    # thing_one.optional_thing will match multiple ThingThree instances.
    with pytest.raises(ThingConnectionError, match="multiple Things"):
        server = lt.ThingServer(things)

    # Set optional thing to one specific name and it will start OK.
    things["thing_one"] = lt.ThingConfig(
        cls=ThingOne,
        thing_connections={"optional_thing": "thing_3"},
    )
    server = lt.ThingServer(things)
    with TestClient(server.app):
        thing_one = server.things["thing_one"]
        assert isinstance(thing_one, ThingOne)
        assert thing_one.optional_thing is not None
        assert thing_one.optional_thing.name == "thing_3"
        assert names_set(thing_one.n_things) == {f"thing_{i + 3}" for i in range(3)}
