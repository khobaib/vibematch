# VibeMatch backend — Task #10 (DECISIONS_LOG.md), Fly.io deployment.
#
# Slim base image, not full python:3.x, to keep image size/build time down —
# this service has no need for anything beyond the interpreter + pip wheels.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first, separately from app code, so Docker's layer
# cache reuses this step on every future deploy where requirements.txt
# hasn't changed (the common case) — only the (fast) COPY + no-op layer
# below re-runs, not a full dependency reinstall.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + data files. hostels.json and hostel_embeddings.json are baked
# into the image deliberately (see DECISIONS_LOG.md "Data storage" decision
# — flat-file source of truth, not a live database yet) rather than mounted
# as a volume: they're read-only at runtime and small enough (a few MB) that
# rebuilding the image on every data update is the simplest correct choice
# at this stage, not a workaround.
COPY . .

# Fly.io's internal_port in fly.toml must match this. 8000 matches the
# existing local dev convention (uvicorn main:app --reload, README.md).
EXPOSE 8000

# --host 0.0.0.0 is required inside a container — the default 127.0.0.1
# only accepts connections from inside the container itself, which would
# make the service unreachable from Fly.io's network. No --reload here
# (that's a dev-only convenience flag); production runs the app as-is.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
