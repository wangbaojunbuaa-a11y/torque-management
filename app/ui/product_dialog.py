import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X
from tkinter import messagebox

from app.services.product_service import ProductService


class ProductDialog(ttk.Toplevel):
    def __init__(self, parent, product_service: ProductService, on_saved) -> None:
        super().__init__(parent)
        self.product_service = product_service
        self.on_saved = on_saved
        self.selected_id: int | None = None

        self.title("产品类型维护")
        self.geometry("1280x720")
        self.minsize(1100, 620)

        root = ttk.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)

        self.tree = ttk.Treeview(
            root,
            columns=("code", "name", "igbt", "screws", "p2", "p3", "t2", "t3", "rest"),
            show="headings",
            height=10,
        )
        headings = {
            "code": "编码",
            "name": "名称",
            "igbt": "IGBT数",
            "screws": "每IGBT螺钉",
            "p2": "二次程序",
            "p3": "三次程序",
            "t2": "二次扭矩",
            "t3": "三次扭矩",
            "rest": "静置分钟",
        }
        for key, text in headings.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=95, anchor="center")
        self.tree.column("name", width=160)
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.Frame(root)
        form.pack(fill=X, pady=(12, 0))
        self.vars = {key: ttk.StringVar() for key in headings}
        labels = [
            ("code", "编码"),
            ("name", "名称"),
            ("igbt", "IGBT数"),
            ("screws", "每IGBT螺钉"),
            ("p2", "二次程序"),
            ("p3", "三次程序"),
            ("t2", "二次扭矩"),
            ("t3", "三次扭矩"),
            ("rest", "静置分钟"),
        ]
        self.entries = {}
        for idx, (key, label) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=idx // 3 * 2, column=idx % 3, sticky="w")
            entry = ttk.Entry(form, textvariable=self.vars[key])
            entry.grid(
                row=idx // 3 * 2 + 1, column=idx % 3, sticky="ew", padx=(0, 12), pady=(2, 8)
            )
            self.entries[key] = entry
        for col in range(3):
            form.columnconfigure(col, weight=1)

        buttons = ttk.Frame(root)
        buttons.pack(fill=X, pady=(6, 0))
        ttk.Button(buttons, text="新增", bootstyle="success", command=self.add_product).pack(
            side=LEFT
        )
        ttk.Button(buttons, text="保存修改", bootstyle="primary", command=self.update_product).pack(
            side=LEFT, padx=8
        )
        ttk.Button(buttons, text="删除", bootstyle="danger", command=self.delete_product).pack(
            side=LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="清空", command=self.new_product).pack(side=LEFT)
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT)

        self.mode_var = ttk.StringVar(value="新增模式：填写表单后点击保存")
        ttk.Label(root, textvariable=self.mode_var, bootstyle="secondary").pack(
            anchor="w", pady=(8, 0)
        )

        self.reload()
        self.new_product()

    def reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.product_service.list_active():
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["code"],
                    row["name"],
                    row["igbt_count"],
                    row["screws_per_igbt"],
                    row["round2_program_no"],
                    row["round3_program_no"],
                    row["round2_set_torque"],
                    row["round3_set_torque"],
                    row["rest_minutes"],
                ),
            )

    def on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self.selected_id = int(selected[0])
        values = self.tree.item(selected[0], "values")
        for key, value in zip(self.vars, values):
            self.vars[key].set(str(value))
        self.mode_var.set("编辑模式：正在修改已选产品，点击保存更新")

    def new_product(self) -> None:
        self.selected_id = None
        self.tree.selection_remove(self.tree.selection())
        for var in self.vars.values():
            var.set("")
        self.mode_var.set("新增模式：填写表单后点击新增")
        self.entries["code"].focus_set()

    def add_product(self) -> None:
        self._save_product(product_id=None, success_message="产品类型已新增")

    def update_product(self) -> None:
        if self.selected_id is None:
            messagebox.showwarning("未选择产品", "请先在上方表格选择要修改的产品")
            return
        self._save_product(product_id=self.selected_id, success_message="产品类型已修改")

    def delete_product(self) -> None:
        if self.selected_id is None:
            messagebox.showwarning("未选择产品", "请先在上方表格选择要删除的产品")
            return
        product_name = self.vars["name"].get() or self.vars["code"].get()
        if not messagebox.askyesno(
            "确认删除",
            f"确定删除产品“{product_name}”吗？\n\n该操作会停用产品，历史生产记录不会删除。",
        ):
            return
        try:
            self.product_service.set_active(self.selected_id, False)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.reload()
        self.new_product()
        self.on_saved()
        messagebox.showinfo("删除成功", "产品已删除")

    def _save_product(self, product_id: int | None, success_message: str) -> None:
        try:
            self.product_service.save(
                {
                    "id": product_id,
                    "code": self.vars["code"].get(),
                    "name": self.vars["name"].get(),
                    "igbt_count": self.vars["igbt"].get(),
                    "screws_per_igbt": self.vars["screws"].get(),
                    "round2_program_no": self.vars["p2"].get(),
                    "round3_program_no": self.vars["p3"].get(),
                    "round2_set_torque": self.vars["t2"].get(),
                    "round3_set_torque": self.vars["t3"].get(),
                    "rest_minutes": self.vars["rest"].get(),
                }
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.reload()
        self.new_product()
        self.on_saved()
        messagebox.showinfo("保存成功", success_message)
