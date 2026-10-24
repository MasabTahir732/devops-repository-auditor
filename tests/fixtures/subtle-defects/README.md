# Subtle configuration fixture

A Python teaching package representing a production configuration module. It has
no container or publishing workflow. Dependencies are managed by pyproject.toml;
a requirements.txt file is unnecessary. Never deploy this deliberate fixture.

## Local development

Use Python 3.11 or newer. Install the development extra, then test:

```sh
python -m pip install -e '.[dev]'
python -m pytest
```

DEBUG should be false in production; see .env.example. The CI workflow verifies
pull requests. Review both event permissions and the source of checked-out code.
No secrets are included. See CONTRIBUTING.md, SECURITY.md, and LICENSE.
