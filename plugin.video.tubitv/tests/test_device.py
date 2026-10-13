import os
import struct
import sys
import tempfile
import unittest


ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)


from resources.lib.device import (deviceModel, elfInfo, loaderSupportsRelr,
                                  widevineCompatibility)


class DeviceCompatibilityTests(unittest.TestCase):

    def test_reads_nul_terminated_device_tree_model(self):
        handle, path = tempfile.mkstemp()
        try:
            os.write(handle, b'Vero4KPlus\x00')
            os.close(handle)
            handle = None
            self.assertEqual(deviceModel(path), 'Vero4KPlus')
        finally:
            if handle is not None:
                os.close(handle)
            os.unlink(path)

    @staticmethod
    def temporaryFile(payload):
        handle, path = tempfile.mkstemp()
        os.write(handle, payload)
        os.close(handle)
        return path

    def test_reads_elf_architecture_version_and_relr_without_loading(self):
        header = bytearray(64)
        header[:6] = b'\x7fELF\x01\x01'
        header[18:20] = struct.pack('<H', 40)
        path = self.temporaryFile(bytes(header) + b'.relr.dyn\x004.10.2662.3\x00')
        try:
            info = elfInfo(path)
            self.assertEqual(32, info['elf_class'])
            self.assertEqual('arm', info['architecture'])
            self.assertTrue(info['has_relr'])
            self.assertEqual('4.10.2662.3', info['version'])
        finally:
            os.unlink(path)

    def test_detects_relr_loader_capability_by_feature_not_device_name(self):
        oldLoader = self.temporaryFile(b'old dynamic loader')
        newLoader = self.temporaryFile(b'assert info[DT_RELRENT] ElfW(Relr)')
        cdm = self.temporaryFile(b'\x7fELF' + b'\x00' * 60 + b'.relr.dyn')
        try:
            self.assertFalse(loaderSupportsRelr(oldLoader))
            self.assertTrue(loaderSupportsRelr(newLoader))
            safe, reason, _ = widevineCompatibility(cdm, oldLoader)
            self.assertFalse(safe)
            self.assertIn('DT_RELR', reason)
            safe, reason, _ = widevineCompatibility(cdm, newLoader)
            self.assertTrue(safe)
            self.assertEqual('compatible', reason)
        finally:
            for path in (oldLoader, newLoader, cdm):
                os.unlink(path)

    def test_cdm_version_and_location_are_left_to_inputstream_adaptive(self):
        loader = self.temporaryFile(b'assert info[DT_RELRENT] ElfW(Relr)')
        oldCdm = self.temporaryFile(
            b'\x7fELF' + b'\x00' * 60 + b'.relr.dyn\x004.10.2662.3\x00')
        try:
            safe, reason, details = widevineCompatibility(oldCdm, loader)
            self.assertTrue(safe)
            self.assertEqual('compatible', reason)
            self.assertEqual('4.10.2662.3', details['version'])
            safe, reason, details = widevineCompatibility(oldCdm + '.absent', loader)
            self.assertTrue(safe)
            self.assertFalse(details['exists'])
        finally:
            for path in (loader, oldCdm):
                os.unlink(path)


if __name__ == '__main__':
    unittest.main()
