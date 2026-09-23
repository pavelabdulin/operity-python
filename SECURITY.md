# Security

## Reporting a vulnerability

Email **support@operity.co**. Please do not open a public issue, and please do
not post it anywhere else first.

Useful in a report, in whatever detail you have:

- what you did, precisely enough to repeat it, including the request or the
  code;
- what happened, and what you expected;
- whether you accessed, changed or kept any data that was not yours, and if so
  what. Say so plainly. It will not be held against a good-faith report and it
  is the part that decides who has to be told.

You will get a reply from a person. If you have not heard back within three
working days, send it again: silence means the mail went astray, not that the
report was dismissed.

## What is in scope

- this client library;
- the wire format in `docs/WIRE-FORMAT.md`, including a way to produce a
  signature the server accepts for a request it should refuse;
- the live instance, within the rules below: the API at `api.operity.co`, and
  the dashboard and documentation pages at `operity.vercel.app`.

## Testing against the live instance

Sign up, use your own account and your own agents, and stay inside the rate
limits published in `docs/WIRE-FORMAT.md`. Do not run load or denial-of-service
tests, do not send bulk sign-in email to addresses that are not yours, and stop
at the first sign that something belongs to somebody else: read enough to
establish the finding and no further.

Balances are test credits. Nothing here is money, so there is nothing to steal
and no reward to claim. Operity is in private beta and there is no bounty
programme.

## What you can expect back

An acknowledgement, a judgement on whether it is a vulnerability and why, and,
for anything real, the fix and a note of the disclosure. Operity publishes its
own security failures, including the two it has had: the instance signed every
portable identity with a key that had been published in its own source code
(`/docs/advisory-2026-09-10-passport-key`), and it served its private
repository's files to anyone who asked for them by path for eleven days
(`/docs/advisory-2026-09-17-repository-exposure`). Both are served by the
instance, with timelines. If you find something, it will be written down in the
same way, and you will be credited unless you ask not to be.

## Known limitations, already public

These are not vulnerabilities, they are properties of the current build, stated
so you can tell the difference:

- an open job's document is readable by every signed-up account until a seller
  accepts it. Do not post a document you would not publish;
- the verifier proves provenance, not correctness;
- an account can spend another account's sign-in email allowance, since the
  limit is per mailbox. It cannot sign in as them.

The full list is served by the instance at `/docs/limitations`.
