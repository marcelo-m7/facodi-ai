# FACODI AI Operations Guide

## Scope

This guide covers production operation of `facodi_ai` and `facodi_ai_website` on Odoo 19 Community. The core add-on is independent of Website; the Website add-on is optional and owns only the Website translation integration.

## Connection setup and testing

Configure providers under **FACODI AI → Configuration → Connections**. Use a separate connection record when credentials, organization/project metadata, endpoint or operational ownership differs. When more than one active connection exists for a provider, explicitly choose the intended default connection.

API keys are write-only. After saving a credential, the form exposes only its effective source and whether a stored Odoo key exists. `GEMINI_API_KEY` and `OPENAI_API_KEY` take precedence over an Odoo-stored credential. When an environment value is active, change it in the deployment secret manager; the Odoo UI cannot read, edit or remove it. The **Remove Stored API Key** action only deletes the Odoo-stored value.

For Coolify, declare `GEMINI_API_KEY` and `OPENAI_API_KEY` as blank environment entries in the service configuration and set values only through its secret management interface. An unset variable lets the runtime use the stored Odoo key; a non-empty variable overrides it.

Use the connection test/status controls available in the FACODI AI UI before enabling a connection for a profile. A failed test should be resolved at the provider/credential layer before changing prompts or Website behavior.

## Provider, model and profile changes

Runtime behavior is resolved from the profile, connection and provider defaults. For Website translation, review the `website_translation` profile before changing global defaults.

When changing provider or model:

1. Confirm an active connection exists for the target provider.
2. Test the connection.
3. Change the profile/provider/model override.
4. Re-open Settings and verify the effective provider/model/connection displayed for Website Translation.
5. Test on a non-critical translated page before broad use.

Do not encode provider-specific behavior into Website templates or JavaScript. Provider selection belongs to the core runtime/profile resolver.

## Website translation workflow

Enter Odoo's normal Website translation mode for the target language. FACODI AI adds three actions to the Translation panel:

- **Translate untranslated**: translates eligible `to_translate` units only; dirty manual edits are preserved.
- **Retranslate page**: requires confirmation and regenerates eligible current-page units.
- **Translate selected**: translate one complete unit associated with the current editor selection.

The AI call only returns candidates. Review the result in the editor. Use Odoo's standard **Save** button to persist accepted translations. Use Undo before saving to revert an AI action as one editor-history operation.

The V1 service accepts only Website-local `ir.ui.view.arch_db` terms belonging to the current page. It rejects default-language targets, disabled Website languages, stale source SHAs, shared views and other models.

## Auditing

FACODI AI creates request audit records for provider calls. Use the audit/request views to inspect:

- user attribution;
- provider and model;
- capability/profile context;
- success/failure state;
- normalized error code;
- usage metadata when supplied by the provider.

Secrets and raw tracebacks must not be exposed in audit records.

## Payload diagnostics

Request/response payload storage is disabled by default. Enable **Store request payloads** only for a defined debugging window. Website content may contain unpublished institutional text or other sensitive content.

After diagnosis:

1. disable payload storage;
2. remove or retain diagnostic records according to the project's data-retention policy;
3. rotate credentials if a diagnostic export or backup was exposed outside the approved environment.

## Error classes

The runtime normalizes provider/runtime failures into stable FACODI AI categories:

- `configuration_error` — missing/disabled runtime configuration, connection or credential;
- `authentication_error` — provider credential rejected;
- `rate_limit` — provider throttling/quota limit;
- `timeout` — provider request timed out;
- `provider_error` — other provider request failure;
- `validation_error` — invalid translation input/output, stale SHA, markup or scope violation;
- `unsupported_capability` — adapter/profile cannot perform the requested capability.

For Website translation, failed/partial/extra/duplicate AI responses are rejected before applying browser mutations. The normal Odoo manual translation workflow can still be used when AI is unavailable.

## Installation and upgrade

Install Python dependencies in the Python environment that executes Odoo:

```bash
pip install -r requirements.txt
```

Install the core alone when Website functionality is not needed:

```bash
odoo -d <database> -i facodi_ai --stop-after-init
```

Install the Website integration:

```bash
odoo -d <database> -i facodi_ai_website --stop-after-init
```

Upgrade both together after repository deployments that modify either add-on:

```bash
odoo -d <database> -u facodi_ai,facodi_ai_website --stop-after-init
```

Always take a current database backup before a production module upgrade and validate the same commit in staging first.

## Backup and credential caution

Connection secrets are stored in `ir.config_parameter`; therefore a database dump can contain live provider API keys. Treat database backups, CI database snapshots and support exports as secrets.

Recommended controls:

- encrypt backups at rest and in transit;
- restrict backup access;
- do not attach raw database dumps to public issues;
- rotate provider keys after suspected disclosure;
- do not log or paste API keys into request payloads, commit messages or support screenshots.

## Uninstall boundaries

`facodi_ai_website` can be removed without making the core runtime depend on Website. Removing the Website add-on removes its translation integration/profile data but should not require removal of `facodi_ai`.

Before uninstalling `facodi_ai`, identify other FACODI add-ons or profiles that depend on its models/services. Do not remove the core while dependent modules remain installed.

## Standard Odoo fallback

FACODI AI does not replace Odoo translation storage or the Website editor. If the AI runtime is disabled, misconfigured, rate-limited or offline, editors can continue translating content manually using Odoo's standard Website translation mode and Save workflow.

## Release verification

Before production release, verify on the exact release commit:

1. repository contract tests pass;
2. core-only `facodi_ai` clean install passes;
3. full `facodi_ai,facodi_ai_website` clean install passes;
4. full upgrade passes;
5. FACODI Website HOOT tests pass and are not skipped;
6. no real provider calls or credentials are required by CI;
7. `git diff --check` and placeholder scans are clean;
8. the PR diff contains no secrets or environment-specific credentials.
