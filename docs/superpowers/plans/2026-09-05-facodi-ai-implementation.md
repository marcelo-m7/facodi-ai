# FACODI AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `facodi_ai` as a reusable multi-provider AI foundation for Odoo 19 Community and `facodi_ai_website` as a safe AI translation extension of Odoo's standard Website translation editor.

**Architecture:** `facodi_ai` owns provider/connection/profile/prompt/request configuration and a reusable `facodi.ai.service` backed by Pydantic AI. `facodi_ai_website` consumes only that service, plugs into Odoo 19's existing Website translation plugin registry, replaces the standard single AI translation button with FACODI actions, resolves source strings from the Website default language, returns validated structured translations to the browser, and leaves persistence to Odoo's standard `SaveTranslationPlugin` and `/website/field/translation/update` flow.

**Tech Stack:** Odoo 19 Community, Python 3, PostgreSQL 16, Pydantic AI 2.39.0, OpenAI Responses API, Google Gemini API, OWL/Website Builder plugins, HOOT JavaScript tests, Odoo `TransactionCase`/`HttpCase`, GitHub Actions, Docker.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-ai-design.md`

## Global Constraints

- Work in an isolated implementation branch/worktree created from `main`; do not implement directly on `main`.
- Follow test-driven development: add a failing test, run it and observe the intended failure, implement the smallest passing change, rerun, then commit.
- Keep `facodi_ai` independent from `website`, `website_slides`, FACODI theme, and FACODI learning.
- `facodi_ai_website` depends only on `website` and `facodi_ai`.
- Do not call external AI APIs from CI. Provider tests use mocks/fakes.
- Do not override or monkey-patch `/html_editor/generate_text`; FACODI owns a dedicated Website translation route.
- Do not create duplicate Website pages, language-specific FACODI pages, or a parallel translation store.
- Do not persist AI-generated Website translations in the AI endpoint. The browser applies validated changes to the existing editor; Odoo's normal Save persists them.
- Use Odoo's `data-oe-translation-source-sha`, model, record and field metadata as translation identity.
- Use unique Website Builder action IDs. Odoo rejects duplicate `builder_actions` IDs.
- Full request payload logging remains disabled by default.
- API keys are stored in `ir.config_parameter`, never returned after save, and never logged.
- Code defaults are visible as effective values but are not copied into database records unless the administrator explicitly overrides them.
- Initial recommended models are `gemini-3.8-flash` for Gemini and `gpt-5.6-luna` for OpenAI. Model names remain configurable.
- Initial translation defaults: provider preference `gemini`, timeout `60`, max output tokens `8192`, Pydantic AI retries `2`, structured output enabled. Temperature has no code default and is only sent when explicitly overridden, avoiding provider/model sampling incompatibilities.

---

## Task 1: Scaffold both addons, dependency image, and CI contract

**Files**

- Create: `requirements.txt`
- Create: `docker/Dockerfile.ci`
- Create: `.github/workflows/ci.yml`
- Create: `facodi_ai/__init__.py`
- Create: `facodi_ai/__manifest__.py`
- Create: `facodi_ai/models/__init__.py`
- Create: `facodi_ai/tests/__init__.py`
- Create: `facodi_ai_website/__init__.py`
- Create: `facodi_ai_website/__manifest__.py`
- Create: `facodi_ai_website/tests/__init__.py`
- Create: `tests/test_repository_contract.py`

**Interfaces**

```python
# facodi_ai/__manifest__.py
{
    "name": "FACODI AI",
    "version": "19.0.1.0.0",
    "depends": ["base", "web"],
    "external_dependencies": {"python": ["pydantic_ai"]},
    "application": True,
    "license": "LGPL-3",
}
```

```python
# facodi_ai_website/__manifest__.py
{
    "name": "FACODI AI Website",
    "version": "19.0.1.0.0",
    "depends": ["website", "facodi_ai"],
    "application": False,
    "license": "LGPL-3",
}
```

- [ ] Add `tests/test_repository_contract.py` asserting both manifests exist, `facodi_ai` does not depend on `website`, `facodi_ai_website` depends exactly on `website` + `facodi_ai` beyond base transitive dependencies, and `requirements.txt` pins Pydantic AI.
- [ ] Run `python -m unittest tests.test_repository_contract -v`; expected failure: manifests/requirements are missing.
- [ ] Add `requirements.txt` containing exactly `pydantic-ai-slim[openai,google]==2.39.0` for the initial pin.
- [ ] Add the minimal addon package/manifests and import files.
- [ ] Add `docker/Dockerfile.ci` based on `odoo:19.0`, installing `requirements.txt` as root and returning to `USER odoo`.
- [ ] Add GitHub Actions CI with PostgreSQL 16 and two Odoo phases: clean install `-i facodi_ai,facodi_ai_website` and upgrade `-u facodi_ai,facodi_ai_website`, both `--workers=0 --without-demo=True --stop-after-init`; include Python contract tests before Odoo tests.
- [ ] Run `python -m unittest tests.test_repository_contract -v`; expected pass.
- [ ] Build the CI image locally: `docker build -f docker/Dockerfile.ci -t facodi-ai-ci .`; expected success and `python3 -c 'import pydantic_ai'` inside the image succeeds.
- [ ] Commit: `git add . && git commit -m "chore: scaffold FACODI AI addons and CI"`.

---

## Task 2: Define core contracts, defaults, errors, and provider registry

**Files**

- Create: `facodi_ai/services/__init__.py`
- Create: `facodi_ai/services/contracts.py`
- Create: `facodi_ai/services/defaults.py`
- Create: `facodi_ai/services/errors.py`
- Create: `facodi_ai/services/provider_registry.py`
- Create: `facodi_ai/tests/test_services_contract.py`

**Interfaces**

```python
class TranslationInputUnit(BaseModel):
    id: str
    source_sha: str
    text: str
    protected_tokens: list[str] = []

