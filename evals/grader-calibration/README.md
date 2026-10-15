# Grader calibration set

`calibration.json` holds claim / snippet / source-text examples with a reference grade for the
`eval-citation-grader` rubric (supported, partially_supported, not_supported).
`run_evals.py --calibrate` grades them and reports exact agreement with `human_grade`.

**Status: human reviewed 2026-10-15.** A person confirmed each `human_grade` against its
source; all 8 drafted labels were kept and `human_reviewed: true` is set on every example.
Calibration agreement now reflects agreement with human judgement.
