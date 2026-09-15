"""Bounded spoken peaking values keep offline requests usable without a provider."""
import pytest

from nebula.llm.spec_parse import parse_offline, SpecOutOfRange
from nebula.web.optional_llm import LanguageAssistant


@pytest.mark.parametrize('word,value', [('three', 3), ('six', 6), ('nine', 9), ('twelve', 12)])
def test_offline_word_peaking_with_units(word, value):
    result = parse_offline(f'please give me {word} dB peaking near 2.1 GHz')
    assert result.target.peaking_db == value
    assert result.target.f_peak_hz == 2.1e9
    assert result.source == 'regex'
    assert not result.notes


def test_word_peaking_case_and_full_unit():
    result = parse_offline('NINE DECIBELS near 1900 MHz')
    assert result.target.peaking_db == 9
    assert result.target.f_peak_hz == 1.9e9


@pytest.mark.parametrize('prefix', ['-', 'minus ', 'negative '])
def test_negative_word_value_still_refused(prefix):
    with pytest.raises(SpecOutOfRange):
        parse_offline(f'{prefix}six dB near 2.1 GHz')


def test_word_target_cannot_bypass_frequency_range():
    with pytest.raises(SpecOutOfRange):
        parse_offline('six dB near 4 GHz')


def test_word_needs_units_and_whole_token():
    for text in ('six near 2.1 GHz', 'twentysix dB near 2.1 GHz'):
        parsed = parse_offline(text)
        assert parsed.target.peaking_db == 7.5
        assert any('no peaking found' in note for note in parsed.notes)


def test_unavailable_provider_fallback_retains_six_db(monkeypatch):
    service = LanguageAssistant()
    monkeypatch.setattr(service, 'availability', lambda: {'available': False})
    parsed = service.parse('please give me six dB peaking near 2.1 GHz', True)
    assert parsed.target.peaking_db == 6
    assert parsed.target.f_peak_hz == 2.1e9
    assert parsed.source == 'regex'
    assert any('fallback' in note for note in parsed.notes)
