.. _quickref:

Quick Reference API Documentation
=================================

This page summarises the parts of the LabThings API that should be most frequently used by people writing `lt.Thing` subclasses. It doesn't list options exhaustively: the full :doc:`API documentation <autoapi/index>` does that if extra detail is needed.

.. py:module:: lt

.. py:class:: Thing(thing_server_interface: ThingServerInterface)

    The basic unit of functionality in LabThings is the `Thing`. Each piece of hardware (or software) controlled by LabThings is represented by an instance of a `Thing` subclass, and so adding a new instrument or software unit generally involves subclassing. Each `Thing` on a server has a name, a URL, and a Thing Description describing its capabilities.

    It is likely that `Thing` subclasses will override `__init__`, `__enter__`, and `__exit__`. See the documentation on those methods for important subclassing notes.

    The capabilities of a `Thing` are described using attributes. Actions are methods decorated with `action`, and properties are declared using `property` or `setting`. `Thing`\ s may communicate with each other using `thing_slot`\ s.

    `Thing`\ s should only be created by a `ThingServer`\ . To create a `Thing` without a server, see `.testing.create_thing_without_server` for a test harness that supplies a dummy `ThingServerInterface`.

    This page offers only the most commonly-used methods: full documentation is available at `labthings_fastapi.thing.Thing`\ .

    .. py:method:: __init__(thing_server_interface: ThingServerInterface)
        
        `__init__` may be overridden in order to accept arguments when your object is created. If you override `__init__` you **must** call ``super().__init__(thing_server_interface)`` to ensure the `Thing` is properly connected to a server.

        `__init__` *should not* acquire any resources (like communications ports), as they may not be closed cleanly. Please acquire any necessary resources in `__enter__` instead.

        :param thing_server_interface: The interface to the server that
            is hosting this Thing. It will be supplied when the `~lt.Thing` is
            instantiated by the `~lt.ThingServer` or by
            `.testing.create_thing_without_server` which generates a mock interface.


    .. autoattribute:: labthings_fastapi.thing.Thing.title
        :no-index:

    .. py:attribute:: _thing_server_interface
        :type:  ThingServerInterface

        Provide access to features of the server that this `~lt.Thing` is attached to.

    .. autoproperty:: labthings_fastapi.thing.Thing.name
        :no-index:

    .. py:property:: logger
        :type: logging.Logger

        A logger, named after this Thing. Use this logger if you wish to log messages from `action` or `property` code.

    .. py:property:: properties
        :type:  labthings_fastapi.properties.PropertyCollection

        A mapping of names to `PropertyInfo` objects. This allows easy access to metadata, for example:

        .. code-block:: python

            self.properties["myprop"].default

    .. py:property:: settings
        :type:  labthings_fastapi.properties.SettingCollection

        A mapping of names to `.SettingInfo` objects, similar to `properties` but providing setting-specific features.

    .. py:property:: actions
        :type:  labthings_fastapi.actions.ActionCollection

        A mapping of names to `.ActionInfo` objects that allows
        convenient access to metadata of each action.


    .. py:property:: thing_state
        :type: collections.abc.Mapping


        This should return a dictionary of metadata, which will be returned to any code requesting it through `ThingServerInterface.get_thing_states`\ .


    .. automethod:: labthings_fastapi.thing.Thing.get_current_invocation_logs
        :no-index:

