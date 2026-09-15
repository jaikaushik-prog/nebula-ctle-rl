"""Protocol, billing and paired-summary tests; no scientific execution."""
import copy
import pytest
from nebula.experiments import exp_submission_recovery_benchmark as B


def row(arm, repeat=0, *, success=True, elapsed=10., calls=137, target="3db_1p9ghz"):
    return dict(purpose="benchmark", target_id=target, selection_mode=arm,
                repeat=repeat, parent_wall_s=elapsed, status="accepted" if success else "exhausted",
                delivered_success=success, spice_calls=calls,
                attempts=[dict(setting=401, accepted=success, spice_calls=calls,
                               n_pass=315 if success else 314, n_points=315)],
                output_complete=success, request_met=success,
                peaking_error_db=.9, frequency_error_oct=.16)


def test_fixed_domain_and_counterbalanced_schedule():
    coverage=B.schedule("coverage")
    benchmark=B.schedule("benchmark")
    assert len(coverage)==13 and len(benchmark)==24
    assert len({r["target_id"] for r in coverage})==13
    assert sum(r["diagnostic_exposed"] for r in coverage)==1
    assert all(r["selection_mode"]=="rl" for r in coverage)
    assert all(r["max_candidates"]==8 for r in benchmark)
    assert [r["selection_mode"] for r in benchmark[:2]]==["rl","classical"]
    assert [r["selection_mode"] for r in benchmark[2:4]]==["classical","rl"]
    assert {r["repeat"] for r in benchmark}=={0,1,2}


def test_accounting_rejects_unbilled_failed_attempt():
    bad=row("rl")
    bad["attempts"].insert(0,dict(setting=273,accepted=False,spice_calls=137,n_pass=314,n_points=315))
    with pytest.raises(ValueError, match="calls"):
        B.validate_workflow(bad)


@pytest.mark.parametrize("damage", ["duplicate", "partial", "missing_output", "request"])
def test_success_gate_fails_closed(damage):
    bad=row("rl")
    if damage=="duplicate":
        bad["attempts"].append(copy.deepcopy(bad["attempts"][0]))
        bad["spice_calls"]=274
    elif damage=="partial":
        bad["attempts"][0]["n_pass"]=314
    elif damage=="missing_output":
        bad["output_complete"]=False
    else:
        bad["request_met"]=False
    with pytest.raises(ValueError):
        B.validate_workflow(bad)


def test_failed_runs_are_billed_and_excluded_from_success_speed_ratio():
    rows=[row("rl",elapsed=20.), row("classical",elapsed=10.),
          row("rl",1,success=False,elapsed=40.,calls=274),
          row("classical",1,elapsed=10.)]
    rows[2]["attempts"]=[dict(setting=273,accepted=False,spice_calls=137,n_pass=314,n_points=315),
                         dict(setting=337,accepted=False,spice_calls=137,n_pass=314,n_points=315)]
    summary=B.summarise(rows)
    assert summary["total_spice_calls"]==685
    assert summary["total_parent_wall_s"]==80
    assert summary["matched_pairs"]==2
    assert summary["both_success_pairs"]==1
    assert summary["paired_classical_over_rl_ratios"]==[.5]
    assert summary["arms"]["rl"]["delivered_successes"]==1
    assert summary["arms"]["rl"]["attempted_workflows"]==2


def test_no_pair_is_not_a_speedup():
    summary=B.summarise([row("rl")])
    assert summary["matched_pairs"]==0
    assert summary["median_classical_over_rl_ratio"] is None


def test_unmatched_target_not_paired():
    summary=B.summarise([row("rl"),row("classical",target="9db_1p9ghz")])
    assert summary["matched_pairs"]==0


def test_duplicate_workflow_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        B.summarise([row("rl"),row("rl")])


def test_unknown_call_count_is_not_zero():
    bad=row("rl",success=False)
    bad["spice_calls"]=None
    bad["attempts"]=[]
    B.validate_workflow(bad)
    summary=B.summarise([bad])
    assert summary["total_spice_calls"] is None
    assert summary["known_spice_calls"]==0
    assert summary["unknown_call_workflows"]==1



