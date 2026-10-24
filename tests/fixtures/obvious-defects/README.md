# Deliberately flawed HTTP service

This teaching repository represents a production Flask service with intentional
DevOps mistakes. Never deploy it. Install Python 3.11 or newer and run:

```sh
python -m pip install -r requirements.txt
python -m pytest
```

The service returns `{"status": "ok"}` from GET /health. The Dockerfile is the
declared deployment configuration. Production configuration lives in config.py;
DATA_DIRECTORY is intended to point to the host's persistent data directory.

See CONTRIBUTING.md, SECURITY.md, and LICENSE for policies. This fixture contains
no credentials. Intentional defects are recorded outside the repository root.