class TranslationUnitResult(BaseModel):
    id: str
    translated_text: str

class TranslationResult(BaseModel):
    units: list[TranslationUnitResult]
```

```python
PROVIDER_DEFAULTS = {
    "openai": {"model": "gpt-5.6-luna"},
    "gemini": {"model": "gemini-3.8-flash"},
}
PROFILE_DEFAULTS = {
    "website_translation": {
        "provider": "gemini",
        "timeout": 60,
        "max_tokens": 8192,
        "retries": 2,
        "structured_output": True,
        "temperature": None,
    },
}
```

```python
class FacodiAIError(Exception):
    code = "internal_error"

class ConfigurationError(FacodiAIError): code = "configuration_error"
class AuthenticationError(FacodiAIError): code = "authentication_error"
class ProviderError(FacodiAIError): code = "provider_error"
class RateLimitError(FacodiAIError): code = "rate_limit"
class TimeoutError(FacodiAIError): code = "timeout"
class ValidationError(FacodiAIError): code = "validation_error"
class UnsupportedCapabilityError(FacodiAIError): code = "unsupported_capability"
```

- [ ] Write tests proving Pydantic contracts reject duplicate/missing IDs at the explicit validation layer, defaults resolve to the exact V1 values above, and registry rejects duplicate provider adapter keys.
- [ ] Run `odoo ... -i facodi_ai --test-tags /facodi_ai:TestServiceContracts --stop-after-init`; expected failure because service files/classes are missing.
- [ ] Implement contracts and a `validate_translation_result(request_units, result)` function that requires exact ID equality, one result per request unit, and exact protected-token preservation.
- [ ] Implement immutable default dictionaries and helper `get_profile_defaults(code)` returning a copy.
- [ ] Implement `ProviderAdapterRegistry.register(key, adapter_cls)`, `.get(key)`, and `.keys()` with duplicate-key validation.
- [ ] Run the focused Odoo test; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: add AI contracts defaults and provider registry"`.

