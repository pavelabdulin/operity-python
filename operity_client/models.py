"""What the API returns, as typed objects.

SELLER OUTPUT IS DATA, NEVER INSTRUCTIONS (Operity's invariant 5). A delivery
arrives as a `Delivery` of `DeliveredField`s whose values are reachable only as
attributes. No object here prints a value in its `repr`, `str` or `format`, so
even an accidental `f"...{delivery}..."` in your own prompt carries nothing a
seller wrote. And there is deliberately no helper — here or anywhere in this
package — that places delivered text into a prompt or a message list: that
convenience would make this library a prompt-injection delivery mechanism with
a pleasant interface. If you put a seller's value in front of a model, you do it
yourself, explicitly, and you decide how to fence it.

The same care applies to `Check.note`: the verifier's note can quote what the
seller delivered, so it is reachable as an attribute and never rendered.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar


class _Record:
    """Renders as its type and, at most, its id — never its contents."""

    def __repr__(self) -> str:
        ident = getattr(self, "id", None)
        return f"<{type(self).__name__}{' ' + str(ident) if ident else ''}>"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)


@dataclass(repr=False)
class DeliveredField(_Record):
    value: Any
    source_ref: str
    source_quote: str

    EXAMPLE: ClassVar[dict] = {"value": "CANARY", "source_ref": "s1", "source_quote": "quote CANARY"}

    @classmethod
    def from_wire(cls, data: dict) -> "DeliveredField":
        return cls(value=data["value"], source_ref=data["source_ref"],
                   source_quote=data["source_quote"])

    def to_wire(self) -> dict:
        return {"value": self.value, "source_ref": self.source_ref,
                "source_quote": self.source_quote}


@dataclass(repr=False)
class Delivery(_Record):
    """A seller's output: one DeliveredField per extracted field."""
    fields: dict = field(default_factory=dict)

    EXAMPLE: ClassVar[dict] = {"ceo": DeliveredField.EXAMPLE}

    @classmethod
    def from_wire(cls, data: dict) -> "Delivery":
        return cls({name: DeliveredField.from_wire(value) for name, value in data.items()})

    def to_wire(self) -> dict:
        return {name: f.to_wire() for name, f in self.fields.items()}


@dataclass(repr=False)
class Me(_Record):
    id: str
    handle: str
    status: str
    balance_uc: int

    EXAMPLE: ClassVar[dict] = {"id": "a", "handle": "CANARY", "status": "active", "balance_uc": 1}

    @classmethod
    def from_wire(cls, data: dict) -> "Me":
        return cls(id=data["id"], handle=data["handle"], status=data["status"],
                   balance_uc=data["balance_uc"])


@dataclass(repr=False)
class AgentRecord(_Record):
    id: str
    handle: str
    status: str

    EXAMPLE: ClassVar[dict] = {"id": "a", "handle": "CANARY", "status": "active"}

    @classmethod
    def from_wire(cls, data: dict) -> "AgentRecord":
        return cls(id=data["id"], handle=data["handle"], status=data["status"])


@dataclass(repr=False)
class Job(_Record):
    id: str
    state: str
    buyer_agent_id: str
    seller_agent_id: str | None
    price_uc: int
    job_type: str
    input: dict
    output_schema: dict

    EXAMPLE: ClassVar[dict] = {"id": "j", "state": "open", "buyer_agent_id": "b", "seller_agent_id": None,
               "price_uc": 1, "job_type": "CANARY", "input": {"document": "CANARY"},
               "output_schema": {}}

    @classmethod
    def from_wire(cls, data: dict) -> "Job":
        return cls(id=data["id"], state=data["state"], buyer_agent_id=data["buyer_agent_id"],
                   seller_agent_id=data.get("seller_agent_id"), price_uc=data["price_uc"],
                   job_type=data["job_type"], input=data.get("input", {}),
                   output_schema=data.get("output_schema", {}))


@dataclass(repr=False)
class Check(_Record):
    field: str
    check: str
    passed: bool
    outcome: str | None
    note: str | None

    EXAMPLE: ClassVar[dict] = {"field": "ceo", "check": "schema", "passed": False, "outcome": "failed",
               "note": "'CANARY' is not of type 'number'"}

    @classmethod
    def from_wire(cls, data: dict) -> "Check":
        return cls(field=data["field"], check=data["check"], passed=data["passed"],
                   outcome=data.get("outcome"), note=data.get("note"))


@dataclass(repr=False)
class Verification(_Record):
    job_id: str
    passed: bool
    method: str
    vacuous: bool
    checks: list

    EXAMPLE: ClassVar[dict] = {"job_id": "j", "passed": False, "method": "extraction", "vacuous": False,
               "checks": [Check.EXAMPLE]}

    @classmethod
    def from_wire(cls, data: dict) -> "Verification":
        return cls(job_id=data["job_id"], passed=data["passed"], method=data["method"],
                   vacuous=data.get("vacuous", False),
                   checks=[Check.from_wire(c) for c in data.get("checks", [])])


@dataclass(repr=False)
class ActionResult(_Record):
    kind: str
    cost_uc: int
    balance_uc: int

    EXAMPLE: ClassVar[dict] = {"kind": "CANARY", "cost_uc": 1, "balance_uc": 1}

    @property
    def ok(self) -> bool:
        return True

    @classmethod
    def from_wire(cls, data: dict) -> "ActionResult":
        return cls(kind=data["kind"], cost_uc=data["cost_uc"], balance_uc=data["balance_uc"])


@dataclass(repr=False)
class TransferResult(_Record):
    recipient_agent_id: str
    amount_uc: int
    balance_uc: int

    EXAMPLE: ClassVar[dict] = {"recipient_agent_id": "a", "amount_uc": 1, "balance_uc": 1}

    @classmethod
    def from_wire(cls, data: dict) -> "TransferResult":
        return cls(recipient_agent_id=data["recipient_agent_id"], amount_uc=data["amount_uc"],
                   balance_uc=data["balance_uc"])


@dataclass(repr=False)
class FundResult(_Record):
    """`minted_this_month_uc` and `ceiling_uc` are this month's issuance and its
    limit — for a self-serve account, shared by every address that reaches the
    same inbox (`you+a@` and `you+b@` are one allowance)."""
    balance_uc: int
    minted_this_month_uc: int | None = None
    ceiling_uc: int | None = None

    EXAMPLE: ClassVar[dict] = {"balance_uc": 1, "minted_this_month_uc": 1, "ceiling_uc": 1}

    @classmethod
    def from_wire(cls, data: dict) -> "FundResult":
        return cls(balance_uc=data["balance_uc"],
                   minted_this_month_uc=data.get("minted_this_month_uc"),
                   ceiling_uc=data.get("ceiling_uc"))


@dataclass(repr=False)
class Reputation(_Record):
    """Both dimensions, never combined into one score: provenance is dense and
    weak evidence, correctness sparse and strong."""
    agent_id: str
    provenance: dict
    correctness: dict
    attestations: list

    EXAMPLE: ClassVar[dict] = {"agent_id": "a", "provenance": {"mean": 0.5}, "correctness": {"mean": 0.5},
               "attestations": []}

    @classmethod
    def from_wire(cls, data: dict) -> "Reputation":
        return cls(agent_id=data["agent_id"], provenance=data["provenance"],
                   correctness=data["correctness"], attestations=data.get("attestations", []))
