"""The committed wire-format vectors, against this client.

Ed25519 is deterministic (RFC 8032), so a signature over a fixed canonical
string is a constant. `vectors.json` holds those constants; the Operity server
is held to the same ones, so neither side can drift without the other noticing.
If you are writing a client in another language, this file is the shape of the
test you want: read `vectors.json`, build the canonical string, sign it, and
compare the bytes.

The signature is asserted on the bytes the client PUTS ON THE WIRE, through a
recording transport, not on a canonical string handed to the canonicaliser. The
difference is not academic: this client once signed `/v1/agents/a b/c/…` while
sending the percent-encoded path, and a test that called the canonicaliser with
the already-encoded path passed throughout.
"""

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from operity_client import Agent, Keypair
from operity_client.signing import canonical_request

DATA = json.loads((Path(__file__).parent / "vectors.json").read_text())
VECTORS = {v["name"]: v for v in DATA["vectors"]}
SEED = bytes.fromhex(DATA["seed_hex"])
TIMESTAMP, NONCE = DATA["timestamp"], DATA["nonce"]
AGENT_ID = "00000000-0000-4000-8000-00000000000a"


def verifies(signature_b64: str, canonical: bytes) -> bool:
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(DATA["public_key_b64"]))
    try:
        key.verify(base64.b64decode(signature_b64), canonical)
    except InvalidSignature:
        return False
    return True


# --------------------------------------------------------------------------
# The vectors themselves.
# --------------------------------------------------------------------------

def test_the_seed_produces_the_committed_public_key():
    assert Keypair.from_seed(SEED).public_key_b64 == DATA["public_key_b64"]


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_the_canonical_string_is_the_committed_one(name):
    v = VECTORS[name]
    assert canonical_request(v["method"], v["sent_path"], TIMESTAMP, NONCE,
                             v["body"].encode()) == v["canonical"].encode()


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_the_body_hash_is_lowercase_hex_of_the_bytes_sent(name):
    v = VECTORS[name]
    assert hashlib.sha256(v["body"].encode()).hexdigest() == v["body_sha256"]
    assert v["canonical"].split("\n")[-1] == v["body_sha256"]


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_the_signature_is_the_committed_one_and_verifies(name):
    v = VECTORS[name]
    assert Keypair.from_seed(SEED).sign(v["canonical"].encode()) == v["signature"]
    assert verifies(v["signature"], v["canonical"].encode())


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_one_changed_character_breaks_the_signature(name):
    """A vector that verified whatever it was handed would prove nothing."""
    v = VECTORS[name]
    mutated = v["canonical"].replace("\n/v1/", "\n/v1//", 1).encode()
    assert mutated != v["canonical"].encode()
    assert not verifies(v["signature"], mutated)


def test_the_readings_a_careless_client_gets_wrong_give_different_bytes():
    """Non-vacuity for the three readings the vectors exist to pin. If the
    wrong reading produced the same canonical string, the vector would be
    testing nothing."""
    # the query string is excluded from the signed path
    assert canonical_request("GET", "/v1/jobs?state=open", TIMESTAMP, NONCE, b"") \
        != f"GET\n/v1/jobs?state=open\n{TIMESTAMP}\n{NONCE}\n".encode()
    assert VECTORS["query_string"]["sent_path"] != VECTORS["query_string"]["canonical_path"]
    # the path is signed raw, never percent-decoded
    assert canonical_request("GET", "/v1/agents/a b/c/reputation", TIMESTAMP, NONCE, b"") \
        != VECTORS["encoded_path"]["canonical"].encode()
    # the body hash covers the exact bytes: one space makes it a different request
    assert canonical_request("POST", "/v1/actions", TIMESTAMP, NONCE,
                             b'{"kind": "retrieval"}') != VECTORS["json_body"]["canonical"].encode()


# --------------------------------------------------------------------------
# On the wire, through the client's own methods.
# --------------------------------------------------------------------------

def recording_agent(responses: dict):
    """An Agent whose transport records requests instead of sending them, with
    the vectors' clock and nonce injected."""
    sent = []

    def handler(request: httpx.Request):
        sent.append(request)
        return httpx.Response(200, json=responses.get(request.url.path, {}))

    http = httpx.Client(base_url="https://operity.invalid",
                        transport=httpx.MockTransport(handler))
    return Agent(AGENT_ID, Keypair.from_seed(SEED), http=http,
                 clock=lambda: TIMESTAMP, nonce=lambda: NONCE), sent


ME = {"id": AGENT_ID, "handle": "h", "status": "active", "balance_uc": 1}


def test_the_headers_are_the_four_the_format_names():
    agent, sent = recording_agent({"/v1/me": ME})
    agent.me()
    (request,) = sent
    assert request.headers["X-Operity-Agent"] == AGENT_ID
    assert request.headers["X-Operity-Timestamp"] == TIMESTAMP
    assert request.headers["X-Operity-Nonce"] == NONCE
    assert request.headers["X-Operity-Signature"] == VECTORS["me"]["signature"]


def test_a_json_body_is_signed_as_the_bytes_that_are_sent():
    agent, sent = recording_agent(
        {"/v1/actions": {"kind": "retrieval", "cost_uc": 1, "balance_uc": 0}})
    agent.action("retrieval")
    (request,) = sent
    v = VECTORS["json_body"]
    assert request.content == v["body"].encode(), "the client sent bytes the vector does not sign"
    assert request.headers["X-Operity-Signature"] == v["signature"]


def test_a_query_string_is_sent_and_not_signed():
    agent, sent = recording_agent({"/v1/jobs": []})
    agent.list_open_jobs()
    (request,) = sent
    v = VECTORS["query_string"]
    assert request.url.raw_path == v["sent_path"].encode()
    assert request.headers["X-Operity-Signature"] == v["signature"]


def test_a_percent_encoded_path_is_signed_exactly_as_it_is_sent():
    v = VECTORS["encoded_path"]
    agent, sent = recording_agent({})
    try:
        agent.reputation("a b/c")    # the recorded REQUEST is what is asserted
    except Exception:                # noqa: BLE001,S110 - the empty reply is not the subject
        pass
    (request,) = sent
    assert request.url.raw_path == v["sent_path"].encode()
    assert request.headers["X-Operity-Signature"] == v["signature"]


def test_every_money_moving_call_carries_one_idempotency_key_across_retries():
    """The key is the whole point of the header: a retry after no answer must
    reuse it, or the retry is a second payment."""
    keys, attempts = [], []

    def handler(request: httpx.Request):
        keys.append(request.headers.get("Idempotency-Key"))
        attempts.append(request.headers["X-Operity-Nonce"])
        if len(attempts) == 1:
            return httpx.Response(503, json={"detail": "no answer"})
        return httpx.Response(200, json={"kind": "retrieval", "cost_uc": 1, "balance_uc": 0})

    http = httpx.Client(base_url="https://operity.invalid",
                        transport=httpx.MockTransport(handler))
    agent = Agent(AGENT_ID, Keypair.from_seed(SEED), http=http)
    agent._sleep = lambda _seconds: None
    agent.action("retrieval")

    assert len(keys) == 2, "a 503 is not an answer and must be retried"
    assert keys[0] == keys[1] is not None, "the retry minted a fresh idempotency key"
    assert attempts[0] != attempts[1], "a nonce is spent once, so the retry must re-sign"
