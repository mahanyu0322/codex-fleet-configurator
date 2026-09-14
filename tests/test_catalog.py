import json
from pathlib import Path
import tempfile
import unittest

from fleet_configurator.catalog import load_catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_official_fallbacks_and_known_unsupported_levels(self):
        catalog = load_catalog(self.root)
        self.assertIn('ultra', catalog.efforts('gpt-6-astra'))
        self.assertNotIn('ultra', catalog.efforts('gpt-5.6-luna'))
        self.assertTrue(catalog.warnings)

    def test_cache_adds_models_and_overlays_efforts_ignoring_hidden(self):
        (self.root / 'models_cache.json').write_text(json.dumps({'models': [
            {'slug': 'new-model', 'supported_reasoning_levels': [{'effort': 'medium'}, {'effort': 'max'}]},
            {'slug': 'gpt-6-astra', 'supported_reasoning_levels': [{'effort': 'medium'}]},
            {'slug': 'hidden-model', 'visibility': 'hide', 'supported_reasoning_levels': [{'effort': 'high'}]},
        ]}), encoding='utf-8')
        catalog = load_catalog(self.root)
        self.assertEqual(catalog.efforts('new-model'), ('medium', 'max'))
        self.assertEqual(catalog.efforts('gpt-6-astra'), ('medium',))
        self.assertNotIn('hidden-model', catalog.models)

    def test_custom_provider_models_appear_without_sensitive_values(self):
        (self.root / 'config.toml').write_text(
            'model = "custom"\nmodel_provider = "proxy"\n'
            '[model_providers.proxy]\nname="Proxy"\nhttp_headers={"X-Key"="SECRET"}\n'
            '[profiles.test]\nmodel="profile-model"\nmodel_provider="proxy"\n', encoding='utf-8')
        catalog = load_catalog(self.root)
        self.assertIn('proxy', catalog.providers)
        self.assertIn('custom', catalog.models)
        self.assertIn('profile-model', catalog.models)
        self.assertNotIn('SECRET', repr(catalog))

    def test_malformed_cache_is_nonfatal_with_visible_warning(self):
        (self.root / 'models_cache.json').write_text('[]', encoding='utf-8')
        catalog = load_catalog(self.root)
        self.assertIn('gpt-5.6-luna', catalog.models)
        self.assertTrue(catalog.warnings)


if __name__ == '__main__':
    unittest.main()
