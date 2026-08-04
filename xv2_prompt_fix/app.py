from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import cast

from .constants import (
    APP_VERSION,
    KNOWN_BROKEN_BUILD_IDS,
    LOG_MAX_AGE_DAYS,
    LOG_MAX_FILES,
    SOURCE_MANIFEST_ID,
)
from .errors import CancelledError, FixError
from .i18n import (
    available_languages,
    language_from_name,
    language_name,
    set_language,
    tr,
)
from .steam import find_game_roots, read_installed_build_id, validate_game_root
from .utils import (
    CancelToken,
    app_data_dir,
    prune_old_logs,
    sanitize_log_text,
    timestamp,
)
from .workflow import Workflow, WorkflowOptions, WorkflowResult


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        set_language("ko")
        self.geometry("940x800")
        self.minsize(820, 700)
        self.option_add("*Font", ("Malgun Gothic", 9))

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.workflow: Workflow | None = None
        self.cancel_token: CancelToken | None = None
        self.progress_running = False
        self.current_log_path: Path | None = None

        self.game_path = tk.StringVar()
        self.build_text = tk.StringVar()
        self.status_text = tk.StringVar()
        self.source_mode = tk.StringVar(value="steam")
        self.local_source = tk.StringVar()
        self.keep_source = tk.BooleanVar(value=False)
        self.allow_unknown_build = tk.BooleanVar(value=False)
        self.force_restore = tk.BooleanVar(value=False)
        self.language_choice = tk.StringVar(value=language_name("ko"))
        self.advanced_visible = False

        self._build_ui()
        self._refresh_language()
        self._source_mode_changed()
        self.after(100, self._poll_events)
        self.after(250, self._auto_detect_initial)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(6, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            header,
            font=("Malgun Gothic", 16, "bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        self.language_label = ttk.Label(header)
        self.language_label.grid(row=0, column=1, padx=(12, 5))
        self.language_combo = ttk.Combobox(
            header,
            textvariable=self.language_choice,
            values=tuple(language_name(code) for code in available_languages()),
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=0, column=2, sticky="e")
        self.language_combo.bind("<<ComboboxSelected>>", self._language_changed)

        self.subtitle_label = ttk.Label(
            container,
            wraplength=890,
            justify="left",
        )
        self.subtitle_label.grid(row=1, column=0, sticky="ew", pady=(4, 14))

        self.path_frame = ttk.LabelFrame(container, padding=10)
        self.path_frame.grid(row=2, column=0, sticky="ew")
        self.path_frame.columnconfigure(0, weight=1)
        game_entry = ttk.Entry(self.path_frame, textvariable=self.game_path)
        game_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        game_entry.bind("<FocusOut>", lambda _event: self._update_build_status())
        self.browse_game_button = ttk.Button(
            self.path_frame, command=self._browse_game
        )
        self.browse_game_button.grid(row=0, column=1, padx=3)
        self.auto_detect_button = ttk.Button(
            self.path_frame, command=self._auto_detect
        )
        self.auto_detect_button.grid(row=0, column=2, padx=(3, 0))
        ttk.Label(self.path_frame, textvariable=self.build_text).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(7, 0)
        )

        self.source_frame = ttk.LabelFrame(container, padding=10)
        self.source_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.source_frame.columnconfigure(1, weight=1)
        self.steam_radio = ttk.Radiobutton(
            self.source_frame,
            value="steam",
            variable=self.source_mode,
            command=self._source_mode_changed,
        )
        self.steam_radio.grid(row=0, column=0, columnspan=3, sticky="w")
        self.steam_notice_label = ttk.Label(
            self.source_frame,
            foreground="#7a3e00",
            wraplength=860,
            justify="left",
        )
        self.steam_notice_label.grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=(22, 0), pady=(2, 7)
        )
        self.local_radio = ttk.Radiobutton(
            self.source_frame,
            value="local",
            variable=self.source_mode,
            command=self._source_mode_changed,
        )
        self.local_radio.grid(row=2, column=0, columnspan=3, sticky="w")
        self.local_source_entry = ttk.Entry(
            self.source_frame, textvariable=self.local_source
        )
        self.local_source_entry.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=(22, 6), pady=(4, 0)
        )
        self.local_source_button = ttk.Button(
            self.source_frame, command=self._browse_source
        )
        self.local_source_button.grid(row=3, column=2, pady=(4, 0))

        options = ttk.Frame(container)
        options.grid(row=4, column=0, sticky="ew", pady=(10, 8))
        self.keep_source_check = ttk.Checkbutton(
            options,
            variable=self.keep_source,
        )
        self.keep_source_check.pack(side="left")
        self.advanced_button = ttk.Button(
            options, command=self._toggle_advanced
        )
        self.advanced_button.pack(side="right")

        self.advanced_frame = ttk.LabelFrame(container, padding=10)
        self.allow_unknown_check = ttk.Checkbutton(
            self.advanced_frame,
            variable=self.allow_unknown_build,
        )
        self.allow_unknown_check.pack(anchor="w")
        self.force_restore_check = ttk.Checkbutton(
            self.advanced_frame,
            variable=self.force_restore,
        )
        self.force_restore_check.pack(anchor="w", pady=(4, 0))

        self.actions_frame = ttk.Frame(container)
        self.actions_frame.grid(row=5, column=0, sticky="ew", pady=(2, 10))
        self.fix_button = ttk.Button(
            self.actions_frame, command=self._start_fix
        )
        self.fix_button.pack(side="left", padx=(0, 6))
        self.restore_button = ttk.Button(
            self.actions_frame, command=self._start_restore
        )
        self.restore_button.pack(side="left", padx=6)
        self.logs_button = ttk.Button(
            self.actions_frame, command=self._open_logs
        )
        self.logs_button.pack(side="left", padx=6)
        self.cancel_button = ttk.Button(
            self.actions_frame, command=self._cancel, state="disabled"
        )
        self.cancel_button.pack(side="right")

        self.log_frame = ttk.LabelFrame(container, padding=8)
        self.log_frame.grid(row=6, column=0, sticky="nsew")
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(2, weight=1)
        ttk.Label(self.log_frame, textvariable=self.status_text).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        self.progressbar = ttk.Progressbar(
            self.log_frame,
            orient="horizontal",
            mode="determinate",
            maximum=100,
        )
        self.progressbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        text_frame = ttk.Frame(self.log_frame)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            text_frame,
            wrap="word",
            state="disabled",
            relief="flat",
            background="#ffffff",
        )
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.footer = ttk.Label(container, foreground="#555555")
        self.footer.grid(row=7, column=0, sticky="w", pady=(8, 0))

    def _dialog_title(self) -> str:
        return tr("XV2 Input Prompt Fix")

    def _language_changed(self, _event: object | None = None) -> None:
        set_language(language_from_name(self.language_choice.get()))
        self.current_log_path = None
        self._clear_log()
        self._refresh_language()

    def _refresh_language(self) -> None:
        self.title(f"{tr('XV2 Input Prompt Fix')} v{APP_VERSION}")
        self.language_label.configure(text="Language")
        self.title_label.configure(
            text=tr(
                "Dragon Ball Xenoverse 2 Input Prompt Fix",
            )
        )
        self.subtitle_label.configure(
            text=tr(
                "This is an unofficial source-only tool that runs directly with Python. It targets only the actual game language configured in Steam and transplants the matching Iggy mapping and compressed image pack after validation.",
            )
        )
        self.path_frame.configure(text=tr("Game installation folder"))
        self.browse_game_button.configure(text=tr("Browse"))
        self.auto_detect_button.configure(text=tr("Auto-detect Steam"))
        self.source_frame.configure(text=tr("Reference resources"))
        self.steam_radio.configure(text=tr("Download automatically from Steam"))
        self.steam_notice_label.configure(
            text=tr(
                "Uses DepotDownloader and Steam QR login. This application does not receive your password, but DepotDownloader may store the account name and session data in Windows local storage.",
            )
        )
        self.local_radio.configure(text=tr("Use a local reference data1.cpk"))
        self.local_source_button.configure(text=tr("Select file"))
        self.keep_source_check.configure(
            text=tr(
                "Keep the downloaded reference data1.cpk (skip QR login and download next time)",
            )
        )
        self.advanced_frame.configure(text=tr("Advanced settings"))
        self.allow_unknown_check.configure(
            text=tr(
                "Allow patching an unknown Steam build (risky after official updates)",
            )
        )
        self.force_restore_check.configure(
            text=tr(
                "Force restore even if the current CPK changed (may overwrite a newer official file)",
            )
        )
        self.advanced_button.configure(
            text=tr("Hide advanced settings")
            if self.advanced_visible
            else tr("Show advanced settings")
        )
        self.fix_button.configure(text=tr("Start automatic patch"))
        self.restore_button.configure(text=tr("Restore original"))
        self.logs_button.configure(text=tr("Log folder"))
        self.cancel_button.configure(text=tr("Cancel"))
        self.log_frame.configure(text=tr("Progress"))
        self.footer.configure(
            text=tr(
                "Verified build: {builds}  |  Source manifest: {manifest}  |  Excludes English/Japanese · EAC-disabled environments only",
                builds=", ".join(sorted(KNOWN_BROKEN_BUILD_IDS)),
                manifest=SOURCE_MANIFEST_ID,
            )
        )
        if not self.worker or not self.worker.is_alive():
            self.status_text.set(tr("Ready"))
        self._update_build_status()

    def _source_mode_changed(self) -> None:
        local = self.source_mode.get() == "local"
        state = "normal" if local else "disabled"
        self.local_source_entry.configure(state=state)
        self.local_source_button.configure(state=state)
        self.keep_source_check.configure(state="disabled" if local else "normal")
        if local:
            self.keep_source.set(False)

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        container = self.advanced_frame.master
        if self.advanced_visible:
            self.advanced_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
            self.actions_frame.grid_configure(row=6)
            self.log_frame.grid_configure(row=7)
            self.footer.grid_configure(row=8)
            container.rowconfigure(6, weight=0)
            container.rowconfigure(7, weight=1)
        else:
            self.advanced_frame.grid_remove()
            self.actions_frame.grid_configure(row=5)
            self.log_frame.grid_configure(row=6)
            self.footer.grid_configure(row=7)
            container.rowconfigure(7, weight=0)
            container.rowconfigure(6, weight=1)
        self._refresh_language()

    def _browse_game(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title=tr(
                "Select the DB Xenoverse 2 installation folder",
            ),
        )
        if selected:
            self.game_path.set(selected)
            self._update_build_status()

    def _browse_source(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title=tr(
                "Select the reference data1.cpk",
            ),
            filetypes=(("CPK archive", "*.cpk"), ("All files", "*.*")),
        )
        if selected:
            self.local_source.set(selected)

    def _auto_detect_initial(self) -> None:
        if not self.game_path.get():
            self._auto_detect(silent=True)

    def _auto_detect(self, silent: bool = False) -> None:
        roots = find_game_roots()
        if roots:
            self.game_path.set(str(roots[0]))
            self._update_build_status()
            self._append_log(
                tr(
                    "Game installation folder found in the Steam library",
                )
            )
            if len(roots) > 1:
                self._append_log(
                    tr(
                        "Found {count} game installation candidates and selected the first one.",
                        count=len(roots),
                    )
                )
        elif not silent:
            messagebox.showinfo(
                self._dialog_title(),
                tr(
                    "The game could not be found automatically in the Steam libraries. Select the installation folder manually.",
                ),
                parent=self,
            )

    def _update_build_status(self) -> None:
        raw = self.game_path.get().strip()
        if not raw:
            self.build_text.set(
                tr("Select the game folder.")
            )
            return
        try:
            root, cpk = validate_game_root(Path(raw))
            self.game_path.set(str(root))
            build_id = read_installed_build_id(root)
            known = build_id in KNOWN_BROKEN_BUILD_IDS
            suffix = (
                tr("verified target")
                if known
                else tr("not verified/review required")
            )
            self.build_text.set(
                f"data1.cpk: {cpk.stat().st_size / (1024**3):.2f} GiB  |  "
                + tr(
                    "Steam build ID: {build} ({status})",
                    build=build_id or tr("[unknown]"),
                    status=suffix,
                )
            )
        except FixError as exc:
            self.build_text.set(str(exc).splitlines()[0])

    def _workflow_options(
        self, *, steam_authorized: bool = False, require_source: bool = False
    ) -> WorkflowOptions:
        raw = self.game_path.get().strip()
        if not raw:
            raise FixError(
                tr("Select the game installation folder.")
            )
        local_source: Path | None = None
        if self.source_mode.get() == "local":
            source_raw = self.local_source.get().strip()
            if require_source and not source_raw:
                raise FixError(
                    tr(
                        "Select a local reference data1.cpk.",
                    )
                )
            if source_raw:
                local_source = Path(source_raw)
        return WorkflowOptions(
            game_root=Path(raw),
            local_source_cpk=local_source,
            allow_third_party_steam_auth=steam_authorized,
            allow_unknown_build=self.allow_unknown_build.get(),
            keep_downloaded_source=self.keep_source.get(),
            force_restore=self.force_restore.get(),
        )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.fix_button.configure(state=state)
        self.restore_button.configure(state=state)
        self.language_combo.configure(state="disabled" if busy else "readonly")
        self.logs_button.configure(state="normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if not busy:
            self._stop_indeterminate()

    def _confirm_patch_scope(self) -> bool:
        scope_text = tr(
            "The application reads the actual game language from the Steam app manifest and validates its `.iggy`, `.iggytex`, and `.iggyted` set. It replaces the `.iggy` button-code mapping together with its matching `.iggyted` auxiliary image pack from the reference version, while keeping the identical `.iggytex`.\n\nContinue only if you have confirmed that the current game language needs this patch.",
        )
        if self.source_mode.get() == "steam":
            scope_text += tr(
                "\n\nThis application does not receive or store your Steam password. After QR authentication, DepotDownloader may store the Steam account name and session data in Windows .NET local storage. This application does not read, upload, or automatically delete that data.",
            )
        return messagebox.askyesno(
            tr("Patch scope and notice"),
            scope_text + tr("\n\nContinue?"),
            parent=self,
        )

    def _start_fix(self) -> None:
        try:
            options = self._workflow_options(require_source=True)
        except FixError as exc:
            messagebox.showerror(self._dialog_title(), str(exc), parent=self)
            return
        if not self._confirm_patch_scope():
            return
        options.allow_third_party_steam_auth = self.source_mode.get() == "steam"
        self._run_worker("apply", options)

    def _start_restore(self) -> None:
        try:
            options = self._workflow_options()
        except FixError as exc:
            messagebox.showerror(self._dialog_title(), str(exc), parent=self)
            return
        if not messagebox.askyesno(
            self._dialog_title(),
            tr(
                "Restore data1.cpk from the original backup saved by this application?",
            ),
            parent=self,
        ):
            return
        self._run_worker("restore", options)

    def _run_worker(self, action: str, options: WorkflowOptions) -> None:
        if self.worker and self.worker.is_alive():
            return
        log_dir = app_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_stamp = timestamp()
        candidate = log_dir / f"session-{log_stamp}.log"
        suffix = 1
        while candidate.exists():
            candidate = log_dir / f"session-{log_stamp}-{suffix}.log"
            suffix += 1
        candidate.touch(exist_ok=False)
        self.current_log_path = candidate
        prune_old_logs(
            log_dir,
            max_files=LOG_MAX_FILES,
            max_age_days=LOG_MAX_AGE_DAYS,
        )
        self._clear_log()
        self._append_log(
            tr("Log file: {path}", path=self.current_log_path)
        )
        self.progressbar.configure(value=0)
        self.status_text.set(tr("Starting"))
        self.cancel_token = CancelToken()
        workflow = Workflow(
            options=options,
            cancel=self.cancel_token,
            log=lambda text: self.events.put(("log", text)),
            status=lambda text: self.events.put(("status", text)),
            progress=lambda value, text: self.events.put(("progress", (value, text))),
        )
        self.workflow = workflow
        self._set_busy(True)

        def target() -> None:
            try:
                result = workflow.apply() if action == "apply" else workflow.restore()
            except CancelledError as exc:
                self.events.put(("cancelled", str(exc)))
            except FixError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - GUI worker safety boundary
                self.events.put(("log", traceback.format_exc()))
                self.events.put(
                    (
                        "error",
                        tr(
                            "An unexpected error occurred. Check the traceback in the progress log.\n{error}",
                            error=exc,
                        ),
                    )
                )
            else:
                self.events.put(("result", result))
            finally:
                self.events.put(("done", None))

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.workflow:
            self.status_text.set(tr("Processing cancellation"))
            self._append_log(
                tr(
                    "The user requested cancellation.",
                )
            )
            self.workflow.cancel_active()
            self.cancel_button.configure(state="disabled")

    def _open_logs(self) -> None:
        folder = app_data_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                raise OSError(tr("Windows-only feature"))
        except OSError as exc:
            messagebox.showerror(
                self._dialog_title(),
                tr(
                    "The log folder could not be opened: {path}\n{error}",
                    path=sanitize_log_text(str(folder)),
                    error=exc,
                ),
                parent=self,
            )

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_text.set(str(payload))
                elif kind == "progress":
                    value, text = cast(tuple[float | None, str], payload)
                    self.status_text.set(text)
                    if value is None:
                        self._start_indeterminate()
                    else:
                        self._stop_indeterminate()
                        self.progressbar.configure(value=float(value))
                elif kind == "result":
                    if not isinstance(payload, WorkflowResult):
                        raise TypeError("Invalid GUI result event payload")
                    detail = payload.message
                    if payload.backup_path:
                        detail += tr(
                            "\n\nOriginal backup: cpk\\{name}",
                            name=payload.backup_path.name,
                        )
                    messagebox.showinfo(self._dialog_title(), detail, parent=self)
                elif kind == "error":
                    self.status_text.set(tr("Error"))
                    detail = sanitize_log_text(str(payload))
                    if self.current_log_path:
                        detail += tr(
                            "\n\nProgress log: {path}",
                            path=sanitize_log_text(str(self.current_log_path)),
                        )
                    messagebox.showerror(self._dialog_title(), detail, parent=self)
                elif kind == "cancelled":
                    self.status_text.set(tr("Cancelled"))
                    messagebox.showinfo(self._dialog_title(), str(payload), parent=self)
                elif kind == "done":
                    self._set_busy(False)
                    self.workflow = None
                    self.cancel_token = None
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001 - Tk event loop recovery boundary
            self._append_log(
                tr(
                    "Error while processing a GUI event:\n{traceback}",
                    traceback=traceback.format_exc(),
                )
            )
        finally:
            try:
                self.after(100, self._poll_events)
            except tk.TclError:
                pass

    def _start_indeterminate(self) -> None:
        if self.progress_running:
            return
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(10)
        self.progress_running = True

    def _stop_indeterminate(self) -> None:
        if not self.progress_running:
            self.progressbar.configure(mode="determinate")
            return
        self.progressbar.stop()
        self.progressbar.configure(mode="determinate")
        self.progress_running = False

    def _append_log(self, text: str) -> None:
        line = sanitize_log_text(text).rstrip() + "\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if self.current_log_path:
            try:
                with self.current_log_path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line)
            except OSError:
                pass

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                self._dialog_title(),
                tr(
                    "A task is running. Cancel it and close the application?",
                ),
                parent=self,
            ):
                return
            self._cancel()
            return
        self.destroy()


def run() -> None:
    window = MainWindow()
    window.mainloop()
