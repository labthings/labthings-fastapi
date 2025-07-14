.. _blobs:

Blob input/output
=================

`.Blob` objects allow binary data to be returned by an Action. This binary data can be passed between Things, or between Things and client code. Using a `.Blob` object allows binary data to be efficiently sent over HTTP if required, and allows the same code to run either on the server (without copying the data) or on a client (where data is transferred over HTTP).

If interactions require only simple data types that can easily be represented in JSON, very little thought needs to be given to data types - strings and numbers will be converted to and from JSON automatically, and your Python code should only ever see native Python datatypes whether it's running on the server or a remote client. However, if you want to transfer larger data objects such as images, large arrays or other binary data, you will need to use a `.Blob` object.

`.Blob` objects are not part of the Web of Things specification, which doesn't give much consideration to returning large or complicated datatypes. In LabThings-FastAPI, the `.Blob` mechanism is intended to provide an efficient way to work with arbitrary binary data. If it's used to transfer data between two Things on the same server, the data should not be copied or otherwise iterated over - and when it must be transferred over the network it can be done using a binary transfer, rather than embedding in JSON with base64 encoding.

A `.Blob` consists of some data and a MIME type, which sets how the data should be interpreted. It is best to create a subclass of `.Blob` with the content type set: this makes it clear what kind of data is in the `.Blob`. In the future, it might be possible to add functionality to `.Blob` subclasses, for example to make it simple to obtain an image object from a `.Blob` containing JPEG data. However, this will not currently work across both client and server code.

Creating and using `.Blob` objects
------------------------------------------------

Blobs can be created from binary data that is in memory (a `bytes` object) with `.Blob.from_bytes`, on disk (with `.Blob.from_temporary_directory` or `.Blob.from_file`), or using a URL as a placeholder. The intention is that the code that uses a `.Blob` should not need to know which of these is the case, and should be able to use the same code regardless of how the data is stored. 

Blobs offer three ways to access their data:

* A `bytes` object, obtained via the `.Blob.data` property. For blobs created with a `bytes` object, this simply returns the original data object with no copying. If the data is stored in a file, the file is opened and read when the `.Blob.data` property is accessed. If the `.Blob` references a URL, it is retrieved and returned when `.Blob.data` is accessed.
* An `.Blob.open` method providing a file-like object. This returns a `~io.BytesIO` wrapper if the `.Blob` was created from a `bytes` object or the file if the data is stored on disk. URLs are retrieved, stored as `bytes` and returned wrapped in a :class:`~io.BytesIO` object. 
* A `.Blob.save` method will either save the data to a file, or copy the existing file on disk. This should be more efficient than loading `.Blob.data` and writing to a file, if the `.Blob` is pointing to a file rather than data in memory. 

The intention here is that `.Blob` objects may be used identically with data in memory or on disk or even at a remote URL, and the code that uses them should not need to know which is the case.

Examples
--------

A camera might want to return an image as a `.Blob` object. The code for the action might look like this:

.. code-block:: python

    import labthings_fastapi as lt

    class JPEGBlob(lt.blob.Blob):
        content_type = "image/jpeg"

    class Camera(lt.Thing):
        @lt.thing_action
        def capture_image(self) -> JPEGBlob:
            # Capture an image and return it as a Blob
            image_data = self._capture_image()  # This returns a bytes object holding the JPEG data
            return JPEGBlob.from_bytes(image_data)

The corresponding client code might look like this:

.. code-block:: python

    from PIL import Image
    from labthings_fastapi import ThingClient

    camera = ThingClient.from_url("http://localhost:5000/camera/")
    image_blob = camera.capture_image()
    image_blob.save("captured_image.jpg")  # Save the image to a file

    # We can also open the image directly with PIL
    with image_blob.open() as f:
        img = Image.open(f)
    img.show()  # This will display the image in a window

Using `.Blob` objects as inputs
--------------------------------------

`.Blob` objects may be used as either the input or output of an action. There are relatively few good use cases for `.Blob` inputs to actions, but a possible example would be image capture: one action could perform a quick capture of raw data, and another action could convert the raw data into a useful image. The output of the capture action would be a `.Blob` representing the raw data, which could be passed to the conversion action. 

Because `.Blob` outputs are represented in JSON as links, they are downloaded with a separate HTTP request if needed. There is currently no way to create a `.Blob` on the server via HTTP, which means remote clients can use `.Blob` objects provided in the output of actions but they cannot yet upload data to be used as input. However, it is possible to pass the URL of a `.Blob` that already exists on the server as input to a subsequent Action. This means, in the example above of raw image capture, a remote client over HTTP can pass the raw `.Blob` to the conversion action, and the raw data need never be sent over the network.

We could define a more sophisticated camera that can capture raw images and convert them to JPEG, using two actions:

