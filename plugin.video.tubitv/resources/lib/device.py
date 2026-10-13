# -*- coding: utf-8 -*-
"""Kodi-independent platform and Widevine compatibility checks.

The functions in here deliberately inspect files instead of loading the CDM.
Loading an incompatible Widevine library is not a harmless capability probe:
on affected 32-bit systems it terminates the whole Kodi process.
"""

import os
import platform
import re
import struct


DEVICE_MODEL_PATH = '/proc/device-tree/model'
CDM_NAME = 'libwidevinecdm.so'

ELF_MACHINES = {
    3: 'x86',
    40: 'arm',
    62: 'x86_64',
    183: 'aarch64',
}


def deviceModel(path=DEVICE_MODEL_PATH):
    """Return the Linux device-tree model, or an empty string elsewhere."""
    try:
        with open(path, 'rb') as modelFile:
            return modelFile.read().replace(b'\x00', b'').decode('utf-8', 'replace').strip()
    except (IOError, OSError):
        return ''


def _read(path, limit=None):
    try:
        with open(path, 'rb') as handle:
            return handle.read() if limit is None else handle.read(limit)
    except (IOError, OSError):
        return b''


def elfInfo(path):
    """Return safe architecture/RELR details for an ELF shared library."""
    header = _read(path, 64)
    info = {'path': path, 'exists': bool(header), 'elf_class': None,
            'architecture': 'unknown', 'has_relr': False, 'version': ''}
    if len(header) < 20 or header[:4] != b'\x7fELF':
        return info

    info['elf_class'] = {1: 32, 2: 64}.get(header[4])
    endian = '<' if header[5] == 1 else '>' if header[5] == 2 else None
    if endian:
        machine = struct.unpack(endian + 'H', header[18:20])[0]
        info['architecture'] = ELF_MACHINES.get(machine, 'machine-%s' % machine)

    # Widevine is stripped, but its section-name table and version text are
    # retained. Reading the file is safe; dlopen() is specifically avoided.
    payload = _read(path)
    info['has_relr'] = b'.relr.dyn' in payload
    versions = re.findall(br'4\.10\.\d+\.\d+', payload)
    if versions:
        info['version'] = versions[0].decode('ascii', 'replace')
    return info


def systemLoader(mapsPath='/proc/self/maps'):
    """Find the dynamic loader used by this process."""
    try:
        with open(mapsPath, 'r') as maps:
            for line in maps:
                path = line.rstrip().split()[-1]
                name = os.path.basename(path)
                if name.startswith(('ld-', 'ld-linux')) and os.path.isfile(path):
                    return path
    except (IOError, OSError, IndexError):
        pass
    for path in ('/lib/ld-linux-armhf.so.3',
                 '/lib/ld-linux-aarch64.so.1',
                 '/lib64/ld-linux-aarch64.so.1',
                 '/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2',
                 '/lib/ld-linux.so.2'):
        if os.path.isfile(path):
            return path
    return ''


def loaderSupportsRelr(path=None):
    """Whether the active ELF loader advertises DT_RELR handling.

    Returns ``None`` when no loader can be inspected. OSMC backported RELR to
    glibc 2.31, so comparing only the printed glibc version is insufficient.
    Both upstream and the OSMC backport retain one of these marker strings.
    """
    path = path or systemLoader()
    payload = _read(path)
    if not payload:
        return None
    return any(marker in payload for marker in
               (b'DT_RELRENT', b'GLIBC_ABI_DT_RELR', b'ElfW(Relr)'))


def widevineCompatibility(cdmPath, loaderPath=None):
    """Return ``(safe, reason, details)`` without loading Widevine.

    The one known process-killing mismatch is a CDM using packed RELR
    relocations with a loader that cannot apply them. Unknown combinations
    are left to InputStream Adaptive rather than being device-name blocked.
    No file at cdmPath is not a reason to refuse either: Android brings its
    own Widevine, Windows and macOS name the library differently, and a
    Linux CDM may live wherever InputStream Adaptive was told to look.
    """
    details = elfInfo(cdmPath)
    details['loader'] = loaderPath or systemLoader()
    details['loader_relr'] = loaderSupportsRelr(details['loader'])
    details['machine'] = platform.machine()
    details['pointer_bits'] = struct.calcsize('P') * 8
    if not details['exists']:
        return True, 'no CDM at the default path, left to inputstream.adaptive', details
    if details['has_relr'] and details['loader_relr'] is False:
        return False, 'CDM needs DT_RELR but the system loader lacks it', details
    return True, 'compatible', details
