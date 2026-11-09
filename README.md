# mistral-openapi-spec-checker

Checks [Mistral's OpenAPI specification](https://docs.mistral.ai/openapi.yaml)
every Monday at 09:00 UTC and publishes endpoint changes as GitHub releases.
Subscribe to the release feed at
`https://github.com/rajbos/mistral-openapi-spec-checker/releases.atom`.

## When releases are created

A release is **not** created on every run. The workflow runs weekly, on manual
dispatch, and when the workflow file itself is pushed. Each run then:

1. With no earlier `mistral-openapi-*` release, publishes a **baseline** release
   (this happens once, on the first run).
2. Otherwise publishes a release only if the spec differs from the previous
   release's snapshot. No changes means no release, so quiet weeks add nothing
   to the feed.

Every run writes a summary (baseline used, spec size, and the outcome with
added/changed/removed counts) to the workflow run page.

The first successful run publishes a baseline release. Later runs publish only
when operations are added, removed, or changed, including changes to their
referenced local schemas, path settings, servers, and effective security schemes.
Each release lists the HTTP method, API URL, description, documentation link, and
changed fields (up to 20 per endpoint). Documentation links use an operation's
Mistral `externalDocs` URL when available; otherwise they use its first tag to
link to the API reference group, or the API reference if no tag is present.
Removed endpoints link to their former documentation, which may no longer exist.

Each release carries its OpenAPI snapshot as `openapi.yaml`; the most recent
published `mistral-openapi-*` release is the baseline for the next check. Keep
that asset when managing releases. A failed download, invalid specification, or
missing baseline asset fails the workflow instead of publishing a false change.
The workflow can also be started manually using **Actions → Check Mistral OpenAPI
→ Run workflow**. The repository must allow GitHub Actions to create releases
(`contents: write`).

To compare snapshots locally:

```sh
python -m pip install -r requirements.txt
python check_openapi.py --previous old.yaml --current new.yaml --output notes.md
python -m unittest discover -s tests -v
```

Omit `--previous` to generate baseline notes. An empty notes file means no
endpoint changes were found.
