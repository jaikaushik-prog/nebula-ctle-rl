from nebula.experiments.audit_post_review_models import ignored_parameters


def test_ignored_parameters_are_parsed_not_inferred_from_exit_success():
    log = 'Warning: unrecognized parameter (p2) - ignored\n unrecognized parameter (q2) - ignored\n'
    assert ignored_parameters(log) == ['p2', 'q2']
    assert ignored_parameters('ngspice exited successfully') == []


def test_warning_duplicates_do_not_inflate_distinct_parameter_count():
    assert ignored_parameters('unrecognized parameter (p3) - ignored\n' * 3) == ['p3']
