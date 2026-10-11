# Stage 9: Mechanical citation check

Goal: prove every finding cites a source `fetch_source.py` saved in this run and quotes it
exactly. Deterministic code, never a model judgement. §9.7.

## Steps

1. `run_state.py verify`, `run_state.py stage 9 --run <run-id> --start`. If Stage 8 was
   skipped, run `run_state.py stage 9 --run <run-id> --skip --reason 'no findings'` and go to
   Stage 10.
2. `<python> <skill_dir>/scripts/verify_citations.py --run <run-id>`. Exit 1 only means some
   findings failed; that is a result, not an error. Failures carry reasons such as
   `snippet_not_found`, `source_not_in_fetch_log` or `source_hash_mismatch`.
3. `status_rules.py verification --run <run-id> --from citations` (marks failed findings
   `citation_failed`; they can only ever appear under Sources › Limitations).
4. `run_state.py stage 9 --run <run-id> --complete`.

Never edit findings to make a citation pass, and never retry research to replace a failed
citation in this build.

## Report

Checked, passed, failed, with the failure reasons per finding.
