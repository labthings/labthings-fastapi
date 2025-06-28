echo "Setting up environemnt"
# BEGIN venv
python -m venv .venv --prompt labthings
source .venv/bin/activate  # or .venv/Scripts/activate on Windows
# END venv
echo "Installing labthings-fastapi"
# BEGIN install
pip install labthings-fastapi
# END install
echo "running example"
# BEGIN serve
python counter.py
# END serve
echo $! > example_server.pid
