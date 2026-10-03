"""Explicit compatibility harness, not the normal Orange Career entry point."""

from streamlit.testing.v1 import AppTest


def legacy_app(*, default_timeout=15):
    return AppTest.from_string("from ui.app import legacy_main\nlegacy_main()", default_timeout=default_timeout)
