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
        self.geometry("980x520")

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
        for idx, (key, label) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=idx // 3 * 2, column=idx % 3, sticky="w")
            ttk.Entry(form, textvariable=self.vars[key]).grid(
                row=idx // 3 * 2 + 1, column=idx % 3, sticky="ew", padx=(0, 12), pady=(2, 8)
            )
        for col in range(3):
            form.columnconfigure(col, weight=1)

        buttons = ttk.Frame(root)
        buttons.pack(fill=X, pady=(6, 0))
        ttk.Button(buttons, text="新增", command=self.clear_form).pack(side=LEFT)
        ttk.Button(buttons, text="保存", bootstyle="primary", command=self.save).pack(
            side=LEFT, padx=8
        )
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side=RIGHT)

        self.reload()

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

    def clear_form(self) -> None:
        self.selected_id = None
        for var in self.vars.values():
            var.set("")

    def save(self) -> None:
        try:
            self.product_service.save(
                {
                    "id": self.selected_id,
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
        self.on_saved()
        messagebox.showinfo("保存成功", "产品类型已保存")
