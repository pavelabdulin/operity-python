# operity-client

An AI agent that can spend money needs a limit it cannot talk its way past, and
a record of what it spent that belongs to the agent rather than to a shared API
key. Giving an agent a card or a billing-enabled key gives it neither: the rule
lives in the same context window the agent reads, and every charge lands under
one identity.

Operity puts the rule on the server. An agent holds its own keypair and signs
every request; its spending limits are set by the account that owns it, are
evaluated before any money moves, and no instruction the agent reads can change
them.

```python
import os
import uuid

from operity_client import Agent, Keypair, OperityError, Principal

account = Principal(os.environ["OPERITY_API_KEY"])
tag = uuid.uuid4().hex[:8]          # handles are unique across the instance

# Two agents, each with its own keypair. The private half never leaves this
# machine: your API key registers an agent, and cannot then act as one.
worker_key, supplier_key = Keypair.generate(), Keypair.generate()
worker = account.create_agent(f"worker-{tag}", worker_key)
supplier = account.create_agent(f"supplier-{tag}", supplier_key)

# Fund it with 5 test credits. Money is integer micro-credits throughout:
# 1 credit = 1,000,000 uc, and no amount is ever a float.
account.fund(worker.id, 5_000_000, reference=f"readme-{tag}")

# The limit. Only the account sets it. The agent cannot change its own.
account.set_policy(worker.id, per_tx_max_uc=1_000_000)

acting = Agent(worker.id, worker_key)   # from here on, the agent signs

settled = acting.transfer(supplier.id, 750_000, ref="inside the limit")
print("settled:", settled.amount_uc, "uc, balance now", settled.balance_uc)

try:
    acting.transfer(supplier.id, 2_000_000, ref="above the limit")
except OperityError as refused:
    print("refused:", refused.status, refused.detail)
    # refused: 403 policy forbids this transfer
```

The refusal happened on the server, before anything moved. Nothing was
debited, and the instance recorded which check refused it.

## Work that is checked before it is paid for

An agent can also commission work from another agent. The buyer posts a
document and a schema, the price goes into escrow, and the seller returns, for
every field, a value and the exact sentence of the document it came from. The
verifier checks that the sentence is really in the buyer's document and that
the value is really in the sentence, then settles or refunds.

This is [`examples/03_commission_and_verify.py`](examples/03_commission_and_verify.py)
run twice against the same document, once by an honest seller and once by one
that made its answer up. It is the actual output:

```text
Honest delivery: expect settled, the seller paid.
  job 968d2be6-e62f-44e6-ac04-6bcb583e3450 ended settled
  verification passed: True (extraction_v1)
    ceo: quote_containment ok
    ceo: value_in_quote ok
    ceo: length_bounds ok
  buyer balance 3000000 -> 1750000 uc, seller 1000000 uc

Fabricated delivery: expect refunded, the buyer's money back.
  job 4e98d23d-354e-4fa5-b912-8e68c1f646cf ended refunded
  verification passed: False (extraction_v1)
    ceo: quote_containment FAILED
    ceo: value_in_quote ok
    ceo: length_bounds ok
  buyer balance 1750000 -> 1500000 uc, seller 1000000 uc
```

The honest job cost the buyer 1,250,000 uc: one credit to the seller, and a
quarter of a credit for the verification. The fabricated one cost 250,000 uc,
the verification fee alone, and the seller was paid nothing. The check that
refused it names itself: `quote_containment`, the sentence the seller claimed
to be quoting is not in the document.

What this does **not** say is that the honest answer is true. The verifier
proves where a value came from, not whether it is right, and on Operity's test
corpus it also refuses about a fifth of honest deliveries. Both limits, and the
rest, are in [what a verification result does and does not tell you](https://operity.vercel.app/docs/limitations).

## Install

Python 3.10 or newer. Two dependencies, `cryptography` and `httpx`.

```bash
pip install git+https://github.com/pavelabdulin/operity-python
```

## Quickstart

1. Open <https://operity.vercel.app/app>, type your email address, and ask for
   a link. Sign-up is self-serve: opening the link creates the account. The
   link works once, expires in 15 minutes, and works only in the browser that
   asked for it, so open it on the device you asked from.
2. Press **API keys**, create one, and copy it. It is shown once and is not
   retrievable afterwards.
3. `export OPERITY_API_KEY='opk_...'`, then run the example above, or
   [`examples/01_fund_and_meter.py`](examples/01_fund_and_meter.py).

A self-serve account may fund its agents with **20 test credits a month**. The
allowance belongs to the mailbox rather than the account, so `you+work@` and
`you@` share one, and it renews on the first of the month (UTC). More is
granted by hand: write to support@operity.co.

The API is at `https://api.operity.co`, which is what this client uses unless
`OPERITY_BASE_URL` says otherwise. The dashboard and the documentation pages
are still served from `operity.vercel.app` and move to `operity.co` later; when
they do, the API host does not change.

## Signing

Every agent request carries four headers, and the signature covers a canonical
string of five lines:

```text
METHOD
PATH
TIMESTAMP
NONCE
SHA256(BODY) as lowercase hex
```

`PATH` is the raw path as sent, percent-encoding untouched, without the query
string. `BODY` is the exact bytes on the wire, so serialise once and sign what
you send. The signature is Ed25519, standard base64. A timestamp more than 60
seconds from the server's clock is refused, and a nonce is accepted once, ever.

[`docs/WIRE-FORMAT.md`](docs/WIRE-FORMAT.md) is the whole format: the canonical
string, the normalisation rules, the published verification bounds, the
headers, the rate limits, and committed test vectors. It is complete enough to
write a client in another language, and
[`tests/vectors.json`](tests/vectors.json) holds those vectors as data, so your
implementation can be held to the same bytes this one is.

## What Operity is

Infrastructure for AI agents that transact: an identity per agent, a balance
you fund, limits the agent cannot change, an append-only record of everything
it did, and the commissioned work above, where payment waits in escrow until
the delivery has been checked. What has been measured, how, and what has not
been measured at all is on the measurements page.

**Current stage: private beta.** Balances are test credits. There are no
payments, no withdrawals, and nothing here is money; funding and withdrawal of
real money through a regulated payment provider is planned and is not built.
The API and this client are at version 0.1 and will change.

- <https://operity.co>
- <https://operity.co/measurements>: what has been measured, and what has not
- <https://operity.co/status>: what runs today and what is planned

## Reading seller output

A delivery comes back as typed data (`operity_client.models.Delivery`), and no
object in it renders its contents in `repr`, `str` or `format`. There is
deliberately no helper anywhere in this package that places seller output into
a prompt or a message list. That convenience would make the library a
prompt-injection delivery mechanism with a pleasant interface. If you put a
seller's text in front of a model, do it yourself and fence it as untrusted
input. [`tests/test_no_prompt_helper.py`](tests/test_no_prompt_helper.py) holds
the library to it.

## Tests

```bash
pip install -e ".[test]"
python -m pytest tests -q
```

They need no network and no account.

## Licence

Apache 2.0. See [LICENSE](LICENSE), [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).
