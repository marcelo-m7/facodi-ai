# FACODI AI

FACODI AI is an Odoo 19 Community add-on suite that provides reusable, server-side AI services and a FACODI Learning bridge. The legacy Website translation add-on has been retired and native Odoo Website translation remains the editorial path.

## Architecture

The repository is intentionally split into two active add-ons:

- `facodi_ai` — reusable AI runtime, providers, connections, profiles, prompts, auditing and generic Settings UI. It has no dependency on FACODI Learning, Website or eLearning.
- `facodi_ai_learning` — optional FACODI Learning bridge. It depends on `facodi_ai` + `facodi_learning` and owns learning jobs, analyses, suggestions, slide actions, cron and Manager review UI.

The legacy `facodi_ai_website` package remains only as a non-installable compatibility shell. It intentionally contains no runtime assets, routes, settings, or data and is excluded from the managed installation set.

## Runtime

- Odoo: 19.0 Community
- Python AI integration: `pydantic-ai-slim[openai,google]==2.39.0`
- Built-in providers: OpenAI and Google Gemini
- Default Website translation profile: `website_translation`
- Website translation default provider/model: Gemini / `gemini-3.8-flash`

Provider/model/profile values are resolved at runtime. Explicit profile and connection configuration takes precedence over defaults.

## Connections and credentials

Administrators configure AI connections from the **FACODI AI** app or **Settings → FACODI AI**. Multiple connections per provider are supported, with deterministic default-connection resolution.

API keys are write-only in the Odoo UI. UI-entered keys are stored in Odoo configuration parameters, keyed by an immutable connection credential UUID. At runtime, `GEMINI_API_KEY` and `OPENAI_API_KEY` take precedence over an Odoo-stored key for the corresponding provider. The connection form shows the effective source and whether a stored key is overridden, but never returns either secret.

For production deployments, configure only the required provider variables as blank environment entries and set their values in the deployment secret manager. Do not copy runtime environment values into Odoo. Removing a stored key in the UI affects only Odoo storage and cannot modify deployment environment variables.

**Backup warning:** database backups include `ir.config_parameter` values and therefore can contain configured AI API keys. Protect backups as secrets and rotate credentials if a backup is exposed.

## Website translation

Native Odoo Website translation remains the authoritative translation workflow. The retired `facodi_ai_website` compatibility shell no longer installs any Website route, asset, or translation profile; editors continue to use standard Website translation, save and history flows.

## Installation

Install the reusable core alone when no FACODI-specific integration is required. Install the optional learning bridge only when its dependency is present:

```bash
odoo -d <database> -i facodi_ai --stop-after-init
odoo -d <database> -i facodi_ai_learning --stop-after-init
```

When upgrading an existing database from the legacy layout, update the core and install the learning bridge in the same maintenance operation so existing learning model/table data remains registered continuously:

```bash
odoo -d <database> -u facodi_ai -i facodi_ai_learning --stop-after-init
odoo -d <database> -u facodi_ai,facodi_ai_learning --stop-after-init
```

Install the Python dependency from `requirements.txt` in the same Python environment used to run Odoo.

## Configuration

1. Open **FACODI AI → Configuration → Connections**.
2. Create or edit a Gemini/OpenAI connection and set its API key.
3. Mark the intended connection as default when multiple active connections exist for a provider.
4. Open **FACODI AI → Configuration → Profiles** to review provider/model/runtime overrides.
5. Review **Settings → FACODI AI** for effective Website translation runtime information and diagnostic options.
6. Keep request-payload storage disabled unless debugging requires it; Website content can be sensitive.

## Testing

The CI validates repository contracts, a true core-only Odoo installation with no FACODI Learning addon path, combined bridge/Website installation, same-version upgrades and a real migration fixture from the legacy `facodi_ai` learning layout. The optional learning bridge is tested against an explicit FACODI Learning compatibility SHA instead of floating on that repository's `main`. Provider calls are mocked in automated tests; CI does not require real API keys.

See [`docs/operations.md`](docs/operations.md) for operational procedures and troubleshooting.

## Failure behavior

AI failures are normalized and audited. Website translation requests are atomic from the browser's perspective: malformed, partial, duplicate or extra unit responses are rejected before DOM mutation. If FACODI AI is disabled or unavailable, Odoo's standard manual Website translation workflow remains available.

## License

LGPL-3.
