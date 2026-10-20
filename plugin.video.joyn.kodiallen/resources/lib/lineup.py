# -*- coding: utf-8 -*-
"""Joyn's live streams as channels, guide categories and programmes.

One LiveChannelsAndEpg answer holds the whole line-up of a region with
about ten hours of programmes per channel. Joyn has no live categories of
its own; the guide's categories are made only from fields Joyn sets on each
stream: its type (LINEAR or ON_DEMAND channel), its liveStreamGroups and
its PLUS marking. Programme data is used as Joyn sends it, nothing is
filled in.
"""
LINEAR, ON_DEMAND = 'LINEAR', 'ON_DEMAND'
# (string id, test) per category, in the order the guide lists them.
CATEGORIES = (
    (30401, lambda stream: stream['type'] == LINEAR),
    (30402, lambda stream: 'SPORTS' in stream['groups']),
    (30403, lambda stream: 'PUBLIC_VALUE' in stream['groups']),
    (30404, lambda stream: stream['type'] == ON_DEMAND),
    (30405, lambda stream: stream['plus']),
)


def channels(streams):
    """{id: channel} in Joyn's order (dicts keep insertion order)."""
    result = {}
    for stream in streams:
        streamId = stream.get('id')
        if not streamId or stream.get('type') not in (LINEAR, ON_DEMAND) or streamId in result:
            continue
        result[streamId] = {'id': streamId, 'title': stream.get('title') or streamId,
                            'logo': (stream.get('logo') or {}).get('url') or '',
                            'type': stream.get('type'), 'quality': stream.get('quality') or '',
                            'groups': list(stream.get('liveStreamGroups') or []),
                            'plus': 'PLUS' in (stream.get('markings') or [])}
    return result


def categories(lineUp, localLang):
    """[(name, [channel ids])], empty categories left out."""
    result = []
    for stringId, test in CATEGORIES:
        ids = [channelId for channelId, channel in lineUp.items() if test(channel)]
        if ids:
            result.append((localLang(stringId), ids))
    return result


def programmes(streams):
    """{channel id: [(start, end, programme)]}, sorted, gaps left as gaps."""
    guide = {}
    for stream in streams:
        items = []
        for event in stream.get('epgEvents') or []:
            program = event.get('program') or {}
            start, end = event.get('startDate'), event.get('endDate')
            if not isinstance(start, int) or not isinstance(end, int) or end <= start:
                continue
            items.append((start, end, {'title': program.get('title') or '',
                                       'episode_title': program.get('secondaryTitle') or '',
                                       'description': program.get('description') or ''}))
        items.sort(key=lambda item: item[0])
        if stream.get('id'):
            guide[stream['id']] = items
    return guide
