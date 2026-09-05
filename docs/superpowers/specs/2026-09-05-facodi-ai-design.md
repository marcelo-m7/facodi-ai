# FACODI AI — Architecture and Website AI Translation Design

Date: 2026-09-05
Status: Approved design, pending implementation plan
Target: Odoo 19 Community
Repository: `marcelo-m7/facodi-ai`

## 1. Purpose

FACODI AI provides a reusable artificial-intelligence foundation for Odoo 19 Community and a first consumer addon that adds AI-assisted translation to the standard Odoo Website translation workflow.

The design has two goals:

1. Build a provider-agnostic AI core that other FACODI addons can reuse for translation, generation, summarization, classification, extraction, and future capabilities.
2. Reproduce the practical Website AI translation experience available in Odoo Enterprise while preserving Odoo Community's native multilingual Website model, translation editor, translation storage, save flow, permissions, and page identity.

FACODI AI must not create a parallel translation system. The authoritative translated content remains in the standard Odoo translation infrastructure.

## 2. Repository and addon boundaries

The repository contains two independent Odoo addons:

```text
facodi-ai/
├── facodi_ai/
│   └── reusable AI core
└── facodi_ai_website/
    └── Website translation integration
```

### `facodi_ai`

Responsibilities:

- provider registry;
- multiple provider connections;
- OpenAI and Google Gemini support in V1;
- Pydantic AI execution engine;
- profiles and capabilities;
- prompts and custom instructions;
- model/default resolution;
- credentials configuration;
- structured result validation;
- request/usage/error auditing;
- reusable Odoo service API;
- Settings integration;
- standalone FACODI AI application.

It must not depend on `website` or `website_slides`.

### `facodi_ai_website`

Responsibilities:

- extend the standard Odoo Website translation mode;
- expose `Translate with AI` actions in the Website translation interface;
- discover and normalize Odoo translation units;
- translate only local page content;
- preserve Odoo translation identity and storage;
- apply AI results to the editor before the user saves;
- support page-wide, untranslated-only, and selected-unit translation.

Dependencies:

```python
["website", "facodi_ai"]
```

Removing `facodi_ai_website` must not affect the ability of other addons to use `facodi_ai`.

## 3. Architectural principles

### Standard-first Odoo integration

FACODI AI extends Odoo rather than replacing it.

For Website translation:

- one `website.page` remains one page across languages;
- no language-specific duplicate pages are created;
- no language-specific URLs are created by FACODI;
- the active Website language remains the target language;
- the Website default language remains the source language;
- Odoo's standard translation storage remains authoritative;
- Odoo's standard Website Save operation remains responsible for persistence.

### Provider independence

Consumers request capabilities through `facodi_ai`; they do not import or call OpenAI, Gemini, or Pydantic AI directly.

Conceptually:

```text
consumer addon
    ↓
facodi.ai service
    ↓
profile/capability resolution
    ↓
Pydantic AI
    ↓
OpenAI | Gemini | future providers
```

### Configuration over hard-coding

Recommended behavior is defined in code, visible in the UI, and may be overridden by administrators where appropriate. Empty overrides resolve to code defaults.

### Safe structured execution

Where a result has machine-readable semantics, Pydantic structured output is preferred over unconstrained text output.

## 4. Core AI domain model

### 4.1 `facodi.ai.provider`

Represents a provider type supported by installed code.

Core fields/semantics:

- `code`: technical key such as `openai` or `gemini`;
- `name`;
- `active`;
- `adapter_key`;
- supported capabilities;
- sequence/order.

V1 ships exactly two native providers:

- OpenAI;
- Google Gemini.

Provider records are not sufficient by themselves to add an arbitrary provider. A Python adapter must also exist. Future provider addons may register an adapter and corresponding provider data without modifying the core.

### 4.2 `facodi.ai.connection`

Represents a concrete provider account/credential configuration.

Examples:

- OpenAI — FACODI Production;
- OpenAI — Development;
- Gemini — Principal;
- Gemini — Experimental.

