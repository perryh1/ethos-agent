# Ethos — the constitution layer

Ethos is a downstream distribution of [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(MIT — see `LICENSE` and `NOTICE`) that adds one thing and keeps it small: **a company
constitution that always sits on top.** Bring any API key, run any model Hermes supports —
OpenRouter, Anthropic, OpenAI, local endpoints, anything OpenAI-compatible — and every session
is governed by the company's ratified values document, injected above the agent's own persona.

The constitution format, the elicitation instruments that produce it, and its governance
(ratifying group, unanimous absolutes, contest paths) live in the companion **ai-values**
repository (`corporate/design.md` there). This repo only *carries* the document; it never
changes it.

## How it works (the injection point)

Hermes assembles its system prompt in three cache tiers (`agent/system_prompt.py`):
`stable` (identity/SOUL.md, tool guidance) → `context` (workspace + context files) →
`volatile` (skills, memory, timestamp). The Ethos layer prepends the constitution as the
**first block of the stable tier — above SOUL.md/identity** — so persona, personality
commands, memory, and project context all operate *under* it. Two deliberate differences
from SOUL.md:

1. **Unconditional when present.** SOUL.md is skipped in some execution modes (cron,
   skip-context). The constitution is not: an agent running a cron job for the company is
   still acting for the company.
2. **Explicit vanilla only.** With a constitution file present, the only way to run without
   it is `ETHOS_VANILLA=1` — logged as an explicit vanilla-mode session (this is the named
   control-condition switch the values design requires; it is a feature, not a hole). A
   missing file also runs vanilla, and is logged so it's visible, never silent.

Content passes the same safety machinery as every other context file: prompt-injection
scanning (`_scan_context_content`) and head/tail truncation with a visible marker.

## Using it

```
# 1. Drop the compiled constitution next to SOUL.md:
cp constitution.v1.md ~/.hermes/CONSTITUTION.md      # or the soul/SOUL.md pack target

# 2. Run Hermes/Ethos normally — every surface (CLI, TUI, desktop, gateways) now
#    composes the constitution above identity. The session log shows:
#    "Ethos constitution active: company=<name> constitution=v1 variant=full profile=0.1.0"

# Optional:
ETHOS_CONSTITUTION_PATH=/path/to/constitution.v1.internal-ops.md   # explicit file (wins over ~/.hermes)
ETHOS_VANILLA=1                                                    # explicit, logged vanilla session
```

Try it immediately with the bundled **demo**: `cp ethos/demo-constitution.md
~/.hermes/CONSTITUTION.md`. The demo is loudly marked `DEMO — not ratified` in its version
block; loading it logs a warning so invented values can never pass as a company's real ones.

## The version-block contract

Section 1 of every compiled constitution is fixed machine-parseable `Key: value` lines —
`Company`, `Profile-Version`, `Schema-Version`, `Constitution-Version`, `Variant`,
`Compiled`, `Source-Commit`, `Ratification-Session`. Ethos parses exactly these labels
(`_parse_constitution_version`) and logs them at session build, so every injected copy is
traceable and the values repository's conflict/prediction logs can join on what actually ran.
The ai-values verify tooling pins the same labels on the template side.

## Patch surface (kept deliberately minimal for upstream rebases)

| File | Change |
|---|---|
| `agent/prompt_builder.py` | +`load_constitution_md`, `_parse_constitution_version`, `ETHOS_CONSTITUTION_PREAMBLE` (new code only, after `load_soul_md`) |
| `agent/system_prompt.py` | +9-line hook at the top of the stable tier; docstring tier list updated |
| `run_agent.py` | +1 re-export line (test-patching contract, same as `load_soul_md`) |
| `ETHOS.md`, `NOTICE`, `ethos/`, `tests/test_ethos_constitution.py`, `README.md` top section | additions |
| `hermes_cli/web_server.py` | `/api/status` gains an `ethos` block (constitution status, from `get_constitution_status`); `/api/ethos/constitution` (auth-gated) serves the active constitution document for the dashboard viewer; built-in theme labels de-branded |
| `web/` (dashboard SPA) | Ethos shell branding (wordmark, title, theme names, update labels) + the `EthosBadge` constitution indicator in the nav; deep feature strings stay upstream |
| `web/public/sittings.html` | **Bundled Sittings questionnaire** — the values-elicitation instrument (personal + corporate tracks) as a self-contained static page, served at `/sittings.html` behind the dashboard's auth gate, with a "Sittings" sidebar entry (`external` nav item, full-page navigation). Answers stay in the respondent's browser (localStorage). Scoring stays sealed while answering; after the final sitting a **Results** stage scores on-device with the published rubric arithmetic (validated against the rubrics' worked examples) and generates the files: response-sheet YAML, profile-preview YAML, and (personal track) a loudly-marked draft-constitution preview. Corporate results are per-respondent only — aggregation, splits, and ratification stay with the scorer and the group |
| `hermes_cli/web_dist/` | **Committed prebuilt dashboard bundle** (upstream gitignores it) — `hermes dashboard --skip-build` serves it with no Node toolchain |

Everything else is untouched upstream. To pull upstream updates:
`git remote add upstream https://github.com/NousResearch/hermes-agent && git fetch upstream
&& git merge upstream/main` — the three touched files are the only likely conflict points,
and each change is additive.

## Roadmap (next patches, in order)

1. `ethos:` config block in `config.yaml` (constitution path, product name, accent tokens)
   replacing the env vars as the primary interface.
2. Version badge in the TUI/desktop status surfaces (done for the **web dashboard**: the nav
   shows the constitution badge, fed by `/api/status.ethos`; TUI/desktop remain).
3. White-label branding tokens for user-facing product strings (shell done for the web
   dashboard; deep feature strings and TUI banner skinning remain).
4. Conflict/override capture: a `/flag` affordance writing entries in the values repo's
   conflict-log schema — the manual stand-in for the gateway intake.

## Trademark note

"Hermes" and "Nous Research" are upstream names. Ethos is an independent downstream
distribution, not affiliated with or endorsed by Nous Research; upstream branding is being
progressively replaced in user-facing surfaces while code-level identifiers stay upstream
to keep the diff rebaseable. See `NOTICE`.
