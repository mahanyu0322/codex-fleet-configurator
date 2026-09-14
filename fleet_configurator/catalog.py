"""Read model metadata without contacting a model service or reading credentials."""

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib

EFFORT_LABELS = {
    'none': '无 · none', 'minimal': '最低 · minimal', 'low': '低 · low',
    'medium': '中 · medium', 'high': '高 · high', 'xhigh': '极高 · xhigh',
    'max': '超高 · max', 'ultra': 'Ultra · ultra',
}
STANDARD = ('low', 'medium', 'high', 'xhigh')
BUILTINS = {
    'gpt-6-astra': STANDARD + ('max', 'ultra'),
    'gpt-5.6-sol': STANDARD + ('max', 'ultra'),
    'gpt-5.6-terra': STANDARD + ('max', 'ultra'),
    'gpt-5.6-luna': STANDARD + ('max',),
    'gpt-5.5': STANDARD,
    'gpt-5.3-codex-spark': STANDARD,
}


@dataclass(frozen=True)
class Catalog:
    capabilities: dict[str, tuple[str, ...]]
    providers: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(self.capabilities)

    def efforts(self, model: str) -> tuple[str, ...]:
        return self.capabilities.get(model, tuple(EFFORT_LABELS))


def load_catalog(codex_home: Path, extra_config: dict | None = None) -> Catalog:
    capabilities = dict(BUILTINS)
    providers = {'openai'}
    warnings = []
    cache = codex_home / 'models_cache.json'
    if cache.exists():
        try:
            models = json.loads(cache.read_text(encoding='utf-8-sig')).get('models', [])
            for entry in models:
                if not isinstance(entry, dict) or entry.get('visibility') == 'hide':
                    continue
                slug = entry.get('slug')
                levels = tuple(level['effort'] for level in entry.get('supported_reasoning_levels', [])
                               if isinstance(level, dict) and level.get('effort') in EFFORT_LABELS)
                if isinstance(slug, str) and levels:
                    capabilities[slug] = levels
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append('本机模型缓存无法读取，已使用内置模型列表。')
    else:
        warnings.append('未找到本机模型缓存，已使用内置模型列表。')

    configs = [extra_config or {}]
    config_path = codex_home / 'config.toml'
    if config_path.exists():
        try:
            configs.append(tomllib.loads(config_path.read_text(encoding='utf-8-sig')))
        except (OSError, ValueError):
            warnings.append('全局配置无法解析，服务来源列表可能不完整。')
    for config in configs:
        configured_providers = config.get('model_providers', {})
        if isinstance(configured_providers, dict):
            providers.update(configured_providers)
        profiles = config.get('profiles', {})
        entries = [config] + (list(profiles.values()) if isinstance(profiles, dict) else [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            provider, model = entry.get('model_provider'), entry.get('model')
            if isinstance(provider, str) and provider:
                providers.add(provider)
            if isinstance(model, str) and model:
                capabilities.setdefault(model, BUILTINS.get(model.split('::')[-1], tuple(EFFORT_LABELS)))
    return Catalog(capabilities, tuple(sorted(providers, key=lambda p: (p != 'openai', p))), tuple(warnings))
