"""Scoped, comment-preserving Codex configuration transactions and backups."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from uuid import uuid4

import tomlkit

from .catalog import BUILTINS, EFFORT_LABELS, Catalog

ROLE_NAMES = ('fleet_code', 'fleet_tests', 'fleet_integration')
ROLE_TITLES = ('代码与调用链', '测试与回归', '日志与兼容性')
MANAGED = '# Managed by Codex Fleet Configurator v1'
RULE_START = '<!-- codex-fleet-configurator:start -->'
RULE_END = '<!-- codex-fleet-configurator:end -->'
DEFAULT_CONCURRENCY = 8
MAX_CONFIG_INTEGER = (1 << 63) - 1
UNSET = object()
CHILD_CONFIG_KEYS = {
    'agents': ('enabled', 'max_concurrent_threads_per_session', 'max_threads',
               'default_subagent_model', 'default_subagent_reasoning_effort'),
    'features': ('multi_agent', 'multi_agent_v2'),
}


class ConfigError(Exception):
    """Actionable error safe to display without dumping the user's configuration."""


@dataclass(frozen=True)
class Choice:
    model: str
    effort: str
    provider: str = 'openai'


@dataclass(frozen=True)
class Settings:
    children: tuple[Choice, Choice, Choice]
    max_concurrent: int = DEFAULT_CONCURRENCY
    enabled: bool = True


@dataclass(frozen=True)
class Target:
    config_dir: Path
    instructions_path: Path

    @property
    def config_path(self) -> Path:
        return self.config_dir / 'config.toml'

    @property
    def backup_dir(self) -> Path:
        return self.config_dir / 'fleet-config-backups'

    def paths(self) -> dict[str, Path]:
        return {'config': self.config_path,
                **{name: self.config_dir / 'agents' / f'{name}.toml' for name in ROLE_NAMES},
                'instructions': self.instructions_path}

    def identity(self) -> dict[str, str]:
        return {'config_dir': str(self.config_dir.resolve()),
                'instructions_path': str(self.instructions_path.resolve())}


@dataclass
class Snapshot:
    target: Target
    config: dict
    originals: dict[str, bytes | None]


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: bytes | None
    after: bytes | None


@dataclass
class Plan:
    target: Target
    changes: dict[str, FileChange]
    settings: Settings

    @property
    def dirty(self) -> bool:
        return any(c.before != c.after for c in self.changes.values())

    def preview(self) -> str:
        mode = '舰队模式（开启）' if self.settings.enabled else '非舰队模式（关闭）'
        lines = [f'目标模式：{mode}（保存后由新任务加载）',
                 '主控：由 Codex 当前任务界面选择模型、推理等级和服务来源。',
                 '关闭时禁用多 Agent 工具；以下参数仍保留，供下次开启使用。',
                 f'保存的子 Agent 并发上限：{self.settings.max_concurrent}（不包含主控）']
        config = _parse(self.changes['config'].after, '预览配置')
        lines.append(f"将写入：agents.enabled={str(config['agents']['enabled']).lower()}，"
                     f"features.multi_agent={str(config['features']['multi_agent']).lower()}，"
                     f"features.multi_agent_v2={str(config['features'].get('multi_agent_v2', False)).lower()}（缺省按 false）。")
        for name, title, choice in zip(ROLE_NAMES, ROLE_TITLES, self.settings.children):
            lines.append(f'{title}：{choice.model} / {choice.effort} / {choice.provider}  [{name}]')
        lines += ['', '以上三行是职责模板；同一模板可创建多个实例，并发上限控制同时运行的实例数。',
                  '通用子 Agent 默认采用第 1 行的模型和等级，服务来源继承主控。',
                  '三个专用角色使用各自行选定的服务来源。其他已有角色保持其原有设置。',
                  '', '涉及文件：']
        for change in self.changes.values():
            state = '更新' if change.before != change.after else '无变化'
            lines.append(f'[{state}] {change.path}')
        lines += ['', '保存前自动备份；保存和恢复均保留主控设置，恢复时检查子 Agent 配置冲突。',
                  '', '将写入的分工规则：', fleet_instructions(self.settings)]
        return '\n'.join(lines)


