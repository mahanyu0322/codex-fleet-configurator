"""Local-only desktop controls for Codex fleet defaults."""

from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from .catalog import EFFORT_LABELS, load_catalog
from .storage import (
    Choice,
    ConfigError,
    DEFAULT_CONCURRENCY,
    MAX_CONFIG_INTEGER,
    Settings,
    Target,
    apply_plan,
    fleet_instructions,
    list_backups,
    load_settings,
    load_snapshot,
    make_plan,
    restore_backup,
)


BACKGROUND = "#F2F5FA"
NAVY = "#15243F"
INK = "#23334E"
MUTED = "#64748B"
BLUE = "#2563EB"
DISPLAY_ERRORS = (ConfigError, OSError, tk.TclError)


class ChoiceRow(ttk.Frame):
    def __init__(self, parent, title, subtitle, catalog, on_change):
        super().__init__(parent, style="Card.TFrame", padding=(0, 3))
        self.catalog = catalog
        self.on_change = on_change
        self.model_var = tk.StringVar(self)
        self.effort_var = tk.StringVar(self)
        self.provider_var = tk.StringVar(self, value="openai")
        self.allowed_efforts = ()
        self._updating = False
        self._custom_effort_pending = False
        self.columnconfigure(1, weight=3, minsize=245)
        self.columnconfigure(2, weight=1, minsize=150)
        self.columnconfigure(3, weight=1, minsize=160)
        identity = ttk.Frame(self, style="Card.TFrame", width=152)
        identity.grid(row=0, column=0, padx=(0, 16), sticky="w")
        identity.grid_propagate(False)
        identity.configure(height=42)
        ttk.Label(identity, text=title, style="RowTitle.TLabel").grid(sticky="w")
        ttk.Label(identity, text=subtitle, style="Caption.TLabel").grid(sticky="w")
        self.model_combo = ttk.Combobox(self, textvariable=self.model_var, width=29)
        self.model_combo.grid(row=0, column=1, padx=(0, 14), sticky="ew")
        self.effort_combo = ttk.Combobox(self, textvariable=self.effort_var, state="readonly", width=17)
        self.effort_combo.grid(row=0, column=2, padx=(0, 14), sticky="ew")
        self.provider_combo = ttk.Combobox(self, textvariable=self.provider_var, state="readonly", width=19)
        self.provider_combo.grid(row=0, column=3, sticky="ew")
        self.model_var.trace_add("write", self._model_changed)
        self.effort_var.trace_add("write", self._choice_changed)
        self.provider_var.trace_add("write", self._choice_changed)
        self.refresh_catalog(catalog)

    def _model_changed(self, *_):
        if not self._updating:
            self._custom_effort_pending = self.model_var.get().strip() not in self.catalog.models
            self.refresh_efforts()
            self.on_change()

    def _choice_changed(self, *_):
        if not self._updating:
            if self.effort_var.get():
                self._custom_effort_pending = False
            self.on_change()

    def refresh_catalog(self, catalog):
        self.catalog = catalog
        self.model_combo.configure(values=catalog.models)
        providers = list(catalog.providers)
        if self.provider_var.get() and self.provider_var.get() not in providers:
            providers.append(self.provider_var.get())
        self.provider_combo.configure(values=providers)
        self.refresh_efforts()

    def raw_effort(self):
        selected = self.effort_var.get()
        return next((raw for raw, label in EFFORT_LABELS.items() if label == selected), selected)

    def set_effort(self, effort):
        self.effort_var.set(EFFORT_LABELS.get(effort, effort))

    def refresh_efforts(self):
        current = self.raw_effort()
        self.allowed_efforts = tuple(self.catalog.efforts(self.model_var.get().strip()))
        self._updating = True
        try:
            self.effort_combo.configure(values=[EFFORT_LABELS.get(item, item) for item in self.allowed_efforts])
            if self._custom_effort_pending:
                current = ""
            elif current not in self.allowed_efforts and self.allowed_efforts:
                current = "xhigh" if "xhigh" in self.allowed_efforts else self.allowed_efforts[-1]
            self.set_effort(current)
        finally:
            self._updating = False

    def set_choice(self, choice):
        self._updating = True
        self._custom_effort_pending = False
        try:
            self.model_var.set(choice.model)
            self.provider_var.set(choice.provider)
            self.set_effort(choice.effort)
        finally:
            self._updating = False
        self.refresh_catalog(self.catalog)

    def get_choice(self):
        return Choice(self.model_var.get().strip(), self.raw_effort(), self.provider_var.get().strip())


