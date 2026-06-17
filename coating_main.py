from __future__ import annotations

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from coating.config import CoatingConfig
from coating.repository import CoatingRepository
from coating.report_service import CoatingReportService
from coating.services import CoatingRecordService
from coating.ui import CoatingLoginWindow
from main import enable_windows_dpi_awareness


def main() -> None:
    enable_windows_dpi_awareness()
    config = CoatingConfig.load()
    repo = CoatingRepository(config.db_path)
    repo.initialize()
    repo.seed_defaults()

    auth_service = AuthService(repo)
    user_service = UserService(repo)
    record_service = CoatingRecordService(repo)
    report_service = CoatingReportService(record_service)

    app = CoatingLoginWindow(
        auth_service,
        user_service,
        record_service,
        report_service,
        config,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
