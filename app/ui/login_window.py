import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, X
from tkinter import messagebox

from app.config.app_config import AppConfig
from app.services.auth_service import AuthService
from app.services.product_service import ProductService
from app.services.tightening_service import TighteningService
from app.ui.main_window import MainWindow


class LoginWindow(ttk.Window):
    def __init__(
        self,
        auth_service: AuthService,
        product_service: ProductService,
        tightening_service: TighteningService,
        config: AppConfig,
    ) -> None:
        super().__init__(themename="flatly")
        self.auth_service = auth_service
        self.product_service = product_service
        self.tightening_service = tightening_service
        self.config = config

        self.title("IGBT扭矩管理 - 登录")
        self.geometry("560x380")
        self.minsize(480, 330)
        self.resizable(True, True)

        frame = ttk.Frame(self, padding=32)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="IGBT扭矩管理", font=("Microsoft YaHei UI", 24, "bold")).pack(
            anchor="w", pady=(0, 26)
        )

        ttk.Label(frame, text="工号").pack(anchor="w")
        self.work_no_var = ttk.StringVar(value="admin")
        ttk.Entry(frame, textvariable=self.work_no_var, font=("Microsoft YaHei UI", 12)).pack(
            fill=X, pady=(4, 12)
        )

        ttk.Label(frame, text="密码").pack(anchor="w")
        self.password_var = ttk.StringVar(value="admin123")
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

    def login(self) -> None:
        user = self.auth_service.login(self.work_no_var.get(), self.password_var.get())
        if user is None:
            messagebox.showerror("登录失败", "工号或密码错误")
            return

        self.withdraw()
        main = MainWindow(
            self,
            user,
            self.product_service,
            self.tightening_service,
            self.config,
        )