---

## Task 3: Implement providers and multiple connections with write-only credentials

**Files**

- Create: `facodi_ai/models/provider.py`
- Create: `facodi_ai/models/connection.py`
- Create: `facodi_ai/services/secret_store.py`
- Create: `facodi_ai/data/provider_data.xml`
- Create: `facodi_ai/tests/test_connection.py`
- Modify: `facodi_ai/models/__init__.py`
- Modify: `facodi_ai/__manifest__.py`

**Interfaces**

`facodi.ai.provider` fields:

- `name: Char(required=True)`
- `code: Char(required=True, index=True)` unique
- `adapter_key: Char(required=True)`
- `active: Boolean(default=True)`
- `sequence: Integer(default=10)`
- `capability_codes: Char(readonly=True)` for V1 display

`facodi.ai.connection` fields:

- `name`, `provider_id`, `active`, `sequence`, `is_default`
- `credential_uuid` generated once and immutable after create
- `api_key` computed/inverse, never stored and always reads as `False`
- `api_key_configured` computed Boolean
- `base_url`, `organization`, `project`
- `last_test_at`, `last_test_status`, `last_test_message`

Secret parameter key:

```python
f"facodi_ai.connection.{connection.credential_uuid}.api_key"
```

- [ ] Write tests for two connections per provider, unique provider code, only one default connection per provider, key write/read through service, and `api_key` never exposing the saved secret when the record is read again.
- [ ] Run focused test; expected failure because models are absent.
- [ ] Implement `SecretStore` around `ir.config_parameter.sudo()` with `set_connection_api_key`, `get_connection_api_key`, `has_connection_api_key`, and `delete_connection_api_key`.
- [ ] Implement provider and connection models; enforce default uniqueness by clearing peers in `write/create` rather than relying on a global SQL constraint.
- [ ] Add two `noupdate="1"` provider data records: `facodi_ai.provider_openai` and `facodi_ai.provider_gemini`. Do not create connections automatically.
- [ ] Add unlink cleanup of the secret parameter.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: add provider connections and credential storage"`.

---

## Task 4: Implement prompts, profiles, and effective override resolution

**Files**

- Create: `facodi_ai/models/prompt.py`
- Create: `facodi_ai/models/profile.py`
- Create: `facodi_ai/services/profile_resolver.py`
- Create: `facodi_ai/tests/test_profile_resolution.py`
- Modify: `facodi_ai/models/__init__.py`

**Interfaces**

`facodi.ai.prompt`:

- `name`, `code`, `capability`, `active`, `custom_instructions`, `version`

`facodi.ai.profile`:

- `name`, `code`, `capability`, `active`
- `connection_id`, `prompt_id`
- `model_override: Char`
- `temperature_override: Float` plus `temperature_overridden: Boolean`
- `timeout_override: Integer`
- `max_tokens_override: Integer`
- `structured_output_override: Selection([("default", ...), ("enabled", ...), ("disabled", ...)])`
- `fallback_profile_id`
- computed readonly effective fields for provider, model, timeout, max tokens, temperature and structured-output behavior

Resolution order:

```text
explicit profile override
→ explicit connection/provider choice where applicable
→ profile code default
→ provider default
```

- [ ] Add failing tests for a blank Website Translation profile resolving to Gemini + `gemini-3.8-flash`, explicit OpenAI connection resolving to `gpt-5.6-luna`, explicit model override winning, timeout/max-token override winning, and temperature remaining `None` unless explicitly enabled.
- [ ] Run focused test and observe failure.
- [ ] Implement resolver as a pure service taking `profile` and returning an immutable `ResolvedAIProfile` dataclass/Pydantic model; do not write effective values back to the profile.
- [ ] Enforce no fallback cycle with a constraint traversing `fallback_profile_id`.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: add AI profiles prompts and default resolution"`.

---

## Task 5: Add request audit records and payload-logging policy

**Files**