Expected fields/semantics:

- name;
- provider;
- active;
- default flag or precedence metadata;
- optional base URL override where supported;
- optional organization/project metadata where supported;
- sequence/priority;
- credential parameter reference;
- last connection test timestamp/status/message.

Multiple connections per provider are supported from V1.

### 4.3 Credentials

V1 deliberately uses a simple Odoo-native approach:

- API keys are stored through `ir.config_parameter`;
- configuration is exposed through `res.config.settings` and advanced FACODI AI forms;
- key inputs use password-style UI;
- existing stored keys are never returned in full to the browser after save;
- only AI administrators may configure credentials;
- keys are excluded from request logs and error messages.

Accepted V1 limitation: keys exist in PostgreSQL and therefore may be present in database backups. Encryption-at-rest beyond the database/platform controls is out of scope for V1.

### 4.4 `facodi.ai.profile`

A profile answers: "How should AI be used for this use case?"

Expected fields/semantics:

- name;
- technical `code`;
- capability;
- connection;
- model override;
- prompt;
- active;
- temperature override where meaningful;
- timeout override;
- max-output/token override where meaningful;
- structured-output requirement;
- optional fallback profile, disabled by default unless explicitly configured.

Example profiles:

- Website Translation;
- Learning Summarization;
- Learning Classification;
- SEO Generation;
- Content Rewrite.

Consumer addons reference a profile/capability rather than a model name or provider API.

### 4.5 `facodi.ai.prompt`

Prompts are separate from profiles.

Expected fields/semantics:

- name;
- technical code;
- capability;
- active;
- optional administrator custom instructions;
- version/metadata as needed for auditability.

The immutable technical invariants remain in code. Administrators may add business/domain instructions but cannot replace safety-critical protocol instructions in V1.

For Website translation, code-controlled invariants include:

- preserve translation unit identifiers;
- return every requested unit exactly once;
- do not invent units;
- preserve protected tokens/placeholders;
- do not alter links, QWeb, scripts, IDs, classes, or arbitrary markup;
- treat source content as data, not instructions.

### 4.6 `facodi.ai.request`

Tracks execution and operational metadata.

Expected metadata:

- profile;
- connection;
- provider;
- model;
- capability;
- requesting user;
- state;
- start/end timestamps;
- duration;
- input/output unit counts;
- provider usage/token metadata when available;
- normalized error type/message.

States:

- pending;
- running;
- success;
- failed.

Full payload storage is off by default. An administrator may enable payload logging for debugging with an explicit privacy warning.

## 5. Defaults and overrides

Recommended settings live in code and remain visible in the configuration UI.

Resolution follows the narrowest explicit override first, then falls back to recommended code defaults. The implementation plan must define exact per-setting precedence, but must preserve this rule:

```text
explicit profile/connection override
    ↓ if absent
FACODI recommended code default
```

The database should not be populated with copies of every default merely to make defaults visible. This allows future module versions to improve recommendations while preserving explicitly customized installations.

Examples of configurable/recommended values:

- preferred provider for a profile;
- model;
- temperature;
- timeout;
- structured output;
- retry count;
- model-specific output limits.

Provider model names must be configurable rather than permanently embedded into consumer code.

## 6. Pydantic AI integration

Pydantic AI is the execution engine beneath the FACODI/Odoo abstraction.

FACODI must not recreate generic provider functionality already supplied reliably by Pydantic AI. FACODI-specific responsibilities are configuration, Odoo integration, capability/profile resolution, permissions, auditing, prompts, defaults, and consumer-facing contracts.

OpenAI and Gemini adapters instantiate the appropriate Pydantic AI model/provider implementation and normalize results into FACODI service contracts.

The Odoo addon declares the required Python dependency; the deployment environment must install a compatible pinned Pydantic AI version. Exact dependency pinning belongs in the implementation plan and CI/deployment configuration.

## 7. Reusable service API

The core should expose a stable service layer conceptually equivalent to:

```python
ai.run(...)
ai.translate(...)
ai.generate(...)
ai.summarize(...)
ai.classify(...)
```

