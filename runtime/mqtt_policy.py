"""Limits and redaction at the local MQTT boundary."""

COMMANDS = frozenset(('wake', 'power', 'sleep', 'home', 'back', 'enter',
                      'up', 'down', 'left', 'right'))


def parse_command(payload, retained=False):
    if retained or not isinstance(payload, bytes) or len(payload) > 64:
        return None
    try:
        command = payload.decode('ascii')
    except UnicodeDecodeError:
        return None
    return command if command in COMMANDS else None


def public_status(status, targets):
    """Keep codes on the root-only socket and other accessories off MQTT."""
    return {
        **status,
        'pending': {},
        'devices': [device for device in status.get('devices', [])
                    if device.get('path') in targets],
    }
