import logging
import sys
from .config import config

def setup_logging():
    """Unified logging configuration for WineBot."""
    level = getattr(logging, config.WINEBOT_LOG_LEVEL.upper(), logging.INFO)
    
    # Root logger configuration
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logger = logging.getLogger("winebot")
    logger.info(f"Logging initialized at level: {config.WINEBOT_LOG_LEVEL}")
    return logger

# Global logger for the project
logger = setup_logging()
