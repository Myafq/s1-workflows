# jev-workflows

Fast, structured risk triage for a pull request or diff. One Jev request returns:

- 0–4 scores for security, performance, change impact, maintainability, and overall risk;
- a `trivial` / `routine` / `significant` / `high_risk` / `critical` classification;
- risk flags with probabilities;
- a Boolean decision on whether deeper code review is warranted.

Jev uses its native `score`, `choice`, and `noul` outputs. The CLI emits a stable,
model-neutral JSON result.

## Setup

Requires Python 3.11+ and a TypeSafe API key.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
export TYPESAFE_API_KEY='...'
```

## Run

Assess a diff from stdin or a file:

```bash
git diff origin/main...HEAD | .venv/bin/jev-assess --pretty --title 'Add cache'
.venv/bin/jev-assess changes.diff --pretty
```

Generate the diff directly from a local repository:

```bash
.venv/bin/jev-assess --git-range origin/main...HEAD --pretty
```

Pass PR metadata and a diff as one JSON object:

```bash
.venv/bin/jev-assess assessment.json --json-input --pretty
```

Input schema:

```json
{
  "diff": "diff --git ...",
  "title": "Optional title",
  "description": "Optional description",
  "repository": "owner/repo",
  "base_revision": "main",
  "head_revision": "feature"
}
```

The default maximum diff size is 1 MB. Override deliberately with `--max-bytes`.

## Model adapters

The boundary is `AssessmentModel` in `jev_workflows/contracts.py`:

```python
class AnotherModel:
    def assess(self, assessment: AssessmentInput) -> AssessmentResult:
        ...
```

Implement that protocol to use another library while keeping identical input and
output dataclasses. `JevAssessmentModel` is the reference adapter.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
