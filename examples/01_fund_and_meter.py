"""From nothing to an agent's first metered call.

    export OPERITY_API_KEY='opk_...'
    python examples/01_fund_and_meter.py

Get the key by signing in at https://operity.vercel.app/app and creating one.
It is shown once. (That is the dashboard; the API this client talks to is
https://api.operity.co.)

Spends 1 test credit of the 20 an account may fund each month.
"""

import os
import uuid

from operity_client import Agent, Keypair, Principal

account = Principal(os.environ["OPERITY_API_KEY"])
tag = uuid.uuid4().hex[:8]                  # handles are unique across the instance

# The agent's own keypair. The private half never leaves this machine: the
# agent signs with it, and the API key that registered it cannot act as it.
# Keep keypair.seed_bytes() if you want this agent back tomorrow; it is the
# agent, so treat it the way you treat a private key.
keypair = Keypair.generate()
record = account.create_agent(f"example-{tag}", keypair)
print("agent:", record.id, record.handle)

# Fund it with one test credit. Money is integer micro-credits everywhere:
# 1 credit = 1,000,000 uc, and no amount is ever a float. The reference names
# the payment the credits stand for, and each one is redeemable once.
funded = account.fund(record.id, 1_000_000, reference=f"example-{tag}")
print("funded:", funded.balance_uc, "uc"
      f" (this month: {funded.minted_this_month_uc} of {funded.ceiling_uc})")

# Now act AS the agent: a signed request, metered against its balance.
agent = Agent(record.id, keypair)
before = agent.me().balance_uc
result = agent.action("retrieval")
after = agent.me().balance_uc

print(f"metered call: {result.kind} cost {result.cost_uc} uc, "
      f"balance {before} -> {after}")
assert before - after == result.cost_uc > 0

# What an action costs is development scaffolding, not a price list: the price
# vector has never been calibrated, and it will change.
