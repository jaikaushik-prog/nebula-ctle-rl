"""
llm/client.py — the Anthropic client, made **optional**.

WHY OPTIONAL
-------------
`NEXT_STEPS.md` step 7: *"Keep a deterministic offline fallback so CI and the
live demo do not depend on a network call."* Two reasons, and the second is the
one that matters on 25 September:

* the test suite must not need a key or a network, and
* **a live demo in front of a panel must not depend on the venue's wifi.**

So `anthropic` is not a dependency of this project. Everything in `nebula/llm/`
works without it; the LLM is an enhancement to the wording, never a link in the
chain that produces a number.

WHAT THE MODEL IS AND IS NOT ALLOWED TO DO
--------------------------------------------
`CLAUDEwa.md` §2 asks for *"LLM-based human interaction with a wrapper"*, and
§2's own objective says **"with zero human intervention"** in the DESIGN. Those
two only coexist if the LLM stays outside the sizing loop, so it does:

    ALLOWED    natural language  ->  a validated (peaking, f_peak) request
    ALLOWED    a finished result ->  prose, with every number checked
    FORBIDDEN  choosing a sizing, steering the search, picking a method,
               deciding whether a spec is met

An LLM in the optimiser would undercut the entry's own claim, and nothing here
gives it that opportunity: `spec_parse` returns a `SpecTarget` that
`nebula.design` then treats exactly like one typed on the command line.
"""

from __future__ import annotations

import os
from typing import Any, Optional

#: The model every call here uses. Opus 5 is the current default; the wrapper
#: does no long-horizon reasoning, so `effort` is dialled down per call rather
#: than the model being downgraded.
MODEL: str = "claude-opus-5"


class LlmUnavailable(RuntimeError):
    """No usable Anthropic client. **Always recoverable** -- every caller in
    this package falls back to its deterministic path."""


def available() -> bool:
    """Is an LLM path usable at all? Never raises."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or _has_profile())


def _has_profile() -> bool:
    """An `ant auth login` profile counts as credentials — the SDK resolves
    it with no environment variable set."""
    from pathlib import Path

    return (Path.home() / ".config" / "anthropic").is_dir()


def get_client(client: Optional[Any] = None) -> Any:
    """An Anthropic client, or `LlmUnavailable`. `client` is for tests."""
    if client is not None:
        return client
    try:
        import anthropic
    except ImportError as exc:
        raise LlmUnavailable(
            "the `anthropic` package is not installed. This is not a failure: "
            "nebula/llm/ has a deterministic offline path for every call, and "
            "`pip install anthropic` only improves the wording."
        ) from exc
    try:
        return anthropic.Anthropic()
    except Exception as exc:                                # pragma: no cover
        raise LlmUnavailable(f"could not construct a client: {exc}") from exc


def ask_json(prompt: str, schema: dict, system: str,
             client: Optional[Any] = None, max_tokens: int = 1024) -> dict:
    """One structured-output call. Returns the parsed object.

    `output_config.format` constrains the response to the schema, so the
    result parses without a repair loop. `effort` is `low` because this is a
    short extraction, not reasoning -- the wrapper never asks the model to
    think about circuits.
    """
    import json

    c = get_client(client)
    resp = c.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def ask_text(prompt: str, system: str, client: Optional[Any] = None,
             max_tokens: int = 1024) -> str:
    """One plain-text call. The caller is responsible for grounding it."""
    c = get_client(client)
    resp = c.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"},
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


__all__ = ["MODEL", "LlmUnavailable", "available", "get_client", "ask_json",
           "ask_text"]
