# Healthy arithmetic fixture

A dependency-free Python teaching library. This is an audit evaluation fixture,
not a production service. It has no deployment, container, or publishing workflow.
Dependencies and optional development tools are declared in `pyproject.toml`.
A requirements.txt file is unnecessary for this packaging approach.

## Development

Use Python 3.11 or newer, create a virtual environment, then run:

```sh
python -m pip install -e '.[dev]'
python -m ruff check .
python -m pytest
```

## Usage

```python
from tiny_math import add
assert add(2, 3) == 5
```

CI runs lint and tests for pushes and pull requests with read-only permissions.
The repository contains no credentials and needs no environment configuration.
See CONTRIBUTING.md, SECURITY.md, and LICENSE for project policies.