.. py:function:: property(getter: Callable[[Owner], Value]) -> FunctionalProperty[Owner, Value]
                 property(*, default: Value, readonly: bool = False, **constraints: Any) -> Value
                 property(*, default_factory: Callable[[], Value], readonly: bool = False, **constraints: Any) -> Value

    This function may be used to define :ref:`properties` either by decorating a function, or marking an attribute. Full documentation is available at `labthings_fastapi.properties.property` and a more in-depth discussion is available at :ref:`properties`\ . This page focuses on the most frequently used examples.

    To mark a class attribute with `property` you should define the attribute as shown below. Note that the type hint is required for LabThings to work properly.

    .. code-block:: python

        class MyThing(lt.Thing):
            intprop: int = lt.property(default=0)
            """A simple read-write property"""

            readonly: int = lt.property(default=42, readonly=True)
            """This property may not be written to over HTTP"""

            listprop: list[int] = lt.property(default_factory=lambda: [1,2,3])
            """Mutable default values should be wrapped in a "factory function".""""

            positive: int = lt.property(default=1, gt=0)
            """Constraints may be used in the same way as for `pydantic.Field`"""
    
    All the examples above are "data properties". `property` can also define "functional properties" when used as a decorator:

    .. code-block:: python

        class MyThing(lt.Thing):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._number = 0
            
            @lt.property
            def the_answer(self) -> int:
                """A read-only property."""
                return 42
            
            @lt.property
            def number(self) -> int:
                """A property that's got extra attributes set."""
            
            @number.setter
            def _set_number(self, value: int) -> None:
                self._number = value
            
            number.readonly = True  # This prevents it being written over HTTP
            number.constraints = {"ge": 0}  # This adds constraints to the schema
            number.default = 0  # This adds a default value to the documentation
    
    For a full listing of attributes that may be modified, see `DataProperty`\ .


.. py:function:: setting(getter: Callable[[Owner], Value]) -> FunctionalSetting[Owner, Value]
                 setting(*, default: Value, readonly: bool = False, **constraints: Any) -> Value
                 setting(*, default_factory: Callable[[], Value], readonly: bool = False, **constraints: Any) -> Value

    A setting is a property that is saved to disk. It is defined in the same way as `property` but will be synchronised with the `Thing`\ 's settings file. Full documentation is available at `labthings_fastapi.properties.setting`


.. py:decorator:: action
                  action(**kwargs: Any)

   Mark a method of a `~lt.Thing` as a LabThings Action.

   Methods decorated with `action` will be available to call
   over HTTP as actions. See :ref:`actions` for an introduction to the concept
   of actions.

   This decorator may be used with or without arguments.

   :param \**kwargs: Keyword arguments are passed to the constructor
       of `.ActionDescriptor`.





.. py:function:: thing_slot(default: str | collections.abc.Iterable[str] | None | types.EllipsisType = ...) -> Any

   Declare a connection to another `~lt.Thing` in the same server.

   ``thing_slot`` marks a class attribute as a connection to another
   `Thing` on the same server. This will be automatically supplied when the
   server is started, based on the type hint and default value.

   In keeping with `property` and `setting`, the type of the attribute should
   be the type of the connected `~lt.Thing`\ . A `~collections.abc.Mapping` should be used
   if the slot supports multiple `Thing`\ s. For example:

   .. code-block:: python

       class ThingA(lt.Thing): ...


       class ThingB(lt.Thing):
           "A class that relies on ThingA."

           thing_a: ThingA = lt.thing_slot()
           multiple_things_a: Mapping[str, ThingA] = lt.thing_slot()

   For more details, see the full API docs for `~labthings_fastapi.thing_slots.thing_slot`\ .

   :param default: The name(s) of the Thing(s) that will be connected by default.
       If the default is omitted or set to ``...`` the server will attempt to find
       a matching `~lt.Thing` instance (or instances). A default value of `None` is
       allowed if the connection is type hinted as optional.
   :return: A `.ThingSlot` descriptor.


.. py:decorator:: endpoint(method: HTTPMethod, path: Optional[str] = None, **kwargs: Any)

   Mark a function as a FastAPI endpoint without making it an action.

   This decorator will cause a method of a `~lt.Thing` to be directly added to
   the HTTP API, bypassing the machinery underlying Action and Property
   affordances. Such endpoints will not be documented in the :ref:`wot_td` but
   may be used as the target of links. For example, this could allow a file
   to be downloaded from the `~lt.Thing` at a known URL, or serve a video stream
   that wouldn't be supported as a `.Blob`\ .

   The majority of `~lt.Thing` implementations won't need this decorator, but
   it is here to enable flexibility when it's needed.

   This decorator always takes arguments; in particular, ``method`` is
   required. It should be used as:

   .. code-block:: python

       class DownloadThing(Thing):
           @endpoint("get")
           def plain_text_response(self) -> str:
               return "example string"

   This decorator is intended to work very similarly to the `fastapi` decorators
   ``@app.get``, ``@app.post``, etc., with two changes:

   1. The path is relative to the host `~lt.Thing` and will default to the name
       of the method.
   2. The method will be called with the host `~lt.Thing` as its first argument,
       i.e. it will be bound to the class as usua.

   :param method: The HTTP verb this endpoint responds to.
   :param path: The path, relative to the host `~lt.Thing` base URL.
   :param \**kwargs: Additional keyword arguments are passed to the
       `fastapi.FastAPI.get` decorator if ``method`` is ``get``, or to
       the equivalent decorator for other HTTP verbs.

   :return: When used as intended, the result is an `.EndpointDescriptor`.


