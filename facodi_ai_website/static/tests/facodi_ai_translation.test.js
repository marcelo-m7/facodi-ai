import { expect, test } from "@odoo/hoot";
import { registry } from "@web/core/registry";
import {
    FacodiAiWebsiteTranslationPlugin,
    RetranslatePageAction,
    TranslateSelectedAction,
    TranslateUntranslatedAction,
    collectTranslationDescriptors,
    validateCompleteResponse,
} from "@facodi_ai_website/builder/facodi_ai_translation_plugin";

function makeRoot() {
    const root = document.createElement("div");
    root.id = "wrap";
    root.innerHTML = `
        <p id="eligible" data-oe-model="ir.ui.view" data-oe-id="42" data-oe-field="arch_db"
           data-oe-translation-state="to_translate" data-oe-translation-source-sha="sha-a">Olá</p>
        <p id="translated" data-oe-model="ir.ui.view" data-oe-id="42" data-oe-field="arch_db"
           data-oe-translation-state="translated" data-oe-translation-source-sha="sha-b">Existing</p>
        <p id="dirty" class="o_dirty" data-oe-model="ir.ui.view" data-oe-id="42" data-oe-field="arch_db"
           data-oe-translation-state="to_translate" data-oe-translation-source-sha="sha-c">Manual</p>
        <div class="o_not_editable">
            <p data-oe-model="ir.ui.view" data-oe-id="42" data-oe-field="arch_db"
               data-oe-translation-state="to_translate" data-oe-translation-source-sha="sha-d">Locked</p>
        </div>
        <nav>
            <p data-oe-model="ir.ui.view" data-oe-id="42" data-oe-field="arch_db"
               data-oe-translation-state="to_translate" data-oe-translation-source-sha="sha-e">Nav</p>
        </nav>
        <p id="other-view" data-oe-model="ir.ui.view" data-oe-id="99" data-oe-field="arch_db"
           data-oe-translation-state="to_translate" data-oe-translation-source-sha="sha-f">Other</p>
        <img id="image" title="Course cover"/>
    `;
    document.body.appendChild(root);
    return root;
}

function ids() {
    let index = 0;
    return () => `unit-${++index}`;
}

test("FACODI Website translation plugin registers unique actions", () => {
    expect(TranslateUntranslatedAction.id).toBe("facodiTranslateUntranslatedAI");
    expect(RetranslatePageAction.id).toBe("facodiRetranslatePageAI");
    expect(TranslateSelectedAction.id).toBe("facodiTranslateSelectedAI");
    expect(TranslateUntranslatedAction.dependencies).not.toContain("valueHistory");
    expect(
        registry.category("website-translation-plugins").get("facodiAiWebsiteTranslation")
    ).toBe(FacodiAiWebsiteTranslationPlugin);
});

test("untranslated mode preserves translated and dirty Website units", () => {
    const root = makeRoot();
    const entries = collectTranslationDescriptors({
        root,
        mode: "untranslated",
        translationInfoMap: new Map(),
        selection: null,
        idFactory: ids(),
    });
    expect(entries).toHaveLength(2);
    expect(entries.map((entry) => entry.descriptor.source_sha)).toEqual(["sha-a", "sha-f"]);
    root.remove();
});

test("full page mode includes translated local content and excludes locked navigation", () => {
    const root = makeRoot();
    const image = root.querySelector("#image");
    const translationInfoMap = new Map([
        [
            image,
            {
                title: {
                    oeModel: "ir.ui.view",
                    oeId: "42",
                    oeField: "arch_db",
                    oeTranslationSourceSha: "sha-title",
                    oeTranslationState: "to_translate",
                    translation: "Course cover",
                },
            },
        ],
    ]);
    const entries = collectTranslationDescriptors({
        root,
        mode: "all",
        translationInfoMap,
        selection: null,
        idFactory: ids(),
    });
    expect(entries.map((entry) => entry.descriptor.source_sha)).toEqual([
        "sha-a",
        "sha-b",
        "sha-c",
        "sha-f",
        "sha-title",
    ]);
    expect(entries.at(-1).descriptor.kind).toBe("attribute");
    expect(entries.at(-1).descriptor.attribute).toBe("title");
    root.remove();
});

test("selected mode maps a substring selection to one complete Odoo translation unit", () => {
    const root = makeRoot();
    const eligible = root.querySelector("#eligible");
    const entries = collectTranslationDescriptors({
        root,
        mode: "selected",
        translationInfoMap: new Map(),
        selection: { anchorNode: eligible.firstChild },
        idFactory: ids(),
    });
    expect(entries).toHaveLength(1);
    expect(entries[0].descriptor.source_sha).toBe("sha-a");
    expect(entries[0].descriptor.selected).toBe(true);
    root.remove();
});

test("invalid partial or duplicate AI responses are rejected before mutation", () => {
    const root = makeRoot();
    const entries = collectTranslationDescriptors({
        root,
        mode: "untranslated",
        translationInfoMap: new Map(),
        selection: null,
        idFactory: ids(),
    });
    const [first, second] = entries.map((entry) => entry.descriptor.id);
    expect(() => validateCompleteResponse(entries, [{ id: first, translated_text: "A" }])).toThrow();
    expect(() =>
        validateCompleteResponse(entries, [
            { id: first, translated_text: "A" },
            { id: first, translated_text: "B" },
        ])
    ).toThrow();
    expect(() =>
        validateCompleteResponse(entries, [
            { id: first, translated_text: "A" },
            { id: second, translated_text: "B" },
            { id: "extra", translated_text: "C" },
        ])
    ).toThrow();
    expect(
        validateCompleteResponse(entries, [
            { id: first, translated_text: "A" },
            { id: second, translated_text: "B" },
        ]).size
    ).toBe(2);
    root.remove();
});
