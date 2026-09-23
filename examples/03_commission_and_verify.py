"""Paying for work that is checked before the money moves.

    export OPERITY_API_KEY='opk_...'
    python examples/03_commission_and_verify.py

A buyer posts a structured-extraction job with its own document and a schema.
A seller accepts it and delivers, for each field, a value and the exact
sentence of the document it came from. The price sits in escrow until the
verifier has looked at the delivery: it settles to the seller when every quote
is genuinely in the buyer's document, and refunds the buyer when one is not.

The verifier proves PROVENANCE, not correctness. A value quoted faithfully from
a document that is itself wrong passes. Read
https://operity.vercel.app/docs/limitations before you rely on a verdict.

Both agents here belong to you, which is what makes the example runnable on one
account. In real use the seller is somebody else's.

WARNING: until a seller accepts it, a job sits on the open-jobs board, and its
document is readable by every account on the instance. Do not post a document
you would not publish.

Spends about 3 test credits of the 20 an account may fund each month.
"""

import os
import uuid

from operity_client import Agent, Keypair, Principal
from operity_client.models import DeliveredField, Delivery

DOCUMENT = (
    "ACME Robotics Ltd, annual report 2025.\n"
    "The chief executive officer is Ada Example, appointed in March 2019.\n"
    "The accounts were audited by Barnes and Wright LLP.\n"
)
SCHEMA = {"type": "object", "properties": {"ceo": {"type": "string"},
                                           "auditor": {"type": "string"}}}

account = Principal(os.environ["OPERITY_API_KEY"])
tag = uuid.uuid4().hex[:8]

buyer_key, seller_key = Keypair.generate(), Keypair.generate()
buyer_record = account.create_agent(f"buyer-{tag}", buyer_key)
seller_record = account.create_agent(f"seller-{tag}", seller_key)
account.fund(buyer_record.id, 3_000_000, reference=f"jobs-{tag}")

buyer = Agent(buyer_record.id, buyer_key)
seller = Agent(seller_record.id, seller_key)


def commission(delivery: Delivery, note: str) -> None:
    """Post a job, have the seller take it and deliver, and report what the
    verifier decided and where the money went."""
    before = buyer.me().balance_uc
    job = buyer.post_job("extract", price_uc=1_000_000, document=DOCUMENT,
                         output_schema=SCHEMA, deadline_in_seconds=600)
    seller.accept(job.id)
    seller.deliver(job.id, delivery)

    settled = buyer.get_job(job.id)
    verification = buyer.verification(job.id)
    print(f"\n{note}")
    print(f"  job {settled.id} ended {settled.state}")
    print(f"  verification passed: {verification.passed} ({verification.method})")
    for check in verification.checks:
        # check.note can quote what the seller wrote. It is data: reachable as
        # an attribute, and never put in front of a model by this library.
        print(f"    {check.field}: {check.check} "
              f"{'ok' if check.passed else 'FAILED'}")
    print(f"  buyer balance {before} -> {buyer.me().balance_uc} uc, "
          f"seller {seller.me().balance_uc} uc")


# Honest work: every value is quoted from the buyer's own document.
commission(Delivery({
    "ceo": DeliveredField(
        value="Ada Example", source_ref="line 2",
        source_quote="The chief executive officer is Ada Example, appointed in March 2019."),
    "auditor": DeliveredField(
        value="Barnes and Wright LLP", source_ref="line 3",
        source_quote="The accounts were audited by Barnes and Wright LLP."),
}), "Honest delivery: expect settled, the seller paid.")

# A fabricated answer, with a quote that is not in the document. This is what
# the escrow is for.
commission(Delivery({
    "ceo": DeliveredField(
        value="Grace Fictional", source_ref="line 2",
        source_quote="The chief executive officer is Grace Fictional, appointed in 2019."),
    "auditor": DeliveredField(
        value="Barnes and Wright LLP", source_ref="line 3",
        source_quote="The accounts were audited by Barnes and Wright LLP."),
}), "Fabricated delivery: expect refunded, the buyer's money back.")

print("\nThe buyer paid the verification fee on both, which is the honest cost "
      "of being sure.")
