# -*- coding: utf-8 -*-
"""The navbar every page shares, and the service's stop flag."""
HOME, LIVE, SEARCH = 301, 302, 303
ALL = (HOME, LIVE, SEARCH)


class Stop(object):
    """Whether Kodi asked the service to stop.

    Kodi wakes only the Monitor that is waiting at that moment; another
    window's loop or the service loop would carry on with GUI calls while
    Kodi holds the GUI waiting for the service, and both would hang. Every
    loop waits through wait() and checks stopping() before touching the GUI.
    """
    requested = False


def wait(monitor, seconds):
    if monitor.waitForAbort(seconds):
        Stop.requested = True
    return Stop.requested


def stopping():
    return Stop.requested
