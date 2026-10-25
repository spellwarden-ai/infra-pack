# Changelog

One entry per version, newest first. The text of an entry is the text of the release notes.

## 0.9.0 (25 October 2026)

- A Claude Code plugin marketplace, `spellwarden`, with one plugin, `infra-pack`, and five skills for infrastructure operations: change safety, Terraform plan review, Kubernetes incident triage, IAM least-privilege review and CI pipeline repair.
- Checks, tests and a continuous integration workflow that keep the layout, the manifests and the skill text within the rules of the pack, and that scan the pack with the Spellwarden scanner.
- `tools/lift.py`, the calculator that recomputes a published measurement from the evaluation runs it came from.
- Measured on 25 October 2026, after the release: +15.0 points on 40 infrastructure tasks (Infra-Ops 40) with all five skills loaded, 95% interval 3.6 to 26.4, over five runs, the first measurement of the pack on this suite. Details in MEASUREMENTS.md.
