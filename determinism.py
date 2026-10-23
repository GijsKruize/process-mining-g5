"""Reproducibility helpers: make two runs of the pipeline give the same output.

Why this module exists
----------------------
Step 2 aligns every trace with the Petri net. For a trace that does not fit
the net there is usually more than one optimal alignment (for example, when an
activity occurs twice and one occurrence has to be treated as an insertion,
either occurrence gives the same cost). Which one pm4py returns depends on the
order in which Python iterates over *sets* of Petri net objects, and in
pm4py 2.2.16 that order is not stable between runs for two reasons:

1. Places, transitions and arcs are hashed by ``id(self)``, i.e. by their
   memory address, which changes from run to run.
2. Sets of strings (activity labels) are ordered by the string hash, which
   Python randomises per process unless ``PYTHONHASHSEED`` is fixed.

We measured the effect on the BPI 2017 log with the course-provided Petri
net: running the unmodified code twice gave identical instance graphs for
only about 40% of the traces. The assignment grades reproducibility, and BIG's
repair step (Algorithm 1 in Diamantini et al., 2016) builds different edges
for different alignments, so this has to be fixed rather than documented.

What this module does
---------------------
* ``ensure_fixed_hash_seed`` restarts the script with ``PYTHONHASHSEED=0`` so
  that string hashing is the same in every run (the variable must be set
  before the interpreter starts, which is why a restart is needed).
* ``install`` replaces the address-based hash of pm4py's Petri net objects by
  a counter that is assigned the first time an object is hashed. The order in
  which objects are first hashed is a property of the program, not of the
  memory layout, so set iteration becomes repeatable. Equality is untouched
  (still identity), so pm4py behaves exactly as before; only the tie-breaking
  order is pinned down.
* ``reset_counter`` restarts the counter. Set iteration order depends on the
  absolute hash values, so the counter is reset to the same value before each
  Petri net is loaded and before each alignment. This makes the alignment of a
  trace independent of which traces were aligned before it, which in turn
  makes the serial and the multi-process code paths give identical results.
* ``canonical_transition_names`` gives labelled transitions a name derived
  from their label. pm4py names them with a random UUID, and the alignment
  code sorts transitions by name, so random names are a third source of
  run-to-run differences.

None of this changes which alignments are *optimal*; it only makes the choice
among equally good alignments repeatable.
"""
import os
import subprocess
import sys

from pm4py.objects.petri_net.obj import PetriNet

HASH_SEED = "0"

# Hash values handed out to the objects of the Petri net itself start at
# NET_BASE; objects created while aligning one trace (the trace net and the
# synchronous product net) start at ALIGNMENT_BASE. The two ranges only need to
# be fixed, not disjoint: equal hashes of different objects are harmless
# because equality is still identity.
NET_BASE = 0
ALIGNMENT_BASE = 1_000_000

_next_hash = [NET_BASE]
_HASH_ATTRIBUTE = "_deterministic_hash"


def ensure_fixed_hash_seed():
    """Restart the running script with ``PYTHONHASHSEED=0`` unless already set.

    Call this first thing in a ``main()`` function. A subprocess is used
    instead of ``os.execv`` because the latter does not behave like a real
    exec on Windows. Standard input/output are inherited, so the interactive
    attribute prompt of step 1 keeps working.
    """
    if os.environ.get("PYTHONHASHSEED") == HASH_SEED:
        return
    environment = dict(os.environ, PYTHONHASHSEED=HASH_SEED)
    sys.exit(subprocess.call([sys.executable] + sys.argv, env=environment))


def _deterministic_hash(self):
    """Hash for Petri net objects: a counter value assigned on first use."""
    attributes = self.__dict__
    value = attributes.get(_HASH_ATTRIBUTE)
    if value is None:
        value = _next_hash[0]
        _next_hash[0] += 1
        attributes[_HASH_ATTRIBUTE] = value
    return value


def install():
    """Replace the address-based hashes of pm4py's Petri net objects.

    Must run before any Petri net object is created, which is why it is
    called when this module is imported (see the bottom of the file) and why
    the other pipeline modules import this module before they use pm4py's
    Petri net classes.
    """
    for petri_class in (PetriNet.Place, PetriNet.Transition, PetriNet.Arc):
        petri_class.__hash__ = _deterministic_hash


def reset_counter(start=NET_BASE):
    """Restart the hash counter at a fixed value (see module docstring)."""
    _next_hash[0] = start


def canonical_transition_names(net):
    """Rename labelled transitions to ``t_<label>`` (numbered if a label repeats).

    Silent transitions and places already get counter-based names from pm4py
    (``skip_3``, ``p_7`` ...), which are repeatable once the hash seed is
    fixed, so they are left alone.
    """
    labelled = sorted(
        (transition for transition in net.transitions if transition.label is not None),
        key=lambda transition: str(transition.label),
    )
    seen = {}
    for transition in labelled:
        label = str(transition.label)
        seen[label] = seen.get(label, 0) + 1
        suffix = "" if seen[label] == 1 else f"#{seen[label]}"
        transition.name = f"t_{label}{suffix}"
    return net


install()
