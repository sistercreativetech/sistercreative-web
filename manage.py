#!/usr/bin/env python
"""Utilitas baris perintah Django."""

import os
import sys

from dotenv import load_dotenv


def main():
    load_dotenv()
    default = "config.settings.test" if sys.argv[1:2] == ["test"] else "config.settings.dev"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
