"""Konfigurasi Gunicorn untuk produksi."""

import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 5)))
threads = 2
timeout = 60
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"
