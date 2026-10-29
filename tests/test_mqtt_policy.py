import unittest

from mqtt_policy import parse_command, public_status


class MqttPolicyTests(unittest.TestCase):
    def test_only_short_non_retained_known_commands_are_accepted(self):
        self.assertEqual(parse_command(b'wake'), 'wake')
        self.assertEqual(parse_command(b'sleep'), 'sleep')
        for payload in (b'wake\n', b'pairing', b'x' * 65, b'\xff', b'', 'wake'):
            with self.subTest(payload_type=type(payload).__name__):
                self.assertIsNone(parse_command(payload))
        self.assertIsNone(parse_command(b'wake', retained=True))

    def test_pairing_code_and_unrelated_accessory_are_not_published(self):
        approved = '/org/bluez/hci0/dev_AA_BB_CC_11_22_33'
        unrelated = '/org/bluez/hci0/dev_AA_BB_CC_44_55_66'
        original = {'pending': {'device': approved, 'code': 123456},
                    'devices': [{'path': approved}, {'path': unrelated}],
                    'pairing_open': True}
        result = public_status(original, {approved})
        self.assertEqual(result['pending'], {})
        self.assertEqual(result['devices'], [{'path': approved}])
        self.assertTrue(result['pairing_open'])
        self.assertEqual(original['pending']['code'], 123456)
        self.assertEqual(len(original['devices']), 2)


if __name__ == '__main__':
    unittest.main()