def test_rl_coverage_is_not_pooled_into_matched_arm_comparison():
    coverage=row("rl",success=False)
    coverage["purpose"]="coverage"
    summary=B.summarise([coverage,row("rl"),row("classical")])
    assert summary["arms"]["rl"]["attempted_workflows"]==1
    assert summary["coverage"]["attempted_workflows"]==1
    assert summary["coverage"]["delivered_successes"]==0


@pytest.mark.parametrize("warning,missing", [(True,False),(False,True)])
def test_workflow_export_failure_cannot_complete(monkeypatch,tmp_path,warning,missing):
    from nebula import recovery_workflow as W
    monkeypatch.setattr(W,"_parse",lambda text:dict(peaking_db=3.,f_peak_hz=1.9e9,parsed_by="regex"))
    design=dict(method="rl-physical",request_match={"request_met":True})
    monkeypatch.setattr(W,"_recover",lambda *a:dict(status="accepted",design=design,
                          attempts=[dict(setting=401,accepted=True,spice_calls=137,n_pass=315,n_points=315)],
                          spice_calls=137,selection_wall_s=1.,physical_wall_s=2.))
    monkeypatch.setattr(W,"_verified",lambda d:True)
    def export(d,out):
        paths=[]
        for name in ("design.json","design.cir","design_schematic.png","explanation.txt"):
            if missing and name=="design_schematic.png":
                continue
            p=out/name
            p.write_text("{}")
            paths.append(p)
        return paths,["drawing failed"] if warning else []
    monkeypatch.setattr(W,"_export",export)
    result=W.run_request("3 dB at 1.9 GHz",tmp_path/"run")
    assert not result["delivered_success"]
    assert result["status"]=="export_or_acceptance_failed"
    assert result["spice_calls"]==137
    assert (tmp_path/"run/workflow_receipt.json").is_file()


def test_workflow_refuses_overwrite(tmp_path):
    from nebula import recovery_workflow as W
    out=tmp_path/"run"
    out.mkdir()
    (out/"design.json").write_text("existing")
    with pytest.raises(FileExistsError):
        W.run_request("3 dB at 1.9 GHz",out)



def test_ready_matrix_keeps_unrun_targets_visible():
    result=B.summarise([row("rl")])
    assert len(result["readiness_matrix"])==37
    assert sum(r["outcome"]=="unrun" for r in result["readiness_matrix"])==36


def test_active_ngspice_guard_parses_only_simulator_processes(monkeypatch):
    monkeypatch.setattr(B.os,"name","nt")
    monkeypatch.setattr(B.subprocess,"check_output",lambda *a,**k:
                        '"ngspice_con.exe","123","Console","1","20 K"\n')
    assert B.active_ngspice()==[{"pid":123,"name":"ngspice_con.exe"}]


def test_manifest_refuses_raw_corruption(tmp_path):
    import json
    (tmp_path/"raw.txt").write_text("original")
    (tmp_path/"evidence_sha256.json").write_text(json.dumps({"raw.txt":B.sha(tmp_path/"raw.txt")}))
    assert B.verify_manifest(tmp_path)==1
    (tmp_path/"raw.txt").write_text("changed")
    with pytest.raises(ValueError,match="hash"):
        B.verify_manifest(tmp_path)


def test_manifest_refuses_escape(tmp_path):
    import json
    (tmp_path/"evidence_sha256.json").write_text(json.dumps({"../outside":"x"}))
    with pytest.raises(ValueError,match="escapes"):
        B.verify_manifest(tmp_path)



def test_timeout_retains_completed_and_pending_charge_records(tmp_path):
    import json
    recovery=tmp_path/"physical_recovery"
    first=recovery/"candidate_01_setting_273"
    active=recovery/"candidate_02_setting_337"
    first.mkdir(parents=True)
    active.mkdir()
    completed=dict(setting=273,directory=str(first),accepted=False,spice_calls=137,n_pass=314,n_points=315)
    (recovery/"progress.json").write_text(json.dumps({"attempts":[completed],"spice_calls":137}))
    (active/"call_progress.json").write_text(json.dumps({"spice_calls":3,
            "charged_invocations":3,"invocation_state":"potentially_active"}))
    result=B.partial_recovery(tmp_path)
    assert result["spice_calls"] is None
    assert result["known_spice_calls"]==137
    assert len(result["attempts"])==2
    assert result["attempts"][1]["spice_calls"] is None
    assert result["attempts"][1]["charged_invocations"]==3
    assert result["known_charged_invocations"]==140

