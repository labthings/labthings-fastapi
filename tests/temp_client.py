# TODO: tidy the functions below into a client library
import time


ACTION_RUNNING_KEYWORDS = ["idle", "pending", "running"]


def get_link(obj: dict, rel: str) -> str:
    """Retrieve a link from an object's `links` list, by its `rel` attribute"""
    return next(link for link in obj["links"] if link["rel"] == rel)


def task_href(t):
    """Extract the endpoint address from a task dictionary"""
    return get_link(t, "self")["href"]


def poll_task(client, task, interval=0.001):
    """Poll a task until it finishes, and return the return value"""
    if "status" not in task:
        raise ValueError(f"task has no status: {task}")
    first_run = True
    while task["status"] in ACTION_RUNNING_KEYWORDS:
        if first_run:
            first_run = False
        else:
            time.sleep(interval)
        r = client.get(task_href(task))
        r.raise_for_status()
        task = r.json()
    return task
