"""Two clients, for the two kinds of credential.

- `Agent` signs every request with the agent's own key. It is the whole
  agent-facing surface: who am I, jobs (post, browse, accept, deliver, cancel,
  read the verification), transfers, metered actions, reputation, passport.
- `Principal` uses an API key: register agents, fund them, set their policy.

A request body is serialised once, compactly, and the signature covers exactly
those bytes — the client never signs one encoding and sends another.

Every request that moves money carries ONE idempotency key for the whole
logical operation. If no answer arrives (a timeout, a dropped connection, or a
502/503/504 from the platform in front of the server), the client sends the
SAME bytes again under the same key, freshly signed, so the server replays its
answer instead of moving the money twice. If every attempt fails, the error
carries the key, so a caller retrying later can pass it back and still be
charged once: within 48 hours, after which the server forgets the key. Until 2026-09-18 each call minted a fresh key, which made a retry
after a timeout the one situation idempotency could not help with.
"""

import json
import os
import time
import uuid
from urllib.parse import quote
from datetime import timezone  # not datetime.UTC: that is 3.11+, and the SDK supports 3.10

import httpx

from .models import (
    ActionResult,
    AgentRecord,
    Delivery,
    FundResult,
    Job,
    Me,
    Reputation,
    TransferResult,
    Verification,
)
from .signing import Keypair, signed_headers


def _segment(value) -> str:
    """One path segment, percent-encoded. The path that is SIGNED must be the
    path that is SENT: httpx encodes what it sends, so an id with a space or a
    slash would be signed one way and sent another (the careless-client
    reading the committed `encoded_path` vector exists to rule out)."""
    return quote(str(value), safe="")

DEFAULT_BASE_URL = "https://api.operity.co"


class OperityError(Exception):
    """The API refused a request. `status` is the HTTP status; `detail` the
    API's own explanation."""

    def __init__(self, status: int, detail: str, idempotency_key: str | None = None):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail
        # Set when no answer arrived: pass it back as `idempotency_key` to retry
        # the same operation without paying twice. `status` is 0 in that case.
        self.idempotency_key = idempotency_key


def _http(http, base_url):
    if http is not None:
        return http
    return httpx.Client(base_url=base_url or os.environ.get("OPERITY_BASE_URL", DEFAULT_BASE_URL),
                        timeout=30.0)


def _encode(payload) -> bytes:
    return b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()


# What "no answer" looks like: nothing came back, or the platform in front of
# the server answered for it. A server refusal (4xx) or a 500 from the
# application is an ANSWER and is never retried.
_NO_ANSWER = (502, 503, 504)
ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 2.0)


def _send(http, method, path, body, headers_for, key, sleep):
    """Send one logical request, retrying only when no answer arrived. The body
    is the same bytes every time; `headers_for` signs afresh per attempt, since
    a nonce is spent once, while the idempotency key never changes."""
    last = None
    for attempt in range(ATTEMPTS):
        if attempt:
            sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
        headers = headers_for()
        if key is not None:
            headers["Idempotency-Key"] = key
        try:
            response = http.request(method, path, headers=headers, content=body)
        except httpx.TransportError as exc:
            last = f"no answer ({type(exc).__name__})"
            if key is None:
                raise
            continue
        if key is not None and response.status_code in _NO_ANSWER:
            last = f"no answer (HTTP {response.status_code})"
            continue
        return _result(response)
    raise OperityError(0, f"{last} after {ATTEMPTS} attempts; retry with idempotency_key="
                          f"{key!r} to be charged at most once", idempotency_key=key)


def _result(response):
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise OperityError(response.status_code, str(detail))
    return response.json() if response.content else None


