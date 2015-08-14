from collections import namedtuple
from mock import patch, MagicMock
from nose.tools import eq_
from discover.yoda_route53.__main__ import route53_sync

Args = namedtuple('Args', 'etcd_host etcd_port etcd_base')


def create_mock_args(etcd_host='mockhost', etcd_port=4001, etcd_base='/'):
    return Args(etcd_host=etcd_host, etcd_port=etcd_port, etcd_base=etcd_base)


@patch('boto.connect_route53')
@patch('yoda.Client')
@patch('etcd.Client')
def test_route53_sync_with_no_polling(m_etcd_cl, m_yoda_cl, m_route53):
    # Given: Polling function that returns false
    poll = MagicMock()
    poll.return_value = False

    # And: Mock parsed arguments
    parsed_args = create_mock_args()

    # When: I perform route53 sync
    route53_sync(parsed_args, poll=poll)

    # Then: No sync is performed
    eq_(m_route53.called, False)
    eq_(m_yoda_cl.called, False)
