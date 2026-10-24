"""Required unattended CLI: python agent.py --repo URL --output report.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_loop import AgentError, run_audit
from config import ConfigError, Settings
from llm_client import LLMError, create_client
from reporting import ReportError, write_report
from repository import RepositoryError, cloned_repository, normalize_repo_url
from safety import redact_text
from tools import InspectionTools
from tracing import Trace


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Audit a public GitHub repository using an LLM tool loop."
    )
    result.add_argument(
        "--repo", required=True, help="Public https://github.com/owner/repository URL"
    )
    result.add_argument("--output", required=True, type=Path, help="Destination JSON report")
    result.add_argument("--trace", type=Path, help="Optional redacted JSONL tool trace")
    result.add_argument(
        "--provider", choices=["gemini", "groq", "openai"], help="Override LLM_PROVIDER"
    )
    result.add_argument("--model", help="Override the selected provider's model")
    result.add_argument("--max-steps", help="Maximum model turns (default: 40)")
    result.add_argument("--timeout", help="LLM request timeout in seconds (default: 60)")
    result.add_argument("--clone-timeout", help="Git clone timeout in seconds (default: 120)")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    trace = None
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
        repository = normalize_repo_url(args.repo)
        if args.trace and args.trace.resolve() == args.output.resolve():
            raise ConfigError("--trace and --output must use different files.")
        settings = Settings.from_environment(args)
        client = create_client(settings)
        trace = Trace(args.trace)
        trace.write(
            "start",
            repository=repository,
            provider=settings.provider,
            model=settings.model,
            max_steps=settings.max_steps,
        )
        print("Inspecting repository; this may require multiple LLM requests.", file=sys.stderr)
        with cloned_repository(repository, timeout=settings.clone_timeout) as root:
            inspection = InspectionTools(root)
            report = run_audit(
                repository, inspection, client, max_steps=settings.max_steps, trace=trace
            )
        write_report(report, args.output)
        trace.write("completed", findings=len(report["violations"]))
        print(
            f"Audit completed: {len(report['violations'])} finding(s); JSON report written.",
            file=sys.stderr,
        )
        return 0
    except (ConfigError, RepositoryError, AgentError, LLMError, ReportError, OSError) as exc:
        message = redact_text(str(exc))
        if trace:
            try:
                trace.write("fatal_error", error=message)
            except OSError:
                pass  # Preserve the original actionable failure if trace storage also failed.
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except ImportError:
        print(
            "Error: Missing dependencies. Run python -m pip install -r requirements.txt.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("Error: Audit interrupted; no new completed report was written.", file=sys.stderr)
        return 130
    finally:
        if trace:
            try:
                trace.close()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
