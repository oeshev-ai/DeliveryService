"""Запись SQLAlchemy URL в конфиг Alembic."""

from __future__ import annotations

from alembic.config import Config


def set_sqlalchemy_url(config: Config, url: str) -> None:
    """Кладёт ``url`` в ``sqlalchemy.url``.

    ConfigParser считает ``%`` началом интерполяции, поэтому
    percent-encoded пароль (``%40``) записывается удвоенным.
    """
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
