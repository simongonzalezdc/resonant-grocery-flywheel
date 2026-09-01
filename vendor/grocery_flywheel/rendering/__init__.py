"""The rendering layer: every HTML string in the project lives here."""

from .layout import CSS, page_shell
from .panels import PANELS, render_dashboard

__all__ = ["CSS", "PANELS", "page_shell", "render_dashboard"]