- Create: `facodi_ai/models/request.py`
- Create: `facodi_ai/services/audit.py`
- Create: `facodi_ai/tests/test_request_audit.py`
- Modify: `facodi_ai/models/__init__.py`

**Interfaces**

`facodi.ai.request` stores profile, connection, provider code, model, capability, user, state, timestamps, duration ms, input/output unit counts, input/output token counts when available, normalized error code/message, and optional JSON payload fields.

Global parameter:

```text
facodi_ai.store_request_payloads = False
```

- [ ] Add tests proving successful and failed runs create audit rows, secrets are never captured, payloads are blank by default, and payloads are stored only when the global flag is explicitly true.
- [ ] Run focused test; expected failure.
- [ ] Implement audit start/success/failure helpers. Sanitize exception strings so provider request headers, API-key-like values, and raw tracebacks are not persisted.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: add AI request auditing"`.

---

## Task 6: Implement Pydantic AI OpenAI/Gemini adapters and reusable `facodi.ai.service`

**Files**

- Create: `facodi_ai/services/adapters/__init__.py`
- Create: `facodi_ai/services/adapters/base.py`
- Create: `facodi_ai/services/adapters/openai.py`
- Create: `facodi_ai/services/adapters/gemini.py`
- Create: `facodi_ai/services/model_factory.py`
- Create: `facodi_ai/models/ai_service.py`
- Create: `facodi_ai/tests/test_ai_service.py`
- Modify: `facodi_ai/models/__init__.py`
- Modify: `facodi_ai/services/__init__.py`

**Interfaces**

OpenAI factory:

```python
provider = OpenAIProvider(api_key=api_key, base_url=base_url or None)
model = OpenAIResponsesModel(model_name, provider=provider)
```

Gemini factory:

```python
provider = GoogleProvider(api_key=api_key)
model = GoogleModel(model_name, provider=provider)
```

Generic Odoo service:

```python
self.env["facodi.ai.service"].run(
    profile_code="website_translation",
    input_data=input_model,
    output_type=TranslationResult,
    system_prompt=system_prompt,
    request_context={"feature": "website_translation"},
)

self.env["facodi.ai.service"].translate(
    profile_code="website_translation",
    units=units,
    source_lang="pt_PT",
    target_lang="en_US",
    context={"page_name": "Home"},
)
```

- [ ] Add tests using fake adapter classes registered in `ProviderAdapterRegistry`; prove the service resolves a profile, refuses disabled/missing connections and missing keys, emits structured `TranslationResult`, validates exact IDs/protected tokens, and writes request audit rows.
- [ ] Add adapter-specific unit tests patching Pydantic AI model/Agent construction so CI never makes HTTP calls.
- [ ] Run focused tests; expected failure.
- [ ] Implement adapter interface `build_model(resolved_profile, api_key)` and `run_structured(...)`.
- [ ] Use `Agent(model, output_type=output_type, retries=resolved.retries, model_settings=...)`. Pass `timeout` and `max_tokens`; pass `temperature` only when the effective value is not `None`.
- [ ] Implement provider-exception normalization to the FACODI error classes, with dedicated handling for authentication, rate limiting and timeouts where the upstream exception type is identifiable.
- [ ] Implement `facodi.ai.service` as an `AbstractModel` delegating to the services above; convenience methods must route through the same `run` engine.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: integrate OpenAI and Gemini through Pydantic AI"`.

---

## Task 7: Add Odoo security, Settings integration, and FACODI AI application UI

**Files**

- Create: `facodi_ai/security/facodi_ai_security.xml`
- Create: `facodi_ai/security/ir.model.access.csv`
- Create: `facodi_ai/models/res_config_settings.py`
- Create: `facodi_ai/views/res_config_settings_views.xml`
- Create: `facodi_ai/views/provider_views.xml`
- Create: `facodi_ai/views/connection_views.xml`
- Create: `facodi_ai/views/profile_views.xml`
- Create: `facodi_ai/views/prompt_views.xml`
- Create: `facodi_ai/views/request_views.xml`
- Create: `facodi_ai/views/dashboard_views.xml`
- Create: `facodi_ai/views/menu.xml`
- Create: `facodi_ai/tests/test_security_settings.py`
- Modify: `facodi_ai/__manifest__.py`

