import pytest

from blackglass.config import DomainPolicy, PolicySettings, Settings
from blackglass.policy import evaluate_policy
from blackglass.schemas import RetrieveRequest, RetrievalBackend


def _request(
    url: str = "https://example.com/article",
    backends: list[RetrievalBackend] | None = None,
    respect_robots: bool = True,
) -> RetrieveRequest:
    return RetrieveRequest(
        url=url,
        preferred_backends=backends or [RetrievalBackend.SCRAPLING_HTTP],
        respect_robots=respect_robots,
    )


def test_denylisted_domain_blocks_retrieval() -> None:
    settings = Settings(domains={"example.com": DomainPolicy(allow=False)})

    decision = evaluate_policy(_request(), settings)

    assert decision.allowed is False
    assert decision.denylist_matched is True


def test_allowlisted_domain_records_match() -> None:
    settings = Settings(domains={"example.com": DomainPolicy(allow=True)})

    decision = evaluate_policy(_request(), settings)

    assert decision.allowed is True
    assert decision.allowlist_matched is True


def test_backend_restriction_blocks_disallowed_backend() -> None:
    settings = Settings(
        domains={
            "example.com": DomainPolicy(
                allowed_backends=[RetrievalBackend.SCRAPLING_HTTP]
            )
        }
    )

    decision = evaluate_policy(
        _request(backends=[RetrievalBackend.CLOAKBROWSER]), settings
    )

    assert decision.allowed is False
    assert decision.backend_allowed is False


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.1.1/",
    ],
)
def test_local_network_targets_are_blocked(url: str) -> None:
    decision = evaluate_policy(_request(url=url), Settings())

    assert decision.allowed is False
    assert decision.local_network_blocked is True


def test_public_hostname_is_not_local_network() -> None:
    decision = evaluate_policy(_request(url="https://example.com/"), Settings())

    assert decision.allowed is True
    assert decision.local_network_blocked is False


def test_local_network_block_can_be_disabled() -> None:
    settings = Settings(policy=PolicySettings(deny_local_networks=False))

    decision = evaluate_policy(_request(url="http://127.0.0.1/"), settings)

    assert decision.allowed is True
    assert decision.local_network_blocked is False


def test_robots_allowed_is_always_unknown_until_implemented() -> None:
    decision_off = evaluate_policy(_request(respect_robots=False), Settings())
    decision_on = evaluate_policy(_request(respect_robots=True), Settings())

    assert decision_off.robots_allowed is None
    assert decision_on.robots_allowed is None
