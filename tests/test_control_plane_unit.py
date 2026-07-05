from lib.version import CLIENT_VERSION
from lib.control_plane import version_tuple


def test_client_version_is_a_dotted_string():
    assert isinstance(CLIENT_VERSION, str)
    assert version_tuple(CLIENT_VERSION)


def test_version_tuple_orders_correctly():
    assert version_tuple("0.0.1") < version_tuple("0.1.0")
    assert version_tuple("1.2.3") == version_tuple("1.2.3")
    assert version_tuple("0.10.0") > version_tuple("0.9.0")
