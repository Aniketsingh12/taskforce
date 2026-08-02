"""Run the content pipeline end to end from the command line.

    python demo.py "How AI agents are changing freelance work"

Uses the built-in `mock` provider, so it works with no Ollama and no API keys —
the same path the live UI uses, printed to the terminal with the full trace.
"""

from __future__ import annotations

import asyncio
import sys

from app.orchestration import CONTENT_PIPELINE, Orchestrator


async def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "The rise of multi-agent AI systems"

    async def emit(event: dict) -> None:
        etype = event["type"]
        if etype == "agent_started":
            print(f"\n\n=== > {event['role']} ===")
        elif etype == "token":
            print(event["text"], end="", flush=True)
        elif etype == "run_completed":
            run = event["run"]
            print("\n\n--- RUN SUMMARY ---")
            print(f"Status: {run['status']}")
            print(f"Total tokens: {run['total_tokens']}  Cost: ${run['total_cost']}")
            for t in run["traces"]:
                print(
                    f"  {t['agent_role']:<10} | {t['model_used']:<28} | "
                    f"{t['latency_ms']:>5}ms | tools={t['tools_called']}"
                )
        elif etype == "run_failed":
            print(f"\n\nRUN FAILED: {event['error']}")

    await Orchestrator().run_workflow(CONTENT_PIPELINE, topic, emit=emit)


if __name__ == "__main__":
    asyncio.run(main())
