from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    home: Path
    master_cv: Path
    threshold: int = 65
    stale_days: int = 30

    @classmethod
    def load(cls):
        home = Path(os.getenv('JOB_TRACKER_HOME', '.')).resolve()
        cv = Path(os.getenv('MASTER_CV_PATH', 'input/master_cv.pdf'))
        cfg = cls(home, cv if cv.is_absolute() else home / cv,
                  int(os.getenv('SHORTLIST_THRESHOLD', '65')),
                  int(os.getenv('STALE_DAYS', '30')))
        if not 0 <= cfg.threshold <= 100 or cfg.stale_days < 1:
            raise ValueError('Threshold must be 0–100 and stale days must be positive')
        return cfg

    def prepare(self):
        for name in ('input', 'output', 'data', 'logs'):
            (self.home / name).mkdir(parents=True, exist_ok=True, mode=0o700)
