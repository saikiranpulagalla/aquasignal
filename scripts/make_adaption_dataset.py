#!/usr/bin/env python3

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from signallock.benchmark.runner import BASE_ALERTS
from signallock.providers.adaption_dataset import build_localization_dataset, sha256_file

path = build_localization_dataset([{"text": x} for x in BASE_ALERTS], "data/dev/adaption_alerts.csv")
print(path)
print("sha256:", sha256_file(path))
