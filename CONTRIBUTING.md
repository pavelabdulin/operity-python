# Contributing

Thank you for looking. Two things are worth knowing before you spend time on a
change.

## Where this code lives

`operity_client/` and `docs/WIRE-FORMAT.md` are published from Operity's
private service repository, which is their source of truth. A manifest there
records the SHA-256 of every published file and the commit it was published at,
and an invariant test in that repository's suite fails, naming the file,
whenever one of them differs from the manifest. That is how the two stay in
step: the service cannot change the signing format without turning its own
suite red until this repository is republished.

The practical consequence for you: a pull request that edits those files cannot
be merged here as a commit. It is read, applied upstream, and comes back in the
next publication, with attribution. Everything else in this repository, the
README, the examples and the tests, is edited here directly.

## What is most useful

- **A client in another language.** `docs/WIRE-FORMAT.md` is meant to be
  sufficient on its own, and `tests/vectors.json` is the same data the Python
  client and the server are both held to. If anything in that document was not
  enough to write your client from, that is a defect in the document and worth
  an issue, even if you worked it out.
- **A vector that disagrees.** If your implementation produces a different
  signature for one of the committed vectors, one of us is wrong and it is
  worth finding out which.
- **Anything in the examples that does not run.**

## Tests

```bash
pip install -e ".[test]"
python -m pytest tests -q
```

No network, no account, no database. `tests/test_wire_format.py` holds the
client to the committed vectors, on the bytes it puts on the wire, not on a
canonical string handed to it. `tests/test_no_prompt_helper.py` holds it to
having no helper that places seller output into a prompt, and carries planted
controls so that a scan which has stopped working fails rather than passes.

## Style

Match the file you are editing. Comments explain why a thing is the way it is,
not what the line does.

## Licence

By contributing you agree that your contribution is licensed under Apache 2.0,
the licence of this repository.