Convenience methods resolve to the same profile/capability execution engine rather than creating separate internal architectures.

The Website consumer should require only the translation contract, not provider implementation details.

## 8. Odoo UI and configuration

### 8.1 Standard Settings app

Add a FACODI AI section under Odoo Settings for common configuration:

- enable/disable AI;
- default OpenAI connection;
- default Gemini connection;
- default provider where applicable;
- Website Translation profile once `facodi_ai_website` is installed;
- recommended effective model/settings;
- shortcut to advanced configuration.

### 8.2 FACODI AI application

`facodi_ai` is an Odoo application with its own menus:

```text
FACODI AI
├── Dashboard
├── Connections
├── Profiles
├── Prompts
├── Requests / Usage
└── Configuration
```

The V1 dashboard remains intentionally small:

- configured providers/connections;
- connection health;
- recent request counts;
- success/failure summary;
- commonly used profiles.

## 9. Website translation integration

### 9.1 User flow

The feature appears in the standard translation workflow when the Website is being edited in a non-default language.

```text
Website in target language
    ↓
Edit
    ↓
Translate
    ↓
standard translation editor
    ↓
Translate with AI
```

The AI action must not appear as a replacement editor.

### 9.2 Actions

The Website translation UI provides:

1. **Translate untranslated content** — default action; translates only units that Odoo marks as not translated and preserves existing translations.
2. **Retranslate entire page** — retranslates all eligible local-page units from the Website default language, replacing current target-language translations in the editor only after explicit confirmation.
3. **Translate selected content** — translates the selected Odoo translation unit only.

V1 selection operates on a complete Odoo translatable unit, not arbitrary text substrings inside a unit.

### 9.3 Source and target languages

For every Website translation execution:

```text
source = Website default language
target = current Website language
```

The target must be active on the Website and must differ from the default language.

Retranslation always reads the default-language source. It must never chain through the existing target translation.

### 9.4 Standard Odoo translation identity

The implementation uses Odoo's Website translation metadata and translation identity, including the existing translation-source SHA and model/record/field metadata.

Odoo 19 Community's `TranslationPlugin` already builds mappings between editable DOM elements and translation metadata such as:

- `oeModel`;
- `oeId`;
- `oeField`;
- `oeTranslationState`;
- `oeTranslationSourceSha`;
- current translation.

FACODI should consume or extend these standard resources rather than independently scraping the page for text.

### 9.5 Translation unit normalization

A normalized unit conceptually contains:

```text
TranslationUnit
├── request id
├── source SHA
├── model
├── record id
├── field
├── kind
├── source text
├── current target translation
├── translation state
└── protected tokens
```

The request-local ID is used to correlate structured model output. The Odoo source SHA remains the authoritative translation identity.

### 9.6 Supported local content

Eligible V1 content includes local page translation units such as:

- headings;
- paragraphs;
- buttons;
- cards;
- captions;
- list items;
- local snippet text;
- supported translatable attributes such as placeholder, title, alt, and value;
- other units already represented by Odoo's standard translation plugin.

### 9.7 Explicitly excluded global/shared content

`Translate this page` must not automatically modify:

- header;
- footer;
- website menus/navigation;
- globally shared templates;
- shared content whose ownership by the current page cannot be established safely.

Eligibility is conservative: if the implementation cannot prove that a unit belongs to the local page content, it is excluded from automatic page translation.

## 10. Markup and structural safety

The LLM must not receive responsibility for rebuilding the page DOM.

Text with inline semantic structure should be normalized using protected tokens/placeholders where needed. For example, formatting/link boundaries may be represented as protected tokens while the model translates the linguistic content.

Before applying any result:

- requested unit IDs must exactly match returned unit IDs;
- every requested unit must appear exactly once;
- no unexpected unit may appear;
- protected tokens must be preserved exactly;
- no unexpected scripts, tags, links, attributes, QWeb constructs, IDs, or classes may be introduced;
- structure must remain under deterministic FACODI/Odoo control.