.. py:class:: ThingServer(things: config_model.ThingsConfig, settings_folder: Optional[str] = None, application_config: Optional[collections.abc.Mapping[str, Any]] = None, debug: bool = False)

    The `ThingServer` sets up a `fastapi.FastAPI` application and uses it
    to expose the capabilities of `Thing` instances over HTTP.

    Full documentation of how the class works is available at `labthings_fastpi.server.ThingServer`\ . Most of the attributes of `ThingServer` should not be accessed directly by `Thing` subclasses - instead they should use the `ThingServerInterface` for a cleaner way to access the server.

    :param things: A mapping of Thing names to `~lt.Thing` subclasses, or
        `ThingConfig` objects specifying the subclass, its initialisation
        arguments, and any connections to other `~lt.Thing`\ s.
    :param settings_folder: the location on disk where `~lt.Thing`
        settings will be saved.
    :param application_config: A mapping containing custom configuration for the
        application. This is not processed by LabThings. Each `~lt.Thing` can access
        application. This is not processed by LabThings. Each `~lt.Thing` can access
        this via the Thing-Server interface.
    :param debug: If ``True``, set the log level for `~lt.Thing` instances to
                    DEBUG.
        

   .. automethod:: labthings_fastapi.server.ThingServer.from_config
        :no-index:



.. py:class:: ThingServerInterface(server: ThingServer, name: str)

   An interface for Things to interact with their server. This is available as `Thing._thing_server_interface` and should not normally be created except by the `ThingServer`\ .

   .. automethod:: labthings_fastapi.thing_server_interface.ThingServerInterface.start_async_task_soon
        :no-index:

   .. automethod:: labthings_fastapi.thing_server_interface.ThingServerInterface.call_async_task
        :no-index:

   .. autoproperty:: labthings_fastapi.thing_server_interface.ThingServerInterface.settings_folder
        :no-index:

   .. autoproperty:: labthings_fastapi.thing_server_interface.ThingServerInterface.settings_file_path
        :no-index:

   .. autoproperty:: labthings_fastapi.thing_server_interface.ThingServerInterface.name
        :no-index:

   .. autoproperty:: labthings_fastapi.thing_server_interface.ThingServerInterface.application_config
        :no-index:

   .. automethod:: labthings_fastapi.thing_server_interface.ThingServerInterface.get_thing_states
        :no-index:


.. py:class:: ThingConfig(/, **data: Any)

   Bases: :py:obj:`pydantic.BaseModel`


   The information needed to add a `~lt.Thing` to a `~lt.ThingServer`\ . This is an alias of `labthings_fastapi.server.config_model.ThingConfig`

   .. autoattribute:: labthings_fastapi.server.config_model.ThingConfig.cls
        :no-index:

   .. autoattribute:: labthings_fastapi.server.config_model.ThingConfig.args
        :no-index:

   .. autoattribute:: labthings_fastapi.server.config_model.ThingConfig.kwargs
        :no-index:

   .. autoattribute:: labthings_fastapi.server.config_model.ThingConfig.thing_slots
        :no-index:


.. py:class:: ThingServerConfig(/, **data: Any)

   Bases: :py:obj:`pydantic.BaseModel`


   The configuration parameters for a `~lt.ThingServer`\ .


   .. autoattribute:: labthings_fastapi.server.config_model.ThingServerConfig.things
        :no-index:

   .. autoattribute:: labthings_fastapi.server.config_model.ThingServerConfig.settings_folder
        :no-index:

   .. autoattribute:: labthings_fastapi.server.config_model.ThingServerConfig.application_config
        :no-index:


