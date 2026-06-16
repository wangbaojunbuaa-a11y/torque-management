import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X
from tkinter import messagebox

from app.services.user_service import UserService


class UserDialog(ttk.Toplevel):
    def __init__(self, parent, user_service: UserService) -> None:
        super().__init__(parent)
        self.user_service = user_service
        self.selected_id: int | None = None

        self.title("用户管理")
        self.geometry("1050x680")
        self.minsize(900, 560)

        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        self.tree = ttk.Treeview(
            root,
            columns=("work_no", "name", "role", "active", "created_at"),
            show="headings",
            height=12,
        )
        for key, text in {
            "work_no": "工号",
            "name": "姓名",
            "role": "角色",
            "active": "启用",
            "created_at": "创建时间",
        }.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=120, anchor="center")
        self.tree.column("created_at", width=180)
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.Frame(root)
        form.pack(fill=X, pady=(12, 0))
        self.work_no_var = ttk.StringVar()
        self.name_var = ttk.StringVar()
        self.password_var = ttk.StringVar()
        self.role_var = ttk.StringVar(value="operator")
        self.active_var = ttk.BooleanVar(value=True)

        fields = [
            ("工号", ttk.Entry(form, textvariable=self.work_no_var)),
            ("姓名", ttk.Entry(form, textvariable=self.name_var)),
            ("密码", ttk.Entry(form, textvariable=self.password_var, show="*")),
            ("角色", ttk.Combobox(form, textvariable=self.role_var, values=("operator", "admin"))),
        ]
        for idx, (label, widget) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=0, column=idx, sticky="w")
            widget.grid(row=1, column=idx, sticky="ew", padx=(0, 10), pady=(2, 8))
            form.columnconfigure(idx, weight=1)
        ttk.Checkbutton(form, text="启用", variable=self.active_var).grid(row=2, column=0, sticky="w")

        buttons = ttk.Frame(root)
        buttons.pack(fill=X)
        ttk.Button(buttons, text="新增", bootstyle="success", command=self.add_user).pack(side=LEFT)
        ttk.Button(buttons, text="保存修改", bootstyle="primary", command=self.update_user).pack(
            side=LEFT, padx=8
        )
        ttk.Button(buttons, text="删除", bootstyle="danger", command=self.delete_user).pack(
            side=LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="清空", command=self.clear_form).pack(side=LEFT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT)

        self.reload()
        self.clear_form()

    def reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.user_service.list_users():
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["work_no"],
                    row["name"],
                    row["role"],
                    "是" if row["active"] else "否",
                    row["created_at"],
                ),
            )

    def on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self.selected_id = int(selected[0])
        values = self.tree.item(selected[0], "values")
        self.work_no_var.set(values[0])
        self.name_var.set(values[1])
        self.role_var.set(values[2])
        self.active_var.set(values[3] == "是")
        self.password_var.set("")

    def clear_form(self) -> None:
        self.selected_id = None
        self.tree.selection_remove(self.tree.selection())
        self.work_no_var.set("")
        self.name_var.set("")
        self.password_var.set("")
        self.role_var.set("operator")
        self.active_var.set(True)

    def add_user(self) -> None:
        self._save(None, "用户已新增")

    def update_user(self) -> None:
        if self.selected_id is None:
            messagebox.showwarning("未选择用户", "请先选择要修改的用户")
            return
        self._save(self.selected_id, "用户已修改")

    def delete_user(self) -> None:
        if self.selected_id is None:
            messagebox.showwarning("未选择用户", "请先选择要删除的用户")
            return
        user_name = self.name_var.get() or self.work_no_var.get()
        if not messagebox.askyesno(
            "确认删除",
            f"确定删除用户“{user_name}”吗？\n\n该操作会停用用户，历史拧紧记录中的工号不会删除。",
        ):
            return
        try:
            self.user_service.set_active(self.selected_id, False)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.reload()
        self.clear_form()
        messagebox.showinfo("删除成功", "用户已删除")

    def _save(self, user_id: int | None, message: str) -> None:
        try:
            self.user_service.save(
                {
                    "id": user_id,
                    "work_no": self.work_no_var.get(),
                    "name": self.name_var.get(),
                    "password": self.password_var.get(),
                    "role": self.role_var.get(),
                    "active": self.active_var.get(),
                }
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.reload()
        self.clear_form()
        messagebox.showinfo("保存成功", message)
