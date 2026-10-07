# s1-workflows

Fast, structured risk triage for a pull request or diff. One decision-model request returns:

- 0–4 scores for security, performance, change impact, maintainability, and overall risk;
- a `trivial` / `routine` / `significant` / `high_risk` / `critical` classification;
- risk flags with probabilities;
- a Boolean decision on whether deeper code review is warranted.

TypeSafe Jev and Cloudflare Clef use compatible `score`, `choice`, and `noul`
outputs. The CLI emits a stable, model-neutral JSON result. It can also emit a
compact GitHub comment with color-coded badges. Badge hover text contains the
full risk description, confidence, or probability.

## Setup

Requires Python 3.11+ and credentials for the selected provider.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
export TYPESAFE_API_KEY='...'
```

For Cloudflare Workers AI:

```bash
export CLOUDFLARE_ACCOUNT_ID='...'
export CLOUDFLARE_API_TOKEN='...'
```

## Run

Assess a diff from stdin or a file:

```bash
git diff origin/main...HEAD | .venv/bin/s1-assess --pretty --title 'Add cache'
.venv/bin/s1-assess changes.diff --pretty
```

Generate Markdown ready for a pull-request comment:

```bash
.venv/bin/s1-assess changes.diff --format github-comment > assessment.md
gh pr comment --body-file assessment.md
```

Use Cloudflare Clef instead:

```bash
.venv/bin/s1-assess changes.diff --provider cloudflare --pretty
.venv/bin/s1-assess changes.diff --provider cloudflare --model clef-flash --pretty
```

Cloudflare supports `clef` (default) and `clef-flash`. `CLOUDFLARE_AUTH_TOKEN`
is accepted as an alternative token variable.

Generate the diff directly from a local repository:

```bash
.venv/bin/s1-assess --git-range origin/main...HEAD --pretty
```

Pass PR metadata and a diff as one JSON object:

```bash
.venv/bin/s1-assess assessment.json --json-input --pretty
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

Diffs up to 48 KB are sent in one request. Larger diffs are grouped by file into
48 KB chunks. Oversized individual file diffs are split by line. If the provider
rejects the input as too large, the threshold is halved and the run retried.
Chunk results
are aggregated conservatively: the maximum risk score, classification, and
Boolean probability win. The output's `execution` object reports what happened.

Tune the per-call threshold or total 10 MB safety limit:

```bash
.venv/bin/s1-assess changes.diff --chunk-bytes 32000 --max-bytes 20000000
```

Chunking can miss risks that emerge only from interactions across chunks. A true
result in any chunk survives aggregation, but this remains fast triage rather
than a substitute for full code review.

## Model adapters

The boundary is `AssessmentModel` in `s1_workflows/contracts.py`:

```python
class AnotherModel:
    def assess(self, assessment: AssessmentInput) -> AssessmentResult:
        ...
```

Implement that protocol to use another library while keeping identical input and
output dataclasses. `DecisionAssessmentModel` adapts the compatible Jev/Clef
answer format.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
