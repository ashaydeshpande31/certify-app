# Read automatically by gunicorn from the project folder, so these settings apply
# no matter what the Start Command on Render says.
import os

# One process keeps memory low on Render's free plan; the threads let it serve
# several people at once (most requests wait on Google or the database).
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
threads = int(os.environ.get("GUNICORN_THREADS", 8))
worker_class = "gthread"
timeout = 120
keepalive = 5
# Restart a worker now and then so memory never creeps up.
max_requests = 1000
max_requests_jitter = 100
