from argparse import Namespace
import unittest
from projectorctl import make_request


class ControlTests(unittest.TestCase):
    def test_pairing_window_is_bounded_before_connecting(self):
        for seconds in (0, -1, 1201):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                make_request(Namespace(action='pair', seconds=seconds))
        self.assertEqual(make_request(Namespace(action='pair', seconds=300)),
                         {'action': 'pairing', 'seconds': 300})

    def test_confirmation_requires_full_device_and_six_digit_code(self):
        path = '/org/bluez/hci0/dev_AA_BB_CC_11_22_33'
        for device, code in [('AA:BB:CC:11:22:33', '123456'), (path, '12345'), (path, 'abc123')]:
            with self.subTest(device=device, code=code), self.assertRaises(ValueError):
                make_request(Namespace(action='confirm', device=device, code=code))
        self.assertEqual(make_request(Namespace(action='confirm', device=path, code='012345')),
                         {'action': 'confirm', 'device': path, 'code': 12345})


if __name__ == '__main__':
    unittest.main()