def _read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ConfigError(f'目标不能是符号链接：{path}')
    if path.exists() and not path.is_file():
        raise ConfigError(f'目标不是普通文件：{path}')
    try:
        return path.read_bytes() if path.exists() else None
    except OSError as exc:
        raise ConfigError(f'无法读取文件：{path}（{exc.strerror}）') from exc


def _parse(data: bytes | None, label: str) -> dict:
    try:
        return tomllib.loads((data or b'').decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        # Parser exception text can include source values such as credentials.
        raise ConfigError(f'{label} 不是有效的 UTF-8 TOML，请先修复后重新读取。') from exc


def load_snapshot(target: Target) -> Snapshot:
    paths = target.paths()
    if len({str(p.resolve()).casefold() for p in paths.values()}) != len(paths):
        raise ConfigError('配置文件与规则文件路径不能重合。')
    root = target.config_dir.resolve()
    for key, path in paths.items():
        if key != 'instructions' and not path.resolve().is_relative_to(root):
            raise ConfigError(f'目标路径超出配置目录：{path}')
    originals = {key: _read(path) for key, path in paths.items()}
    return Snapshot(target, _parse(originals['config'], '配置文件'), originals)


def _mapping(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f'{label} 必须是 TOML 表。')
    return value


def load_settings(snapshot: Snapshot) -> Settings:
    config = snapshot.config
    agents = _mapping(config.get('agents', {}), 'agents')
    features = _mapping(config.get('features', {}), 'features')
    for value in (agents.get('enabled', True), features.get('multi_agent', True),
                  features.get('multi_agent_v2', False)):
        if type(value) is not bool:
            raise ConfigError('舰队模式开关必须为布尔值。')
    # V2 bypasses agents.enabled; otherwise use the legacy flag only as a UI fallback.
    enabled = features.get('multi_agent_v2', False) or agents.get('enabled', features.get('multi_agent', True))
    fallback = Choice(str(agents.get('default_subagent_model', 'gpt-5.6-luna')),
                      str(agents.get('default_subagent_reasoning_effort', 'xhigh')),
                      str(config.get('model_provider', 'openai')) if 'default_subagent_model' in agents else 'openai')
    children = []
    for name in ROLE_NAMES:
        raw = snapshot.originals[name]
        if raw is not None and raw.decode('utf-8-sig', errors='replace').startswith(MANAGED):
            role = _parse(raw, f'角色 {name}')
            children.append(Choice(str(role.get('model', fallback.model)),
                                   str(role.get('model_reasoning_effort', fallback.effort)),
                                   str(role.get('model_provider', fallback.provider))))
        else:
            children.append(fallback)
    count = agents.get('max_concurrent_threads_per_session', agents.get('max_threads', DEFAULT_CONCURRENCY))
    if isinstance(count, bool) or not isinstance(count, int):
        raise ConfigError('子 Agent 并发数必须为整数。')
    return Settings(tuple(children), count, enabled)


def _validate(settings: Settings, catalog: Catalog | None = None) -> None:
    if type(settings.enabled) is not bool:
        raise ConfigError('舰队模式开关必须为布尔值。')
    if len(settings.children) != 3:
        raise ConfigError('需要配置三个子 Agent 职责模板。')
    if type(settings.max_concurrent) is not int or settings.max_concurrent < 1:
        raise ConfigError('子 Agent 并发数必须为正整数。')
    if settings.max_concurrent > MAX_CONFIG_INTEGER:
        raise ConfigError('子 Agent 并发数超出配置文件支持的整数范围。')
    capabilities = {**BUILTINS, **(catalog.capabilities if catalog else {})}
    for choice in settings.children:
        for label, value in (('模型', choice.model), ('服务来源', choice.provider)):
            if not isinstance(value, str) or not value.strip() or len(value) > 240 or re.search(r'[\s\x00-\x1f]', value):
                raise ConfigError(f'{label}不能为空或包含空白字符，且长度不能超过 240。')
        if choice.effort not in EFFORT_LABELS:
            raise ConfigError(f'不支持的推理等级：{choice.effort}')
        if choice.provider == 'openai' and choice.model in capabilities and choice.effort not in capabilities[choice.model]:
            raise ConfigError(f'{choice.model} 不支持 {choice.effort} 推理等级。')


def fleet_instructions(settings: Settings) -> str:
    if not settings.enabled:
        return ('## 非舰队模式\n\n'
                '舰队模式已关闭。主控使用 Codex 当前任务界面选定的模型和推理等级，独立完成分析、修改、测试及最终验收。\n'
                '不创建或委派子 Agent；代码审查、测试和兼容性检查由主控完成。\n'
                '已保存的子 Agent 模型、推理等级、服务来源和并发数仅保留供下次开启舰队模式使用。')
    lines = ['## 多 Agent 分工', '',
             '主控使用当前任务实际选定的模型和推理等级，负责拆任务、确定方案、修改代码、更新文档和最终验收。',
             f'存在可独立开展的分析工作时，按需使用以下三个子 Agent 职责模板；子 Agent 并发上限为 {settings.max_concurrent} 个，不包含主控：']
    for index, (name, title, choice) in enumerate(zip(ROLE_NAMES, ROLE_TITLES, settings.children), 1):
        lines.append(f'{index}. {name}：{title}；模型 {choice.model}，推理 {choice.effort}，服务来源 {choice.provider}。')
    lines += ['', '同一职责模板可按独立任务重复创建实例；模板数量不等于运行中的子 Agent 数量，无需为每个并发名额新增角色。',
              '子 Agent 仅分析与取证，不修改文件、不重启服务、不再创建子 Agent。',
              '每次委派明确目标、范围、已知事实和交付要求，只传必要上下文。',
              '返回结论、文件及行号、关键依据和未确认事项，区分验证事实与推测。',
              '主控等待期间继续处理独立工作，复核关键证据后统一修改；冲突或失败由主控补查或接管。',
              '小任务由主控直接处理。长任务进度同时显示已完成内容和剩余工作。',
              '最终交付说明改动、设计取舍、验证结果和未覆盖风险。']
    return '\n'.join(lines)


def _update_rules(before: bytes | None, settings: Settings) -> bytes:
    try:
        text = (before or b'').decode('utf-8-sig')
    except UnicodeError as exc:
        raise ConfigError('AGENTS.md 不是有效 UTF-8，无法安全追加规则。') from exc
    newline = '\r\n' if '\r\n' in text else '\n'
    start_count, end_count = text.count(RULE_START), text.count(RULE_END)
    if start_count != end_count or start_count > 1 or (start_count and text.index(RULE_START) > text.index(RULE_END)):
        raise ConfigError('AGENTS.md 的舰队规则标记不完整或重复，请先修复。')
    block = (RULE_START + '\n' + fleet_instructions(settings) + '\n' + RULE_END).replace('\n', newline)
    if start_count:
        text = text[:text.index(RULE_START)] + block + text[text.index(RULE_END) + len(RULE_END):]
    else:
        text += (newline * 2 if text else '') + block + newline
    bom = b'\xef\xbb\xbf' if (before or b'').startswith(b'\xef\xbb\xbf') else b''
    return bom + text.encode('utf-8')


def make_plan(snapshot: Snapshot, settings: Settings, catalog: Catalog | None = None) -> Plan:
    _validate(settings, catalog)
    before = snapshot.originals['config']
    doc = tomlkit.parse((before or b'').decode('utf-8-sig'))
    for table_name in ('agents', 'features'):
        _mapping(snapshot.config.get(table_name, {}), table_name)
        if table_name not in doc:
            doc[table_name] = tomlkit.table()
    agents = doc['agents']
    for name in ROLE_NAMES:
        if name in agents:
            raise ConfigError(f'配置中已注册同名角色 {name}，可能覆盖专用角色文件；请先处理该角色冲突。')
    if 'max_threads' in agents:
        del agents['max_threads']
    agents['enabled'] = settings.enabled
    agents['max_concurrent_threads_per_session'] = settings.max_concurrent
    agents['default_subagent_model'] = settings.children[0].model
    agents['default_subagent_reasoning_effort'] = settings.children[0].effort
    doc['features']['multi_agent'] = settings.enabled
    if not settings.enabled:
        doc['features']['multi_agent_v2'] = False
    config_text = tomlkit.dumps(doc)
    if b'\r\n' in (before or b''):
        config_text = config_text.replace('\r\n', '\n').replace('\n', '\r\n')
    bom = b'\xef\xbb\xbf' if (before or b'').startswith(b'\xef\xbb\xbf') else b''
    contents = {'config': bom + config_text.encode('utf-8')}
    for name, title, choice in zip(ROLE_NAMES, ROLE_TITLES, settings.children):
        existing = snapshot.originals[name]
        if existing is not None and not existing.decode('utf-8-sig', errors='replace').startswith(MANAGED):
            raise ConfigError(f'已有同名角色 {name} 不属于本工具，不能覆盖。')
        role = tomlkit.document()
        role.add(tomlkit.comment(MANAGED.removeprefix('# ')))
        role.update({'name': name, 'description': f'负责{title}的独立分析与取证。',
                     'model': choice.model, 'model_reasoning_effort': choice.effort,
                     'model_provider': choice.provider,
                     'developer_instructions': f'仅负责主控分配的{title}任务。只分析与取证，不修改文件，不安装依赖，不重启服务，不进行 Git 写操作，不再创建子 Agent。优先定向搜索，追踪真实调用链。返回结论、文件及行号、证据和未确认事项。遇到阻塞及时报告，由主控接管。'})
        contents[name] = tomlkit.dumps(role).encode('utf-8')
    contents['instructions'] = _update_rules(snapshot.originals['instructions'], settings)
    for key in ('config', *ROLE_NAMES):
        _parse(contents[key], key)
    return Plan(snapshot.target, {key: FileChange(path, snapshot.originals[key], contents[key])
                                for key, path in snapshot.target.paths().items()}, settings)


def _hash(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, data: bytes, *, expected=UNSET) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.fleet-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not UNSET and _read(path) != expected:
            raise ConfigError(f'暂存期间文件已被其他程序修改，未覆盖：{path}')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _replace(path: Path, data: bytes | None, *, expected=UNSET) -> None:
    if data is None:
        if expected is not UNSET and _read(path) != expected:
            raise ConfigError(f'删除前文件已被其他程序修改，未删除：{path}')
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, data, expected=expected)


