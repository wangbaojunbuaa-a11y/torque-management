from app.config.app_config import AppConfig
from app.repositories.sqlite_repo import SQLiteRepository
from app.services.auth_service import AuthService
from app.services.product_service import ProductService
from app.services.tightening_service import TighteningService
from app.ui.login_window import LoginWindow


def enable_windows_dpi_awareness() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> None:
    enable_windows_dpi_awareness()
    config = AppConfig.load()
    repo = SQLiteRepository(config.db_path)
    repo.initialize()
    repo.seed_defaults()

    auth_service = AuthService(repo)
    product_service = ProductService(repo)
    tightening_service = TighteningService(repo)

    app = LoginWindow(auth_service, product_service, tightening_service, config)
    app.mainloop()


if __name__ == "__main__":
    main()