.. code-block:: python

    import labthings_fastapi as lt

    class JPEGBlob(lt.Blob):
        content_type = "image/jpeg"

    class RAWBlob(lt.Blob):
        content_type = "image/x-raw"

    class Camera(lt.Thing):
        @lt.thing_action
        def capture_raw_image(self) -> RAWBlob:
            # Capture a raw image and return it as a Blob
            raw_data = self._capture_raw_image()  # This returns a bytes object holding the raw data
            return RAWBlob.from_bytes(raw_data)
        
        @lt.thing_action
        def convert_raw_to_jpeg(self, raw_blob: RAWBlob) -> JPEGBlob:
            # Convert a raw image Blob to a JPEG Blob
            jpeg_data = self._convert_raw_to_jpeg(raw_blob.data)  # This returns a bytes object holding the JPEG data
            return JPEGBlob.from_bytes(jpeg_data)
        
        @lt.thing_action
        def capture_image(self) -> JPEGBlob:
            # Capture an image and return it as a Blob
            raw_blob = self.capture_raw_image()  # Capture the raw image
            jpeg_blob = self.convert_raw_to_jpeg(raw_blob)  # Convert the raw image to JPEG
            return jpeg_blob  # Return the JPEG Blob
            # NB the `raw_blob` is not retained after this action completes, so it will be garbage collected

On the client, we can use the `capture_image` action directly (as before), or we can capture a raw image and convert it to JPEG:

.. code-block:: python

    from PIL import Image
    from labthings_fastapi import ThingClient

    camera = ThingClient.from_url("http://localhost:5000/camera/")
    
    # Capture a JPEG image directly
    jpeg_blob = camera.capture_image()
    jpeg_blob.save("captured_image.jpg")

    # Alternatively, capture a raw image and convert it to JPEG
    raw_blob = camera.capture_raw_image() # NB the raw image is not yet downloaded
    jpeg_blob = camera.convert_raw_to_jpeg(raw_blob)
    jpeg_blob.save("converted_image.jpg")

    raw_blob.save("raw_image.raw")  # Download and save the raw image to a file

HTTP interface and serialization
--------------------------------

`.Blob` objects are subclasses of `pydantic.BaseModel`, which means they can be serialized to JSON and deserialized from JSON. When this happens, the `.Blob` is represented as a JSON object with `.Blob.url` and `.Blob.content_type` fields. The `.Blob.url` field is a link to the data. The `.Blob.content_type` field is a string representing the MIME type of the data. It is worth noting that models may be nested: this means an action may return many `.Blob` objects in its output, either as a list or as fields in a `pydantic.BaseModel` subclass. Each `.Blob` in the output will be serialized to JSON with its URL and content type, and the client can then download the data from the URL, one download per `.Blob` object.

When a `.Blob` is serialized, the URL is generated with a unique ID to allow it to be downloaded. The URL is not guaranteed to be permanent, and should not be used as a long-term reference to the data. For `.Blob` objects that are part of the output of an action, the URL will expire after 5 minutes (or the retention time set for the action), and the data will no longer be available for download after that time.

In order to run an action and download the data, currently an HTTP client must:

* Call the action that returns a `.Blob` object, which will return a JSON object representing the invocation.
* Poll the invocation until it is complete, and the `.Blob` is available in its ``output`` property with the URL and content type.
* Download the data from the URL in the `.Blob` object, which will return the binary data.

It may be possible to have actions return binary data directly in the future, but this is not yet implemented.

.. note::

    Serialising or deserialising `.Blob` objects requires access to the `.BlobDataManager` associated with the `.ThingServer`. As there is no way to pass this in to the relevant methods at serialisation/deserialisation time, we use context variables to access them. This means that a `.blob_serialisation_context_manager` should be used to set (and then clear) those context variables. This is done by the `.BlobIOContextDep` dependency on the relevant endpoints (currently any endpoint that may return the output of an action).


Memory management and retention
-------------------------------

Management of `.Blob` objects is currently very basic: when a `.Blob` object is returned in the output of an Action that has been called via the HTTP interface, it will be retained as long as the action's output. This may be set on each action, and defaults to 5 minutes. This should be improved in the future to avoid memory management issues. 

When a `.Blob` is serialized, a URL is generated with a unique ID to allow it to be downloaded. However, only a weak reference is held to the `.Blob`. Once an Action has finished running, the only strong reference to the `.Blob` should be held by the output property of the action invocation. The `.Blob` should be garbage collected once the output is no longer required, i.e. when the invocation is discarded - currently 5 minutes after the action completes, once the maximum number of invocations has been reached or when it is explicitly deleted by the client.

The behaviour is different when actions are called from other actions. If `action_a` calls `action_b`, and `action_b` returns a `.Blob`, that `.Blob` will be subject to Python's usual garbage collection rules when `action_a` ends - i.e. it will not be retained unless it is included in the output of `action_a`.


