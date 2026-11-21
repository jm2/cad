"""Fulcrum mouse assembly (work in progress)."""
import form
import layout

NAME = "fulcrum"


def build():
    parts = {"shell": form.shell()}
    parts.update(layout.dummies())
    return parts


COLORS = {"shell": "#c9d1dc"}