.. py:class:: ThingClient

   A client for a LabThings-FastAPI Thing, alias of `labthings_fastapi.client.ThingClient`

   .. note::
       ThingClient must be subclassed to add actions/properties,
       so this class will be minimally useful on its own.

       The best way to get a client for a particular Thing is
       currently `ThingClient.from_url`, which dynamically
       creates a subclass with the right attributes.

   .. automethod:: labthings_fastapi.client.ThingClient.from_url
        :no-index:


.. py:function:: cancellable_sleep(interval: float) -> None

   Sleep for a specified time, allowing cancellation.

   This function should be called from action functions instead of
   `time.sleep` to allow them to be cancelled. Usually, this
   function is equivalent to `time.sleep` (it waits the specified
   number of seconds). If the action is cancelled during the sleep,
   it will raise an `.InvocationCancelledError` to signal that the
   action should finish.

   .. warning::

       This function uses `.Event.wait` internally, which suffers
       from timing errors on some platforms: it may have error of
       around 10-20ms. If that's a problem, consider using
       `time.sleep` instead. ``lt.raise_if_cancelled()`` may then
       be used to allow cancellation.

   If this function is called from outside of an action thread, it
   will revert to `time.sleep`\ .

   :param interval: The length of time to wait for, in seconds.


.. py:function:: raise_if_cancelled() -> None

   Raise an exception if the current invocation has been cancelled.

   This function checks for cancellation events and, if the current
   action invocation has been cancelled, it will raise an
   `.InvocationCancelledError` to signal the thread to terminate.
   It is equivalent to `~lt.cancellable_sleep` but without waiting any
   time.

   If called outside of an invocation context, this function does
   nothing, and will not raise an error.


.. py:class:: ThreadWithInvocationID(target: Callable, args: collections.abc.Sequence[Any] | None = None, kwargs: collections.abc.Mapping[str, Any] | None = None, *super_args: Any, **super_kwargs: Any)

   Bases: :py:obj:`threading.Thread`


   A thread that sets a new invocation ID.

   This is a subclass of `threading.Thread` and works very much the
   same way. It implements its functionality by overriding the ``run``
   method, so this should not be overridden again - you should instead
   specify the code to run using the ``target`` argument.

   This function enables an action to be run in a thread, which gets its
   own invocation ID and cancel hook. This means logs will not be interleaved
   with the calling action, and the thread may be cancelled just like an
   action started over HTTP, by calling its ``cancel`` method.

   The thread also remembers the return value of the target function
   in the property ``result`` and stores any exception raised in the
   ``exception`` property.

   A final LabThings-specific feature is cancellation propagation. If
   the thread is started from an action that may be cancelled, it may
   be joined with ``join_and_propagate_cancel``\ . This is intended
   to be equivalent to calling ``join`` but with the added feature that,
   if the parent thread is cancelled while waiting for the child thread
   to join, the child thread will also be cancelled.

   :param target: the function to call in the thread.
   :param args: positional arguments to ``target``\ .
   :param kwargs: keyword arguments to ``target``\ .
   :param \*super_args: arguments passed to `threading.Thread`\ .
   :param \*\*super_kwargs: keyword arguments passed to `threading.Thread`\ .


   .. py:property:: result
      :type: Any


      The return value of the target function.



   .. py:property:: exception
      :type: BaseException | None


      The exception raised by the target function, or None.



   .. py:method:: cancel() -> None

      Set the cancel event to tell the code to terminate.



   .. py:method:: join_and_propagate_cancel(poll_interval: float = 0.2) -> None

      Wait for the thread to finish, and propagate cancellation.

      This function wraps `threading.Thread.join` but periodically checks if
      the calling thread has been cancelled. If it has, it will cancel the
      thread, before attempting to ``join`` it again.

      Note that, if the invocation that calls this function is cancelled
      while the function is running, the exception will propagate, i.e.
      you should handle `.InvocationCancelledError` unless you wish
      your invocation to terminate if it is cancelled.

      :param poll_interval: How often to check for cancellation of the
          calling thread, in seconds.
      :raises InvocationCancelledError: if this invocation is cancelled
          while waiting for the thread to join.



   .. py:method:: run() -> None

      Run the target function, with invocation ID set in the context variable.