@contextmanager
def _locked(target: Target):
    target.config_dir.mkdir(parents=True, exist_ok=True)
    lock = target.config_dir / '.fleet-config.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ConfigError(f'另一个配置操作正在运行；若程序曾异常退出，请确认没有配置器运行后删除 {lock}。') from exc
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _assert_current(changes: dict[str, FileChange]) -> None:
    for change in changes.values():
        if _read(change.path) != change.before:
            raise ConfigError(f'文件已被其他程序修改，请重新读取后操作：{change.path}')


def _commit(target: Target, changes: dict[str, FileChange], action: str) -> Path | None:
    dirty = {key: c for key, c in changes.items() if c.before != c.after}
    if not dirty:
        return None
    with _locked(target):
        _assert_current(changes)
        backup = target.backup_dir / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
        backup.mkdir(mode=0o700, parents=True)
        manifest = {'version': 1, 'target': target.identity(), 'action': action, 'state': 'preparing', 'files': {}}
        for key, change in dirty.items():
            for suffix, data in (('before', change.before), ('after', change.after)):
                if data is not None:
                    backup_file = backup / f'{key}.{suffix}'
                    backup_file.write_bytes(data)
                    if os.name != 'nt':
                        backup_file.chmod(0o600)
            manifest['files'][key] = {'before': _hash(change.before), 'after': _hash(change.after)}
        manifest_path = backup / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if os.name != 'nt':
            manifest_path.chmod(0o600)
        written = []
        try:
            for key, change in dirty.items():
                _assert_current({key: change})
                _replace(change.path, change.after, expected=change.before)
                written.append(change)
            for change in dirty.values():
                if _read(change.path) != change.after:
                    raise ConfigError(f'写入后校验失败：{change.path}')
            manifest['state'] = 'applied'
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            errors = []
            for change in reversed(written):
                try:
                    if _read(change.path) != change.after:
                        raise ConfigError('文件再次被外部修改，未覆盖')
                    _replace(change.path, change.before, expected=change.after)
                except Exception as rollback_exc:
                    errors.append(f'{change.path}: {rollback_exc}')
            manifest['state'] = 'recovery_required' if errors else 'rolled_back'
            try:
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError:
                errors.append('备份状态无法更新')
            detail = '；回滚未全部完成：' + '；'.join(errors) if errors else '；已撤销本次已写入的文件'
            raise ConfigError(f'保存失败：{exc}{detail}。备份：{backup}') from exc
        return backup