**Interfaces**

Groups:

```text
facodi_ai.group_ai_user
facodi_ai.group_ai_manager      implies user
facodi_ai.group_ai_admin        implies manager
```

Settings parameters:

```text
facodi_ai.enabled
facodi_ai.default_provider
facodi_ai.default_openai_connection_id
facodi_ai.default_gemini_connection_id
facodi_ai.store_request_payloads
```

- [ ] Add tests proving normal internal users cannot read connection credential configuration or manage providers/profiles/prompts, managers can read requests, administrators can configure all records, and Settings effective default fields render without creating override rows.
- [ ] Run focused test; expected failure.
- [ ] Implement ACLs and record visibility. Only AI administrators may write provider/connection/profile/prompt configuration. AI users do not get raw connection record access solely because they can consume an AI feature.
- [ ] Add the standard Settings section with enable switch, default provider/connections, effective recommended model labels, request-payload debug switch and action link to advanced configuration.
- [ ] Add own app menus: Dashboard, Connections, Profiles, Prompts, Requests / Usage, Configuration. Keep Dashboard to operational counts/status only.
- [ ] Ensure password field writes a new key but does not display the prior value.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai && git commit -m "feat: add FACODI AI configuration application"`.

---

## Task 8: Scaffold Website consumer and default Website Translation profile

**Files**

- Create: `facodi_ai_website/models/__init__.py`
- Create: `facodi_ai_website/models/res_config_settings.py`
- Create: `facodi_ai_website/data/profile_data.xml`
- Create: `facodi_ai_website/views/res_config_settings_views.xml`
- Create: `facodi_ai_website/tests/test_profile_setup.py`
- Modify: `facodi_ai_website/__init__.py`
- Modify: `facodi_ai_website/__manifest__.py`

**Interfaces**

Data records:

```text
prompt code: website_translation
profile code: website_translation
capability: translation
```

The profile record has blank provider/model/runtime overrides so effective values come from code defaults; administrators can override them later.

- [ ] Add failing test proving installing `facodi_ai_website` creates exactly one Website Translation prompt/profile, does not create a provider connection, and the effective provider/model use code defaults.
- [ ] Run focused test and observe failure.
- [ ] Implement data and Settings extension exposing Website Translation profile plus effective connection/provider/model values.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: add Website AI translation profile"`.

---

## Task 9: Resolve authoritative source terms and enforce local-page eligibility

**Files**

- Create: `facodi_ai_website/services/__init__.py`
- Create: `facodi_ai_website/services/source_resolver.py`
- Create: `facodi_ai_website/services/eligibility.py`
- Create: `facodi_ai_website/tests/test_source_resolver.py`

**Interfaces**

Browser-to-server unit descriptor contains no authoritative source text:

```json
{
  "id": "facodi_u_1",
  "source_sha": "sha256-value",
  "model": "ir.ui.view",
  "record_id": 123,
  "field": "arch_db",
  "kind": "text",
  "attribute": null,
  "translation_state": "to_translate"
}
```

Resolver algorithm:

1. Validate model/record/field existence and read access.
2. Validate field is translatable.
3. Read the field in `website.default_lang_id.code` context.
4. Extract Odoo translation source terms using the field's standard translation term extraction.
5. Build `sha256(term.encode()).hexdigest() -> term` and resolve only the supplied source SHA.
6. Reject unknown SHAs rather than trusting browser text.

Eligibility V1:

- Allow local page `ir.ui.view.arch_db` translation units tied to the current `website.page.view_id` / website-specific local view ancestry.
- Reject `website.menu`, header/footer layout views, global shared templates, other websites, and ambiguous records.
- Require current target language to be in `website.language_ids` and differ from `website.default_lang_id`.

