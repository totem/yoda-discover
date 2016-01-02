"""
Syncs yoda etcd proxy nodes with route53
"""
import argparse
import time
import random
import os

from boto.route53.record import ResourceRecordSets
from urllib3.exceptions import ReadTimeoutError
import yoda
import etcd
import boto

from discover import logger
from discover.util import init_shutdown_handler


def etcd_client(parsed_args):
    return etcd.Client(host=parsed_args.etcd_host, port=parsed_args.etcd_port)


def yoda_client(etcd_cl):
    return yoda.Client(etcd_cl=etcd_cl)


def job_lock(etcd_cl, etcd_base):
    lock_key = '%s/route53/_lock' % etcd_base
    try:
        node = etcd_cl.write(lock_key, True, ttl=60, prevExist=False)
        return node.modifiedIndex
    except KeyError:
        return None


def job_unlock(etcd_cl, etcd_base, lock):
    if lock:
        lock_key = '%s/route53/_lock' % etcd_base
        try:
            etcd_cl.delete(lock_key, prevIndex=lock)
        except KeyError:
            logger.warn('Failed to unlock route53 job %d', lock)
            return False
    else:
        return False


class ApplyLock:
    def __init__(self, etcd_cl, etcd_base):
        self.etcd_cl = etcd_cl
        self.etcd_base = etcd_base
        self.lock = job_lock(etcd_cl, etcd_base)

    def __enter__(self):
        return self.lock

    def __exit__(self, type, value, traceback):
        job_unlock(self.etcd_cl, self.etcd_base, self.lock)


def set_sync_index(etcd_cl, etcd_base, sync_index):
    sync_key = '%s/route53/sync-index/' % etcd_base
    etcd_cl.write(sync_key, sync_index)


def get_sync_index(etcd_cl, etcd_base):
    sync_key = '%s/route53/sync-index/' % etcd_base
    try:
        return int(etcd_cl.read(sync_key, consistent=True).value)
    except KeyError:
        pass


def remove_sync_index(etcd_cl, etcd_base):
    sync_key = '%s/route53/sync-index/' % etcd_base
    try:
        etcd_cl.delete(sync_key)
    except KeyError:
        pass


def update_route53(node_name, value, parsed_args):
    conn = boto.connect_route53(
        aws_access_key_id=parsed_args.access_key_id,
        aws_secret_access_key=parsed_args.secret_access_key)
    records = conn.get_all_rrsets(parsed_args.zone_id,
                                  type=parsed_args.record_type,
                                  name=parsed_args.dns_record,
                                  identifier=node_name, maxitems=1)
    changes = ResourceRecordSets(conn, parsed_args.zone_id)
    change = changes.add_change(
        'UPSERT', name=parsed_args.dns_record,
        type=parsed_args.record_type, ttl=parsed_args.dns_ttl,
        identifier=node_name, weight=parsed_args.record_weight)
    change.add_value(value)
    if len(records) > 0 and records[0].name == parsed_args.dns_record + '.' \
            and records[0].identifier == node_name:
        if len(records[0].resource_records) > 0 and \
                records[0].resource_records[0] == value:
            logger.info('No change in Record %s. Skipping...',
                        parsed_args.dns_record)
        else:
            logger.info('Modifying record: %s:%s with identifier:%s',
                        parsed_args.dns_record, value, node_name)
            changes.commit()
    else:
        logger.info('Adding record: %s:%s with identifier:%s',
                    parsed_args.dns_record, value, node_name)
        changes.commit()


def delete_route53(node_name, parsed_args):
    conn = boto.connect_route53(
        aws_access_key_id=parsed_args.access_key_id,
        aws_secret_access_key=parsed_args.secret_access_key)
    records = conn.get_all_rrsets(parsed_args.zone_id,
                                  name=parsed_args.dns_record,
                                  identifier=node_name, maxitems=1)
    changes = ResourceRecordSets(conn, parsed_args.zone_id)
    change = changes.add_change(
        'DELETE', name=parsed_args.dns_record, identifier=node_name,
        type=parsed_args.record_type, ttl=records[0].ttl,
        weight=records[0].weight)
    change.add_value(records[0].resource_records[0])
    if len(records) > 0 and records[0].name == parsed_args.dns_record + '.' \
            and records[0].identifier == node_name:

        logger.info('Deleting record: %s with identifier %s',
                    parsed_args.dns_record, node_name)
        changes.commit()
    else:
        logger.info('Skip delete  for non existing record: %s with '
                    'identifier:%s', parsed_args.dns_record, node_name)


