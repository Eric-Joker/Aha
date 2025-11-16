from contextlib import suppress
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

from httpx import AsyncClient

_httpx_client: AsyncClient = None


def get_httpx_client():
    global _httpx_client
    return (_httpx_client := AsyncClient()) if _httpx_client is None or _httpx_client.is_closed else _httpx_client


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
LOCAL_NETS = [ip_network("127.0.0.0/8"), ip_network("::1/128"), ip_network("::ffff:127.0.0.0/104")]


def local_srv(s: str):
    if (s := s.lower().strip()) in LOCAL_HOSTS:
        return True

    # IP
    with suppress(ValueError):
        ip = ip_address(s)
        for net in LOCAL_NETS:
            if ip in net:
                return True

    # 主机
    if "://" not in s:
        s = f"//{s}"
    try:
        if not (hostname := urlparse(s).hostname):
            return False
    except ValueError:
        return False
    if hostname in LOCAL_HOSTS:
        return True

    with suppress(ValueError):
        ip = ip_address(hostname)
        for net in LOCAL_NETS:
            if ip in net:
                return True
    return False
