# Phase 2 Global Audit — Sol v3

This package corrects the actual runner file used in v2.1.

Verified configuration in the packaged Python source:
- model: `gpt-5.6-sol`
- reasoning: `high`
- `max_output_tokens = 128000`
- output/evidence directory: `phase2_global_audit_sol_v3`
- exactly one API request
- OpenAI SDK retries: zero
- no automatic semantic retry

The runner prints the model, reasoning effort, token ceiling and evidence path
BEFORE the paid call.

Immediately after the API responds it prints:
- response id
- response status
- incomplete details
- token usage
- confirmation that the raw response was saved

Incomplete, no-output, parse-failure and validation-failure paths all print a
visible error before exiting.

The v1 and v2 evidence directories are not touched.
