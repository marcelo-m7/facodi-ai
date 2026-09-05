from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSecuritySettings(TransactionCase):
    def _group(self, name):
        group = self.env["res.groups"].search([("name", "=", name)], limit=1)
        self.assertTrue(group, f"Missing security group: {name}")
        return group

    def _user(self, login, groups):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "group_ids": [(6, 0, groups.ids)],
            }
        )

    def test_internal_user_cannot_read_connection_records(self):
        user = self._user("ai-consumer", self.env.ref("base.group_user"))
        with self.assertRaises(AccessError):
            self.env["facodi.ai.connection"].with_user(user).search([]).read(["name"])

    def test_manager_can_read_requests_but_not_connections(self):
        manager_group = self._group("FACODI AI / Manager")
        user = self._user("ai-manager", self.env.ref("base.group_user") | manager_group)

        self.env["facodi.ai.request"].with_user(user).search([]).read(["state"])
        with self.assertRaises(AccessError):
            self.env["facodi.ai.connection"].with_user(user).search([]).read(["name"])

    def test_administrator_can_manage_configuration_records(self):
        admin_group = self._group("FACODI AI / Administrator")
        user = self._user("ai-admin", self.env.ref("base.group_user") | admin_group)
        provider = self.env["facodi.ai.provider"].with_user(user).create(
            {
                "name": "Test Provider",
                "code": "security-test",
                "adapter_key": "security-test",
            }
        )
        provider.with_user(user).write({"name": "Updated Test Provider"})
        self.assertEqual(provider.name, "Updated Test Provider")
        provider.with_user(user).unlink()

    def test_settings_default_connection_uses_connection_flag(self):
        settings_model = self.env["res.config.settings"]
        self.assertIn("default_openai_connection_id", settings_model._fields)
        self.assertIn("default_gemini_connection_id", settings_model._fields)

        provider = self.env.ref("facodi_ai.provider_openai")
        first = self.env["facodi.ai.connection"].create(
            {
                "name": "Primary OpenAI",
                "provider_id": provider.id,
                "is_default": True,
            }
        )
        second = self.env["facodi.ai.connection"].create(
            {
                "name": "Secondary OpenAI",
                "provider_id": provider.id,
            }
        )
        settings = settings_model.create({})
        self.assertEqual(settings.default_openai_connection_id, first)

        settings.write({"default_openai_connection_id": second.id})
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_settings_expose_code_defaults_and_persist_global_options(self):
        settings_model = self.env["res.config.settings"]
        for field_name in (
            "facodi_ai_enabled",
            "default_provider_code",
            "store_request_payloads",
            "recommended_openai_model",
            "recommended_gemini_model",
        ):
            self.assertIn(field_name, settings_model._fields)

        settings = settings_model.create({})
        self.assertTrue(settings.facodi_ai_enabled)
        self.assertEqual(settings.recommended_openai_model, "gpt-5.6-luna")
        self.assertEqual(settings.recommended_gemini_model, "gemini-3.8-flash")

        settings.write(
            {
                "facodi_ai_enabled": False,
                "default_provider_code": "openai",
                "store_request_payloads": True,
            }
        )
        settings.set_values()
        params = self.env["ir.config_parameter"].sudo()
        self.assertEqual(params.get_param("facodi_ai.enabled"), "False")
        self.assertEqual(params.get_param("facodi_ai.default_provider"), "openai")
        self.assertEqual(params.get_param("facodi_ai.store_request_payloads"), "True")

    def test_configuration_views_and_application_menu_are_loaded(self):
        xmlids = (
            "facodi_ai.res_config_settings_view_form",
            "facodi_ai.menu_facodi_ai_root",
            "facodi_ai.action_facodi_ai_dashboard",
            "facodi_ai.action_facodi_ai_connection",
            "facodi_ai.action_facodi_ai_profile",
            "facodi_ai.action_facodi_ai_prompt",
            "facodi_ai.action_facodi_ai_request",
        )
        for xmlid in xmlids:
            module, name = xmlid.split(".", 1)
            exists = self.env["ir.model.data"].search_count(
                [("module", "=", module), ("name", "=", name)]
            )
            self.assertEqual(exists, 1, f"Missing XML ID: {xmlid}")
