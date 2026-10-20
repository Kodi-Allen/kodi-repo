# -*- coding: utf-8 -*-
"""The three Joyn regions and what each one keeps for itself.

Joyn runs one platform with three tenants. The catalogue, the line-up and the
playback rights differ per tenant; the API hosts are shared. A region here is
that tenant plus everything the add-on stores for it: its own session, cache,
channel numbers and network route. Switching regions never touches another
region's files or settings.
"""
import os

AT, DE, CH = 'at', 'de', 'ch'
ORDER = (AT, DE, CH)

REGIONS = {
    AT: {'name': 30201, 'short': 'AT', 'tenant': 'JOYN_AT', 'site': 'https://www.joyn.at'},
    DE: {'name': 30202, 'short': 'DE', 'tenant': 'JOYN', 'site': 'https://www.joyn.de'},
    CH: {'name': 30203, 'short': 'CH', 'tenant': 'JOYN_CH', 'site': 'https://www.joyn.ch'},
}

# Fixed IPTV Manager number ranges, one per region. The Vero's existing
# line-up uses 1-190 and 2001-5203; these ranges were free on 2026-10-20.
CHANNEL_RANGES = {AT: (6001, 6499), DE: (6501, 6999), CH: (7001, 7499)}

# The setting the region selector writes; the add-on opens in this region.
CURRENT = 'region'


def valid(region):
    return region in REGIONS


def current(addon):
    region = addon.getSetting(CURRENT)
    return region if valid(region) else AT


def setting(region, key):
    """The id of a per-region setting, e.g. at.route_mode."""
    return '%s.%s' % (region, key)


def folder(profile, region, *parts):
    """A path inside the region's own profile folder, created on demand."""
    path = os.path.join(profile, 'regions', region)
    if not os.path.isdir(path):
        os.makedirs(path)
    return os.path.join(path, *parts)
