# LabThings-FastAPI Examples

The files in this folder are example code that was used in development and may be helpful to users. It's not currently tested, so there are no guarantees as to how current each example is. Some of them have been moved into `/tests/` and those ones do get checked: at some point in the future a combined documentation/testing system might usefully deduplicate this.

To run the `demo_thing_server` example, you need to have `labthings_fastapi` installed (we recommend in a virtual environment, see the top-level README), and then do

```shell
cd examples/
uvicorn demo_thing_server:thing_server.app --reload --reload-dir=..
```

The two arguments starting `--reload` will reload the demo if anything changes in the repository, which is useful for development (if you've previously installed the repository as editable) but not necessary if you just want to play with the demo.
