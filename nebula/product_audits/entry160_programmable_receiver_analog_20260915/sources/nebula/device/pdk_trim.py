"""
device/pdk_trim.py — make an ngspice invocation pay only for what it uses.

WHY THIS FILE EXISTS
--------------------
Session 17 measured that **99.7 % of a training run is the simulator**, so
per-evaluation SPICE cost is the single largest lever on this project. The
extended library (G58) cost **2.07 s per evaluation against the nfet-only
trim's ~0.33 s**, and PASSIVES.md §6 item 6 has listed the fix as open since
session 15.

THE COST WAS NOT WHERE FOUR SESSIONS OF NOTES SAID IT WAS
----------------------------------------------------------
The standing explanation, in G70 and PASSIVES.md §3.2, was that the R/C corner
files "pull in `parameters/typical.spice` (3023 lines) and `invariant.spice`
(7340)". Measured, both halves are wrong:

  * **`invariant.spice` is not in the include tree at all.** Only
    `parameters/montecarlo.spice` includes it, and no section this project
    uses reaches that.
  * **`typical.spice` is real but minor.** It defines 8,909 named parameters,
    of which the library references **86**. Deleting the other 8,823 is worth
    about **1.5x**.

The actual cause, found by ablating the include list and then the file itself:

    **ngspice expands EVERY `.lib` section in a file, not just the one asked
    for.** Same netlist, same machine:

        extended library, one section extracted    0.093 s
        extended library, the real 25-section file 1.386 s   <- 15x
        nfet-only library, the real 5-section file 0.297 s

The cost scales with the **section count**, not with what the netlist uses.
The extended library grew to 25 sections the day G58 added the 5x5 (MOS x
passive) corner cross product, and its per-evaluation cost went with it. This
was invisible to every previous measurement because they all compared whole
libraries against each other, never a library against itself with one section
removed.

WHAT THIS MODULE GENERATES, into `spice/pdk_trim/`
---------------------------------------------------
  * `<corner>.trim.spice` — one per R/C parameter deck, holding only the
    `.param` lines reachable from the library's model cards, PDK order kept;
  * `<corner>.spice` — the PDK's r+c corner file with exactly one line
    changed: `.include "../parameters/<x>.spice"` now points at the trim;
  * `sections/<library>__<sect>.lib.spice` — every `.lib` section of both
    trimmed libraries, alone in its own file. `sky130_runner.lib_for_device`
    selects one of these and falls back to the monolithic library if it is
    missing, so an un-regenerated tree still runs, just slowly.

RULE 9 (ONE DEFINITION, NEVER REDECLARED) IS THE WHOLE DESIGN HERE
------------------------------------------------------------------
Nothing in `pdk_trim/` is hand-written and no number is copied. Every
generated file is a pure function of the PDK files plus the monolithic
libraries, and `test_pdk_trim.py` re-derives all forty on every run and fails
on a single differing byte. The consumer set is read out of the library's own
include list, so **adding a device to the library automatically widens the
keep-set** and the regeneration test goes red until someone reruns this
module. That is what stops the trim from silently going stale — the G32
failure, where the file a human reads is not the one that produced the
numbers.

    python -m nebula.device.pdk_trim            # report, write nothing
    python -m nebula.device.pdk_trim --write    # regenerate spice/pdk_trim/

EQUIVALENCE IS NOT ASSUMED
--------------------------
`test_pdk_trim.py` runs a probe exercising every device the netlists use — the
nfet, both generic poly families, five fixed-width variants of each, the
`res_po` parasitic, the MIM, and routing capacitors that make the kept
parameters load-bearing — through the untrimmed library and the trimmed one,
and compares the **raw printed text** at rel=0, abs=0 (G36's precedent, and
PASSIVES.md §3.1 on not parsing to float first). Further tests do the same for
the one-section split, and a `slow`-marked pair against the FULL SKY130
library. `experiments/lib_cost.py` re-checks equivalence on 50 real designs
through `run_point` and exits non-zero if a number moved.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Where things are.
# ─────────────────────────────────────────────────────────────────────────────

SPICE_DIR: Path = Path(__file__).resolve().parent / "spice"

#: The extended library whose include list DEFINES the consumer set. Reading
#: it rather than restating it is what makes the keep-set self-maintaining.
CTLE_LIB: Path = SPICE_DIR / "sky130_ctle.lib.spice"

#: Generated-section stem for D11's PFET-capable derivative. There is no
#: hand-maintained monolithic copy: `pfet_library_text` derives it from
#: `CTLE_LIB`, preserving rule 9's single definition.
PFET_STEM: str = "sky130_ctle_pfet"

#: Generated output. Tracked in git (G49: results are tracked), never edited.
TRIM_DIR: Path = SPICE_DIR / "pdk_trim"

PDK_NGSPICE: Path = Path(r"C:/Users/DELL/sky130A/libs.tech/ngspice")

#: The five R/C corner decks the 25 library sections draw on, and the
#: parameter file each one includes. Parsed from the PDK, not remembered —
#: `rc_corner_parameter_file` re-reads it, so a PDK update that repointed one
#: of these would be picked up rather than silently ignored.
RC_CORNERS: tuple[str, ...] = (
    "res_typical__cap_typical",
    "res_low__cap_low",
    "res_high__cap_high",
    "res_high__cap_low",
    "res_low__cap_high",
)

_INCLUDE = re.compile(r'^\s*\.include\s+"?([^"\s]+)"?', re.I)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_ASSIGN = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\s*=")
_PARAM_INCLUDE = re.compile(r'^\s*\.include\s+"?\.\./parameters/([^"\s]+)"?', re.I)


class PdkTrimError(RuntimeError):
    """The trim cannot be derived. Never degrade to a partial keep-set."""


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — resolve what the library actually includes.
# ─────────────────────────────────────────────────────────────────────────────


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError as exc:                                 # pragma: no cover
        raise PdkTrimError(f"cannot read {path}: {exc}") from exc


def rc_corner_parameter_file(corner: str) -> str:
    """The `parameters/<x>.spice` that PDK r+c deck `corner` includes.

    Read out of the PDK file. `res_high__cap_low` includes `fast.spice` and
    `res_low__cap_high` includes `slow.spice`, which is the opposite of what
    the names suggest and is exactly why this is parsed rather than tabulated.
    """
    src = PDK_NGSPICE / "r+c" / f"{corner}.spice"
    hits = [m.group(1) for m in
            (_PARAM_INCLUDE.match(ln) for ln in _read(src).splitlines()) if m]
    if len(hits) != 1:
        raise PdkTrimError(
            f"{src} includes {len(hits)} parameter decks ({hits}), expected 1. "
            f"The PDK layout changed; re-derive this module before trusting it.")
    return hits[0]


def _walk(path: Path, acc: "dict[Path, str]", stop: "set[Path]") -> None:
    path = path.resolve()
    if path in acc or path in stop:
        return
    acc[path] = _read(path)
    for line in acc[path].splitlines():
        m = _INCLUDE.match(line)
        if m:
            _walk((path.parent / m.group(1)), acc, stop)


def _library_include_tree(library_text: str, library_dir: Path) -> "dict[Path, str]":
    """Every file `library_text` reaches, minus generated/PDK parameter decks."""
    stop = {(PDK_NGSPICE / "parameters" / f"{p}.spice").resolve()
            for p in ("typical", "fast", "slow", "fast_70p", "slow_70p",
                      "invariant", "montecarlo", "critical", "lod")}
    stop |= {p.resolve() for p in TRIM_DIR.glob("*.trim.spice")}

    acc: "dict[Path, str]" = {}
    for line in library_text.splitlines():
        m = _INCLUDE.match(line)
        if m:
            included = Path(m.group(1))
            _walk(included if included.is_absolute()
                  else library_dir / included, acc, stop)
    return acc


def library_include_tree() -> "dict[Path, str]":
    """Every file `sky130_ctle.lib.spice` reaches, minus the parameter decks.

    The parameter decks — PDK and generated alike — are the thing being
    trimmed, so they are excluded from the tree that decides what to keep.
    Excluding the GENERATED ones too is what keeps this idempotent: running
    the generator against an already-trimmed library reproduces the same
    keep-set instead of shrinking it a second time.
    """
    acc = _library_include_tree(_read(CTLE_LIB), CTLE_LIB.parent)
    if not acc:
        raise PdkTrimError(f"{CTLE_LIB} resolved to no include files at all")
    return acc


#: Extra text scanned for parameter names on top of the library's own tree.
#: Netlists can reference a `.param` by name too, and a false negative here is
#: a wrong number rather than a loud failure — so this is deliberately
#: over-generous. Keeping a handful of parameters that turn out to be unused
#: costs microseconds; dropping one that is used costs a silent miscompare.
def _extra_reference_text() -> str:
    parts = [_read(p) for p in sorted(SPICE_DIR.glob("*.cir"))]
    here = Path(__file__).resolve().parent
    parts += [_read(here / n) for n in
              ("sky130_runner.py", "passives.py", "tail.py", "cap_probe.py")
              if (here / n).exists()]
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — decide which parameters survive.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParamLine:
    """One `.param` definition line: where it is, what it defines, what it uses."""

    index: int
    text: str
    names: "tuple[str, ...]"
    rhs: "frozenset[str]"


def parse_param_lines(text: str) -> "list[ParamLine]":
    """Split a parameter deck into definition lines.

    Only lines that are `.param ...` or a `+` continuation carrying at least
    one `name =` are returned; comments and the bare `.param` header are not
    definitions and are dropped by the trim.

    **The format assumption is checked, not assumed.** Every `+` line in the
    five decks this module trims begins with `name =` and has balanced quotes
    and braces, so a line is a self-contained group of assignments and can be
    re-emitted as its own `.param` card. A deck that violated that would have
    expressions spanning lines, and slicing it by line would corrupt them —
    hence the raise rather than a best effort.
    """
    out: "list[ParamLine]" = []
    for i, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        body = stripped.split(";")[0].rstrip()
        is_cont = body.startswith("+")
        if not (is_cont or body.lower().startswith(".param")):
            raise PdkTrimError(
                f"line {i + 1} is neither a comment, a .param nor a "
                f"continuation: {raw[:80]!r}")
        if body.count("'") % 2 or body.count("{") != body.count("}"):
            raise PdkTrimError(
                f"line {i + 1} has unbalanced quotes/braces, so it is not a "
                f"self-contained card and cannot be sliced: {raw[:80]!r}")
        if is_cont and not re.match(r"\+\s*[A-Za-z_][A-Za-z_0-9]*\s*=", body):
            raise PdkTrimError(
                f"line {i + 1} continues an expression rather than starting a "
                f"new assignment: {raw[:80]!r}")
        names = tuple(_ASSIGN.findall(body))
        if not names:
            continue                       # the bare `.param` header
        rhs = frozenset(_IDENT.findall(body)) - set(names)
        out.append(ParamLine(index=i, text=body, names=names, rhs=rhs))
    return out


def needed_names(defs: "Sequence[ParamLine]", referenced: "set[str]") -> "set[str]":
    """Names to keep: referenced outside the deck, closed over right-hand sides.

    The closure matters — `cm3d` may be referenced by a model card while its
    value is `'cm3d_base * tol_m3'`, and dropping `cm3d_base` would leave an
    unresolvable expression. ngspice reports that as a warning and carries on
    with a garbage value (G26), so the closure is a correctness requirement,
    not tidiness.
    """
    defined = {n for d in defs for n in d.names}
    need = {n for n in defined if n in referenced}
    changed = True
    while changed:
        changed = False
        for d in defs:
            if any(n in need for n in d.names):
                new = (d.rhs & defined) - need
                if new:
                    need |= new
                    changed = True
    return need


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — render.
# ─────────────────────────────────────────────────────────────────────────────


_TRIM_HEADER = """\
* GENERATED by nebula/device/pdk_trim.py -- DO NOT EDIT.
* Regenerate with: python -m nebula.device.pdk_trim --write
*
* Source: {src}
* Kept {kept} of {total} .param definition lines ({names} of {all_names} names):
* exactly those reachable from {consumer},
* closed over right-hand sides. The rest describe vpp fringe caps, flash
* {discarded} -- parsed and thrown away.
*
* Order is the PDK's own, so a parameter that depends on an earlier one still
* resolves. {verification}
"""

_RC_HEADER = """\
* GENERATED by nebula/device/pdk_trim.py -- DO NOT EDIT.
* Regenerate with: python -m nebula.device.pdk_trim --write
*
* Source: {src}
* Exactly one line differs from the PDK original: the `.include` of
* `../parameters/{param}` now points at the trimmed deck alongside this file.
* Every other line, including every process constant, is the PDK's verbatim.
"""


def render_trim(src: Path, keep: "set[str]", *,
                consumer: str = "the model cards sky130_ctle.lib.spice includes",
                discarded: str = (
                    "cells, ESD diodes, 20 V devices and the pfet set"),
                verification: str = (
                    "Equivalence to the untrimmed deck is asserted at rel=0, "
                    "abs=0 by\n* nebula/tests/test_pdk_trim.py, which also "
                    "re-derives this file byte for byte.")) -> str:
    """The trimmed parameter deck, as text."""
    text = _read(src)
    defs = parse_param_lines(text)
    kept = [d for d in defs if any(n in keep for n in d.names)]
    all_names = {n for d in defs for n in d.names}
    lines = [_TRIM_HEADER.format(
        src=src.as_posix(), kept=len(kept), total=len(defs),
        names=len(keep & all_names), all_names=len(all_names),
        consumer=consumer, discarded=discarded, verification=verification)]
    for d in kept:
        # A `+` continuation becomes its own card. Same tokens, same order,
        # no dependence on which line happens to precede it after the cut.
        lines.append(".param " + d.text[1:].strip() if d.text.startswith("+")
                     else d.text)
    return "\n".join(lines) + "\n"


def render_rc_corner(corner: str, param_file: str) -> str:
    """The PDK r+c deck with its parameter include repointed at the trim."""
    src = PDK_NGSPICE / "r+c" / f"{corner}.spice"
    out = [_RC_HEADER.format(src=src.as_posix(), param=param_file)]
    swapped = 0
    for raw in _read(src).splitlines():
        m = _INCLUDE.match(raw)
        if m and _PARAM_INCLUDE.match(raw):
            out.append(f'.include "{Path(param_file).stem}.trim.spice"')
            swapped += 1
        elif m:
            # Relative to the PDK file's own directory; this file lives
            # elsewhere, so make it absolute rather than hope.
            out.append(f'.include "{(src.parent / m.group(1)).resolve().as_posix()}"')
        else:
            out.append(raw)
    if swapped != 1:
        raise PdkTrimError(f"{src}: swapped {swapped} parameter includes, expected 1")
    return "\n".join(out) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — the whole build, as data.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrimBuild:
    """Everything `pdk_trim/` should contain, plus the numbers behind it."""

    files: "dict[str, str]"          # filename -> content
    keep: "frozenset[str]"           # parameter names kept
    referenced: int                  # identifiers seen outside the decks
    per_deck: "dict[str, tuple[int, int]]"   # deck -> (kept lines, total lines)
    tree_files: int
    tree_lines: int
    #: library stem -> its section names, one generated file each.
    sections: "dict[str, tuple[str, ...]]" = field(default_factory=dict)


def build() -> TrimBuild:
    """Derive every generated file from the PDK and the library. No I/O."""
    tree = library_include_tree()
    referenced: "set[str]" = set()
    for text in tree.values():
        referenced |= set(_IDENT.findall(text))
    referenced |= set(_IDENT.findall(_extra_reference_text()))

    param_files = {c: rc_corner_parameter_file(c) for c in RC_CORNERS}

    # The keep-set is the UNION over the five decks. They define the same
    # names with different values, but taking the union rather than trusting
    # that means a deck that gained a name in a PDK update cannot quietly
    # produce a narrower trim than its neighbours.
    keep: "set[str]" = set()
    parsed: "dict[str, list[ParamLine]]" = {}
    for pf in sorted(set(param_files.values())):
        src = PDK_NGSPICE / "parameters" / pf
        parsed[pf] = parse_param_lines(_read(src))
        keep |= needed_names(parsed[pf], referenced)

    files: "dict[str, str]" = {}
    per_deck: "dict[str, tuple[int, int]]" = {}
    for pf in sorted(set(param_files.values())):
        src = PDK_NGSPICE / "parameters" / pf
        files[f"{Path(pf).stem}.trim.spice"] = render_trim(src, keep)
        defs = parsed[pf]
        per_deck[pf] = (sum(1 for d in defs if any(n in keep for n in d.names)),
                        len(defs))
        missing = keep - {n for d in defs for n in d.names}
        if missing:
            raise PdkTrimError(
                f"{pf} does not define {len(missing)} kept name(s) the other "
                f"decks do ({sorted(missing)[:6]}); the decks are not "
                f"interchangeable and the union keep-set is unsafe.")
    for corner, pf in param_files.items():
        files[f"{corner}.spice"] = render_rc_corner(corner, pf)

    all_sections: "dict[str, tuple[str, ...]]" = {}
    for stem, expected in SPLIT_LIBRARIES.items():
        lib_text = _read(library_path(stem))
        sections = library_sections(stem, lib_text)
        if len(sections) != expected:
            raise PdkTrimError(
                f"{stem}.lib.spice has {len(sections)} sections, expected "
                f"{expected}: {sections}")
        for sect in sections:
            files[f"sections/{section_library_path(sect, stem).name}"] = \
                render_section_library(sect, stem, lib_text)
        all_sections[stem] = tuple(sections)

    # D11's opt-in PFET-capable derivative. Keeping this outside
    # SPLIT_LIBRARIES is deliberate: that mapping names checked-in monolithic
    # sources, while this variant has exactly one source -- CTLE_LIB above.
    pfet_text = pfet_library_text()
    files.update(pfet_parameter_supplements())
    pfet_sections = library_sections(PFET_STEM, pfet_text)
    if len(pfet_sections) != 25:
        raise PdkTrimError(
            f"{PFET_STEM} derivative has {len(pfet_sections)} sections, "
            f"expected 25: {pfet_sections}")
    for sect in pfet_sections:
        files[f"sections/{section_library_path(sect, PFET_STEM).name}"] = \
            render_section_library(sect, PFET_STEM, pfet_text)
    all_sections[PFET_STEM] = tuple(pfet_sections)

    return TrimBuild(
        files=files, keep=frozenset(keep), referenced=len(referenced),
        per_deck=per_deck, tree_files=len(tree),
        tree_lines=sum(t.count("\n") for t in tree.values()),
        sections=all_sections,
    )


#: Where the one-section libraries go. See `render_section_library`.
SECTION_DIR: Path = TRIM_DIR / "sections"

#: The nfet-only trim (G36). Split for the same reason as the extended one —
#: it carries 5 sections and a run uses 1, so it pays 5x its own parse.
NFET_LIB: Path = SPICE_DIR / "sky130_nfet_only.lib.spice"

#: Libraries that get split, and how many sections each must have. The counts
#: are asserted rather than discovered: a library that lost a corner would
#: otherwise split cleanly into fewer files and fail much later, at the corner
#: that no longer exists.
SPLIT_LIBRARIES: "dict[str, int]" = {
    "sky130_ctle": 25,          # 5 MOS x 5 passive (G58)
    "sky130_nfet_only": 5,      # MOS corners only
}

_LIB_BLOCK = re.compile(r"^\.lib[ \t]+(\S+)[ \t]*$.*?^\.endl\b.*?$",
                        re.M | re.S)

_SECTION_HEADER = """\
* GENERATED by nebula/device/pdk_trim.py -- DO NOT EDIT.
* Regenerate with: python -m nebula.device.pdk_trim --write
*
* Section `{sect}` of {stem}.lib.spice, ALONE in its own file.
*
* WHY THIS FILE EXISTS, and it is the largest single throughput finding in
* this project: **ngspice expands EVERY `.lib` section in a file, not only the
* one you asked for.** Measured on the same trivial netlist, same machine:
*
*     extended library, this one section extracted   0.093 s
*     extended library, real 25-section file         1.386 s   <- 15x
*     nfet-only library, real 5-section file         0.297 s
*
* The cost scales with the SECTION COUNT, not with what the netlist uses. The
* extended library's 25 sections are the 5x5 (MOS x passive) corner cross
* product G58 added, so the file got 5x bigger the day the passive corner axis
* arrived and the per-evaluation cost went with it. Splitting is the fix; the
* section a run asks for is the only one it now pays for.
*
* Bit-identity to the monolithic library is asserted at rel=0, abs=0 by
* nebula/tests/test_pdk_trim.py.
"""


def library_path(stem: str) -> Path:
    """The monolithic library named `stem`."""
    if stem not in SPLIT_LIBRARIES:
        raise PdkTrimError(f"unknown library {stem!r}; "
                           f"expected one of {sorted(SPLIT_LIBRARIES)}")
    return SPICE_DIR / f"{stem}.lib.spice"


def render_section_library(section: str, stem: str = "sky130_ctle",
                           library_text: "str | None" = None) -> str:
    """One `.lib` section, extracted verbatim into a standalone file.

    Derived from the monolithic library, never rewritten by hand, so that
    library stays the single definition of what a section contains (rule 9).
    The only edit is to the RELATIVE includes: this file sits one directory
    deeper, so `pdk_trim/x.spice` becomes `../x.spice`. Absolute PDK includes
    are untouched.
    """
    text = library_text if library_text is not None else _read(library_path(stem))
    blocks = {m.group(1): m.group(0) for m in _LIB_BLOCK.finditer(text)}
    if section not in blocks:
        raise PdkTrimError(
            f"{stem}.lib.spice has no section {section!r}; it has "
            f"{sorted(blocks)}")
    body = blocks[section].replace('.include "pdk_trim/', '.include "../')
    return (_SECTION_HEADER.format(sect=section, stem=stem)
            + "\n" + body + "\n")


def library_sections(stem: str = "sky130_ctle",
                     library_text: "str | None" = None) -> "list[str]":
    """Every `.lib` section name in a library, in file order."""
    text = library_text if library_text is not None else _read(library_path(stem))
    return [m.group(1) for m in _LIB_BLOCK.finditer(text)]


def add_pfet_includes(library_text: str, expected_sites: int) -> str:
    """Add matching `pfet_01v8` cards after every NFET corner/mismatch card.

    This is the ONE transformation used both by the entry-76 cost instrument
    and by the generated production variant. Count the sites before returning:
    a partial library would work at some corners and fail much later at S9.
    """
    out: "list[str]" = []
    n_corner = n_mismatch = 0
    for line in library_text.splitlines(keepends=True):
        out.append(line)
        if "sky130_fd_pr__nfet_01v8__mismatch.corner.spice" in line:
            out.append(line.replace("nfet_01v8__mismatch",
                                    "pfet_01v8__mismatch"))
            n_mismatch += 1
        elif "sky130_fd_pr__nfet_01v8__" in line and ".pm3.spice" in line:
            out.append(line.replace("nfet_01v8__", "pfet_01v8__"))
            n_corner += 1
    if (n_corner, n_mismatch) != (expected_sites, expected_sites):
        label = ("one corner and one mismatch" if expected_sites == 1 else
                 f"{expected_sites} corner and {expected_sites} mismatch")
        raise PdkTrimError(
            f"PFET derivative expected {label} NFET include sites; found "
            f"corner={n_corner}, mismatch={n_mismatch}")
    return "".join(out)


_PFET_PARAMETER_DECKS: tuple[str, ...] = ("lod", "invariant")
_PFET_PARAMETER_INCLUDE_MARKER = ".param mc_pr_switch=0"


def _pfet_model_library_text(library_text: str) -> str:
    """Base CTLE library plus PFET model cards, before parameter supplements."""
    return add_pfet_includes(library_text, expected_sites=25)


def pfet_parameter_supplements(
        library_text: "str | None" = None) -> "dict[str, str]":
    """Minimal PDK parameter context needed only by the added PFET cards.

    The reference set is derived from files newly reached when PFET cards are
    added to the live CTLE library. `needed_names` then closes each PDK deck
    over right-hand-side dependencies. This is deliberately not folded into
    the ordinary trim: entry 76 measured that doing so materially increases
    every design's parse time.
    """
    source = _read(CTLE_LIB) if library_text is None else library_text
    base_tree = _library_include_tree(source, CTLE_LIB.parent)
    pfet_tree = _library_include_tree(
        _pfet_model_library_text(source), CTLE_LIB.parent)
    added_paths = set(pfet_tree) - set(base_tree)
    if not added_paths:
        raise PdkTrimError("PFET derivative reached no new model-card files")

    referenced: "set[str]" = set()
    for path in added_paths:
        referenced |= set(_IDENT.findall(pfet_tree[path]))

    files: "dict[str, str]" = {}
    kept_by_deck: "dict[str, set[str]]" = {}
    for deck in _PFET_PARAMETER_DECKS:
        src = PDK_NGSPICE / "parameters" / f"{deck}.spice"
        defs = parse_param_lines(_read(src))
        keep = needed_names(defs, referenced)
        if not keep:
            raise PdkTrimError(
                f"PFET model cards reference no names in {src}; refusing an "
                "empty parameter supplement")
        kept_by_deck[deck] = keep
        files[f"pfet_{deck}.trim.spice"] = render_trim(
            src, keep, consumer="the opt-in PFET model cards",
            discarded="cells, ESD diodes and unrelated devices",
            verification=(
                "Dependency derivation and real-ngspice PMOS instantiation "
                "are asserted by\n* "
                "nebula/tests/test_pfet_attenuator.py."))

    required = {"sky130_fd_pr__pfet_01v8__wlod_diff"}
    missing = required - kept_by_deck["lod"]
    if missing:
        raise PdkTrimError(
            "PFET LOD supplement omitted the parameter that stopped entry "
            f"77: {sorted(missing)}")
    return files


def _add_pfet_parameter_includes(library_text: str,
                                 expected_sites: int = 25) -> str:
    """Insert PFET-only parameter decks once at the start of every section."""
    includes = "".join(
        f'.include "pdk_trim/pfet_{deck}.trim.spice"\n'
        for deck in _PFET_PARAMETER_DECKS)
    out: "list[str]" = []
    inserted = 0
    for line in library_text.splitlines(keepends=True):
        out.append(line)
        if line.strip().lower() == _PFET_PARAMETER_INCLUDE_MARKER:
            out.append(includes)
            inserted += 1
    if inserted != expected_sites:
        raise PdkTrimError(
            f"PFET derivative inserted parameter context at {inserted} "
            f"sections, expected {expected_sites}")
    return "".join(out)


def pfet_library_text(library_text: "str | None" = None) -> str:
    """The opt-in 25-section, parameter-complete PFET derivative."""
    source = _read(CTLE_LIB) if library_text is None else library_text
    return _add_pfet_parameter_includes(_pfet_model_library_text(source))


def section_library_path(section: str, stem: str = "sky130_ctle") -> Path:
    """The one-section file for `section`. Existence is the caller's problem."""
    return SECTION_DIR / f"{stem}__{section}.lib.spice"


