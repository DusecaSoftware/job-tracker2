import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                           'level': record.levelname, 'event': record.getMessage()})


def configure(path):
    handler = logging.FileHandler(path, encoding='utf-8')
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger('job_tracker')
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
