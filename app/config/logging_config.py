import logging
import os

from rich.logging import RichHandler

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DISABLE_WERKZEUG_LOG = os.environ.get("WERKZEUG_LOG_DISABLED", "False").lower() == "true"
SQLALCHEMY_LOG_LEVEL = logging.INFO if LOG_LEVEL == "DEBUG" else logging.WARNING


def setup_logging():
    log_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)-8s - %(name)s [%(filename)s:%(lineno)d] -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    rich_handler = RichHandler(
        level=LOG_LEVEL,
        show_time=False,
        show_level=False,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=(LOG_LEVEL == "DEBUG"),
        tracebacks_word_wrap=False,
    )

    rich_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(rich_handler)

    sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
    sqlalchemy_logger.handlers.clear()
    sqlalchemy_logger.propagate = True
    sqlalchemy_logger.setLevel(SQLALCHEMY_LOG_LEVEL)
    root_logger.info(
        f"SQLAlchemy logging handlers cleared; propagation enabled. Level set to {logging.getLevelName(SQLALCHEMY_LOG_LEVEL)}")

    werkzeug_logger = logging.getLogger("werkzeug")
    if DISABLE_WERKZEUG_LOG:
        werkzeug_logger.disabled = True
        root_logger.info("Werkzeug default logging disabled.")
    else:
        werkzeug_logger.handlers.clear()
        werkzeug_logger.setLevel(logging.INFO if LOG_LEVEL != "DEBUG" else logging.DEBUG)
        werkzeug_logger.addHandler(rich_handler)
        werkzeug_logger.propagate = False
        root_logger.info(f"Werkzeug logging configured with custom format at level {werkzeug_logger.level}")

    root_logger.info(f"Root logging setup complete. Handler level: {LOG_LEVEL}")
