
"""
llm/spec_parse.py — natural language in, a **validated** `SpecTarget` out.

    "I need about 9 dB of peaking with the peak near 1.9 GHz"
        -> SpecTarget(peaking_db=9.0, f_peak_hz=1.9e9)

TWO PATHS, ONE VALIDATOR
-------------------------
The offline path is a regex; the LLM path is one structured-output call. **Both
end at the same `SpecTarget` constructor**, which refuses anything outside S3's
band. So the worst an LLM misreading can do is produce a *different legal
request* -- it can never widen the spec, and it can never hand the sizing loop
a target the spec table does not permit.

That is the whole safety argument for putting a language model in front of this
project, and it is one line of code: the validator is not in the prompt, it is
in the type.

THE OFFLINE PATH IS THE DEFAULT AND IT IS NOT A STUB
------------------------------------------------------
It handles what a designer actually types -- "9 dB at 1.9 GHz", "peak around
2 GHz with 6 dB of boost", "1900 MHz, 10dB" -- because unit-tagged numbers are
what an engineer writes. It is used whenever `anthropic` is missing, no
credentials are set, or the API call fails, and the result records which path
ran so a demo never silently claims to have used a model it did not reach.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.llm import client as C
from nebula.rl.spec_dist import LEGACY_TARGET, SpecTarget

#: dB with its unit attached. `(?i)` because "10DB" and "10 db" both happen.
_DB = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:d\s*b|decibels?)\b", re.I)

#: A frequency with a scale word. Hz is included so "1900000000 Hz" parses.
_FREQ = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*(ghz|mhz|khz|hz)\b", re.I)

_SCALE = {"ghz": 1e9, "mhz": 1e6, "khz": 1e3, "hz": 1.0}


@dataclass(frozen=True)
class ParsedRequest:
    """What a request turned into, and how."""

    target: SpecTarget
    source: str                  # "regex" | "llm" | "default"
    raw: str
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"peaking_db": self.target.peaking_db,
                "f_peak_hz": self.target.f_peak_hz,
                "f_peak_ghz": self.target.f_peak_hz / 1e9,
                "parsed_by": self.source, "request": self.raw,
                "notes": list(self.notes)}


class SpecOutOfRange(ValueError):
    """The request named a legal-looking number outside S3."""


def _clamp_note(name: str, value: float, lo: float, hi: float,
                unit: str) -> str:
    return (f"{name} {value:g} {unit} is outside S3's {lo:g}-{hi:g} {unit}; "
            f"the request was REFUSED rather than clamped")


def parse_offline(text: str) -> ParsedRequest:
    """Regex. Deterministic, no network, no key. **The default path.**

    Missing fields fall back to the window centre -- the same `LEGACY_TARGET`
    every published run used -- and say so in `notes`, because a demo that
    silently invents half a request is worse than one that says what it
    assumed.
    """
    notes: list[str] = []
    db_m = _DB.search(text)
    f_m = _FREQ.search(text)

    if db_m:
        peaking = float(db_m.group(1))
    else:
        peaking = LEGACY_TARGET.peaking_db
        notes.append(f"no peaking found in the request; assumed the band "
                     f"centre, {peaking:g} dB")

    if f_m:
        f_hz = float(f_m.group(1)) * _SCALE[f_m.group(2).lower()]
    else:
        f_hz = LEGACY_TARGET.f_peak_hz
        notes.append("no peak frequency found in the request; assumed the "
                     "window centre")

    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    if not (lo_db <= peaking <= hi_db):
        raise SpecOutOfRange(_clamp_note("peaking", peaking, lo_db, hi_db, "dB"))
    if not (lo_hz <= f_hz <= hi_hz):
        raise SpecOutOfRange(_clamp_note("peak frequency", f_hz / 1e9,
                                         lo_hz / 1e9, hi_hz / 1e9, "GHz"))
    return ParsedRequest(SpecTarget(peaking_db=peaking, f_peak_hz=f_hz),
                         "regex", text, tuple(notes))


_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "peaking_db": {"type": "number",
                       "description": "HF peaking in dB, 3 to 12"},
        "f_peak_hz": {"type": "number",
                      "description": "peak frequency in HERTZ, 1.25e9 to 2.5e9"},
        "peaking_stated": {"type": "boolean",
                           "description": "true if the user gave a peaking"},
        "f_peak_stated": {"type": "boolean",
                          "description": "true if the user gave a frequency"},
    },
    "required": ["peaking_db", "f_peak_hz", "peaking_stated", "f_peak_stated"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You extract a CTLE equaliser specification from a designer's sentence. "
    "You do NOT design anything, choose any component value, or judge whether "
    "a request is achievable -- a SPICE-in-the-loop optimiser does that "
    "afterwards.\n"
    "Return the peaking in dB and the peak frequency in HERTZ (so 1.9 GHz is "
    "1900000000). S3's legal band is 3-12 dB with the peak in 1.25-2.5 GHz. "
    "If the user names a value outside that, return it ANYWAY and unchanged -- "
    "the caller refuses out-of-range requests explicitly and must be allowed "
    "to. Never silently move a number into range.\n"
    "If the user did not state one of the two, set its *_stated flag false and "
    "put the centre of the legal band in the field (7.5 dB, 1767766952 Hz)."
)


def parse_llm(text: str, client: Optional[Any] = None) -> ParsedRequest:
    """One structured-output call, then **the same validator as the regex.**"""
    data = C.ask_json(f"Designer's request:\n{text}", _SCHEMA, _SYSTEM,
                      client=client)
    notes: list[str] = []
    if not data.get("peaking_stated", True):
        notes.append("the model judged no peaking was stated; the band centre "
                     "was used")
    if not data.get("f_peak_stated", True):
        notes.append("the model judged no peak frequency was stated; the "
                     "window centre was used")
    peaking = float(data["peaking_db"])
    f_hz = float(data["f_peak_hz"])

    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    if not (lo_db <= peaking <= hi_db):
        raise SpecOutOfRange(_clamp_note("peaking", peaking, lo_db, hi_db, "dB"))
    if not (lo_hz <= f_hz <= hi_hz):
        raise SpecOutOfRange(_clamp_note("peak frequency", f_hz / 1e9,
                                         lo_hz / 1e9, hi_hz / 1e9, "GHz"))
    return ParsedRequest(SpecTarget(peaking_db=peaking, f_peak_hz=f_hz),
                         "llm", text, tuple(notes))


def parse_request(text: str, use_llm: bool = False,
                  client: Optional[Any] = None) -> ParsedRequest:
    """The entry point. `use_llm` opts IN; the regex is the default.

    **An out-of-range request is never retried offline.** If the model read
    "20 dB" correctly, falling back to a regex that reads the same 20 dB and
    raises the same error is noise; and if it read it wrongly, quietly trying
    another parser until one succeeds is how a demo answers a question nobody
    asked. Only an infrastructure failure -- no package, no key, no network --
    falls back.
    """
    if not use_llm:
        return parse_offline(text)
    try:
        return parse_llm(text, client=client)
    except (C.LlmUnavailable, ImportError) as exc:
        out = parse_offline(text)
        return ParsedRequest(out.target, out.source, out.raw,
                             out.notes + (f"the LLM path was unavailable "
                                          f"({exc.__class__.__name__}); parsed "
                                          f"offline instead",))


__all__ = ["ParsedRequest", "SpecOutOfRange", "parse_request", "parse_offline",
           "parse_llm"]
