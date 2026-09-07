from odoo.addons.web.tests.test_js import HOOTCommon, unit_test_error_checker
from odoo.tests import no_retry, tagged


@tagged("post_install", "-at_install")
class TestFacodiAIWebsiteHoot(HOOTCommon):
    @no_retry
    def test_facodi_ai_website_hoot(self):
        module_hash = self._generate_hash("@facodi_ai_website")
        self.browser_js(
            f"/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&id={module_hash}",
            "",
            "",
            login="admin",
            timeout=600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )
