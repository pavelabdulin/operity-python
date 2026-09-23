"""Seller output is data, never instructions.

This library will not hand you a helper that places a seller's text into a
prompt or a message list. That convenience would make it a prompt-injection
delivery mechanism with a pleasant interface, so the absence is a property to
be held to rather than a habit to be trusted.

It is asserted by BEHAVIOUR, not by name. Every public class is built from
canary-bearing data, every zero-argument method, property and dunder of it is
INVOKED on a fresh object, every module-level function is invoked with those
objects, and every result is taken apart. A string carrying the canary fails
unless it is one the object was HANDED: an accessor may give you back what it
received, including a verifier's note that the server composed, and nothing may
build a new sentence out of it. An object of this package's own is held to more
than that, and must not render its contents at all.

Client methods are exercised through a transport that answers with a seller's
canary-bearing delivery and a verification note quoting it, which is how that
text really arrives.

The controls at the bottom are the reason any of it means anything. Each plants
a helper of a kind that has actually been proposed, in a copy of the package,
and requires the same scan to report it. A scan that has quietly stopped
walking anything fails there instead of passing everywhere.
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import httpx
import pytest

import operity_client

CANARY = "IGNORE-PREVIOUS-INSTRUCTIONS-canary-5e1f"
PACKAGE_DIR = Path(operity_client.__file__).parent

# Names that would be a composition helper if they existed. Checked as well as
# the behaviour, because a helper that is never invoked by the scan (it needs
# an API object, say) is still one a caller can find.
SUSPICIOUS = ("prompt", "message", "as_text", "to_text", "render", "describe",
              "summary", "summarise", "summarize", "format_for", "for_model")


def canary_wire(example):
    """An EXAMPLE dict from the models, with every "CANARY" marker replaced by
    a string that could only come from a seller."""
    if isinstance(example, dict):
        return {k: canary_wire(v) for k, v in example.items()}
    if isinstance(example, list):
        return [canary_wire(v) for v in example]
    if isinstance(example, str):
        return example.replace("CANARY", CANARY)
    return example


def leaves(value, depth=0):
    """Every string reachable inside a result, the result itself included."""
    if depth > 5:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items()
                for s in leaves(k, depth + 1) + leaves(v, depth + 1)]
    if isinstance(value, (list, tuple, set)):
        return [s for item in value for s in leaves(item, depth + 1)]
    if hasattr(value, "__dict__"):
        return [s for item in vars(value).values() for s in leaves(item, depth + 1)]
    return []


def renderings(value):
    """Every way a caller could turn a value into text without reaching into
    it for a field, which is what an accidental f-string in a prompt does."""
    out = [str(value), repr(value), format(value), f"{value}",
           "%s" % (value,)]  # noqa: UP031 - percent formatting is one of the ways under test
    try:
        out.append(json.dumps(value, default=str))
    except (TypeError, ValueError):
        pass
    return out


def composes(result, package_modules=(), received=frozenset()) -> bool:
    """Whether seller text was turned into NEW text.

    An accessor is allowed to hand you data. `to_wire()` giving back
    `{"value": <canary>}`, or a verifier's note that the SERVER composed and
    this library only carried, are both values the object RECEIVED, verbatim,
    and they are the whole point of a typed client. The defect is a string
    holding the canary that nobody handed in: this library built it.

    An object of this package's own is held to more than that: it must not
    render its contents at all, whatever a caller does to it, so that an
    accidental f-string in your prompt carries nothing a seller wrote."""
    if any(CANARY in leaf and leaf not in received for leaf in leaves(result)):
        return True
    return type(result).__module__ in package_modules \
        and any(CANARY in text for text in renderings(result))


def scan(package_dir: Path, module_name: str) -> list[str]:
    """Import every module of a package, build every public class from
    canary-bearing data, invoke everything invokable, and report each callable
    whose result RENDERS the canary. Returns offences, most useful first."""
    offences = []
    modules = []
    for path in sorted(package_dir.rglob("*.py")):
        if path.name.startswith("."):
            continue        # a macOS resource fork, not a module Python can import
        relative = path.relative_to(package_dir).with_suffix("")
        parts = [p for p in relative.parts if p != "__init__"]
        name = ".".join([module_name, *parts])
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:                                    # noqa: BLE001
            offences.append(f"{name}: does not import ({type(exc).__name__}: {exc})")
            continue
        modules.append((name, module))

    package_modules = {name for name, _ in modules}
    built, invoked = [], 0
    for name, module in modules:
        for attribute in sorted(vars(module)):
            if attribute.startswith("_"):
                continue
            obj = vars(module)[attribute]
            if getattr(obj, "__module__", None) != name:
                continue                                            # imported, not defined here
            lowered = attribute.lower()
            if any(word in lowered for word in SUSPICIOUS):
                offences.append(f"{name}.{attribute}: a public name that promises composition")
            if isinstance(obj, type) and hasattr(obj, "EXAMPLE") and hasattr(obj, "from_wire"):
                wire = canary_wire(obj.EXAMPLE)
                built.append((f"{name}.{attribute}", obj, wire, frozenset(leaves(wire))))

    assert built, f"{module_name}: the scan built nothing, so it asserted nothing"
    assert any(CANARY in leaf for _, _, _, r in built for leaf in r), (
        f"{module_name}: nothing the scan built carries the canary")

    for where, cls, wire, received in built:
        for attribute in sorted(dir(cls)):
            if attribute in ("EXAMPLE", "from_wire"):
                continue
            # A FRESH object per attribute: invoking `__init__()` on a shared
            # one resets its fields, and everything after it would then be
            # inspecting an empty object and finding nothing. The scan spent an
            # afternoon passing that way.
            instance = cls.from_wire(wire)
            member = getattr(cls, attribute, None)
            value = getattr(instance, attribute)
            if isinstance(member, property) or not callable(value):
                results = [value]                                   # a plain or computed attribute
            else:
                try:
                    results, invoked = [value()], invoked + 1       # zero-argument call
                except TypeError:
                    continue
            for result in results:
                if composes(result, package_modules, received):
                    offences.append(f"{where}.{attribute}: composes seller text: "
                                    f"{_first_composition(result, received)!r}")

    for name, module in modules:                                    # module-level helpers
        for attribute in sorted(vars(module)):
            obj = vars(module)[attribute]
            if attribute.startswith("_") or not callable(obj) or isinstance(obj, type):
                continue
            if getattr(obj, "__module__", None) != name:
                continue
            for _, cls, wire, received in built:
                try:
                    result = obj(cls.from_wire(wire))
                except Exception:            # noqa: BLE001,S112 - not every helper takes one
                    continue
                invoked += 1
                if composes(result, package_modules, received):
                    offences.append(f"{name}.{attribute}(): composes seller text: "
                                    f"{_first_composition(result, received)!r}")

    assert invoked, f"{module_name}: the scan invoked nothing, so it asserted nothing"
    return sorted(set(offences))


def _first_composition(result, received=frozenset()) -> str:
    return next((text[:90] for text in leaves(result)
                 if CANARY in text and text not in received),
                next((text[:90] for text in renderings(result) if CANARY in text), "?"))


# --------------------------------------------------------------------------
# The library itself.
# --------------------------------------------------------------------------

def test_nothing_in_the_package_composes_seller_output(tmp_path):
    copy = tmp_path / "operity_client"
    shutil.copytree(PACKAGE_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    assert scan(copy, "subject_clean") == []


def test_no_public_name_promises_a_prompt():
    for name in dir(operity_client):
        if not name.startswith("_"):
            assert not any(word in name.lower() for word in SUSPICIOUS), name


def test_a_delivery_does_not_render_its_contents():
    """The last line of defence: an accidental f-string in your own prompt
    carries nothing a seller wrote."""
    delivery = operity_client.models.Delivery.from_wire(
        canary_wire(operity_client.models.Delivery.EXAMPLE))
    for text in (str(delivery), repr(delivery), f"{delivery}",
                 "%s" % (delivery,)):  # noqa: UP031 - the renderings are the subject
        assert CANARY not in text, text
    # and the value is still reachable, deliberately, as data
    assert delivery.fields["ceo"].value == CANARY


def test_a_verifiers_note_is_reachable_but_never_rendered():
    """A verification note can quote what the seller delivered, so it is the
    same hazard as the delivery itself."""
    check = operity_client.models.Check.from_wire(
        canary_wire(operity_client.models.Check.EXAMPLE))
    assert CANARY not in str(check) and CANARY not in repr(check)
    assert CANARY in check.note


def test_seller_text_arriving_from_the_api_stays_data():
    """Through the client, over a transport that answers the way a real
    instance does when a seller has delivered."""
    job_id = "00000000-0000-4000-8000-0000000000b0"
    responses = {
        f"/v1/jobs/{job_id}/verification": {
            "job_id": job_id, "passed": False, "method": "extraction", "vacuous": False,
            "checks": [{"field": "ceo", "check": "schema", "passed": False,
                        "outcome": "failed", "note": f"'{CANARY}' is not of type 'number'"}]},
        f"/v1/jobs/{job_id}": {
            "id": job_id, "state": "verifying", "buyer_agent_id": job_id,
            "seller_agent_id": None, "price_uc": 1, "job_type": CANARY,
            "input": {"document": CANARY}, "output_schema": {}},
    }
    http = httpx.Client(base_url="https://operity.invalid", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=responses[request.url.path])))
    agent = operity_client.Agent("00000000-0000-4000-8000-00000000000a",
                                 operity_client.Keypair.generate(), http=http)

    verification = agent.verification(job_id)
    job = agent.get_job(job_id)
    for value in (verification, job):
        for text in (str(value), repr(value), f"{value}",
                     "%s" % (value,)):  # noqa: UP031 - the renderings are the subject
            assert CANARY not in text, text
    assert CANARY in verification.checks[0].note          # reachable as data
    assert job.input["document"] == CANARY


# --------------------------------------------------------------------------
# The controls. Each is a helper somebody could reasonably add.
# --------------------------------------------------------------------------

PLANTS = {
    "a method on Delivery": (
        "models.py",
        ('\n\ndef _summary(self):\n'
         '    return " ".join(f"{n}: {f.value}" for n, f in self.fields.items())\n'
         'Delivery.brief = _summary\n')),
    "a module-level helper": (
        "models.py",
        ('\n\ndef into_context(delivery):\n'
         '    values = getattr(delivery, "fields", {})\n'
         '    return "Seller said: " + " ".join(str(f.value) for f in values.values())\n')),
    # Note what this one has to do to be a control: joining a single note would
    # return that note unchanged, which is an accessor handing back a value it
    # received, and the scan is right to allow it. Composition is the field
    # name and the note becoming one new sentence.
    "a helper that joins a verification note": (
        "models.py",
        ('\n\ndef explain(verification):\n'
         '    return "; ".join(f"{c.field}: {c.note}"\n'
         '                     for c in getattr(verification, "checks", []))\n')),
    "a submodule for a package that is not installed": (
        "integrations.py",
        "import vendor_sdk_not_installed  # noqa: F401\n"),
}


@pytest.mark.parametrize("what", sorted(PLANTS))
def test_the_scan_catches_each_planted_helper(tmp_path, what):
    where, source = PLANTS[what]
    copy = tmp_path / "operity_client"
    shutil.copytree(PACKAGE_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    target = copy / where
    target.write_text(target.read_text() + source if target.exists() else source)

    offences = scan(copy, f"subject_{abs(hash(what))}")
    assert offences, f"the scan did not report {what}"
    print(f"{what}: {offences}")


def test_the_planted_helpers_are_each_a_different_defect():
    """Four controls that all fire on the same rule would be one control."""
    assert len({source for _, source in PLANTS.values()}) == len(PLANTS)
