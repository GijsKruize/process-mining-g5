"""Synthetic event logs with known organizational patterns, for the evaluation.

A real log has no ground truth: nobody knows which work practices it
"really" contains. As advised, we therefore generate a log in which we
*inject* known patterns, add noise, run the whole pipeline on it and measure
how many of the injected patterns come back (recall) and how many of the
discovered patterns are injected ones (precision).

The process (a simplified loan application, like BPI 2017) has four
departments, each with its own employees and activities:

    Intake      (3 employees)  Register, Check-completeness
    Offer       (6 employees)  Call-customer, Complete-application, Create-offer,
                               Send-offer, Notify-customer
    Validation  (4 employees)  Validate-documents, Check-fraud
    Decision    (3 employees)  Decide, Approve, Deny

Every case runs through:

    Register -> Check-completeness
      -> (60%) Call-customer -> Complete-application  |  (40%) Complete-application
      -> Create-offer -> Send-offer
      -> (70%) Validate-documents || Check-fraud (any order)  |  (30%) Validate-documents
      -> Decide -> (35%) Approve  |  (65%) Deny -> Notify-customer

The injected patterns (the gold standard, ``GOLD_PATTERNS``) are the work
practices this produces, two of them handovers between departments and one
with parallel work. Noise: with probability ``noise`` a case gets one random
disturbance: an event performed by an employee of another department, an
extra event, a missing event, or two neighbouring events swapped.
"""
import random
from datetime import datetime, timedelta

import pandas as pd

DEPARTMENTS = {"Intake": 3, "Offer": 6, "Validation": 4, "Decision": 3}

ACTIVITY_DEPARTMENT = {
    "Register": "Intake", "Check-completeness": "Intake",
    "Call-customer": "Offer", "Complete-application": "Offer", "Create-offer": "Offer",
    "Send-offer": "Offer", "Notify-customer": "Offer",
    "Validate-documents": "Validation", "Check-fraud": "Validation",
    "Decide": "Decision", "Approve": "Decision", "Deny": "Decision",
}

# Injected work practices, labelled <activity>_<department>.
GOLD_PATTERNS = [
    ("G1", "Intake registers and checks the application",
     "Register_Intake -> Check-completeness_Intake"),
    ("G2", "Handover intake -> offer team: call and complete",
     "Check-completeness_Intake -> Call-customer_Offer; Call-customer_Offer -> Complete-application_Offer"),
    ("G3", "Offer team creates and sends the offer",
     "Create-offer_Offer -> Send-offer_Offer"),
    ("G4", "Validation checks documents and fraud in parallel, then decision",
     "Send-offer_Offer -> Validate-documents_Validation; Send-offer_Offer -> Check-fraud_Validation; "
     "Validate-documents_Validation -> Decide_Decision; Check-fraud_Validation -> Decide_Decision"),
    ("G5", "Handover decision -> offer team after a denial",
     "Decide_Decision -> Deny_Decision; Deny_Decision -> Notify-customer_Offer"),
]

NOISE_TYPES = ("other_department", "insert", "delete", "swap")


def employees():
    """{employee: department}, e.g. {'Intake_1': 'Intake', ...}."""
    return {f"{department}_{number}": department
            for department, count in DEPARTMENTS.items() for number in range(1, count + 1)}


class SyntheticLogGenerator:
    """Generates the synthetic log described in the module docstring."""

    def __init__(self, n_cases=500, noise=0.0, seed=42):
        if not 0 <= noise <= 1:
            raise ValueError("noise must be between 0 and 1")
        self.n_cases = n_cases
        self.noise = noise
        self.rng = random.Random(seed)
        self.staff = {}
        for employee, department in employees().items():
            self.staff.setdefault(department, []).append(employee)

    def employee_for(self, activity):
        return self.rng.choice(self.staff[ACTIVITY_DEPARTMENT[activity]])

    def activities_of_case(self):
        """The activity sequence of one case, following the process."""
        rng = self.rng
        activities = ["Register", "Check-completeness"]
        activities += ["Call-customer", "Complete-application"] if rng.random() < 0.6 \
            else ["Complete-application"]
        activities += ["Create-offer", "Send-offer"]
        if rng.random() < 0.7:
            parallel = ["Validate-documents", "Check-fraud"]
            rng.shuffle(parallel)           # parallel work: recorded in any order
            activities += parallel
        else:
            activities += ["Validate-documents"]
        activities += ["Decide"]
        activities += ["Approve"] if rng.random() < 0.35 else ["Deny", "Notify-customer"]
        return activities

    def add_noise(self, events):
        """Apply one random disturbance to a case: (activity, employee) pairs."""
        kind = self.rng.choice(NOISE_TYPES)
        position = self.rng.randrange(len(events))
        if kind == "other_department":
            activity, _ = events[position]
            others = [d for d in DEPARTMENTS if d != ACTIVITY_DEPARTMENT[activity]]
            events[position] = (activity, self.rng.choice(self.staff[self.rng.choice(others)]))
        elif kind == "insert":
            activity = self.rng.choice(sorted(ACTIVITY_DEPARTMENT))
            events.insert(position, (activity, self.employee_for(activity)))
        elif kind == "delete" and len(events) > 2:
            del events[position]
        elif kind == "swap" and position + 1 < len(events):
            events[position], events[position + 1] = events[position + 1], events[position]
        return events, kind

    def generate(self):
        """Return (event DataFrame, case table with the noise applied to each case)."""
        rows, cases = [], []
        start = datetime(2026, 1, 1, 8, 0)
        for number in range(1, self.n_cases + 1):
            case_id = f"Case_{number:04d}"
            events = [(a, self.employee_for(a)) for a in self.activities_of_case()]
            kind = None
            if self.rng.random() < self.noise:
                events, kind = self.add_noise(events)
            cases.append({"case_id": case_id, "noise": kind or ""})
            timestamp = start + timedelta(hours=number)
            for activity, employee in events:
                timestamp += timedelta(minutes=self.rng.randint(5, 120))
                rows.append({"case:concept:name": case_id, "concept:name": activity,
                             "org:resource": employee, "lifecycle:transition": "complete",
                             "time:timestamp": pd.Timestamp(timestamp, tz="UTC")})
        return pd.DataFrame(rows), pd.DataFrame(cases)


def gold_standard_table():
    """The injected patterns as a gold standard table (department labels)."""
    return pd.DataFrame(GOLD_PATTERNS, columns=["id", "name", "edges"])


def translate_gold(gold_table, department_to_role):
    """Replace department names in the gold labels by the discovered role names."""
    def translate(label):
        activity, department = label.rsplit("_", 1)
        return f"{activity}_{department_to_role.get(department, department)}"

    def translate_edges(text):
        return "; ".join(" -> ".join(translate(label.strip()) for label in edge.split("->"))
                         for edge in text.split(";"))
    table = gold_table.copy()
    table["edges"] = table["edges"].map(translate_edges)
    return table


def match_roles_to_departments(resource_roles):
    """Map every department to the discovered role most of its employees got.

    ``resource_roles``: step 1's resource_roles.csv (columns resource, role).
    Returns ({department: role}, purity), where purity is the share of
    employees whose role is the one of their department.
    """
    truth = employees()
    table = resource_roles.assign(department=resource_roles["resource"].map(truth)).dropna()
    mapping = (table.groupby("department")["role"]
               .agg(lambda roles: roles.value_counts().index[0]).to_dict())
    purity = (table["role"] == table["department"].map(mapping)).mean()
    return mapping, float(purity)