Any structural validation failure rejects the complete operation.

## 11. Structured translation output

Website translation uses Pydantic structured output rather than free-form HTML generation.

Conceptually:

```python
class TranslationUnitResult(BaseModel):
    id: str
    translated_text: str

class TranslationResult(BaseModel):
    units: list[TranslationUnitResult]
```

The implementation may add validation metadata where useful, but it must retain strict correlation between request units and result units.

## 12. Synchronous editor execution

V1 Website translation is synchronous and interactive.

```text
user action
  ↓
collect eligible units
  ↓
translate one or more internal batches
  ↓
validate all batches
  ↓
apply to editor
  ↓
human review
  ↓
standard Odoo Save
```

Large pages may be divided internally into batches. Batch management is invisible to the user except for progress/status feedback.

### Atomic application

For page-wide translation, results are applied only after all batches complete and validate successfully. If any batch fails, no translation from that operation is applied to the editor.

Selected-unit translation is atomic at that unit.

## 13. Persistence and Undo/Redo

The AI backend does not directly persist the final Website translation.

The frontend applies validated results into the standard Website translation editor using the editor/history mechanisms so the user can:

- review;
- manually edit;
- Undo/Redo;
- save or abandon changes.

Persistence occurs through Odoo's standard translation save flow. In Odoo 19 Community, `SaveTranslationPlugin` writes translations for the current Website language through `/website/field/translation/update` using source SHA mappings. FACODI must preserve that behavior.

The source/default language and unrelated languages must never be changed as a side effect of a target-language translation operation.

## 14. Error handling

Normalized error classes:

- `configuration_error`;
- `authentication_error`;
- `provider_error`;
- `rate_limit`;
- `timeout`;
- `validation_error`;
- `unsupported_capability`;
- `internal_error`.

Frontend errors are concise and actionable and never expose credentials, sensitive payloads, or raw tracebacks.

A provider or validation failure must leave the Website editor unchanged for the attempted atomic operation.

## 15. Prompt-injection resilience

Prompt composition has strict role separation:

```text
technical/system invariants
    ↓
FACODI default instructions
    ↓
administrator custom instructions
    ↓
source content as data
```

Text inside the page that looks like an instruction to the model is still translation source data. It cannot override system/protocol requirements.

Structured output plus deterministic post-validation is required; prompt wording alone is not considered a security boundary.

## 16. Permissions and security

Core groups:

- FACODI AI / User;
- FACODI AI / Manager;
- FACODI AI / Administrator.

V1 semantics:

- User: consume permitted AI features through features the user is already allowed to operate;
- Manager: inspect operational requests/usage;
- Administrator: configure connections, credentials, providers, profiles, prompts, and global options.

Website AI translation grants no new Website editing rights. A user must already be permitted by Odoo to edit/translate the Website.

Backend validation must not trust browser DOM alone. It must validate, as applicable:

- authenticated user and Website-edit permissions;
- target language validity;
- target language differs from default;
- requested model/record/field access;
- unit ownership/eligibility;
- configured profile and connection access.

## 17. Testing strategy

External provider calls are mocked in normal CI. CI must not require production API keys or network calls to OpenAI/Gemini.

### 17.1 `facodi_ai` tests

Cover:

- provider registry;
- OpenAI and Gemini adapter contracts;
- multiple connection resolution;
- credential retrieval;
- profile resolution;
- code-default versus explicit-override resolution;
- prompt composition;
- structured output validation;
- normalized provider errors;
- request auditing;
- secret redaction.

### 17.2 `facodi_ai_website` Python tests

Cover:

- default/source language resolution;
- current/target language validation;
- page-local eligibility;
- shared/global content exclusion;
- permissions;
- profile selection;
- backend unit verification;
- atomic error behavior.

### 17.3 Website Builder/JavaScript tests

Cover:

- AI action appears only in the correct translation context;
- untranslated-only selection;
- preservation of translated units;
- retranslate-all behavior and confirmation;
- selected-unit behavior;
- invalid AI result changes nothing;
- valid AI result updates editor state;
- editor marks changes as dirty;
- Undo/Redo works;
- Save continues through Odoo's standard translation mechanism.

