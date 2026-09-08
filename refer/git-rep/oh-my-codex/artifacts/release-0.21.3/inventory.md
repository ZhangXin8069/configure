# Release inventory — v0.21.2..dev@3902573e

- Previous tag: `v0.21.2` = `020576d3071d70e72af7b9ddfd797e7281a87fea`.
- Candidate: `dev@3902573ef309e54534d7388579f2a7243ca7f465`.
- Range: 15 commits, 20 files, +1,285/−101.
- Referenced PRs: #3604, #3605, #3606, #3608, #3610, #3612 (linked issues #3609, #3611).
- Contributors from git shortlog: Bellman, dependabot[bot], Oreochococukie.

## Included work

- #3608 — prevents duplicate Team wakes and retires terminal projections.
- #3612 — raises the detached tmux scrollback clamp 500 → 5000 with an `OMX_TMUX_HISTORY_LIMIT` override; fixes #3611.
- #3610 — troubleshooting entry for composer drift triage and recovery; documents #3609.
- #3606 — `@types/node` 26.2.0 → 26.4.0.
- #3605 — `zod` 4.4.3 → 4.5.2.
- #3604 — `@biomejs/biome` 2.5.10 → 2.5.11.

## Reproduction

```sh
git rev-list --count v0.21.2..3902573ef309e54534d7388579f2a7243ca7f465
git diff --shortstat v0.21.2..3902573ef309e54534d7388579f2a7243ca7f465
git log --pretty='%s' v0.21.2..3902573ef309e54534d7388579f2a7243ca7f465 | grep -oE '#[0-9]+' | sort -u
```