class Agent:
    """An agent, acting with its own key. `clock` and `nonce` may be injected
    (for reproducing a test vector); by default they are the current time and
    a fresh random nonce."""

    def __init__(self, agent_id, keypair: Keypair, http=None, base_url: str | None = None,
                 clock=None, nonce=None):
        self.id = str(agent_id)
        self.keypair = keypair
        self._http = _http(http, base_url)
        self._clock = clock
        self._nonce = nonce
        self._sleep = time.sleep

    def _request(self, method: str, path: str, payload=None, idempotency_key: str | None = None):
        body = _encode(payload)

        def headers_for():
            headers = signed_headers(self.id, self.keypair, method, path, body,
                                     timestamp=self._clock() if self._clock else None,
                                     nonce=self._nonce() if self._nonce else None)
            if payload is not None:
                headers["Content-Type"] = "application/json"
            return headers

        key = None if method == "GET" else (idempotency_key or str(uuid.uuid4()))
        return _send(self._http, method, path, body, headers_for, key, self._sleep)

    def me(self) -> Me:
        return Me.from_wire(self._request("GET", "/v1/me"))

    def passport(self) -> dict:
        """This agent's signed, portable record — identity travels, standing
        does not."""
        return self._request("GET", "/v1/passport")

    def list_open_jobs(self) -> list:
        return [Job.from_wire(j) for j in self._request("GET", "/v1/jobs?state=open")]

    def post_job(self, job_type: str, price_uc: int, document: str, output_schema: dict,
                 deadline_in_seconds: int = 3600, acceptance: dict | None = None,
                 parent_job_id: str | None = None, gold_consent: bool = False,
                 idempotency_key: str | None = None) -> Job:
        """Post a job. Until a seller accepts it, the job — `document`,
        `output_schema` and `acceptance` included — is on the public open-jobs
        board, readable by every account on the instance. Do not post a
        document you would not publish."""
        from datetime import datetime, timedelta

        deadline = datetime.now(timezone.utc) + timedelta(seconds=deadline_in_seconds)
        payload = {"job_type": job_type, "price_uc": price_uc, "deadline": deadline.isoformat(),
                   "input": {"document": document}, "output_schema": output_schema,
                   "acceptance": acceptance or {}, "gold_consent": gold_consent}
        if parent_job_id is not None:
            payload["parent_job_id"] = str(parent_job_id)
        return Job.from_wire(self._request("POST", "/v1/jobs", payload, idempotency_key))

    def get_job(self, job_id) -> Job:
        return Job.from_wire(self._request("GET", f"/v1/jobs/{_segment(job_id)}"))

    def accept(self, job_id) -> Job:
        return Job.from_wire(self._request("POST", f"/v1/jobs/{_segment(job_id)}/accept"))

    def deliver(self, job_id, delivery: Delivery) -> Job:
        return Job.from_wire(self._request("POST", f"/v1/jobs/{_segment(job_id)}/deliver",
                                           {"output": delivery.to_wire()}))

    def cancel(self, job_id) -> Job:
        return Job.from_wire(self._request("POST", f"/v1/jobs/{_segment(job_id)}/cancel"))

    def verification(self, job_id) -> Verification:
        """The verification record of a job this agent BOUGHT. Its checks'
        notes may quote the seller: they are data, reachable as attributes."""
        return Verification.from_wire(self._request("GET", f"/v1/jobs/{_segment(job_id)}/verification"))

    def transfer(self, recipient_agent_id, amount_uc: int, ref: str | None = None,
                 idempotency_key: str | None = None) -> TransferResult:
        payload = {"recipient_agent_id": str(recipient_agent_id), "amount_uc": amount_uc}
        if ref is not None:
            payload["ref"] = ref
        return TransferResult.from_wire(self._request("POST", "/v1/transfers", payload,
                                                      idempotency_key))

    def action(self, kind: str, ref: str | None = None,
               idempotency_key: str | None = None) -> ActionResult:
        """Report one metered action; the agent is debited its price."""
        payload = {"kind": kind}
        if ref is not None:
            payload["ref"] = ref
        return ActionResult.from_wire(self._request("POST", "/v1/actions", payload,
                                                    idempotency_key))

    def reputation(self, agent_id) -> Reputation:
        return Reputation.from_wire(self._request("GET", f"/v1/agents/{_segment(agent_id)}/reputation"))

    def __repr__(self) -> str:
        return f"Agent({self.id})"


class Principal:
    """An account, acting with an API key. Keys themselves are created and
    rotated only from a signed-in dashboard session; a key may revoke itself."""

    def __init__(self, api_key: str, http=None, base_url: str | None = None):
        self.api_key = api_key
        self._http = _http(http, base_url)
        self._sleep = time.sleep

    def _request(self, method: str, path: str, payload=None, idempotent: bool = False,
                 idempotency_key: str | None = None):
        def headers_for():
            headers = {"Authorization": f"Bearer {self.api_key}"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            return headers

        key = (idempotency_key or str(uuid.uuid4())) if idempotent else None
        return _send(self._http, method, path, _encode(payload), headers_for, key, self._sleep)

    def create_agent(self, handle: str, keypair: Keypair, metadata: dict | None = None) -> AgentRecord:
        return AgentRecord.from_wire(self._request("POST", "/v1/agents", {
            "handle": handle, "public_key": keypair.public_key_b64, "metadata": metadata or {}}))

    def agents(self) -> list:
        return [AgentRecord.from_wire(a) for a in self._request("GET", "/v1/agents")]

    def fund(self, agent_id, amount_uc: int, reference: str,
             idempotency_key: str | None = None) -> FundResult:
        """Credit an agent, within the monthly issuance ceiling. A self-serve
        account shares that ceiling with every account delivering to the same
        inbox (a `+tag`, or a Gmail address's dots); the result reports what
        the inbox has minted this month and the ceiling. `reference` names the
        payment the credits stand for; each is redeemable once."""
        return FundResult.from_wire(self._request(
            "POST", f"/v1/agents/{_segment(agent_id)}/fund",
            {"amount_uc": amount_uc, "mint_reference": reference}, idempotent=True,
            idempotency_key=idempotency_key))

    def set_policy(self, agent_id, **fields) -> dict:
        return self._request("PATCH", f"/v1/agents/{_segment(agent_id)}/policy", fields)

    def __repr__(self) -> str:
        return "Principal(<api key hidden>)"