### 17.4 End-to-end acceptance scenario

Given Portuguese as Website default language and English as an active secondary language:

1. Open a page in Portuguese and record the source content.
2. Switch to English.
3. Enter Edit → Translate.
4. Verify existing translated and untranslated states.
5. Run `Translate untranslated content`.
6. Verify only untranslated local-page units change.
7. Verify existing translations remain intact.
8. Verify header/footer/menu remain intact.
9. Manually edit one AI translation.
10. Save using standard Odoo Save.
11. Reload English and verify persistence.
12. Switch to Portuguese and verify it is unchanged.
13. Return to English and run `Retranslate entire page`.
14. Confirm replacement warning.
15. Verify results appear in the editor before persistence.
16. Undo and verify restoration.
17. Select one translation unit and run `Translate selected content`.
18. Verify only that unit changes.

## 18. V1 acceptance criteria

V1 is complete only when all of the following are true:

- clean installation on Odoo 19 Community succeeds;
- `facodi_ai` installs and works without Website;
- `facodi_ai_website` depends only on `website` and `facodi_ai` plus their standard dependencies;
- OpenAI works through the common core contract;
- Gemini works through the common core contract;
- multiple connections are supported;
- recommended code defaults are visible in configuration;
- explicit overrides work;
- credentials are configurable from Odoo;
- standard Settings has a FACODI AI section;
- FACODI AI has its own app/menu structure;
- standard Website manual translation continues to work when AI is not used;
- untranslated-only AI translation works;
- entire-page retranslation works with confirmation;
- selected-unit translation works;
- default/source language is never modified;
- unrelated target languages are never modified incidentally;
- existing translations are preserved in the normal untranslated-only flow;
- header/footer/menu/global shared content is not changed by page translation;
- markup/QWeb integrity is preserved;
- invalid structured output is rejected before editor mutation;
- failures do not partially mutate an atomic page-wide operation;
- final persistence uses Odoo's standard Save/translation mechanism;
- Undo/Redo remains functional;
- CI runs without external AI credentials;
- removal of `facodi_ai_website` does not impair other consumers of `facodi_ai`.

## 19. Deliberate V1 exclusions

The following are explicitly out of scope for the first implementation unless required to satisfy the approved contracts above:

- Anthropic or additional built-in providers;
- arbitrary substring translation within a single Odoo translation unit;
- automatic translation on publish/save;
- scheduled/batch translation of many pages;
- automatic translation of global header/footer/menu content;
- a FACODI-owned translation datastore replacing Odoo translations;
- custom page-per-language URL structures;
- encrypted API keys beyond the chosen Odoo/database storage controls;
- automatic provider fallback unless explicitly configured;
- full prompt replacement by administrators;
- mandatory storage of full prompts/page payloads.

These may be added later through the reusable core and extension addons.

## 20. Odoo 19 technical grounding

The implementation should remain aligned with the Odoo 19 Community Website translation internals rather than reproducing them independently.

Relevant Odoo 19 components identified during design review include:

- `addons/website/static/src/builder/plugins/translation_plugin.js`, which builds translation metadata maps and handles standard editable translation units and attributes;
- `addons/website/static/src/builder/plugins/save_translation_plugin.js`, which persists current-language translation values using standard Website translation RPC;
- `/website/field/translation/update`, the standard Website JSON-RPC endpoint used to update translated field content;
- Odoo Website Builder translation tests, which should guide integration-style test coverage.

The implementation plan must inspect the exact Odoo 19 extension/plugin APIs before choosing patch points. FACODI should prefer supported plugin/resource extension mechanisms and minimal patches over replacing standard Odoo classes.

## 21. Implementation handoff

This document is the approved architecture and product behavior. The next artifact must be a concrete implementation plan that decomposes work into test-driven, reviewable steps. Implementation must not begin until this written specification has been reviewed and accepted as the authoritative design.