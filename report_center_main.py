from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import os
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X, Y

from report_center.config import CONFIG_FILE, LineConfig, ReportCenterConfig
from report_center.network_paths import NetworkPathReconnector
from report_center.report_engine import ReportEngine, format_poll_summary
from report_center.state_repo import ReportStateRepository


class ReportCenterApp:
    def __init__(self, root: ttk.Window) -> None:
        self.root = root
        self.root.title("IGBT 拧紧/涂敷报表中心")
        self.root.geometry("1480x860")
        self.root.minsize(1220, 720)

        self.config = ReportCenterConfig.load()
        self.state_repo = ReportStateRepository(self.config.state_db)
        self.state_repo.initialize()

        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_ui()
        self._load_config_to_ui()
        self._refresh_jobs()
        self._poll_ui_queue()
        self._start_worker()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=BOTH, expand=True)

        top = ttk.Frame(main)
        top.pack(fill=X)

        ttk.Label(top, text="IGBT 拧紧/涂敷报表中心", font=("Microsoft YaHei", 18, "bold")).pack(side=LEFT)
        ttk.Button(top, text="退出程序", bootstyle="danger", command=self.exit_app).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="后台运行", command=self.run_in_background).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="手动轮询", bootstyle="primary", command=self._manual_poll).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="验证路径", command=self._validate_paths).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(top, text="保存配置", bootstyle="success", command=self._save_config).pack(side=RIGHT)

        cfg = ttk.Labelframe(main, text="基础配置", padding=10)
        cfg.pack(fill=X, pady=(12, 8))
        cfg.columnconfigure(1, weight=1)
        cfg.columnconfigure(3, weight=1)

        ttk.Label(cfg, text="轮询时间(秒)").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.poll_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.poll_var, width=10).grid(row=0, column=1, sticky="w", pady=4)

        self.copy_var = tk.BooleanVar()
        ttk.Checkbutton(cfg, text="读取前复制数据库快照", variable=self.copy_var).grid(row=0, column=2, sticky="w", padx=20)
        self.background_var = tk.BooleanVar()
        ttk.Checkbutton(cfg, text="关闭窗口时转后台", variable=self.background_var).grid(row=0, column=3, sticky="w", padx=8)

        ttk.Label(cfg, text="本地暂存目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.staging_report_dir_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.staging_report_dir_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(cfg, text="选择", command=self._choose_staging_report_dir).grid(row=1, column=3, sticky="w", padx=8)

        ttk.Label(cfg, text="归档根目录").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.report_dir_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.report_dir_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(cfg, text="选择", command=self._choose_report_dir).grid(row=2, column=3, sticky="w", padx=8)

        self.network_reconnect_var = tk.BooleanVar()
        ttk.Checkbutton(cfg, text="启用网络盘定时重连", variable=self.network_reconnect_var).grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(cfg, text="重连间隔(秒)").grid(row=3, column=1, sticky="e", padx=(0, 8), pady=4)
        self.network_interval_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.network_interval_var, width=10).grid(row=3, column=2, sticky="w", pady=4)

        mes = ttk.Labelframe(main, text="MES 设置", padding=10)
        mes.pack(fill=X, pady=8)
        for col in (1, 3, 5):
            mes.columnconfigure(col, weight=1)

        self.mes_enabled_var = tk.BooleanVar()
        self.mes_mock_var = tk.BooleanVar()
        ttk.Checkbutton(mes, text="启用 MES", variable=self.mes_enabled_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(mes, text="模拟模式", variable=self.mes_mock_var).grid(row=0, column=1, sticky="w")

        self.mes_host_var = tk.StringVar()
        self.mes_port_var = tk.StringVar()
        self.mes_user_var = tk.StringVar()
        self.mes_password_var = tk.StringVar()
        self.mes_db_var = tk.StringVar()
        self.lookback_var = tk.StringVar()
        self.rules_var = tk.StringVar()

        self._add_labeled_entry(mes, 1, 0, "主机", self.mes_host_var)
        self._add_labeled_entry(mes, 1, 2, "端口", self.mes_port_var, width=8)
        self._add_labeled_entry(mes, 1, 4, "数据库", self.mes_db_var)
        self._add_labeled_entry(mes, 2, 0, "用户", self.mes_user_var)
        self._add_labeled_entry(mes, 2, 2, "密码", self.mes_password_var, show="*")
        self._add_labeled_entry(mes, 2, 4, "追溯天数", self.lookback_var, width=8)
        self._add_labeled_entry(mes, 3, 0, "IGBT编码前缀", self.rules_var, columnspan=5)

        lines_frame = ttk.Frame(main)
        lines_frame.pack(fill=BOTH, expand=True, pady=(8, 0))
        lines_frame.columnconfigure(0, weight=1)
        lines_frame.columnconfigure(1, weight=1)
        lines_frame.rowconfigure(0, weight=1)

        left = ttk.Labelframe(lines_frame, text="产线数据源", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ttk.Labelframe(lines_frame, text="任务状态", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.lines_tree = ttk.Treeview(
            left,
            columns=("enabled", "code", "name", "torque_db", "coating_db"),
            show="headings",
            height=12,
        )
        for col, text, width in (
            ("enabled", "启用", 60),
            ("code", "产线编码", 110),
            ("name", "产线名称", 120),
            ("torque_db", "拧紧数据库", 300),
            ("coating_db", "涂敷数据库", 300),
        ):
            self.lines_tree.heading(col, text=text)
            self.lines_tree.column(col, width=width, anchor="w")
        self.lines_tree.grid(row=0, column=0, sticky="nsew")

        line_buttons = ttk.Frame(left)
        line_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(line_buttons, text="新增", command=self._add_line).pack(side=LEFT)
        ttk.Button(line_buttons, text="编辑", command=self._edit_line).pack(side=LEFT, padx=6)
        ttk.Button(line_buttons, text="删除", bootstyle="danger", command=self._delete_line).pack(side=LEFT)

        self.jobs_tree = ttk.Treeview(
            right,
            columns=("updated", "type", "line", "barcode", "serial", "status", "path", "error"),
            show="headings",
            height=12,
            selectmode="extended",
        )
        for col, text, width in (
            ("updated", "更新时间", 140),
            ("type", "类型", 70),
            ("line", "产线", 80),
            ("barcode", "水冷基板条码", 190),
            ("serial", "产品序列号", 170),
            ("status", "状态", 100),
            ("path", "报表路径", 260),
            ("error", "错误", 200),
        ):
            self.jobs_tree.heading(col, text=text)
            self.jobs_tree.column(col, width=width, anchor="w")
        self.jobs_tree.grid(row=0, column=0, sticky="nsew")
        self.jobs_tree.bind("<Double-1>", lambda _event: self._open_selected_job_detail())
        self.jobs_tree.bind("<Button-3>", self._show_job_menu)

        job_buttons = ttk.Frame(right)
        job_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(job_buttons, text="详情/手动匹配", command=self._open_selected_job_detail).pack(side=LEFT)
        ttk.Button(job_buttons, text="匹配全部等待任务", bootstyle="primary", command=self._match_waiting_jobs).pack(side=LEFT, padx=6)
        ttk.Button(job_buttons, text="删除任务", bootstyle="danger", command=self._delete_selected_jobs).pack(side=LEFT)

        self.job_menu = tk.Menu(self.root, tearoff=0)
        self.job_menu.add_command(label="详情/手动匹配", command=self._open_selected_job_detail)
        self.job_menu.add_command(label="匹配全部等待任务", command=self._match_waiting_jobs)
        self.job_menu.add_separator()
        self.job_menu.add_command(label="删除任务", command=self._delete_selected_jobs)

        bottom = ttk.Frame(main)
        bottom.pack(fill=X, pady=(8, 0))
        self.status_var = tk.StringVar(value="准备就绪")
        ttk.Label(bottom, textvariable=self.status_var).pack(side=LEFT)

    def _add_labeled_entry(
        self,
        parent,
        row: int,
        col: int,
        label: str,
        variable: tk.StringVar,
        width: int | None = None,
        show: str | None = None,
        columnspan: int = 1,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable, width=width, show=show).grid(
            row=row,
            column=col + 1,
            columnspan=columnspan,
            sticky="ew",
            pady=4,
        )

    def _load_config_to_ui(self) -> None:
        cfg = self.config
        self.poll_var.set(str(cfg.poll_interval_seconds))
        self.copy_var.set(cfg.copy_before_read)
        self.background_var.set(cfg.background_on_close)
        self.network_reconnect_var.set(cfg.network_reconnect_enabled)
        self.network_interval_var.set(str(cfg.network_reconnect_interval_seconds))
        self.staging_report_dir_var.set(cfg.staging_report_dir)
        self.report_dir_var.set(cfg.report_dir)
        self.mes_enabled_var.set(cfg.mes.enabled)
        self.mes_mock_var.set(cfg.mes.mock)
        self.mes_host_var.set(cfg.mes.host)
        self.mes_port_var.set(cfg.mes.port)
        self.mes_user_var.set(cfg.mes.user)
        self.mes_password_var.set(cfg.mes.password)
        self.mes_db_var.set(cfg.mes.dbname)
        self.lookback_var.set(str(cfg.mes.lookback_days))
        self.rules_var.set(",".join(cfg.mes.igbt_filter_rules))
        self._reload_lines_tree()

    def _reload_lines_tree(self) -> None:
        self.lines_tree.delete(*self.lines_tree.get_children())
        for index, line in enumerate(self.config.lines):
            self.lines_tree.insert(
                "",
                END,
                iid=str(index),
                values=(
                    "是" if line.enabled else "否",
                    line.code,
                    line.name,
                    line.db_path,
                    line.coating_db_path,
                ),
            )

    def _refresh_jobs(self) -> None:
        self.jobs_tree.delete(*self.jobs_tree.get_children())
        for row in self.state_repo.recent_jobs():
            self.jobs_tree.insert(
                "",
                END,
                iid=str(row["id"]),
                values=(
                    row["updated_at"],
                    "涂敷" if row["report_type"] == "coating" else "拧紧",
                    row["line_code"],
                    row["base_barcode"],
                    row["product_serial_no"] or "",
                    row["status"],
                    row["report_path"] or "",
                    row["last_error"] or "",
                ),
            )

    def _show_job_menu(self, event) -> None:
        row_id = self.jobs_tree.identify_row(event.y)
        if row_id and row_id not in self.jobs_tree.selection():
            self.jobs_tree.selection_set(row_id)
        self.job_menu.tk_popup(event.x_root, event.y_root)

    def _selected_job_ids(self) -> list[int]:
        result = []
        for item in self.jobs_tree.selection():
            try:
                result.append(int(item))
            except ValueError:
                continue
        return result

    def _open_selected_job_detail(self) -> None:
        selected = self._selected_job_ids()
        if not selected:
            messagebox.showwarning("提示", "请选择一条任务", parent=self.root)
            return
        try:
            self.config = self._collect_config()
        except Exception as exc:
            messagebox.showerror("配置无效", str(exc), parent=self.root)
            return
        ReportJobDetailDialog(self, selected[0])

    def _delete_selected_jobs(self) -> None:
        selected = self._selected_job_ids()
        if not selected:
            messagebox.showwarning("提示", "请选择要删除的任务", parent=self.root)
            return
        if not messagebox.askyesno(
            "确认删除",
            f"确定从任务清单删除选中的 {len(selected)} 条记录吗？\n如果任务已经生成过报表，也会清理对应的生成记录，便于重新处理调试数据。",
            parent=self.root,
        ):
            return
        deleted = 0
        for job_id in selected:
            if self.state_repo.delete_job(job_id):
                deleted += 1
        self._refresh_jobs()
        self.status_var.set(f"已删除 {deleted} 条任务记录")

    def _match_waiting_jobs(self) -> None:
        try:
            self.config = self._collect_config()
            self.config.save(CONFIG_FILE)
        except Exception as exc:
            messagebox.showerror("配置无效", str(exc), parent=self.root)
            return
        self.status_var.set("正在匹配全部等待任务...")
        threading.Thread(target=self._run_match_waiting_jobs, daemon=True).start()

    def _run_match_waiting_jobs(self) -> None:
        try:
            summary = ReportEngine(self.config, self.state_repo).match_waiting_jobs()
            self.ui_queue.put(("match_all", summary))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def _choose_report_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.report_dir_var.set(path)

    def _choose_staging_report_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.staging_report_dir_var.set(path)

    def _add_line(self) -> None:
        self._open_line_editor()

    def _edit_line(self) -> None:
        selected = self.lines_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请选择一条产线", parent=self.root)
            return
        index = int(selected[0])
        self._open_line_editor(index)

    def _delete_line(self) -> None:
        selected = self.lines_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        del self.config.lines[index]
        self._reload_lines_tree()

    def _open_line_editor(self, index: int | None = None) -> None:
        line = self.config.lines[index] if index is not None else LineConfig(code="", name="", db_path="", coating_db_path="")
        win = ttk.Toplevel(self.root)
        win.title("产线数据源")
        win.geometry("820x340")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        enabled_var = tk.BooleanVar(value=line.enabled)
        code_var = tk.StringVar(value=line.code)
        name_var = tk.StringVar(value=line.name)
        db_var = tk.StringVar(value=line.db_path)
        coating_db_var = tk.StringVar(value=line.coating_db_path)

        ttk.Checkbutton(frame, text="启用", variable=enabled_var).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="产线编码").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=code_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="产线名称").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=name_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="torque.db 路径").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=db_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="coating.db 路径").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=coating_db_var).grid(row=4, column=1, sticky="ew", pady=4)

        def choose_db() -> None:
            path = filedialog.askopenfilename(
                parent=win,
                title="选择 torque.db",
                filetypes=[("SQLite DB", "*.db"), ("所有文件", "*.*")],
            )
            if path:
                db_var.set(path)

        ttk.Button(frame, text="选择", command=choose_db).grid(row=3, column=2, padx=8)

        def choose_coating_db() -> None:
            path = filedialog.askopenfilename(
                parent=win,
                title="选择 coating.db",
                filetypes=[("SQLite DB", "*.db"), ("所有文件", "*.*")],
            )
            if path:
                coating_db_var.set(path)

        ttk.Button(frame, text="选择", command=choose_coating_db).grid(row=4, column=2, padx=8)

        def save_line() -> None:
            code = code_var.get().strip()
            db_path = db_var.get().strip()
            coating_db_path = coating_db_var.get().strip()
            if not code or (not db_path and not coating_db_path):
                messagebox.showwarning("提示", "产线编码不能为空，至少填写一个数据库路径", parent=win)
                return
            new_line = LineConfig(
                code=code,
                name=name_var.get().strip() or code,
                db_path=db_path,
                coating_db_path=coating_db_path,
                enabled=enabled_var.get(),
            )
            if index is None:
                self.config.lines.append(new_line)
            else:
                self.config.lines[index] = new_line
            self._reload_lines_tree()
            win.destroy()

        ttk.Button(frame, text="保存", bootstyle="success", command=save_line).grid(row=5, column=1, sticky="e", pady=16)

    def _collect_config(self) -> ReportCenterConfig:
        cfg = self.config
        cfg.poll_interval_seconds = max(5, int(self.poll_var.get().strip()))
        cfg.copy_before_read = self.copy_var.get()
        cfg.background_on_close = self.background_var.get()
        cfg.network_reconnect_enabled = self.network_reconnect_var.get()
        cfg.network_reconnect_interval_seconds = max(5, int(self.network_interval_var.get().strip()))
        cfg.staging_report_dir = self.staging_report_dir_var.get().strip() or "reports"
        cfg.report_dir = self.report_dir_var.get().strip()
        cfg.mes.enabled = self.mes_enabled_var.get()
        cfg.mes.mock = self.mes_mock_var.get()
        cfg.mes.host = self.mes_host_var.get().strip()
        cfg.mes.port = self.mes_port_var.get().strip()
        cfg.mes.user = self.mes_user_var.get().strip()
        cfg.mes.password = self.mes_password_var.get()
        cfg.mes.dbname = self.mes_db_var.get().strip()
        cfg.mes.lookback_days = max(1, int(self.lookback_var.get().strip()))
        cfg.mes.igbt_filter_rules = [item.strip() for item in self.rules_var.get().split(",") if item.strip()]
        return cfg

    def _save_config(self) -> None:
        try:
            self.config = self._collect_config()
            self.config.save(CONFIG_FILE)
            self.status_var.set(f"配置已保存: {CONFIG_FILE}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def _validate_paths(self) -> None:
        try:
            cfg = self._collect_config()
        except Exception as exc:
            messagebox.showerror("配置无效", str(exc), parent=self.root)
            return

        paths = [cfg.staging_report_dir, cfg.report_dir]
        for line in cfg.lines:
            if line.enabled:
                paths.extend([line.db_path, line.coating_db_path])

        reconnect_errors = NetworkPathReconnector(
            cfg.network_reconnect_enabled,
            0,
        ).ensure_paths([path for path in paths if path])

        checks: list[tuple[str, str, bool, str]] = []
        checks.append(("本地暂存目录", cfg.staging_report_dir, os.path.isdir(cfg.staging_report_dir), "目录不存在"))
        checks.append(("归档根目录", cfg.report_dir, os.path.isdir(cfg.report_dir), "目录不可达"))
        for line in cfg.lines:
            if not line.enabled:
                continue
            if line.db_path:
                checks.append((f"{line.code} 拧紧库", line.db_path, os.path.isfile(line.db_path), "文件不可达"))
            if line.coating_db_path:
                checks.append((f"{line.code} 涂敷库", line.coating_db_path, os.path.isfile(line.coating_db_path), "文件不可达"))

        lines = []
        ok_count = 0
        for label, path, ok, error in checks:
            if ok:
                ok_count += 1
            lines.append(f"{'OK' if ok else 'NG'}  {label}: {path or '-'}{'' if ok else '  (' + error + ')'}")
        if reconnect_errors:
            lines.append("")
            lines.extend(f"重连提示：{item}" for item in reconnect_errors)
        messagebox.showinfo(
            "路径验证结果",
            f"通过 {ok_count}/{len(checks)} 项\n\n" + "\n".join(lines),
            parent=self.root,
        )

    def _manual_poll(self) -> None:
        self._save_config()
        threading.Thread(target=self._run_poll, daemon=True).start()

    def _run_poll(self) -> None:
        try:
            summary = ReportEngine(self.config, self.state_repo).poll_once()
            self.ui_queue.put(("summary", summary))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def _start_worker(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            self._run_poll()
            interval = max(5, int(self.config.poll_interval_seconds))
            for _ in range(interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def _poll_ui_queue(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "summary":
                self.status_var.set(format_poll_summary(payload))
                self._refresh_jobs()
            elif kind == "match_all":
                self._handle_match_all_result(payload)
            elif kind == "error":
                self.status_var.set(f"轮询异常: {payload}")
        self.root.after(500, self._poll_ui_queue)

    def _handle_match_all_result(self, summary) -> None:
        self._refresh_jobs()
        self.status_var.set(
            f"匹配全部完成：等待任务 {summary.total} 条，新生成 {summary.generated_reports} 份，"
            f"未匹配/跳过 {summary.skipped} 条，错误 {len(summary.errors)} 条"
        )
        if summary.errors:
            detail = "\n".join(summary.errors[:20])
            if len(summary.errors) > 20:
                detail += f"\n... 还有 {len(summary.errors) - 20} 条错误"
            messagebox.showwarning("匹配全部完成但有错误", detail, parent=self.root)

    def close(self) -> None:
        if self.config.background_on_close:
            self.run_in_background()
            return
        self.exit_app()

    def run_in_background(self) -> None:
        self.root.iconify()
        self.status_var.set("已转入后台运行，窗口最小化后仍会继续轮询")

    def exit_app(self) -> None:
        self.stop_event.set()
        self.root.destroy()


class ReportJobDetailDialog:
    def __init__(self, app: ReportCenterApp, job_id: int) -> None:
        self.app = app
        self.job_id = job_id
        self.win = ttk.Toplevel(app.root)
        self.win.title("任务详情 / 手动匹配")
        self.win.geometry("980x720")
        self.win.minsize(860, 620)
        self.win.transient(app.root)

        frame = ttk.Frame(self.win, padding=12)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(frame)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(text_frame, wrap="word", font=("Consolas", 11), height=24)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        bottom = ttk.Frame(frame)
        bottom.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(1, weight=1)

        ttk.Label(bottom, text="产品序列号").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.serial_var = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.serial_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(bottom, text="刷新诊断", command=self.refresh).grid(row=0, column=2, padx=8)
        ttk.Button(bottom, text="按序列号手动生成", bootstyle="primary", command=self.manual_generate).grid(row=0, column=3)
        ttk.Button(bottom, text="关闭", command=self.win.destroy).grid(row=0, column=4, padx=(8, 0))

        self._load_serial()
        self.refresh()

    def _load_serial(self) -> None:
        row = self.app.state_repo.job_by_id(self.job_id)
        if row and row["product_serial_no"]:
            self.serial_var.set(str(row["product_serial_no"]))

    def refresh(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", END)
        try:
            detail = ReportEngine(self.app.config, self.app.state_repo).diagnose_job(self.job_id)
        except Exception as exc:
            detail = f"诊断失败: {exc}"
        self.text.insert("1.0", detail)
        self.text.configure(state="disabled")

    def manual_generate(self) -> None:
        serial = self.serial_var.get().strip()
        if not serial:
            messagebox.showwarning("提示", "请输入产品序列号", parent=self.win)
            return
        try:
            result = ReportEngine(self.app.config, self.app.state_repo).manual_generate(self.job_id, serial)
        except Exception as exc:
            messagebox.showerror("手动匹配失败", str(exc), parent=self.win)
            self.refresh()
            self.app._refresh_jobs()
            return
        messagebox.showinfo(
            "手动匹配完成",
            f"已生成报表：\n{result.report_path}",
            parent=self.win,
        )
        self.app._refresh_jobs()
        self.refresh()


def main() -> None:
    root = ttk.Window(themename="flatly")
    app = ReportCenterApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
