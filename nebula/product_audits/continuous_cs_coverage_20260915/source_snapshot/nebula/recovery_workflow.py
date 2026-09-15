"""Parse, recover and export a fresh fixed physical CTLE with complete timing.

The returned wall_s includes parsing, imports, all rejected physical attempts,
exact deck export, drawing and design.json persistence. Receipt serialization
after that timestamp is separately disclosed. No LLM provider is invoked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time


def _parse(text):
    from nebula.llm.spec_parse import parse_request
    return parse_request(text, use_llm=False).as_dict()


def _recover(request, out, mode, max_candidates, progress):
    from nebula.physical_recovery import run
    return run(request, evidence_dir=out, selection_mode=mode,
               max_candidates=max_candidates, progress=progress)


def _verified(design):
    from nebula.physical_design import is_verified
    return is_verified(design)


def _export(design, out):
    from nebula.physical_design import output_deck, report
    from nebula.design import write_outputs
    deck = output_deck(design)
    explanation = report(design)
    design["explanation"] = dict(text=explanation, source="physical-evidence-template")
    return write_outputs(design, out, deck=deck, extra_files={"explanation.txt": explanation})


def run_request(text, out, *, selection_mode="rl", max_candidates=8, progress=None):
    started = time.perf_counter()
    if selection_mode not in ("rl", "classical"):
        raise ValueError("selection_mode must be rl or classical")
    if max_candidates != 8:
        raise ValueError("the registered recovery workflow uses exactly eight candidate slots")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError("recovery output directory must be empty")
    result = dict(status="error", design=None, attempts=[], spice_calls=None,
                  selection_mode=selection_mode, max_candidates=max_candidates,
                  delivered_success=False, output_complete=False, request_met=False,
                  written=[], artifact_warnings=[], parse_wall_s=None,
                  selection_wall_s=None, physical_wall_s=None, export_wall_s=None,
                  error=None)
    try:
        parse_started = time.perf_counter()
        parsed = _parse(str(text))
        result["parse_wall_s"] = time.perf_counter() - parse_started
        result["parsed_request"] = parsed
        request = {key: parsed[key] for key in ("peaking_db", "f_peak_hz")}
        recovered = _recover(request, out / "physical_recovery", selection_mode,
                             max_candidates, progress)
        result.update(recovered)
        design = result.get("design")
        if design is not None:
            design["natural_language"] = parsed
            design["wall_s_scope"] = ("All recovery selection and physical attempts; parsing and "
                                      "final export are additional. Complete workflow time is in workflow_receipt.json.")
            design["recovery"] = dict(status=result.get("status"),
                                      attempt_count=len(result.get("attempts", [])),
                                      all_spice_calls=result.get("spice_calls"),
                                      selection_mode=selection_mode)
            design["recovery_workflow"] = {
                key: result.get(key) for key in
                ("status", "selection_mode", "max_candidates", "attempts",
                 "spice_calls", "selection_wall_s", "physical_wall_s")}
            if progress:
                progress("Exporting the recovered circuit and full attempt record", 90)
            export_started = time.perf_counter()
            written, warnings = _export(design, out)
            result["written"] = [str(Path(p).resolve()) for p in written]
            result["artifact_warnings"] = list(warnings)
            required = [out / name for name in
                        ("design.json", "design.cir", "design_schematic.png", "explanation.txt")]
            result["output_complete"] = not warnings and all(
                p.is_file() and p.stat().st_size > 0 for p in required)
            result["request_met"] = bool((design.get("request_match") or {}).get("request_met"))
            result["delivered_success"] = bool(
                result["status"] == "accepted" and _verified(design)
                and result["request_met"] and result["output_complete"])
            result["artifact_sha256"] = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in required if p.is_file()}
            result["export_wall_s"] = time.perf_counter() - export_started
        if result.get("status") == "accepted" and not result["delivered_success"]:
            result["status"] = "export_or_acceptance_failed"
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}")
    result["wall_s"] = time.perf_counter() - started
    result["timing_scope"] = (
        "Entry through parsing/imports, all recovery attempts, verification, exact deck, "
        "drawing, explanation, design.json writes and required-output checks/hashes. "
        "The following workflow receipt serialization is excluded; a benchmark parent "
        "timer includes it and process startup/shutdown. Not a warm-cache guarantee.")
    result["full_receiver_compliance"] = False
    result["scope"] = "Fixed physical CTLE plus ideal behavioral DFE; full receiver/S7 signoff excluded."
    receipt_path = out / "workflow_receipt.json"
    result["workflow_receipt"] = str(receipt_path)
    # Avoid duplicating the full 315-row final design in this outer accounting receipt.
    receipt = {k: v for k, v in result.items() if k != "design"}
    receipt["design_json"] = "design.json" if (out / "design.json").exists() else None
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n",
                            encoding="utf-8", newline="\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--selection-mode", choices=("rl", "classical"), default="rl")
    parser.add_argument("--max-candidates", type=int, choices=(8,), default=8)
    args = parser.parse_args(argv)
    result = run_request(args.request, args.out, selection_mode=args.selection_mode,
                         max_candidates=args.max_candidates)
    print(json.dumps({k: result[k] for k in
                      ("status", "delivered_success", "spice_calls", "wall_s", "workflow_receipt")}))
    return 0 if result["delivered_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