def route53_sync(parsed_args, poll=None):
    """
    Syncs yoda proxy nodes with route53 based on parsed arguments.
    :param parsed_args: Parsed arguments
    :param should_poll: Lambda or function that evaluates if polling should
        continue. Added for ease of unit testing
    :type should_poll: function
    :return: None
    """
    logger.info('Started sync for yoda proxy nodes with route53')
    etcd_cl = etcd_client(parsed_args)
    proxy_nodes_key = '%s/%s' % (parsed_args.etcd_base, 'proxy-nodes')
    etcd_args = {
        'key': proxy_nodes_key,
        'recursive': True,
        'wait': True,
        'timeout': 300
    }
    poll = poll or (lambda: True)
    while poll():
        sync_index = get_sync_index(etcd_cl, parsed_args.etcd_base)
        if sync_index:
            etcd_args['waitIndex'] = int(sync_index) + 1
        elif etcd_args.get('waitIndex'):
            del(etcd_args['waitIndex'])
        logger.info('Watching for changes for %s', proxy_nodes_key)
        try:
            result = etcd_cl.read(**etcd_args)
        except ReadTimeoutError:
            logger.info('Did not receive any changes. Will restart polling...')
            continue
        except etcd.EtcdException as etcd_error:
            etcd_msg = str(etcd_error).lower()
            if etcd_msg.startswith(
                    'the event in requested index is outdated and cleared'):
                logger.warn('Wait Index is stale. Removing the waitIndex')
                remove_sync_index(etcd_cl, parsed_args.etcd_base)
                # Adding a sleep to prevent high cpu during infinite looping.
                time.sleep(5)
                continue
            elif etcd_msg.startswith('unable to decode server response:'):
                # Let the job retry after 5s. This seems intermittent issue.
                time.sleep(5)
                continue
            else:
                raise

        with ApplyLock(etcd_cl, parsed_args.etcd_base) as lock:
            if lock:
                sync_index = get_sync_index(etcd_cl, parsed_args.etcd_base)
                if sync_index and sync_index >= result.modifiedIndex:
                    # Change is already processed by another node. Skip
                    continue
                else:
                    node_name = os.path.basename(result.key)
                    if result.action not in ('delete', 'expire'):
                        update_route53(node_name, result.value, parsed_args)
                    else:
                        delete_route53(node_name, parsed_args)
                    # Persist the new sync index so that other nodes can poll
                    # from sync_index+1
                    set_sync_index(etcd_cl, parsed_args.etcd_base,
                                   result.modifiedIndex)
                    etcd_args['waitIndex'] = result.modifiedIndex + 1
                    # Sleep for 5s before releasing lock. AWS API Limit
                    time.sleep(5)
            else:
                # Sleep for 5s before next poll.
                logger.info('Job locked by another node. '
                            'Will sleep and poll again')
                time.sleep(random.randint(1, 10))
                # Set default value of waitIndex to current modified index so
                # that the result is not lost in-case currently processing node
                # fails
                etcd_args['waitIndex'] = result.modifiedIndex

        if lock:
            # This node will not poll for next 11-15 seconds.
            # To give other nodes a fair chance
            time.sleep(random.randint(11, 15))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Syncs route53 nodes with etcd')

    parser.add_argument(
        '--etcd-host', metavar='<ETCD_HOST>',
        default=os.environ.get('ETCD_HOST', '172.17.42.1'),
        help='Etcd Host (defaults to 172.17.42.1)')
    parser.add_argument(
        '--etcd-port', metavar='<ETCD_PORT>',
        default=os.environ.get('ETCD_PORT', '4001'), type=int,
        help='Etcd Port (defaults to 4001)')
    parser.add_argument(
        '--etcd-base', metavar='<ETCD_BASE>',
        default=os.environ.get('ETCD_BASE', '/yoda'),
        help='Yoda base key (defaults to /yoda)')
    parser.add_argument(
        '--check-ports', metavar='<CHECK_PORTS>',
        default=os.environ.get('CHECK_PORTS', ''),
        help='Comma separated ports to be used for status check. '
             'Defaults to empty')
    parser.add_argument(
        '--access-key-id', metavar='<AWS_ACCESS_KEY_ID>',
        default=os.environ.get('AWS_ACCESS_KEY_ID'),
        help='AWS Access Key id for connecting to route53 API.')
    parser.add_argument(
        '--secret-access-key', metavar='<AWS_SECRET_ACCESS_KEY>',
        default=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        help='AWS Secret Access Key for connecting to route53 API.')
    parser.add_argument(
        '--poll-interval', metavar='<POLL_INTERVAL">',
        help='Poll interval in seconds', type=int,
        default=os.environ.get('POLL_INTERVAL', '180'))
    parser.add_argument(
        '--dns-ttl', metavar='<ROUTE53_DNS_RECORD_TTL>', type=int,
        help='DNS Record TTL in seconds. Defaults to 60.',
        default=os.environ.get('ROUTE53_DNS_RECORD_TTL', '60'))
    parser.add_argument(
        '--record-weight', metavar='<ROUTE53_DNS_RECORD_WEIGHT>', type=int,
        help='Weight of the dns record for this node. Defaults to 1',
        default=os.environ.get('ROUTE53_DNS_RECORD_WEIGHT', '1'))
    parser.add_argument(
        '--record-type', metavar='<ROUTE53_DNS_RECORD_TYPE>',
        help='Type of dns record (CNAME, A). Defaults to CNAME',
        default=os.environ.get('ROUTE53_DNS_RECORD_TYPE', 'CNAME'))
    parser.add_argument(
        'zone_id', metavar='<ROUTE53_HOSTED_ZONE_ID>',
        help='Hosted zone id for route53.')
    parser.add_argument(
        'dns_record', metavar='<ROUTE53_DNS_RECORD>',
        help='DNS Record e.g. (mycluster.abc.com)')

    parsed_args = parser.parse_args()
    parsed_args.check_ports = parsed_args.check_ports.split(',')
    init_shutdown_handler()
    route53_sync(parsed_args)
