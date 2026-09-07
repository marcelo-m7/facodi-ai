import { BuilderAction } from "@html_builder/core/builder_action";
import { Plugin } from "@html_editor/plugin";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { uniqueId } from "@web/core/utils/functions";

const PAGE_SCOPE_SELECTOR = "#wrap";
const SOURCE_SELECTOR = "[data-oe-translation-source-sha]";
const FORBIDDEN_SCOPE_SELECTOR =
    ".o_not_editable, .o_frontend_to_backend_buttons, .o_brand_promotion, nav, [role='navigation']";
const SUPPORTED_ATTRIBUTES = new Set(["alt", "title", "placeholder", "value", "textContent"]);
const ACTION_DEPENDENCIES = [
    "customizeTranslationTab",
    "translation",
    "history",
    "valueHistory",
    "selection",
];

function asElement(node) {
    if (!node) {
        return null;
    }
    return node.nodeType === 1 ? node : node.parentElement;
}

function isInsidePageScope(element, root) {
    return Boolean(
        element &&
            root &&
            root.contains(element) &&
            !element.closest(FORBIDDEN_SCOPE_SELECTOR)
    );
}

function normalizeRecordId(value) {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function makeKey(candidate) {
    return [
        candidate.model,
        candidate.record_id,
        candidate.field,
        candidate.source_sha,
        candidate.kind,
        candidate.attribute || "",
        candidate.translation_state || "",
    ].join("|");
}

function candidateIsEligible(candidate, mode, selectedElement) {
    if (!candidate.source_sha || candidate.model !== "ir.ui.view" || candidate.field !== "arch_db") {
        return false;
    }
    if (!candidate.record_id || !isInsidePageScope(candidate.element, candidate.root)) {
        return false;
    }
    if (mode === "untranslated") {
        return candidate.translation_state === "to_translate" && !candidate.element.classList.contains("o_dirty");
    }
    if (mode === "selected") {
        return Boolean(
            selectedElement &&
                (candidate.element === selectedElement ||
                    candidate.element.contains(selectedElement) ||
                    selectedElement.contains(candidate.element))
        );
    }
    return true;
}

function collectTextCandidates(root) {
    const elements = [
        ...(root.matches(SOURCE_SELECTOR) ? [root] : []),
        ...root.querySelectorAll(SOURCE_SELECTOR),
    ];
    return elements.map((element) => ({
        root,
        element,
        kind: "text",
        attribute: null,
        model: element.dataset.oeModel,
        record_id: normalizeRecordId(element.dataset.oeId),
        field: element.dataset.oeField,
        source_sha: element.dataset.oeTranslationSourceSha,
        translation_state: element.dataset.oeTranslationState || "to_translate",
        attributeInfo: null,
    }));
}

function collectAttributeCandidates(root, translationInfoMap) {
    const candidates = [];
    for (const [element, attributeMap] of translationInfoMap || []) {
        if (!isInsidePageScope(element, root)) {
            continue;
        }
        for (const [attribute, info] of Object.entries(attributeMap || {})) {
            if (!SUPPORTED_ATTRIBUTES.has(attribute) || !info?.oeTranslationSourceSha) {
                continue;
            }
            candidates.push({
                root,
                element,
                kind: "attribute",
                attribute,
                model: info.oeModel,
                record_id: normalizeRecordId(info.oeId),
                field: info.oeField,
                source_sha: info.oeTranslationSourceSha,
                translation_state:
                    info.oeTranslationState || element.dataset.oeTranslationState || "to_translate",
                attributeInfo: info,
            });
        }
    }
    return candidates;
}

function findSelectedTranslationElement(root, selection) {
    const anchor = asElement(selection?.anchorNode);
    if (!anchor || !root.contains(anchor)) {
        return null;
    }
    return anchor.closest(`${SOURCE_SELECTOR}, .o_translatable_attribute, .o_translatable_text`);
}

export function collectTranslationDescriptors({
    root,
    mode,
    translationInfoMap,
    selection,
    idFactory = () => uniqueId("facodi_u_"),
}) {
    const selectedElement = mode === "selected" ? findSelectedTranslationElement(root, selection) : null;
    const rawCandidates = [
        ...collectTextCandidates(root),
        ...collectAttributeCandidates(root, translationInfoMap),
    ];
    const eligibleCandidates = rawCandidates.filter((candidate) =>
        candidateIsEligible(candidate, mode, selectedElement)
    );

    if (mode === "selected" && selectedElement) {
        const direct = eligibleCandidates.filter(
            (candidate) =>
                candidate.element === selectedElement || candidate.element.contains(selectedElement)
        );
        if (direct.length) {
            eligibleCandidates.splice(0, eligibleCandidates.length, ...direct);
        }
    }

    const grouped = new Map();
    for (const candidate of eligibleCandidates) {
        const key = makeKey(candidate);
        if (!grouped.has(key)) {
            const id = idFactory();
            const descriptor = {
                id,
                source_sha: candidate.source_sha,
                model: candidate.model,
                record_id: candidate.record_id,
                field: candidate.field,
                kind: candidate.kind,
                attribute: candidate.attribute,
                translation_state: candidate.translation_state,
            };
            if (mode === "selected") {
                descriptor.selected = true;
            }
            grouped.set(key, { descriptor, targets: [] });
        }
        grouped.get(key).targets.push(candidate);
    }

    const entries = [...grouped.values()];
    if (mode === "selected" && entries.length > 1) {
        entries.splice(1);
    }
    return entries;
}

export function validateCompleteResponse(entries, responseUnits) {
    if (!Array.isArray(responseUnits)) {
        throw new Error(_t("Invalid AI translation response."));
    }
    const expected = new Set(entries.map(({ descriptor }) => descriptor.id));
    const returnedIds = responseUnits.map((unit) => unit?.id);
    if (
        returnedIds.length !== expected.size ||
        new Set(returnedIds).size !== expected.size ||
        returnedIds.some((id) => !expected.has(id))
    ) {
        throw new Error(_t("Invalid AI translation response."));
    }
    return new Map(responseUnits.map((unit) => [unit.id, unit.translated_text]));
}

function inferPageViewId(root, entries) {
    const rootRecordId = normalizeRecordId(root.dataset.oeId);
    if (root.dataset.oeModel === "ir.ui.view" && rootRecordId) {
        return rootRecordId;
    }
    const counts = new Map();
    for (const { descriptor } of entries) {
        counts.set(descriptor.record_id, (counts.get(descriptor.record_id) || 0) + 1);
    }
    const ranked = [...counts.entries()].sort((left, right) => right[1] - left[1]);
    return ranked[0]?.[0] || null;
}

function keepOnlyPageLocalEntries(entries, pageViewId) {
    return entries.filter(({ descriptor }) => descriptor.record_id === pageViewId);
}

function applyTextTarget(target, translatedText) {
    target.element.innerHTML = translatedText;
    target.element.dataset.oeTranslationState = "translated";
}

function applyAttributeTarget(action, target, translatedText) {
    const { element, attribute, attributeInfo } = target;
    const oldValue = attributeInfo.translation;
    action.dependencies.history.applyCustomMutation({
        apply: () => (attributeInfo.translation = translatedText),
        revert: () => (attributeInfo.translation = oldValue),
    });
    element.dataset.oeTranslationState = "translated";
    if (attribute === "textContent" || attribute === "value") {
        action.dependencies.valueHistory.setValue(element, translatedText);
    } else {
        element.setAttribute(attribute, translatedText);
    }
}

function applyTranslations(action, entries, translatedById) {
    for (const entry of entries) {
        const translatedText = translatedById.get(entry.descriptor.id);
        if (typeof translatedText !== "string" || !translatedText.trim()) {
            throw new Error(_t("Invalid AI translation response."));
        }
        for (const target of entry.targets) {
            if (target.kind === "attribute") {
                applyAttributeTarget(action, target, translatedText);
            } else {
                applyTextTarget(target, translatedText);
            }
        }
    }
}

function showNotification(action, message, type = "info") {
    action.services.notification.add(message, {
        title: _t("FACODI AI"),
        type,
        sticky: type === "danger",
    });
}

async function executeTranslation(action, mode) {
    const translationState = action.dependencies.customizeTranslationTab.getTranslationState();
    const root = action.editable.querySelector(PAGE_SCOPE_SELECTOR) ||
        (action.editable.matches?.(PAGE_SCOPE_SELECTOR) ? action.editable : null);
    if (!root) {
        showNotification(action, _t("This page has no editable Website content."));
        return;
    }

    const translationInfoMap = action.dependencies.translation.getElToTranslationInfoMap();
    const selection =
        mode === "selected" ? action.dependencies.selection.getEditableSelection() : null;
    let entries = collectTranslationDescriptors({ root, mode, translationInfoMap, selection });
    if (!entries.length) {
        showNotification(
            action,
            mode === "selected"
                ? _t("Select text inside a complete translatable Website unit first.")
                : _t("No eligible Website translation units were found.")
        );
        return;
    }

    const pageViewId = inferPageViewId(root, entries);
    if (!pageViewId) {
        showNotification(action, _t("The local Website page view could not be identified."), "danger");
        return;
    }
    entries = keepOnlyPageLocalEntries(entries, pageViewId);
    if (!entries.length) {
        showNotification(action, _t("No Website-local translation units were found."));
        return;
    }

    const descriptors = entries.map(({ descriptor }) => descriptor);
    const targetLang = action.services.website.currentWebsite?.metadata?.lang;
    if (!targetLang) {
        showNotification(action, _t("The target Website language could not be identified."), "danger");
        return;
    }

    translationState.isTranslating = true;
    try {
        const response = await rpc(
            "/facodi_ai/website/translate",
            {
                units: descriptors,
                mode,
                target_lang: targetLang,
                page_view_id: pageViewId,
            },
            { silent: true }
        );
        if (response?.ok === false) {
            throw new Error(response.error?.message || _t("FACODI AI translation failed."));
        }
        const translatedById = validateCompleteResponse(entries, response?.units);
        applyTranslations(action, entries, translatedById);
        showNotification(
            action,
            _t("AI translations were applied in the editor. Review them and use the standard Save button to persist."),
            "success"
        );
    } catch (error) {
        showNotification(
            action,
            error?.message || _t("FACODI AI translation failed."),
            "danger"
        );
        throw error;
    } finally {
        translationState.isTranslating = false;
    }
}

async function confirmRetranslation(action) {
    return new Promise((resolve) => {
        action.services.dialog.add(ConfirmationDialog, {
            title: _t("Retranslate page with FACODI AI?"),
            body: _t(
                "Existing translations in the current language will be replaced in the editor. You can review or undo the changes before using the standard Save button."
            ),
            confirmLabel: _t("Retranslate page"),
            confirm: () => resolve(true),
            cancel: () => resolve(false),
        });
    });
}

export class TranslateUntranslatedAction extends BuilderAction {
    static id = "facodiTranslateUntranslatedAI";
    static dependencies = ACTION_DEPENDENCIES;

    setup() {
        this.canTimeout = false;
    }

    async apply() {
        return executeTranslation(this, "untranslated");
    }
}

export class RetranslatePageAction extends BuilderAction {
    static id = "facodiRetranslatePageAI";
    static dependencies = ACTION_DEPENDENCIES;

    setup() {
        this.canTimeout = false;
    }

    async apply() {
        if (await confirmRetranslation(this)) {
            return executeTranslation(this, "all");
        }
    }
}

export class TranslateSelectedAction extends BuilderAction {
    static id = "facodiTranslateSelectedAI";
    static dependencies = ACTION_DEPENDENCIES;

    setup() {
        this.canTimeout = false;
    }

    async apply() {
        return executeTranslation(this, "selected");
    }
}

export class FacodiAiWebsiteTranslationPlugin extends Plugin {
    static id = "facodiAiWebsiteTranslation";

    resources = {
        builder_actions: {
            TranslateUntranslatedAction,
            RetranslatePageAction,
            TranslateSelectedAction,
        },
    };
}

registry
    .category("website-translation-plugins")
    .add(FacodiAiWebsiteTranslationPlugin.id, FacodiAiWebsiteTranslationPlugin);