- [ ] Add tests with PT default + EN target for valid page term, invalid SHA, wrong language, global header/footer view, menu record, different website and non-translatable field.
- [ ] Run tests; expected failure.
- [ ] Implement resolver and conservative eligibility service using standard Odoo field translation helpers rather than parsing browser HTML for source authority.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: resolve safe Website translation sources"`.

---

## Task 10: Add deterministic markup protection and response validation

**Files**

- Create: `facodi_ai_website/services/markup.py`
- Create: `facodi_ai_website/tests/test_markup.py`

**Interfaces**

```python
ProtectedText(
    text="Conheça {{TAG_1_OPEN}}cursos{{TAG_1_CLOSE}}.",
    tokens=["{{TAG_1_OPEN}}", "{{TAG_1_CLOSE}}"],
    reconstruction={...},
)
```

- [ ] Add failing tests for plain text, `<strong>`, nested inline tags, links with unchanged `href`, leading/trailing whitespace, malicious returned `<script>`, changed token, missing token, duplicate token and unexpected tag.
- [ ] Run focused test; expected failure.
- [ ] Implement deterministic tokenizer for inline markup approved by Odoo translation units. Replace structure with opaque tokens; never expose mutable `href`, class, id, style, `data-*`, QWeb attributes, scripts or structural attributes to the model.
- [ ] Implement reconstruction that only accepts the exact multiset/order constraints required by the source unit and restores original markup/attributes.
- [ ] Reject rather than repair structural mismatches.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: protect Website translation markup"`.

---

## Task 11: Add dedicated synchronous Website translation controller

**Files**

- Create: `facodi_ai_website/controllers/__init__.py`
- Create: `facodi_ai_website/controllers/main.py`
- Create: `facodi_ai_website/tests/test_translation_controller.py`
- Modify: `facodi_ai_website/__init__.py`

**Interface**

Route:

```python
@http.route(
    "/facodi_ai/website/translate",
    type="jsonrpc",
    auth="user",
    website=True,
    methods=["POST"],
)
def translate(self, units, mode, target_lang, page_view_id): ...
```

Response:

```json
{
  "units": [
    {"id": "facodi_u_1", "translated_text": "Discover our courses"}
  ],
  "meta": {"provider": "gemini", "model": "gemini-3.8-flash", "request_id": 42}
}
```

- [ ] Add failing `HttpCase` tests for anonymous rejection, non-Website-editor rejection, default-language rejection, inactive target language, invalid local ownership, valid editor request, and provider failure returning a normalized user-safe error.
- [ ] Patch `facodi.ai.service.translate` in tests; no real provider calls.
- [ ] Run focused test and observe failure.
- [ ] Implement controller permission checks using the Website editor groups already required by Odoo; do not grant rights through FACODI AI groups.
- [ ] Resolve all source texts server-side, protect markup, call `facodi.ai.service.translate`, validate full result, reconstruct deterministic output, and return only after every requested unit validates. Do not call `write()` on translated fields and do not call `/website/field/translation/update`.
- [ ] Chunk server-side by a deterministic character budget of 6000 while preserving atomic semantics: collect and validate every batch before returning any result.
- [ ] Run tests; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: add Website AI translation endpoint"`.

---

## Task 12: Integrate FACODI actions into Odoo 19's standard translation builder

**Files**

- Create: `facodi_ai_website/static/src/builder/facodi_ai_translation_plugin.js`
- Create: `facodi_ai_website/static/src/builder/facodi_ai_translation_option.xml`
- Create: `facodi_ai_website/static/tests/facodi_ai_translation.test.js`
- Modify: `facodi_ai_website/__manifest__.py`

**Odoo integration points already present in Community**