def apply_plan(plan: Plan) -> Path | None:
    return _commit(plan.target, plan.changes, 'apply')


def list_backups(target: Target) -> list[Path]:
    if not target.backup_dir.exists():
        return []
    result = []
    for path in sorted(target.backup_dir.iterdir(), reverse=True):
        if path.is_dir() and not path.is_symlink():
            try:
                manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                if manifest.get('state') == 'applied' and manifest.get('target') == target.identity():
                    result.append(path)
            except (OSError, ValueError, AttributeError):
                continue
    return result


def _restore_child_config(path: Path, before: bytes | None, after: bytes | None) -> FileChange:
    current = _read(path)
    current_data = _parse(current, '当前配置')
    before_data = _parse(before, '备份原配置')
    after_data = _parse(after, '备份应用后配置')
    doc = tomlkit.parse((current or b'').decode('utf-8-sig'))
    for table_name, keys in CHILD_CONFIG_KEYS.items():
        actual = _mapping(current_data.get(table_name, {}), table_name)
        expected = _mapping(after_data.get(table_name, {}), table_name)
        original = _mapping(before_data.get(table_name, {}), table_name)
        for key in keys:
            # Older releases did not own V2; leave it alone if this backup never changed it.
            if (key == 'multi_agent_v2'
                    and type(original.get(key, UNSET)) is type(expected.get(key, UNSET))
                    and original.get(key, UNSET) == expected.get(key, UNSET)):
                continue
            actual_value, expected_value = actual.get(key, UNSET), expected.get(key, UNSET)
            if type(actual_value) is not type(expected_value) or actual_value != expected_value:
                raise ConfigError(f'子 Agent 配置已被其他程序修改，未恢复：{table_name}.{key}')
            if key in original:
                if table_name not in doc:
                    doc[table_name] = tomlkit.table()
                doc[table_name][key] = original[key]
            elif table_name in doc and key in doc[table_name]:
                del doc[table_name][key]
        if (table_name in doc and table_name not in before_data
                and not doc[table_name] and not doc[table_name].as_string().strip()):
            del doc[table_name]
    text = tomlkit.dumps(doc)
    if b'\r\n' in (current or b''):
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
    bom = b'\xef\xbb\xbf' if (current or b'').startswith(b'\xef\xbb\xbf') else b''
    restored = bom + text.encode('utf-8')
    # Old releases backed up main settings too; restore only child-owned keys.
    # Exact original bytes remain safe when neither main nor other fields differ.
    if current == after and _parse(restored, '恢复配置') == before_data:
        restored = before
    return FileChange(path, current, restored)


def restore_backup(target: Target, backup: Path) -> None:
    if backup.is_symlink() or backup.resolve().parent != target.backup_dir.resolve():
        raise ConfigError('备份必须位于当前目标的备份目录内。')
    try:
        manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('version') != 1 or manifest.get('state') != 'applied'
                or manifest.get('target') != target.identity()):
            raise ConfigError('备份身份或状态与当前目标不匹配。')
        entries = manifest['files']
        paths = target.paths()
        if not isinstance(entries, dict) or not entries or not set(entries).issubset(paths):
            raise ConfigError('备份文件列表不合法。')
        changes = {}
        for key, hashes in entries.items():
            values = {}
            for suffix in ('before', 'after'):
                expected = hashes[suffix]
                values[suffix] = _read(backup / f'{key}.{suffix}') if expected is not None else None
                if _hash(values[suffix]) != expected:
                    raise ConfigError(f'备份文件校验失败：{key}.{suffix}')
            if key == 'config':
                changes[key] = _restore_child_config(paths[key], values['before'], values['after'])
            else:
                changes[key] = FileChange(paths[key], values['after'], values['before'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ConfigError('备份记录无法读取或格式不合法。') from exc
    load_snapshot(target)
    _commit(target, changes, 'restore')