def untrimmed_library_text() -> str:
    """`sky130_ctle.lib.spice` with the trim undone — the equivalence reference.

    ONE DEFINITION (rule 9). The "before" library is not a checked-in copy that
    could drift from the "after" one; it is derived from the live library by
    pointing each `pdk_trim/<corner>.spice` back at the PDK's own
    `r+c/<corner>.spice`. So the two libraries being compared differ in exactly
    the thing under test and in nothing else, by construction rather than by
    review — and a future edit to the library shows up on both sides.

    Used by `test_pdk_trim.py` for the fast bit-identity gate and by
    `experiments/lib_cost.py` for the before/after timing.
    """
    text = _read(CTLE_LIB)
    swapped = 0
    for corner in RC_CORNERS:
        old = f'.include "pdk_trim/{corner}.spice"'
        new = f'.include "{(PDK_NGSPICE / "r+c" / f"{corner}.spice").as_posix()}"'
        swapped += text.count(old)
        text = text.replace(old, new)
    if swapped != 25:
        raise PdkTrimError(
            f"{CTLE_LIB.name} has {swapped} pdk_trim includes, expected 25 "
            f"(one per section). Either the library was edited by hand or the "
            f"trim was never applied; in both cases the reference is not a "
            f"reference.")
    return text


def stale_files(b: "TrimBuild | None" = None) -> "list[str]":
    """Generated files on disk that differ from a fresh derivation. Empty = clean."""
    b = b or build()
    bad = [name for name, want in b.files.items()
           if not (TRIM_DIR / name).exists()
           or (TRIM_DIR / name).read_text(errors="replace").replace("\r\n", "\n")
           != want]
    on_disk = {p.relative_to(TRIM_DIR).as_posix()
               for p in TRIM_DIR.rglob("*.spice")}
    extra = on_disk - set(b.files)
    return sorted(bad + [f"{n} (not generated by this module)"
                         for n in sorted(extra)])


