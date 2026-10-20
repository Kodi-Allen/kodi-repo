# -*- coding: utf-8 -*-
"""Playback and the context key for the custom windows.

Joyn keeps no watch history for anonymous sessions, so the custom pages
offer no resume point of their own; a title starts through the same plugin
route the classic folders use.
"""
import xbmc

CONTEXT_MENU = 117


def play(url, item=None):
    """Play a title or channel through its plugin route."""
    xbmc.executebuiltin('PlayMedia("%s")' % url)
