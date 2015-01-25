import discover.util
from mock import patch
from nose.tools import eq_
from discover.util import convert_to_milliseconds, DEFAULT_TIMEOUT_MS


def test_convert_to_milliseconds_for_timeout_in_hours():

    # When: I convert timeout to 'ms'
    timeout_ms = convert_to_milliseconds('1h')

    # Then: Expected timeout (int) is returned in ms
    eq_(timeout_ms, 3600 * 1000)


def test_convert_to_milliseconds_for_timeout_in_minutes():

    # When: I convert timeout to 'ms'
    timeout_ms = convert_to_milliseconds('5m')

    # Then: Expected timeout (int) is returned in ms
    eq_(timeout_ms, 5 * 60 * 1000)


def test_convert_to_milliseconds_for_timeout_in_seconds():

    # When: I convert timeout to 'ms'
    timeout_ms = convert_to_milliseconds('5s')

    # Then: Expected timeout (int) is returned in ms
    eq_(timeout_ms, 5 * 1000)


def test_convert_to_milliseconds_for_timeout_in_milliseconds():

    # When: I convert timeout to 'ms'
    timeout_ms = convert_to_milliseconds('5ms')

    # Then: Expected timeout (int) is returned in ms
    eq_(timeout_ms, 5)


def test_convert_to_milliseconds_for_invalid_timeout():

    # When: I convert timeout to 'ms'
    timeout_ms = convert_to_milliseconds('5dms')

    # Then: DEFAULT_TIMEOUT_MS is returned
    eq_(timeout_ms, DEFAULT_TIMEOUT_MS)


@patch('discover.util.urlopen')
def test_health_when_uri_is_specified(murlopen):

    # When: I perform health test with given uri
    healthy = discover.util.health_test('8080', 'mockhost', uri='/test')

    # Then: http health test is performed
    eq_(healthy, True)
    murlopen.assert_called_once_with('http://mockhost:8080/test', None, 2000)


@patch('discover.util.urlopen')
def test_health_when_uri_and_timeout_is_specified(murlopen):

    # When: I perform health test with given uri
    healthy = discover.util.health_test(8080, 'mockhost', uri='/test',
                                        timeout='1m')

    # Then: http health test is performed
    eq_(healthy, True)
    murlopen.assert_called_once_with('http://mockhost:8080/test', None, 60000)


@patch('discover.util.socket')
def test_health_when_uri_is_not_specified(msocket):

    # When: I perform health test with given uri
    healthy = discover.util.health_test(8080, 'mockhost')

    # Then: tcp test returns healthy
    eq_(healthy, True)


@patch('discover.util.urlopen')
def test_http_when_urlopen_fails(murlopen):
    # Given: An invalid uri
    murlopen.side_effect = Exception('Invalid uri')

    # When: I perform http_test with given uri
    healthy = discover.util.http_test(8080, 'mockhost')

    # Then: http test returns false
    eq_(healthy, False)
    murlopen.assert_called_once_with('http://mockhost:8080/health', None,
                                     2000)


@patch('discover.util.socket')
def test_port_when_port_is_not_listening(msocket):
    # Given: Invalid Server
    msocket.socket().connect.side_effect = Exception('Invalid server')

    # When: I perform port_test
    healthy = discover.util.port_test('8080', 'mockhost')

    # Then: Port Test returns False
    eq_(healthy, False)


@patch('discover.util.get_instance_metadata')
def test_map_proxy_host_using_ec2_metadata(mock_get):
    # Given: Existing ec2 instance with metadata
    mock_get().__getitem__.return_value = 'testhost'

    # When: I map proxy host using ec2-metadata
    host = discover.util.map_proxy_host('ec2:meta-data:mock')

    # Then: Ec2 metadata gets resolved successfully
    eq_(host, 'testhost')
    mock_get().__getitem__.assert_called_once_with('mock')


@patch('discover.util.get_instance_metadata')
def test_map_proxy_host_using_actualhost(mock_get):

    # When: I map proxy host using actual host
    host = discover.util.map_proxy_host('testhost')

    # Then: The actual host value is returned.
    eq_(host, 'testhost')
