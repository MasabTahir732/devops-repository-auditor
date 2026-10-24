"""Check local prerequisites; --live makes one small real LLM tool request."""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import ConfigError, Settings  # noqa: E402
from llm_client import LLMError, create_client  # noqa: E402
from safety import redact_text  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make one small real API request")
    parser.add_argument("--provider", choices=["gemini", "groq", "openai"])
    parser.add_argument("--model")
    parser.set_defaults(max_steps=None, timeout=None, clone_timeout=None)
    args = parser.parse_args(argv)
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 11):  # noqa: UP036 -- useful prerequisite diagnostic
        print("FAIL: Python 3.11 or newer is required.")
        return 1
    if not shutil.which("git"):
        print("FAIL: Install Git and reopen your terminal.")
        return 1
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True, timeout=10)
        print("Git: available")
        for name in ["openai", "python-dotenv"]:
            print(f"{name}: {importlib.metadata.version(name)}")
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        settings = Settings.from_environment(args)
        print(f"Provider: {settings.provider}; model: {settings.model}")
        print("API key: configured (value hidden)")
        if not args.live:
            print(
                "Local setup passed. API credentials, quota, and model access have not been verified."
            )
            print("Use --live for one small tool-call check.")
            return 0
        schema = {
            "type": "function",
            "name": "setup_ping",
            "strict": True,
            "description": "Confirm the connection by setting message to ready.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string", "enum": ["ready"]}},
                "required": ["message"],
                "additionalProperties": False,
            },
        }
        response = create_client(settings).respond(
            [
                {
                    "role": "system",
                    "content": "Call setup_ping with message ready. No other response is needed.",
                },
                {"role": "user", "content": "Check tool calling."},
            ],
            [schema],
        )
        if not response.calls or response.calls[0].name != "setup_ping":
            print("FAIL: Provider responded but did not return the expected tool call.")
            return 1
        print("Live API/tool-call check passed. This did not run a repository audit.")
        return 0
    except importlib.metadata.PackageNotFoundError:
        print("FAIL: Install dependencies: python -m pip install -r requirements.txt")
    except (ConfigError, LLMError, OSError, subprocess.SubprocessError) as exc:
        print("FAIL: " + redact_text(str(exc)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
