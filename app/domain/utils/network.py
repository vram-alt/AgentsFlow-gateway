"""Shared network utilities for SSRF protection.

[RED-3] Centralized _is_private_ip() to prevent DNS rebinding attacks.
Previously duplicated in provider_service.py and tester_service.py.
"""

from __future__ import annotations

import ipaddress
import socket


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private IP address.

    [RED-3] Resolves hostnames via socket.getaddrinfo to prevent DNS rebinding
    attacks where a hostname initially resolves to a public IP but later
    resolves to a private one.
    """
    clean = hostname.strip("[]")

    # First, check if it's a literal IP address
    try:
        addr = ipaddress.ip_address(clean)
        if addr.is_loopback or addr.is_private or addr.is_link_local:
            return True
        if str(addr) == "169.254.169.254":
            return True
        return False
    except ValueError:
        pass

    # [RED-3] It's a hostname — resolve it and check all resulting IPs
    try:
        addrinfos = socket.getaddrinfo(
            clean, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        for family, _type, _proto, _canonname, sockaddr in addrinfos:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if addr.is_loopback or addr.is_private or addr.is_link_local:
                    return True
                if str(addr) == "169.254.169.254":
                    return True
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        pass

    return False
