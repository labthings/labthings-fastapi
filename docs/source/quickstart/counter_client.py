from labthings_fastapi.client import ThingClient

counter = ThingClient.from_url("http://localhost:5000/counter/")

v = counter.counter
print(f"The counter value was {v}")

counter.increment_counter()

v = counter.counter
print(f"After incrementing, the counter value was {v}")
