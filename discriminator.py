"""
llm_baseline.py
----------------
!! READ THIS FIRST !!
The paper's LLM-FS / LLM-FT baselines are few-shot-prompted and LoRA
fine-tuned LLaMA-2-7B (Sec. V.C, ref. [22]/[23]). This sandbox has no
network access to model-weight hosts (e.g. huggingface.co is not in the
allowed egress list) and no local GPU/weights, so we CANNOT reproduce the
literal LLM-FS/LLM-FT numbers here.

This module gives you two honest options instead:

  1. `APILLMBaseline`: a real few-shot baseline that calls an LLM through
     the Anthropic Messages API (api.anthropic.com IS reachable from this
     sandbox). It builds the same kind of few-shot prompt described in the
     paper (target SNDR/SFDR -> propose normalized circuit parameters) and
     parses a JSON parameter vector from the response. This is a legitimate
     apples-to-apples "LLM proposes sizing" baseline, just with a different
     base model than LLaMA-2-7B -- update `model` below to whichever Claude
     model you're licensed to call, and set ANTHROPIC_API_KEY.

  2. `RandomHeuristicBaseline`: a zero-network placeholder (uniform / biased
     random proposal) ONLY so the rest of the pipeline (evaluate.py, Table
     comparisons) has something to run against out of the box. Its numbers
     are NOT meaningful as an "LLM baseline" -- they exist purely so
     reproduce_tables.py produces a complete, runnable table without
     external dependencies. Swap in (1) before trusting any LLM-baseline row.
"""
from __future__ import annotations
import json, os, re
import numpy as np
from typing import Optional

from circuits import dim, param_names


class RandomHeuristicBaseline:
    """NOT an LLM. Zero-dependency placeholder so the pipeline runs end to
    end offline. See module docstring."""

    def __init__(self, circuit: str, seed: int = 0):
        self.circuit = circuit
        self.d = dim(circuit)
        self.rng = np.random.default_rng(seed)

    def propose(self, tau_sndr: float, tau_sfdr: float) -> np.ndarray:
        # mild bias toward mid-range values, matching how an under-grounded
        # LLM baseline in the paper is described as producing "physically
        # ungrounded" but not adversarial proposals.
        return np.clip(self.rng.normal(0.5, 0.2, size=self.d), 0, 1)


class APILLMBaseline:
    """Real few-shot LLM baseline via the Anthropic Messages API.
    Requires `pip install anthropic` and an ANTHROPIC_API_KEY env var.
    Not wired into reproduce_tables.py by default (keeps that script
    dependency-free); call it directly if you want a genuine LLM-FS row.
    """

    def __init__(self, circuit: str, model: str = "claude-sonnet-4-6",
                 few_shot_examples: Optional[list] = None):
        self.circuit = circuit
        self.names = param_names(circuit)
        self.model = model
        self.few_shot_examples = few_shot_examples or []

    def _build_prompt(self, tau_sndr: float, tau_sfdr: float) -> str:
        header = (
            f"You are sizing a 28nm CMOS ADC front-end circuit ({self.circuit}) "
            f"with {len(self.names)} tunable parameters, each normalized to [0,1]. "
            f"Parameter order: {self.names}. "
            f"Target: SNDR >= {tau_sndr:.1f} dB, SFDR >= {tau_sfdr:.1f} dB. "
        )
        examples = ""
        for ex in self.few_shot_examples:
            examples += f"\nExample -- target SNDR={ex['tau_sndr']}, SFDR={ex['tau_sfdr']} -> {json.dumps(ex['params'])}"
        instruction = (
            "\nRespond with ONLY a JSON array of "
            f"{len(self.names)} floats in [0,1], no other text."
        )
        return header + examples + instruction

    def propose(self, tau_sndr: float, tau_sfdr: float) -> np.ndarray:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "pip install anthropic, and set ANTHROPIC_API_KEY, to use APILLMBaseline"
            ) from e
        client = anthropic.Anthropic()
        prompt = self._build_prompt(tau_sndr, tau_sfdr)
        resp = client.messages.create(
            model=self.model, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        match = re.search(r"\[[\d\.,\s]+\]", text)
        if not match:
            raise ValueError(f"Could not parse parameter vector from LLM response: {text!r}")
        vals = json.loads(match.group(0))
        arr = np.array(vals, dtype=np.float64)
        if len(arr) != len(self.names):
            raise ValueError(f"Expected {len(self.names)} values, got {len(arr)}")
        return np.clip(arr, 0, 1)
