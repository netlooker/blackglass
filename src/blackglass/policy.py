from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from blackglass.config import Settings
from blackglass.schemas import PolicyDecision, RetrieveRequest, RetrievalBackend


def evaluate_policy(request: RetrieveRequest, settings: Settings) -> PolicyDecision:
    hostname = _hostname(request.url)
    domain_policy = settings.domains.get(hostname)
    denylist_matched = domain_policy is not None and domain_policy.allow is False
    allowlist_matched = domain_policy is not None and domain_policy.allow is True

    backend_allowed = _backends_allowed(request.preferred_backends, domain_policy)
    local_network_blocked = settings.policy.deny_local_networks and _is_local_network(hostname)

    allowed = not denylist_matched and backend_allowed and not local_network_blocked

    return PolicyDecision(
        allowed=allowed,
        robots_allowed=None,
        allowlist_matched=allowlist_matched,
        denylist_matched=denylist_matched,
        backend_allowed=backend_allowed,
        local_network_blocked=local_network_blocked,
    )


def _hostname(url: object) -> str:
    return (urlparse(str(url)).hostname or "").lower()


def _backends_allowed(
    requested_backends: list[RetrievalBackend], domain_policy: object | None
) -> bool:
    allowed_backends = getattr(domain_policy, "allowed_backends", None)
    if not allowed_backends:
        return True
    return all(backend in allowed_backends for backend in requested_backends)


def _is_local_network(hostname: str) -> bool:
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local
