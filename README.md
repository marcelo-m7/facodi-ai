# FACODI AI

FACODI AI is an Odoo 19 Community add-on suite that provides reusable, server-side AI services and a conservative Website translation integration for FACODI.

## Architecture

The repository is intentionally split into two add-ons:

- `facodi_ai` — reusable AI runtime, providers, connections, profiles, prompts, auditing and Settings UI. It has no dependency on `website` or `website_slides`.
- `facodi_ai_website` — optional Website integration. It depends on `website` and `facodi_ai` and adds AI-assisted translation to Odoo's standard Website translation editor.

This boundary keeps the AI runtime reusable by future FACODI features without coupling the core to Website.

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

Install `facodi_ai_website` to extend Odoo's normal Website translation mode. The integration uses Odoo 19's `website-translation-plugins` registry and the standard translation/history/save mechanisms rather than replacing the Website editor.

The Translation panel exposes three FACODI AI actions:

1. **Translate untranslated** — translates eligible local-page units still marked `to_translate`, preserving manually dirty and already translated content.
2. **Retranslate page** — after confirmation, regenerates eligible local-page translated and untranslated units in the current target language.
3. **Translate selected** — maps the current selection to one complete Odoo translation unit and translates that unit.

Only the current Website page's local `ir.ui.view.arch_db` is eligible in V1. Shared views, menus/navigation, other Website records and non-editable regions are excluded.

The browser sends translation identities, not authoritative source text. The server resolves the source term from the Website default language using Odoo's translation SHA, protects inline markup, calls the configured AI profile, validates the complete response, and returns candidate translations. The FACODI AI endpoint does **not** persist Website translations. The editor applies the result to the DOM/history; the user reviews it and uses Odoo's standard **Save** action, which persists through `/website/field/translation/update`.

This design avoids duplicate pages and preserves Odoo's normal multilingual Website model.

## Installation

Make both add-ons available on the Odoo add-ons path and install the core first, or install the Website integration directly and let Odoo resolve its dependency:

```bash
odoo -d <database> -i facodi_ai --stop-after-init
odoo -d <database> -i facodi_ai_website --stop-after-init
```

For upgrades:

```bash
odoo -d <database> -u facodi_ai,facodi_ai_website --stop-after-init
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

The CI validates repository contracts, Odoo clean installation, upgrades, server-side Website translation contracts and the FACODI Website HOOT tests. Provider calls are mocked in automated tests; CI does not require real API keys.

See [`docs/operations.md`](docs/operations.md) for operational procedures and troubleshooting.

## Failure behavior

AI failures are normalized and audited. Website translation requests are atomic from the browser's perspective: malformed, partial, duplicate or extra unit responses are rejected before DOM mutation. If FACODI AI is disabled or unavailable, Odoo's standard manual Website translation workflow remains available.

## License

LGPL-3.
