"""A limit the agent cannot talk its way past.

    export OPERITY_API_KEY='opk_...'
    python examples/02_limits.py

Sets a per-payment limit on an agent, then has the agent pay under it and try
to pay over it. The second attempt is refused by the server before anything
moves, and the agent has no way to lift the limit: the route that writes policy
takes an account credential, and an agent's signature is not one.

Spends 5 test credits of the 20 an account may fund each month.
"""

import os
import uuid

from operity_client import Agent, Keypair, OperityError, Principal

account = Principal(os.environ["OPERITY_API_KEY"])
tag = uuid.uuid4().hex[:8]

payer_key, payee_key = Keypair.generate(), Keypair.generate()
payer = account.create_agent(f"payer-{tag}", payer_key)
payee = account.create_agent(f"payee-{tag}", payee_key)

account.fund(payer.id, 5_000_000, reference=f"limits-{tag}")

# Only the account sets policy. An agent has no route to its own.
account.set_policy(payer.id, per_tx_max_uc=1_000_000)
print("limit set: 1,000,000 uc a payment")

acting = Agent(payer.id, payer_key)

settled = acting.transfer(payee.id, 750_000, ref="inside the limit")
print(f"settled: {settled.amount_uc} uc, balance now {settled.balance_uc} uc")

try:
    acting.transfer(payee.id, 2_000_000, ref="above the limit")
except OperityError as refused:
    print(f"refused: {refused.status} {refused.detail}")
else:
    raise SystemExit("the transfer above the limit was NOT refused")

# Nothing was debited by the refusal.
assert acting.me().balance_uc == settled.balance_uc
print("balance unchanged by the refusal:", settled.balance_uc, "uc")

# The agent cannot raise its own limit. There is no method here that would let
# it, because there is no endpoint: policy is written with an account
# credential only, and this agent's signature is not one.
