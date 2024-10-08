from __future__ import annotations
import datetime
import logging
from collections import deque
from threading import Event, Thread, Lock
from typing import MutableSequence, Optional, Any
import uuid
from typing import TYPE_CHECKING
import weakref
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from labthings_fastapi.outputs.blob import blob_to_link

from labthings_fastapi.utilities.introspection import EmptyInput
from ..thing_description.model import LinkElement
from ..file_manager import FileManager
from .invocation_model import InvocationModel, InvocationStatus
from ..dependencies.invocation import (
    CancelHook,
    InvocationCancelledError,
    invocation_logger,
)

if TYPE_CHECKING:
    # We only need these imports for type hints, so this avoids circular imports.
    from ..descriptors import ActionDescriptor
    from ..thing import Thing

ACTION_INVOCATIONS_PATH = "/action_invocations"


class Invocation(Thread):
    """A Thread subclass that retains output values and tracks progress

    TODO: In the future this should probably not be a Thread subclass, but might run in
    a thread anyway.
    """

    def __init__(
        self,
        action: ActionDescriptor,
        thing: Thing,
        input: Optional[BaseModel] = None,
        dependencies: Optional[dict[str, Any]] = None,
        default_stop_timeout: float = 5,
        log_len: int = 1000,
        id: Optional[uuid.UUID] = None,
        cancel_hook: Optional[CancelHook] = None,
    ):
        Thread.__init__(self, daemon=True)

        # keep track of the corresponding ActionDescriptor
        self.action_ref = weakref.ref(action)
        self.thing_ref = weakref.ref(thing)
        self.input = input if input is not None else EmptyInput()
        self.dependencies = dependencies if dependencies is not None else {}
        self.cancel_hook = cancel_hook

        # A UUID for the Invocation (not the same as the threading.Thread ident)
        self._ID = id if id is not None else uuid.uuid4()  # Task ID

        # Event to track if the user has requested stop
        self.stopping: Event = Event()
        self.default_stop_timeout: float = default_stop_timeout

        # How long to keep the invocation after it finishes
        self.retention_time = action.retention_time
        self.expiry_time: Optional[datetime.datetime] = None

        # This is added post-hoc by the FastAPI endpoint, in
        # `ActionDescriptor.add_to_fastapi`
        self._file_manager: Optional[FileManager] = None

        # Private state properties
        self._status_lock = Lock()  # This Lock protects properties below
        self._status: InvocationStatus = InvocationStatus.PENDING  # Task status
        self._return_value: Optional[Any] = None  # Return value
        self._request_time: datetime.datetime = datetime.datetime.now()
        self._start_time: Optional[datetime.datetime] = None  # Task start time
        self._end_time: Optional[datetime.datetime] = None  # Task end time
        self._exception: Optional[Exception] = None  # Propagate exceptions helpfully
        self._log: deque = deque(maxlen=log_len)  # log entries for this thread

    @property
    def id(self) -> uuid.UUID:
        """
        UUID for the thread. Note this not the same as the native thread ident.
        """
        return self._ID

    @property
    def output(self) -> Any:
        """
        Return value of the Action. If the Action is still running, returns None.
        """
        with self._status_lock:
            return self._return_value

    @property
    def log(self):
        """A list of log items generated by the Action."""
        with self._status_lock:
            return list(self._log)

    @property
    def status(self) -> InvocationStatus:
        """
        Current running status of the thread.

        ==============  =============================================
        Status          Meaning
        ==============  =============================================
        ``pending``     Not yet started
        ``running``     Currently in-progress
        ``completed``   Finished without error
        ``cancelled``   Thread stopped after a cancel request
        ``error``       Exception occured in thread
        ==============  =============================================
        """
        with self._status_lock:
            return self._status

    @property
    def action(self):
        return self.action_ref()

    @property
    def thing(self):
        return self.thing_ref()

    def cancel(self):
        """Cancel the task by requesting the code to stop

        This is very much not guaranteed to work: the action must use
        a CancelHook dependency and periodically check it.
        """
        if self.cancel_hook is not None:
            self.cancel_hook.set()

    def response(self, request: Optional[Request] = None):
        if request:
            href = str(request.url_for("action_invocation", id=self.id))
        else:
            href = f"{ACTION_INVOCATIONS_PATH}/{self.id}"
        links = [
            LinkElement(rel="self", href=href),
            LinkElement(rel="output", href=href + "/output"),
        ]
        if self._file_manager:
            links += self._file_manager.links(href)
        return self.action.invocation_model(
            status=self.status,
            id=self.id,
            action=self.thing.path + self.action.name,
            href=href,
            timeStarted=self._start_time,
            timeCompleted=self._end_time,
            timeRequested=self._request_time,
            input=self.input,
            output=blob_to_link(self.output, href + "/output"),
            links=links,
            log=self.log,
        )

    def run(self):
        """Overrides default threading.Thread run() method"""
        self.action.emit_changed_event(self.thing, self._status)

        # Capture just this thread's log messages
        handler = DequeLogHandler(dest=self._log)
        logger = invocation_logger(self.id)
        logger.addHandler(handler)

        action = self.action
        thing = self.thing
        kwargs = self.input.model_dump() or {}
        assert action is not None
        assert thing is not None

        with self._status_lock:
            self._status = InvocationStatus.RUNNING
            self._start_time = datetime.datetime.now()
            self.action.emit_changed_event(self.thing, self._status)

        try:
            # The next line actually runs the action.
            ret = action.__get__(thing)(**kwargs, **self.dependencies)

            with self._status_lock:
                self._return_value = ret
                self._status = InvocationStatus.COMPLETED
                self.action.emit_changed_event(self.thing, self._status)
        except InvocationCancelledError:
            logger.error(f"Invocation {self.id} was cancelled.")
            with self._status_lock:
                self._status = InvocationStatus.CANCELLED
                self.action.emit_changed_event(self.thing, self._status)
        except Exception as e:  # skipcq: PYL-W0703
            logger.exception(e)
            with self._status_lock:
                self._status = InvocationStatus.ERROR
                self._exception = e
                self.action.emit_changed_event(self.thing, self._status)
            raise e
        finally:
            with self._status_lock:
                self._end_time = datetime.datetime.now()
                self.expiry_time = self._end_time + datetime.timedelta(
                    seconds=self.retention_time,
                )
            logger.removeHandler(handler)  # Stop saving logs
            # If we don't remove the log handler, it's a circular ref/memory leak.


