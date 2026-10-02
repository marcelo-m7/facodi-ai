# Remove FACODI AI Website Translation Design

Date: 2026-10-02
Status: Proposed implementation design
Target: Odoo 19 Community
Repositories: `marcelo-m7/facodi-ai`, `Corvanis/facodi-deploy`

## Purpose

Retire FACODI AI's Website translation integration so Website editors use only
Odoo's standard translation panel, translation storage, and save flow. Preserve
the reusable `facodi_ai` runtime and `facodi_ai_learning` integration.

## Current behavior

`facodi_ai_website` registers AI translation actions in Odoo's
`website-translation-plugins` registry, adds JavaScript to Website Builder
assets, exposes `/facodi_ai/website/translate`, and adds Website translation
configuration/profile records. The deployment migration currently includes
the addon in its managed update list and does not retire it.

## Design

1. Remove the Website AI actions, browser assets, controller route, translation
   service, profile/settings additions, and related tests from active runtime
   behavior. Odoo's built-in Website translation plugin remains untouched.
2. Retire `facodi_ai_website` from the deployment's managed module list and add
   it to the existing standard Odoo module-uninstall phase. This phase must run
   before managed-module updates so Odoo removes module-owned records and
   references through its normal uninstall API.
3. Keep a minimal, non-installable compatibility package at the old addon path
   for the retirement release. It must contain no translation code or assets;
   it exists only so an already-installed database can load the module
   metadata while the migration gate uninstalls it. This avoids booting Odoo
   against an installed module whose source disappeared before cleanup.
4. Remove all runtime and acceptance-test expectations that the module is
   installed, and document the standard Website translation workflow. Retain
   the AI core's generic translation capability if other consumers use it.

## Data and compatibility

Uninstallation is limited to records owned by `facodi_ai_website`, including
its profile and prompt. It must not modify Website pages, existing translations,
languages, `facodi_ai` provider/connection data, or learning records. Existing
Odoo translations remain authoritative and available to the standard editor.
The migration remains fail-closed: if standard module uninstallation fails,
the deployment gate prevents Odoo from starting.

## Verification

- Repository contracts assert the Website integration is absent from the
  managed module set and present in the retired-module cleanup set.
- A disposable runtime upgrade begins with `facodi_ai_website` installed,
  runs the migration gate, and confirms the module is uninstalled, its AI
  translation assets/actions/routes are absent, and the standard Website
  translation mode and save flow remain available.
- Core-only and learning-bridge install/upgrade contracts continue to pass.
- Live deployment and any live database uninstallation remain separate
  operations; this source change alone does not claim production deployment.
