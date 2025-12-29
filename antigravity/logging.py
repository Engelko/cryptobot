import logging
import sys
import structlog
from antigravity.config import settings

def configure_logging():
    """
    Configure structured logging for the application.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.ENVIRONMENT == "production":
        processors = shared_processors + [
            structlog.processors.JSONRenderer()
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer()
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT == "development" else structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # File Handler for Dashboard visibility
    try:
        file_handler = logging.FileHandler("storage/antigravity.log")

        # Use a plain renderer (no colors) for the file handler to ensure readability in dashboard
        file_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
        )
        file_handler.setFormatter(file_formatter)

        logging.getLogger().addHandler(file_handler)
    except PermissionError:
        sys.stderr.write("WARNING: Could not open storage/antigravity.log for writing. Logging to console only.\n")
    except Exception as e:
        sys.stderr.write(f"WARNING: Failed to setup file logging: {e}\n")

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL)

    logging.getLogger("asyncio").setLevel(logging.WARNING)

def get_logger(name: str):
    return structlog.get_logger(name)
