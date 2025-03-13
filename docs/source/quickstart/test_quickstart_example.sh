# cd to this directory
cd "${BASH_SOURCE%/*}/"
rm -rf .venv
# Override the virtual environment so we use the package
# from this repo, not from pypi
python -m venv .venv
source .venv/bin/activate
pip install ../../..
# Run the quickstart code in the background
bash "quickstart_example.sh" 2>&1 &
quickstart_example_pid=$!
echo "Spawned example with PID $quickstart_example_pid"

function killserver {
  # Stop the server that we spawned.
  children=$(ps -o pid= --ppid "$quickstart_example_pid")
  kill $children
  echo "Killed spawned processes: $children"

  wait
}
trap killserver EXIT

# Wait for it to respond
# Loop until the command is successful or the maximum number of attempts is reached
ret=7
attempt_num=0
while [[ $ret == 7 ]]; do  # && [ $attempt_num -le 50 ]
  # Execute the command
  ret=0
  curl -sf -m 10 http://localhost:5000/counter/counter || ret=$?
  if [[ $ret == 7 ]]; then
    echo "Curl didn't connect on attempt $attempt_num"

    # Check the example process hasn't died
    ps $quickstart_example_pid > /dev/null
    if [[ $? != 0 ]]; then
      echo "Child process (the server example) died without responding."
      exit -1
    fi

    attempt_num=$(( attempt_num + 1 ))
    sleep 1
  fi
done
echo "Final return value $ret on attempt $attempt_num"

if [[ $ret == 0 ]]; then
    echo "Success"
else
    echo "Curl returned $ret, likely something went wrong."
    exit -1
fi

# Check the Python client code
echo "Running Python client code"
(source .venv/bin/activate && python counter_client.py)
if [[ $? != 0 ]]; then
  echo "Python client code did not run OK."
  exit -1
fi