class DequeLogHandler(logging.Handler):
    def __init__(
        self,
        dest: MutableSequence,
        level=logging.INFO,
    ):
        """Set up a log handler that appends messages to a list.

        This log handler will first filter by ``thread``, if one is
        supplied.  This should be a ``threading.Thread`` object.
        Only log entries from the specified thread will be
        saved.

        ``dest`` should specify a deque, to which we will append
        each log entry as it comes in. This is assumed to be thread
        safe.

        NB this log handler does not currently rotate or truncate
        the list - so if you use it on a thread that produces a
        lot of log messages, you may run into memory problems.


        """
        logging.Handler.__init__(self)
        self.setLevel(level)
        self.dest = dest

    def emit(self, record):
        """Save a log record to the destination deque"""
        self.dest.append(record)


class ActionManager:
    """A class to manage a collection of actions"""

    def __init__(self):
        self._invocations = {}
        self._invocations_lock = Lock()

    @property
    def invocations(self):
        with self._invocations_lock:
            return list(self._invocations.values())

    def append_invocation(self, invocation: Invocation):
        with self._invocations_lock:
            self._invocations[invocation.id] = invocation

    def invoke_action(
        self,
        action: ActionDescriptor,
        thing: Thing,
        id: uuid.UUID,
        input: Any,
        dependencies: dict[str, Any],
        cancel_hook: CancelHook,
    ) -> Invocation:
        """Invoke an action, returning the thread where it's running"""
        thread = Invocation(
            action=action,
            thing=thing,
            input=input,
            dependencies=dependencies,
            id=id,
            cancel_hook=cancel_hook,
        )
        self.append_invocation(thread)
        thread.start()
        return thread

    def list_invocations(
        self,
        action: Optional[ActionDescriptor] = None,
        thing: Optional[Thing] = None,
        as_responses: bool = False,
        request: Optional[Request] = None,
    ) -> list[InvocationModel]:
        """All of the invocations currently managed"""
        return [
            i.response(request=request) if as_responses else i
            for i in self.invocations
            if thing is None or i.thing == thing
            if action is None or i.action == action
        ]

    def expire_invocations(self):
        """Delete invocations that have passed their expiry time"""
        to_delete = []
        with self._invocations_lock:
            for k, v in self._invocations.items():
                if v.expiry_time is not None:
                    if v.expiry_time < datetime.datetime.now():
                        to_delete.append(k)
            logging.info(f"Deleting invocations {to_delete} as they have expired")
            for k in to_delete:
                del self._invocations[k]

    def attach_to_app(self, app: FastAPI):
        """Add /action_invocations and /action_invocation/{id} endpoints to FastAPI"""

        @app.get(ACTION_INVOCATIONS_PATH, response_model=list[InvocationModel])
        def list_all_invocations(request: Request):
            return self.list_invocations(as_responses=True, request=request)

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}",
            response_model=InvocationModel,
            responses={404: {"description": "Invocation ID not found"}},
        )
        def action_invocation(id: uuid.UUID, request: Request):
            try:
                with self._invocations_lock:
                    return self._invocations[id].response(request=request)
            except KeyError:
                raise HTTPException(
                    status_code=404,
                    detail="No action invocation found with ID {id}",
                )

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}/output",
            response_model=Any,
            responses={
                200: {
                    "description": "Action invocation output",
                    "content": {
                        "*/*": {},
                    },
                },
                404: {"description": "Invocation ID not found"},
                503: {"description": "No result is available for this invocation"},
            },
        )
        def action_invocation_output(id: uuid.UUID):
            """Get the output of an action invocation

            This returns just the "output" component of the action invocation. If the
            output is a file, it will return the file.
            """
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    )
                if not invocation.output:
                    raise HTTPException(
                        status_code=503,
                        detail="No result is available for this invocation",
                    )
                if hasattr(invocation.output, "response") and callable(
                    invocation.output.response
                ):
                    # TODO: honour "accept" header
                    return invocation.output.response()
                return invocation.output

        @app.delete(
            ACTION_INVOCATIONS_PATH + "/{id}",
            response_model=None,
            responses={
                200: {
                    "description": "Cancel request sent",
                },
                404: {"description": "Invocation ID not found"},
                503: {"description": "Invocation may not be cancelled"},
            },
        )
        def delete_invocation(id: uuid.UUID) -> None:
            """Cancel an action invocation"""
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    )
                if invocation.status not in [
                    InvocationStatus.RUNNING,
                    InvocationStatus.PENDING,
                ]:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"The invocation is {invocation.status} "
                            "and may not be cancelled."
                        ),
                    )
                invocation.cancel()

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}/files",
            responses={
                404: {"description": "Invocation ID not found"},
                503: {"description": "No files are available for this invocation"},
            },
        )
        def action_invocation_files(id: uuid.UUID) -> list[str]:
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    )
                if not invocation._file_manager:
                    raise HTTPException(
                        status_code=503,
                        detail="No files are available for this invocation",
                    )
                return invocation._file_manager.filenames

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}/files/{filename}",
            response_class=FileResponse,
            responses={
                404: {"description": "Invocation ID not found, or file not found"},
                503: {"description": "No files are available for this invocation"},
            },
        )
        def action_invocation_file(id: uuid.UUID, filename: str):
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    )
                if not invocation._file_manager:
                    raise HTTPException(
                        status_code=503,
                        detail="No files are available for this invocation",
                    )
                return FileResponse(invocation._file_manager.path(filename))