class FleetConfiguratorApp(ttk.Frame):
    def __init__(self, root, *, config_dir=None, instructions_path=None, show_errors=True):
        super().__init__(root, style="App.TFrame")
        self.root = root
        self.show_errors = show_errors
        chosen_home = Path(config_dir or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
        chosen_instructions = Path(instructions_path).expanduser().resolve() if instructions_path else chosen_home / "AGENTS.md"
        self.global_target = Target(chosen_home, chosen_instructions)
        self.snapshot = None
        self.catalog = load_catalog(chosen_home)
        self.backup_paths = {}
        self._loading = True
        self._preview_after = None
        self.scope_var = tk.StringVar(root, value="global")
        self.project_var = tk.StringVar(root)
        self.target_var = tk.StringVar(root)
        self.status_var = tk.StringVar(root, value="读取本地配置…")
        self.warning_var = tk.StringVar(root)
        self.concurrent_var = tk.StringVar(root, value=str(DEFAULT_CONCURRENCY))
        self.enabled_var = tk.BooleanVar(root, value=True)
        self.mode_var = tk.StringVar(root)
        self._configure_window()
        self._build_interface()
        self.concurrent_var.trace_add("write", self._schedule_preview)
        self.enabled_var.trace_add("write", self._mode_changed)
        self._loading = False
        self.load_current()

    def _configure_window(self):
        available_fonts = set(tkfont.families(self.root))
        self.ui_font = next((name for name in ("Microsoft YaHei UI", "PingFang SC", "Heiti SC") if name in available_fonts),
                            tkfont.nametofont("TkDefaultFont", root=self.root).actual("family"))
        self.mono_font = next((name for name in ("Consolas", "Menlo", "Monaco") if name in available_fonts),
                              tkfont.nametofont("TkFixedFont", root=self.root).actual("family"))
        height = min(820, max(600, self.root.winfo_screenheight() - 80))
        width = min(1100, max(990, self.root.winfo_screenwidth() - 40))
        self.root.title("Codex 舰队配置器 · 子 Agent")
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(990, min(790, height))
        self.root.configure(background=BACKGROUND)
        self.root.option_add("*Font", (self.ui_font, 10))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=(self.ui_font, 10), foreground=INK)
        style.configure("App.TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="white", foreground=INK)
        style.configure("Title.TLabel", font=(self.ui_font, 12, "bold"))
        style.configure("RowTitle.TLabel", font=(self.ui_font, 10, "bold"))
        style.configure("Small.TLabel", font=(self.ui_font, 9), foreground=MUTED)
        style.configure("Caption.TLabel", font=(self.ui_font, -11), foreground=MUTED)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Status.TLabel", background=BACKGROUND, foreground=MUTED, font=(self.ui_font, 9))
        style.configure("TButton", padding=(13, 4), background="white", bordercolor="#D7E0EE")
        style.map("TButton", background=[("active", "#EAF1FE")])
        style.configure("Primary.TButton", background=BLUE, foreground="white", bordercolor=BLUE)
        style.map("Primary.TButton", background=[("active", "#1D4ED8"), ("pressed", "#1E40AF")], foreground=[("disabled", "#D1D5DB")])
        style.configure("TRadiobutton", background="white")
        style.configure("Mode.TCheckbutton", background="white", font=(self.ui_font, 12, "bold"))
        style.configure("TCombobox", padding=6, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)])
        style.configure("TEntry", padding=6)
        style.configure("TSpinbox", padding=5)
        style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(17, 7))
        style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", BLUE)])
        style.configure("Treeview", rowheight=31, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=(self.ui_font, 9, "bold"), padding=5)
        self.pack(fill="both", expand=True)

    def destroy(self):
        pending_preview = getattr(self, "_preview_after", None)
        if pending_preview is not None:
            self.root.after_cancel(pending_preview)
            self._preview_after = None
        super().destroy()

    def _build_interface(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        header = tk.Frame(self, background=NAVY, padx=25, pady=12)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="Codex 舰队配置器", font=(self.ui_font, 18, "bold"), foreground="white", background=NAVY).pack(anchor="w")
        tk.Label(header, text="主控由 Codex 当前任务界面选择 · 本工具配置三个子 Agent 职责模板", font=(self.ui_font, 10), foreground="#B8CAE8", background=NAVY).pack(anchor="w", pady=(4, 0))

        scope = ttk.Frame(self, style="Card.TFrame", padding=(18, 10))
        scope.grid(row=1, column=0, padx=20, pady=(14, 10), sticky="ew")
        scope.columnconfigure(4, weight=1)
        ttk.Label(scope, text="作用范围", style="Title.TLabel").grid(row=0, column=0, padx=(0, 22), sticky="w")
        ttk.Radiobutton(scope, text="全局默认", variable=self.scope_var, value="global", command=self._scope_changed).grid(row=0, column=1, padx=(0, 17))
        ttk.Radiobutton(scope, text="指定项目", variable=self.scope_var, value="project", command=self._scope_changed).grid(row=0, column=2, padx=(0, 12))
        self.project_entry = ttk.Entry(scope, textvariable=self.project_var, width=22)
        self.project_entry.grid(row=0, column=4, padx=(0, 8), sticky="ew")
        self.project_entry.bind("<Return>", lambda _event: self.load_current())
        ttk.Button(scope, text="选择目录…", command=self.choose_project).grid(row=0, column=5, padx=(0, 8))
        self.load_button = ttk.Button(scope, text="读取当前配置", command=self.load_current)
        self.load_button.grid(row=0, column=6)
        ttk.Label(scope, textvariable=self.target_var, style="Small.TLabel", wraplength=980).grid(row=1, column=0, columnspan=7, sticky="w", pady=(8, 0))

        model_card = ttk.Frame(self, style="Card.TFrame", padding=(18, 12))
        model_card.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        model_card.columnconfigure(0, weight=1)
        mode_bar = ttk.Frame(model_card, style="Card.TFrame")
        mode_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.mode_switch = ttk.Checkbutton(mode_bar, text="启用舰队模式", variable=self.enabled_var, style="Mode.TCheckbutton")
        self.mode_switch.pack(side="left")
        ttk.Label(mode_bar, textvariable=self.mode_var).pack(side="left", padx=16)
        ttk.Label(mode_bar, text="切换后点击“保存并应用”", style="Small.TLabel").pack(side="right")
        heading = ttk.Frame(model_card, style="Card.TFrame")
        heading.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="子 Agent 模型与推理强度", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(heading, text="全部设为 Luna / 极高", command=self.apply_preset).grid(row=0, column=1)
        labels = ttk.Frame(model_card, style="Card.TFrame")
        labels.grid(row=2, column=0, sticky="ew")
        labels.columnconfigure(1, weight=3, minsize=245)
        labels.columnconfigure(2, weight=1, minsize=150)
        labels.columnconfigure(3, weight=1, minsize=160)
        ttk.Label(labels, text="分工", style="Small.TLabel", width=20).grid(row=0, column=0, padx=(0, 16), sticky="w")
        ttk.Label(labels, text="模型（可输入自定义 ID）", style="Small.TLabel").grid(row=0, column=1, padx=(0, 14), sticky="w")
        ttk.Label(labels, text="推理强度", style="Small.TLabel").grid(row=0, column=2, padx=(0, 14), sticky="w")
        ttk.Label(labels, text="提供方", style="Small.TLabel").grid(row=0, column=3, sticky="w")
        descriptions = [("代码分析模板", "入口 / 调用链 / 文件"), ("测试分析模板", "测试 / 边界 / 回归"), ("兼容性分析模板", "日志 / 接口 / 兼容性")]
        self.rows = []
        for index, (title, subtitle) in enumerate(descriptions):
            row = ChoiceRow(model_card, title, subtitle, self.catalog, self._schedule_preview)
            row.grid(row=index + 3, column=0, sticky="ew")
            self.rows.append(row)
        footer = ttk.Frame(model_card, style="Card.TFrame")
        footer.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, text="子 Agent 并发上限（不含主控）").pack(side="left", padx=(0, 10))
        self.concurrent_entry = ttk.Entry(footer, textvariable=self.concurrent_var, width=7)
        self.concurrent_entry.pack(side="left")
        ttk.Label(footer, text="默认 8（官方示例），可输入其他正整数。", style="Small.TLabel").pack(side="right")
        ttk.Label(model_card, text="关闭时保留以上参数，供下次开启使用。开启后按需调度，并发数不会新增配置行。", style="Small.TLabel").grid(row=7, column=0, sticky="w", pady=(5, 0))
        ttk.Label(model_card, textvariable=self.warning_var, style="Small.TLabel", wraplength=980).grid(row=8, column=0, sticky="w", pady=(6, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=3, column=0, padx=20, sticky="nsew")
        preview = ttk.Frame(self.notebook, style="Card.TFrame", padding=12)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        self.notebook.add(preview, text="变更预览")
        preview_head = ttk.Frame(preview, style="Card.TFrame")
        preview_head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Label(preview_head, text="仅展示本工具管理的设置与协作说明", style="Small.TLabel").pack(side="left")
        ttk.Button(preview_head, text="更新预览", command=self.preview_changes).pack(side="right")
        self.preview_text = tk.Text(preview, height=6, wrap="word", state="disabled", relief="flat", background="#F8FAFD", foreground=INK, padx=10, pady=8, font=(self.mono_font, 10), borderwidth=0)
        self.preview_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(preview, orient="vertical", command=self.preview_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.preview_text.configure(yscrollcommand=scroll.set)
        backups = ttk.Frame(self.notebook, style="Card.TFrame", padding=12)
        self.notebook.add(backups, text="备份恢复")
        backups.columnconfigure(0, weight=1)
        backups.rowconfigure(1, weight=1)
        backup_head = ttk.Frame(backups, style="Card.TFrame")
        backup_head.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(backup_head, text="每次保存前自动备份；恢复作用于当前选定范围。", style="Small.TLabel").pack(side="left")
        ttk.Button(backup_head, text="刷新", command=self.refresh_backups).pack(side="right", padx=(8, 0))
        ttk.Button(backup_head, text="恢复所选备份", command=self.restore_selected).pack(side="right")
        self.backup_tree = ttk.Treeview(backups, columns=("created", "name"), show="headings", height=4, selectmode="browse")
        self.backup_tree.heading("created", text="备份时间")
        self.backup_tree.heading("name", text="备份名称")
        self.backup_tree.column("created", width=180, stretch=False)
        self.backup_tree.column("name", width=580)
        self.backup_tree.grid(row=1, column=0, sticky="nsew")
        backup_scroll = ttk.Scrollbar(backups, orient="vertical", command=self.backup_tree.yview)
        backup_scroll.grid(row=1, column=1, sticky="ns")
        self.backup_tree.configure(yscrollcommand=backup_scroll.set)

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=4, column=0, padx=20, pady=(10, 8), sticky="ew")
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, text="只修改本地文件，不调用模型服务，也不自动重启 Codex。", style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="复制协作指令", command=self.copy_instructions).grid(row=0, column=1, padx=(10, 8))
        self.save_button = ttk.Button(actions, text="保存并应用", style="Primary.TButton", command=self.save_changes)
        self.save_button.grid(row=0, column=2)
        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel", wraplength=1040).grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 12))

    def current_target(self):
        if self.scope_var.get() == "global":
            return self.global_target
        project_text = self.project_var.get().strip()
        if not project_text:
            raise ConfigError("请先选择项目目录。")
        project = Path(project_text).expanduser().resolve()
        return Target(project / ".codex", project / "AGENTS.md")

    def _scope_changed(self):
        self.project_entry.configure(state="normal" if self.scope_var.get() == "project" else "disabled")
        if self.scope_var.get() == "project" and not self.project_var.get().strip():
            self.choose_project()
        else:
            self.load_current()

    def choose_project(self):
        directory = filedialog.askdirectory(parent=self.root, title="选择应用配置的项目目录", initialdir=self.project_var.get() or str(Path.home()), mustexist=True)
        if directory:
            self.project_var.set(directory)
            self.scope_var.set("project")
            self.load_current()
        elif not self.project_var.get().strip():
            self.scope_var.set("global")
            self.project_entry.configure(state="disabled")

    def _catalog_for(self, snapshot):
        return load_catalog(self.global_target.config_dir, extra_config=snapshot.config)

    def load_current(self):
        self._loading = True
        try:
            target = self.current_target()
            snapshot = load_snapshot(target)
            settings = load_settings(snapshot)
            catalog = self._catalog_for(snapshot)
            self.snapshot, self.catalog = snapshot, catalog
            self.project_entry.configure(state="normal" if self.scope_var.get() == "project" else "disabled")
            if target.instructions_path == target.config_dir / "AGENTS.md":
                rule_location = "配置目录内的 AGENTS.md"
            elif target.instructions_path == target.config_dir.parent / "AGENTS.md":
                rule_location = "项目目录内的 AGENTS.md"
            else:
                rule_location = str(target.instructions_path)
            self.target_var.set(f"配置目录：{target.config_dir}　·　协作说明：{rule_location}")
            for row, choice in zip(self.rows, settings.children):
                row.catalog = catalog
                row.set_choice(choice)
            self.concurrent_var.set(str(settings.max_concurrent))
            self.enabled_var.set(settings.enabled)
            self.warning_var.set("；".join(catalog.warnings))
            self.status_var.set(f"已读取：{self.mode_var.get()}。主控设置由 Codex 当前任务界面选择。")
            self._update_preview()
            return self.refresh_backups()
        except DISPLAY_ERRORS as exc:
            self._report_error("读取失败", exc)
            return False
        finally:
            self._loading = False

    def current_settings(self):
        try:
            concurrent = int(self.concurrent_var.get())
        except ValueError as exc:
            raise ConfigError("子 Agent 并发上限必须为正整数，不包含主控。") from exc
        if concurrent < 1:
            raise ConfigError("子 Agent 并发上限必须为正整数，不包含主控。")
        if concurrent > MAX_CONFIG_INTEGER:
            raise ConfigError("子 Agent 并发数超出配置文件支持的整数范围。")
        choices = [row.get_choice() for row in self.rows]
        for index, choice in enumerate(choices):
            if not choice.model:
                raise ConfigError(f"第 {index + 1} 行的模型不能为空。")
            if choice.effort not in self.rows[index].allowed_efforts:
                raise ConfigError(f"第 {index + 1} 行请选择该模型支持的推理强度。")
            if not choice.provider:
                raise ConfigError(f"第 {index + 1} 行请选择提供方。")
        return Settings(children=tuple(choices), max_concurrent=concurrent, enabled=self.enabled_var.get())

    def _mode_changed(self, *_):
        mode = "舰队模式（开启）" if self.enabled_var.get() else "非舰队模式（关闭）"
        self.mode_var.set(mode)
        if not self._loading:
            self.status_var.set(f"已选择：{mode}；点击“保存并应用”后写入，供新任务加载。")
        self._schedule_preview()

    def apply_preset(self):
        self._loading = True
        try:
            for row in self.rows:
                row.set_choice(Choice("gpt-5.6-luna", "xhigh", row.provider_var.get() or "openai"))
            self._update_preview()
            self.status_var.set("预设已填入，可继续分别调整；点击“保存并应用”后才会写入文件。")
        except DISPLAY_ERRORS as exc:
            self._report_error("预设失败", exc)
        finally:
            self._loading = False

    def _plan(self):
        target = self.current_target()
        if self.snapshot is None or self.snapshot.target != target:
            raise ConfigError("作用范围已变更，请先点击“读取当前配置”。")
        return make_plan(self.snapshot, self.current_settings(), catalog=self.catalog)

    def _set_preview(self, text):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _schedule_preview(self, *_):
        if self._loading:
            return
        if self._preview_after is not None:
            self.root.after_cancel(self._preview_after)
        self._preview_after = self.root.after(180, self._automatic_preview)

    def _automatic_preview(self):
        self._preview_after = None
        self._update_preview()

    def _update_preview(self):
        try:
            plan = self._plan()
            self._set_preview(plan.preview())
        except DISPLAY_ERRORS as exc:
            self._set_preview(f"暂时无法预览：{exc}")

    def preview_changes(self):
        try:
            plan = self._plan()
            self._set_preview(plan.preview())
            self.notebook.select(0)
            self.status_var.set("预览已更新，尚未写入文件。" if plan.dirty else "当前选择已与配置一致，无需写入。")
        except DISPLAY_ERRORS as exc:
            self._report_error("预览失败", exc)

    def save_changes(self):
        try:
            backup = apply_plan(self._plan())
            if not self.load_current():
                self.status_var.set(f"文件已保存，但重新读取遇到问题。{self.status_var.get()}")
                return
            if backup is None:
                self.status_var.set(f"当前配置无需变更：{self.mode_var.get()}。主控由 Codex 当前任务界面选择。")
            else:
                self.status_var.set(f"已保存：{self.mode_var.get()}，已自动备份；供新任务加载，必要时重启 Codex。")
        except DISPLAY_ERRORS as exc:
            self._report_error("保存失败", exc)

    def refresh_backups(self):
        try:
            backups = list_backups(self.current_target())
            for item in self.backup_tree.get_children():
                self.backup_tree.delete(item)
            self.backup_paths = {}
            for index, path in enumerate(backups):
                item = str(index)
                created = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                self.backup_tree.insert("", "end", iid=item, values=(created, path.name))
                self.backup_paths[item] = path
            return True
        except DISPLAY_ERRORS as exc:
            self._report_error("读取备份失败", exc)
            return False

    def restore_selected(self):
        try:
            selection = self.backup_tree.selection()
            if not selection:
                raise ConfigError("请先选择一份备份。")
            target = self.current_target()
            if self.snapshot is None or target != self.snapshot.target:
                raise ConfigError("作用范围已变更，请先点击“读取当前配置”。")
            backup = self.backup_paths[selection[0]]
            if not messagebox.askyesno("确认恢复备份", f"恢复备份：{backup.name}\n\n将恢复子 Agent 配置与分工规则：\n{target.config_path}\n{target.instructions_path}\n以及本工具的三个角色配置文件。\n主控设置保持当前值，旧版备份中的主控设置也不会恢复。\n\n是否继续？", parent=self.root, icon="warning"):
                return
            restore_backup(target, backup)
            if not self.load_current():
                self.status_var.set(f"备份已恢复，但重新读取遇到问题。{self.status_var.get()}")
                return
            self.status_var.set(f"已恢复：{self.mode_var.get()}，供新任务加载。主控设置未改动。")
        except DISPLAY_ERRORS as exc:
            self._report_error("恢复失败", exc)

    def copy_instructions(self):
        try:
            instructions = fleet_instructions(self.current_settings())
            self.root.clipboard_clear()
            self.root.clipboard_append(instructions)
            self.status_var.set("协作指令已复制，可粘贴到新任务中；配置文件未写入。")
        except DISPLAY_ERRORS as exc:
            self._report_error("复制失败", exc)

    def _report_error(self, title, error):
        self.status_var.set(f"{title}：{error}")
        if self.show_errors:
            messagebox.showerror(title, str(error), parent=self.root)

    def report_callback_exception(self, _exception_type, error, _traceback):
        self._report_error("操作失败", error)