- Translation mode appends `registry.category("website-translation-plugins").getAll()`.
- `TranslationPlugin` exposes `getElToTranslationInfoMap()` and standard translation metadata.
- `CustomizeTranslationTabPlugin` already owns `translationState.isTranslating` and standard option block.
- Standard action ID `translateWebpageAI` already exists; FACODI must not reuse it.

**Unique action IDs**

```text
facodiTranslateUntranslatedAI
facodiRetranslatePageAI
facodiTranslateSelectedAI
```

Plugin registration:

```javascript
registry.category("website-translation-plugins").add(
    "facodiAiWebsiteTranslation",
    FacodiAiWebsiteTranslationPlugin
);
```

- [ ] Add HOOT test asserting FACODI plugin loads only in Website translation mode and its action IDs register without duplicate-action error.
- [ ] Run the JS unit test through Odoo's `web.assets_unit_tests`; expected failure because assets/plugin do not exist.
- [ ] Implement the plugin with dependencies `customizeTranslationTab`, `translation`, `history`, `valueHistory`, and `selection` where required.
- [ ] Implement collection from standard `[data-oe-translation-source-sha]` metadata and `translation.getElToTranslationInfoMap()`; do not invent a second translation-state system.
- [ ] Replace the contents of the standard `website.TranslateWebpageOption` template using `t-inherit` so the existing single Odoo OLG button is not presented when `facodi_ai_website` is installed. Render a standard Builder row labelled `Translate with AI` with three FACODI BuilderButtons: untranslated, entire page, selected content. The old `translateWebpageAI` action may remain registered internally but must not be wired to the visible FACODI UI.
- [ ] Add assets to `website.website_builder_assets` and test assets to `web.assets_unit_tests`.
- [ ] Run JS test; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: integrate FACODI AI with Website translation builder"`.

---

## Task 13: Implement untranslated, retranslate-all, selected-unit, atomic apply, and Undo/Redo

**Files**

- Modify: `facodi_ai_website/static/src/builder/facodi_ai_translation_plugin.js`
- Modify: `facodi_ai_website/static/tests/facodi_ai_translation.test.js`

**Behavior**

Untranslated mode selects only eligible elements with `data-oe-translation-state="to_translate"` and skips `.o_dirty`/existing translated units.

Retranslate mode includes every eligible local unit regardless of current translation state and shows Odoo `ConfirmationDialog` before RPC.

Selected mode uses `selection.getEditableSelection().anchorNode`, finds its closest complete `[data-oe-translation-source-sha]` unit, and refuses arbitrary substring translation.

Atomic apply:

```text
collect descriptors
→ one RPC
→ validate complete response
→ create one history save point / mutation group
→ mutate all nodes and translation-map values
→ history.addStep()
```

- [ ] Add failing HOOT test: untranslated action sends only yellow/to-translate unit and leaves green/translations untouched.
- [ ] Add failing HOOT test: retranslate sends both translated and untranslated eligible units only after confirmation.
- [ ] Add failing HOOT test: selected action sends exactly the containing Odoo translation unit, even when the browser selection covers only part of its text.
- [ ] Add failing HOOT test: header/footer/menu-like `.o_not_editable` content is excluded before RPC.
- [ ] Add failing HOOT test: malformed/missing/extra response IDs cause zero DOM changes.
- [ ] Add failing HOOT test: successful response updates text and translated state, standard Save later calls `/website/field/translation/update`, and FACODI action itself never calls that endpoint.
- [ ] Add failing HOOT test: Undo restores every AI change from a page-wide operation in one step.
- [ ] Run JS tests and observe failures.
- [ ] Implement request descriptor collection and server RPC to `/facodi_ai/website/translate` with `target_lang = currentWebsite.metadata.lang` and current page view identity.
- [ ] Implement all-response validation before any mutation.
- [ ] Apply text mutations and attribute translations through standard translation map/value-history APIs mirroring Odoo's existing translation action behavior. Preserve standard dirty/save semantics.
- [ ] Ensure `translationState.isTranslating` is set/reset in `try/finally`; use notifications for no eligible content and normalized failures.
- [ ] Run JS tests; expected pass.
- [ ] Commit: `git add facodi_ai_website && git commit -m "feat: complete interactive Website AI translation flows"`.

