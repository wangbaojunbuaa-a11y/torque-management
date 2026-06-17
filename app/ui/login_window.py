import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, X
from tkinter import messagebox

from app.config.app_config import AppConfig
from app.services.auth_service import AuthService
from app.services.offline_check_service import OfflineCheckService
from app.services.product_service import ProductService
from app.services.report_service import ReportService
from app.services.tightening_service import TighteningService
from app.services.user_service import UserService
from app.ui.main_window import MainWindow


class LoginWindow(ttk.Window):
    def __init__(
        self,
        auth_service: AuthService,
        user_service: UserService,
        product_service: ProductService,
        tightening_service: TighteningService,
        report_service: ReportService,
        offline_check_service: OfflineCheckService,
        config: AppConfig,
    ) -> None:
        super().__init__(themename="flatly")
        self.auth_service = auth_service
        self.user_service = user_service
        self.product_service = product_service
        self.tightening_service = tightening_service
        self.report_service = report_service
        self.offline_check_service = offline_check_service
        self.config = config
        self._configure_fonts()

        self.title("IGBT扭矩管理 - 登录")
        self.geometry("680x440")
        self.minsize(560, 380)
        self.resizable(True, True)

        frame = ttk.Frame(self, padding=32)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="IGBT扭矩管理", font=("Microsoft YaHei UI", 24, "bold")).pack(
            anchor="w", pady=(0, 26)
        )

        ttk.Label(frame, text="工号").pack(anchor="w")
        user_options = self._work_no_options()
        default_work_no = self._default_work_no(user_options)
        self.work_no_var = ttk.StringVar(value=default_work_no)
        ttk.Combobox(
            frame,
            textvariable=self.work_no_var,
            values=user_options,
            state="readonly",
            font=("Microsoft YaHei UI", 12),
        ).pack(
            fill=X, pady=(4, 12)
        )

        ttk.Label(frame, text="密码").pack(anchor="w")
        self.password_var = ttk.StringVar(value="")
        password_entry = ttk.Entry(
            frame, textvariable=self.password_var, show="*", font=("Microsoft YaHei UI", 12)
        )
        password_entry.pack(fill=X, pady=(4, 18))
        password_entry.bind("<Return>", lambda _event: self.login())

        button_row = ttk.Frame(frame)
        button_row.pack(fill=X, pady=(8, 0))
        ttk.Button(button_row, text="登录", bootstyle="primary", command=self.login).pack(
            side=LEFT, fill=X, expand=True
        )

    def _configure_fonts(self) -> None:
        self.option_add("*Font", ("Microsoft YaHei UI", 12))
        style = ttk.Style()
        style.configure(".", font=("Microsoft YaHei UI", 12))
        style.configure("TButton", font=("Microsoft YaHei UI", 12))
        style.configure("Treeview", font=("Microsoft YaHei UI", 12), rowheight=30)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 12, "bold"))

    def _work_no_options(self) -> list[str]:
        rows = self.user_service.list_users()
        values = [row["work_no"] for row in rows if row["active"]]
        return values or ["admin"]

    def _default_work_no(self, options: list[str]) -> str:
        last = self.config.last_login_work_no or ""
        if last in options:
            return last
        if "admin" in options:
            return "admin"
        return options[0]

    def login(self) -> None:
        user = self.auth_service.login(self.work_no_var.get(), self.password_var.get())
        if user is None:
            messagebox.showerror("登录失败", "工号或密码错误")
            return
        self.config.last_login_work_no = user["work_no"]
        self.config.save()

        self.withdraw()
        main = MainWindow(
            self,
            user,
            self.user_service,
            self.product_service,
            self.tightening_service,
            self.report_service,
            self.offline_check_service,
            self.config,
        )
