# -*- coding: utf-8 -*-
"""Playback and the context key for the custom windows.

Live channels have no resume point; a channel starts through the same
plugin route the classic folders use.
"""
import xbmc

CONTEXT_MENU = 117


def play(url, item=None):
    """Play a title or channel through its plugin route."""
    xbmc.executebuiltin('PlayMedia("%s")' % url)
