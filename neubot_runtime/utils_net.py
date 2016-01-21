# Part of Neubot <https://neubot.nexacenter.org/>.
# Neubot is free software. See AUTHORS and LICENSE for more
# information on the copying conditions.

''' Network utils '''

import errno
import logging
import os
import socket
import sys

# Winsock returns EWOULDBLOCK
INPROGRESS = (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EAGAIN)

def format_epnt(epnt):
    ''' Format endpoint for printing '''
    address, port = epnt[:2]
    if not address:
        address = ''
    if ':' in address:
        address = ''.join(['[', address, ']'])
    return ':'.join([address, str(port)])

def format_epnt_web100(epnt):
    ''' Format endpoint for web100 '''
    address, port = epnt[:2]
    if not address:
        address = ''
    if ':' in address:
        sep = '.'
    else:
        sep = ':'
    return sep.join([address, str(port)])

def format_ainfo(ainfo):
    ''' Format addrinfo for printing '''
    family, socktype, proto, canonname, sockaddr = ainfo

    if family == socket.AF_INET:
        family = 'AF_INET'
    elif family == socket.AF_INET6:
        family = 'AF_INET6'
    else:
        family = str(family)

    if socktype == socket.SOCK_STREAM:
        socktype = 'SOCK_STREAM'
    elif socktype == socket.SOCK_DGRAM:
        socktype = 'SOCK_DGRAM'
    else:
        socktype = str(socktype)

    if proto == socket.IPPROTO_TCP:
        proto = 'IPPROTO_TCP'
    elif proto == socket.IPPROTO_UDP:
        proto = 'IPPROTO_UDP'
    else:
        proto = str(proto)

    if not canonname:
        canonname = '""'

    return '(%s, %s, %s, %s, %s)' % (family, socktype, proto,
                                     canonname, sockaddr)

# Make sure AF_INET < AF_INET6
COMPARE_AF = {
    socket.AF_INET: 1,
    socket.AF_INET6: 2,
}

def addrinfo_key(ainfo):
    ''' Map addrinfo to protocol family '''
    return COMPARE_AF[ainfo[0]]

def listen(epnt):
    ''' Listen to all sockets represented by epnt '''

    logging.debug('try listen %s', str(epnt))

    sockets = []

    # Allow to set any-address from command line
    if not epnt[0]:
        epnt = (None, epnt[1])

    try:
        addrinfo = socket.getaddrinfo(epnt[0], epnt[1], socket.AF_UNSPEC,
                                      socket.SOCK_STREAM, 0, socket.AI_PASSIVE)
    except socket.error:
        logging.error('getaddrinfo failed', exc_info=1)
        return sockets

    logging.debug("getaddrinfo returned:")
    for ainfo in addrinfo:
        logging.debug("    - %s", format_ainfo(ainfo))

    addrinfo.sort(key=addrinfo_key, reverse=True)

    for ainfo in addrinfo:
        try:
            logging.debug('try %s', format_ainfo(ainfo))

            sock = socket.socket(ainfo[0], socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if ainfo[0] == socket.AF_INET6:
                try:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                except AttributeError:
                    pass
            sock.setblocking(False)
            sock.bind(ainfo[4])
            # Probably the backlog here is too big
            sock.listen(128)

            logging.debug('listen... ok (fileno %d)', sock.fileno())
            sockets.append(sock)

        except socket.error:
            logging.warning('listen... error', exc_info=1)
        except:
            logging.warning('listen... error', exc_info=1)

    if not sockets:
        logging.error('all listen attempts failed')

    return sockets

def connect(epnt, prefer_ipv6):
    ''' Connect to epnt '''

    logging.debug('try connect to %s', str(epnt))

    try:
        addrinfo = socket.getaddrinfo(epnt[0], epnt[1], socket.AF_UNSPEC,
                                      socket.SOCK_STREAM)
    except socket.error:
        logging.error('getaddrinfo failed', exc_info=1)
        return None

    logging.debug('getaddrinfo returned:')
    for ainfo in addrinfo:
        logging.debug("    - %s", format_ainfo(ainfo))

    addrinfo.sort(key=addrinfo_key, reverse=prefer_ipv6)

    for ainfo in addrinfo:
        try:
            logging.debug('try %s', format_ainfo(ainfo))

            sock = socket.socket(ainfo[0], socket.SOCK_STREAM)
            sock.setblocking(False)
            result = sock.connect_ex(ainfo[4])
            if result not in INPROGRESS:
                raise socket.error(result, os.strerror(result))

            logging.debug('connect... in progress (fileno %d)', sock.fileno())
            return sock

        except socket.error:
            logging.warning('connect... error', exc_info=1)
        except:
            logging.warning('connect... error', exc_info=1)

    logging.error('all connect attempts failed')
    return None

def isconnected(endpoint, sock):
    ''' Check whether connect() succeeded '''

    # See http://cr.yp.to/docs/connect.html

    logging.debug('are we connected to %s?', format_epnt(endpoint))

    exception = None
    try:
        sock.getpeername()
    except socket.error as err:
        exception = err

    if not exception:
        logging.debug('yes, we are connected')
        return True

    # MacOSX getpeername() fails with EINVAL
    if exception.args[0] not in (errno.ENOTCONN, errno.EINVAL):
        logging.error('connect failed (reason: %s)',
                      str(exception.args[0]))
        return False

    try:
        sock.recv(1024)
    except socket.error as err:
        logging.error('connect failed (reason: %s)',
                      str(err.args[1]))
        return False

    raise RuntimeError('isconnected(): internal error')

def __strip_ipv4mapped_prefix(function):
    ''' Strip IPv4-mapped and IPv4-compatible prefix when the kernel does
        not implement a hard separation between IPv4 and IPv6 '''
    return __strip_ipv4mapped_prefix1(function())

def __strip_ipv4mapped_prefix1(result):
    ''' Strip IPv4-mapped and IPv4-compatible prefix when the kernel does
        not implement a hard separation between IPv4 and IPv6 '''
    result = list(result)
    if result[0].startswith('::ffff:'):
        result[0] = result[0][7:]
    elif result[0].startswith('::') and result[0] != '::1':
        result[0] = result[0][2:]
    return tuple(result)

def getpeername(sock):
    ''' getpeername() wrapper that strips IPv4-mapped prefix '''
    return __strip_ipv4mapped_prefix(sock.getpeername)

def getsockname(sock):
    ''' getsockname() wrapper that strips IPv4-mapped prefix '''
    return __strip_ipv4mapped_prefix(sock.getsockname)
