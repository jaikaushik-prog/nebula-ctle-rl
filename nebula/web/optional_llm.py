"""Optional web language assistance; circuit selection and verdicts stay deterministic."""
from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import replace

from nebula.llm import client as C, grounding as G, explanation as E
from nebula.llm.spec_parse import parse_request, parse_offline, SpecOutOfRange

SCOPE = ('Language assistance only. Circuit selection, acceptance and the displayed '
         'verification verdict are computed by the existing deterministic workflow. '
         'Physical results cover the CTLE with an ideal DFE, not a complete transistor receiver.')


def opt_in(data):
    value = data.get('use_llm', False)
    if not isinstance(value, bool):
        raise ValueError('use_llm must be true or false.')
    return value


class _ModelClient:
    """Reuse the existing wrapper while permitting an explicitly configured model."""
    def __init__(self, client, model):
        self.client, self.model, self.messages = client, model, self

    def create(self, **kwargs):
        kwargs['model'] = self.model
        return self.client.messages.create(**kwargs)


class LanguageAssistant:
    def __init__(self, client=None):
        self._injected = client

    def availability(self):
        installed = importlib.util.find_spec('anthropic') is not None
        configured = bool(os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_AUTH_TOKEN'))
        available = self._injected is not None or (installed and configured)
        reason = ('Configured; provider connectivity has not been verified.' if available else
                  'Optional provider SDK or credentials are missing. Deterministic mode remains available.')
        return {'available': available, 'label': 'Optional LLM available' if available else 'LLM unavailable',
                'reason': reason, 'provider_verified': False,
                'model': os.getenv('NEBULA_LLM_MODEL', C.MODEL)}

    def _client(self):
        if self._injected is not None:
            return self._injected
        if not self.availability()['available']:
            raise C.LlmUnavailable('Optional provider is not configured.')
        import anthropic
        # No retries: a provider outage must not block a deadline demonstration.
        client = anthropic.Anthropic(timeout=15.0, max_retries=0)
        return _ModelClient(client, os.getenv('NEBULA_LLM_MODEL', C.MODEL))

    def parse(self, text, use_llm=False):
        if not use_llm:
            return parse_offline(text)
        try:
            return parse_request(text, use_llm=True, client=self._client())
        except SpecOutOfRange:
            raise
        except (ValueError, KeyError, TypeError):
            # A malformed provider result is not permission to silently reinterpret it.
            raise ValueError('The LLM returned an invalid target. Use deterministic parsing or revise the request.') from None
        except Exception:
            parsed = parse_offline(text)
            return replace(parsed, notes=parsed.notes + (
                'LLM unavailable or provider call failed; deterministic fallback used.',))

    @staticmethod
    def parsed_view(parsed, use_llm=False):
        result = parsed.as_dict()
        if use_llm:
            result['notes'].append('Optional language parsing is outside the displayed circuit-workflow time.')
        result.update(llm_requested=use_llm, label=(
            'LLM parsed; target validated' if parsed.source == 'llm' else
            'Deterministic fallback' if use_llm else 'Deterministic parser'))
        return result

    def explain(self, design, use_llm=False):
        physical = design.get('method') == 'rl-physical'
        if physical:
            from nebula.physical_design import report, is_verified
            baseline = report(design)
            verdict = 'Physical electrical model pass' if is_verified(design) else 'Physical verification needs work'
            n = design.get('nominal') or {}
            m, v = n.get('meas') or {}, design.get('verification') or {}
            facts = {'requested_peaking_db': design['request']['peaking_db'],
                     'requested_frequency_ghz': design['request']['f_peak_ghz'],
                     'peaking_db': m.get('peaking_db'), 'frequency_ghz': m.get('_f_peak_ghz'),
                     'noise_mv_rms': m.get('_noise_mv'), 'power_mw': m.get('_power_mw'),
                     'passing_conditions': v.get('n_pass'), 'tested_conditions': v.get('n_points')}
        else:
            baseline, verdict, facts = E.template(design), json.dumps(E.verdicts(design)), E.facts(design)
        result = {'text': baseline, 'source': 'template', 'label': 'Deterministic explanation',
                  'scope': SCOPE, 'verdict': verdict}
        if not use_llm:
            return result
        try:
            client = self._client()
            if physical:
                text = C.ask_text(
                    'FACTS:\n' + json.dumps(facts, sort_keys=True) + '\nVERDICT:\n' + verdict,
                    'Explain only these measured facts in a short paragraph. Do not decide acceptance, '
                    'recommend settings, infer other specifications, or claim complete receiver verification. '
                    'The supplied verdict is final. ' + SCOPE + '\n' + G.prompt_rules(),
                    client=client, max_tokens=384)
                text, source = G.check(text, facts), 'llm'
            else:
                text, source = E.explain(design, use_llm=True, client=client)
                if source != 'llm':
                    raise ValueError('Generated wording rejected')
            if not text.strip():
                raise ValueError('Empty explanation')
            result.update(text=text, source=source, label='LLM wording; numbers checked against evidence')
        except Exception:
            # Never expose provider exceptions: they can contain request headers or credentials.
            result['label'] = 'Deterministic fallback; LLM unavailable or wording rejected'
        return result