---

## Task 14: Validate language isolation, standard Save persistence, install/upgrade, docs, and release readiness

**Files**

- Create: `facodi_ai_website/tests/test_translation_integration.py`
- Create: `README.md`
- Create: `docs/operations.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `facodi_ai/__manifest__.py`
- Modify: `facodi_ai_website/__manifest__.py`

**Integration acceptance fixture**

- Website default language: `pt_PT`
- Target language: `en_US`
- Third installed language: `es_ES`
- Page with local translated + untranslated content and separately shared header/footer/menu content.

- [ ] Add integration test proving a FACODI-generated EN value saved through Odoo's standard `/website/field/translation/update` changes only `en_US`; `pt_PT` source and `es_ES` remain unchanged; no additional `website.page` or website-specific duplicate `ir.ui.view` is created.
- [ ] Add integration test proving core `facodi_ai` installs and its service/model configuration works with `facodi_ai_website` absent.
- [ ] Add install/upgrade CI jobs using the custom CI image and module test tags for both modules. Include HOOT unit tests through Odoo's standard unit-test asset route/test command used by Odoo 19.
- [ ] Run complete clean install: `odoo --addons-path=/usr/lib/python3/dist-packages/odoo/addons,. --workers=0 --without-demo=True -d facodi_ai_test -i facodi_ai,facodi_ai_website --test-enable --stop-after-init` and require exit 0.
- [ ] Run complete upgrade: same database with `-u facodi_ai,facodi_ai_website --test-enable --stop-after-init` and require exit 0.
- [ ] Run all Python/JS tests; require zero failures and confirm no network access to OpenAI/Google occurred in CI tests.
- [ ] Add `README.md` covering architecture, installation, Python dependency, OpenAI/Gemini connection setup, multiple connections, Settings, profiles, Website translation workflow and security limitation that keys are in DB backups.
- [ ] Add `docs/operations.md` covering connection test, provider/model overrides, request audit, payload logging, debugging normalized errors, upgrade procedure and uninstall boundary.
- [ ] Bump both module manifests to `19.0.1.0.0` only if not already at that version; do not invent a higher version before first release.
- [ ] Run repository placeholder scan: `grep -RInE '\b(TODO|TBD|FIXME)\b' facodi_ai facodi_ai_website README.md docs/operations.md`; expected no project placeholders.
- [ ] Run `git diff --check`; expected no whitespace errors.
- [ ] Commit: `git add . && git commit -m "docs: finalize FACODI AI v1 validation and operations"`.

---

## Final Verification Gate

Before claiming implementation complete:

- [ ] Run the full CI-equivalent suite from a clean database.
- [ ] Verify both module install and upgrade paths.
- [ ] Verify `facodi_ai` alone installs without Website.
- [ ] Verify OpenAI and Gemini adapters with mocked provider calls and manual connection-test capability in a configured development database.
- [ ] Verify Website default language remains untouched after target-language translation.
- [ ] Verify third languages remain untouched.
- [ ] Verify Translate untranslated preserves manual translations.
- [ ] Verify Retranslate entire page requires confirmation and can be undone as one editor operation.
- [ ] Verify Translate selected content maps to a whole Odoo translation unit.
- [ ] Verify header, footer, menus and ambiguous shared templates are excluded.
- [ ] Verify invalid AI output produces zero editor mutations.
- [ ] Verify standard Save, not FACODI backend, performs translation persistence.
- [ ] Verify no API key appears in browser reads, application logs, audit rows or test output.
- [ ] Run `git status --short`; expected clean worktree after final commit.
- [ ] Request code review using `superpowers:requesting-code-review` before opening/marking the implementation PR ready.
- [ ] Use `superpowers:verification-before-completion` before stating that V1 is complete or passing.
