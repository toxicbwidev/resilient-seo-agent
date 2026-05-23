# TrueFoundry Gateway config

Manifests for `tfy apply -f <file>`.

## Files (not committed if they contain secrets)

- `aws-bedrock.yaml` — provider account + 4 Bedrock models (ignored by .gitignore — contains access key)
- `routing.yaml` — task-type → model priority chain
- `guardrails.yaml` — guardrail policy definitions
- `rate-limits.yaml` — per-user/model/app throttle settings

## Sanitized copies for submission

Before submitting to judges, run:

```bash
python scripts/sanitize-manifests.py
```

This produces `*-redacted.yaml` versions where credentials are replaced with `${VAR_NAME}` placeholders. Those redacted files ARE committed.