def write(b: "TrimBuild | None" = None) -> "list[str]":
    """Write the build to `spice/pdk_trim/`. Returns the filenames written."""
    b = b or build()
    for name, content in sorted(b.files.items()):
        out = TRIM_DIR / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="ascii", newline="\n")
    return sorted(b.files)


def _main(argv: "Sequence[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true",
                    help="regenerate spice/pdk_trim/ (default: report only)")
    args = ap.parse_args(argv)

    b = build()
    total_kept = sum(k for k, _ in b.per_deck.values())
    total_lines = sum(t for _, t in b.per_deck.values())
    print(f"library include tree: {b.tree_files} files, {b.tree_lines} lines "
          f"(parameter decks excluded)")
    print(f"identifiers referenced by it: {b.referenced}")
    print(f"parameters kept: {len(b.keep)}")
    for pf, (kept, total) in sorted(b.per_deck.items()):
        print(f"  {pf:<18} {kept:>5} / {total:<5} definition lines "
              f"({100.0 * kept / total:.1f}%)")
    print(f"  {'TOTAL':<18} {total_kept:>5} / {total_lines:<5} "
          f"({100.0 * total_kept / total_lines:.1f}%)")
    print("one-section libraries (ngspice expands EVERY section in a file, "
          "not just")
    print("the one asked for -- 1.386 s for 25 sections, 0.093 s for one):")
    for stem, sects in sorted(b.sections.items()):
        print(f"  {stem:<18} {len(sects):>5} sections -> {len(sects)} files")

    if args.write:
        for name in write(b):
            print(f"wrote {(TRIM_DIR / name).as_posix()}")
        return 0

    stale = stale_files(b)
    print("\npdk_trim/ is up to date" if not stale
          else "\nSTALE, rerun with --write:\n  " + "\n  ".join(stale))
    return 1 if stale else 0


__all__: Sequence[str] = (
    "PdkTrimError", "ParamLine", "TrimBuild",
    "SPICE_DIR", "CTLE_LIB", "PFET_STEM", "TRIM_DIR", "SECTION_DIR", "PDK_NGSPICE",
    "RC_CORNERS",
    "rc_corner_parameter_file", "library_include_tree", "parse_param_lines",
    "needed_names", "render_trim", "render_rc_corner", "build",
    "render_section_library", "library_sections", "section_library_path",
    "library_path", "SPLIT_LIBRARIES", "NFET_LIB",
    "add_pfet_includes", "pfet_library_text", "untrimmed_library_text",
    "stale_files", "write",
)

if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(_main())
