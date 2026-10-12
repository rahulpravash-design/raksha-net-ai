"""Whose address a request is recorded and throttled under (``app.core.client_address``)."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.client_address import client_address


def request(peer: str | None, *forwarded: str) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 50000) if peer else None,
    }
    return Request(scope)


def test_with_no_trusted_proxy_the_connection_is_the_client() -> None:
    # The header is ignored entirely: anyone can send it.
    assert client_address(request("203.0.113.9", "198.51.100.1"), 0) == "203.0.113.9"


def test_one_trusted_proxy_means_the_entry_it_appended() -> None:
    req = request("10.0.0.2", "198.51.100.7")
    assert client_address(req, 1) == "198.51.100.7"


def test_a_forged_left_hand_entry_is_never_believed() -> None:
    """The client wrote "1.2.3.4"; the proxy appended the address it really saw."""
    req = request("10.0.0.2", "1.2.3.4, 198.51.100.7")
    assert client_address(req, 1) == "198.51.100.7"


def test_two_trusted_proxies_count_two_from_the_right() -> None:
    req = request("10.0.0.3", "1.2.3.4, 198.51.100.7, 10.0.0.2")
    assert client_address(req, 2) == "198.51.100.7"


def test_repeated_headers_are_read_as_one_list() -> None:
    req = request("10.0.0.2", "1.2.3.4", "198.51.100.7")
    assert client_address(req, 1) == "198.51.100.7"


def test_too_few_entries_falls_back_to_the_connection() -> None:
    """The request did not come through the proxies it was supposed to."""
    assert client_address(request("203.0.113.9"), 1) == "203.0.113.9"
    assert client_address(request("203.0.113.9", "198.51.100.7"), 2) == "203.0.113.9"


@pytest.mark.parametrize("value", ["not-an-ip", "unknown", "1.2.3"])
def test_a_forwarded_value_that_is_not_an_ip_becomes_none(value: str) -> None:
    """The audit columns are INET: a label must become NULL, not fail the request."""
    assert client_address(request("10.0.0.2", value), 1) is None


def test_a_peer_that_is_not_an_ip_becomes_none() -> None:
    assert client_address(request("testclient"), 0) is None


def test_an_empty_header_counts_as_no_entries() -> None:
    assert client_address(request("10.0.0.2", ""), 1) == "10.0.0.2"


def test_ipv6_is_normalised() -> None:
    req = request("10.0.0.2", "2001:DB8::0001")
    assert client_address(req, 1) == "2001:db8::1"
