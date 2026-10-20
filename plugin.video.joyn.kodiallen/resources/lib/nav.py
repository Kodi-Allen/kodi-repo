# -*- coding: utf-8 -*-
"""The navbar every page shares: control ids and the pages behind them."""
HOME, LIVE, SERIES, MOVIES, SHOWS, SEARCH, REGION = 301, 302, 303, 304, 305, 306, 307
ALL = (HOME, LIVE, SERIES, MOVIES, SHOWS, SEARCH, REGION)
# Joyn's own landing pages behind the three catalogue entries, each with
# the string id of the heading its page shows.
PAGES = {SERIES: ('/serien', 30212), MOVIES: ('/filme', 30213), SHOWS: ('/shows', 30214)}


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
