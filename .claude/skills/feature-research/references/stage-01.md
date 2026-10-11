# Stage 1: Intake

Goal: preserve the inputs exactly, open the run, and decide whether the mockup can be
captured. Performed by `run_state.py start` and `check_url.py`. §4, §7 Stage 1.

## Steps

1. **Requirements argument.** If the text after the URL is the path of an existing file,
   use `--requirements-file '<path>'`. Otherwise it is the requirements text: encode it,
   exactly as the user typed it (UTF-8, no trimming or rewording), as standard base64 and use
   `--requirements-b64 <base64>`.
2. **Start the run:**

   ```
   <python> <skill_dir>/scripts/run_state.py start --mockup-url '<url>' --requirements-file '<path>'
   <python> <skill_dir>/scripts/run_state.py start --mockup-url '<url>' --requirements-b64 <base64>
   ```

   Add `--prior-decisions '<path>'` if the user supplied a decisions file, and
   `--non-interactive '<case file>'` only if the user passed `--non-interactive`.
   The output gives `run_id` and `run_dir`. A refusal (exit 3) means no run exists; report
   the reason and stop. Common refusals: hooks not active (restart Claude Code in this
   repository so `.claude/settings.json` hooks load), another run active (offer
   `--abort <id>`), missing setup.
3. **Check the requirements were preserved.** If you passed text, Read
   `<run_dir>/input/requirements.md` and compare it with the user's text. If it differs at
   all (base64 mistakes happen with long text), run
   `run_state.py abort --run <run-id> --reason 'requirements text was not preserved exactly'`
   and ask the user to save the requirements to a file and run `/feature-research` again
   with the file path.
4. **Check the URL:**

   ```
   <python> <skill_dir>/scripts/check_url.py --run <run-id> '<url>'
   ```

   - `status: ok` → note `input_type` (html, image or figma) for Stage 2.
   - `auth_required` → explain the `reason` to the user (for Figma: a read-only personal
     access token exported as `FIGMA_TOKEN`). Never try to get around authentication.
   - `blocked` → the URL points somewhere the workflow will not go (internal address,
     disallowed scheme, credentials in the URL). Explain the `reason`.
   - `unreachable` / `unsupported` → explain the `reason`.

   Whatever the status, continue with steps 5 and 6 before stopping: the inputs were
   preserved, so Stage 1 itself is complete even when the mockup cannot be captured.
5. **Prior decisions.** If the user supplied a decisions file, record it now:
   `<python> <skill_dir>/scripts/status_rules.py decide --run <run-id> --prior`. Each prior
   decision becomes a DEC with source `prior_decisions_file`; later agents read them.
6. **Complete (always):** `run_state.py stage 1 --run <run-id> --complete`.
7. Only now, if `check_url.py` did not return `ok`, do not start Stage 2. Run
   `run_state.py abort --run <run-id> --reason 'mockup cannot be captured: <reason>'`, report,
   and stop.

## Report

Run ID, run directory, run mode, input type, requirements source (text or file), and any
check_url warnings.
