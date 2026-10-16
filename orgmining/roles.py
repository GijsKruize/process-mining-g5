"""Grouping resources into organisational roles (part of step 1).

With ``org:resource`` the BPI 2017 log has 134 users and 3,338 distinct
``activity_user`` labels: too fine for the Petri net and BIG in step 2, and
too fragmented for SUBDUE to find frequent patterns. Following the course
advice, users are therefore replaced by the *role* they play.

How pm4py discovers roles (Burattin, Sperduti & Veluscek, 2013)
---------------------------------------------------------------
1. Every activity starts as its own role, described by the multiset of
   resources that perform it ({User_3: 120, User_7: 15, ...}).
2. The two roles whose (normalised) resource multisets are most similar are
   merged, as long as their similarity is above a threshold (default 0.65).
3. Result: groups of activities, each with the resources that performed them.

How we assign one role to every resource
----------------------------------------
A resource usually appears in several of these roles. Labelling an event with
"the role its activity belongs to" would add nothing, because that role
follows from the activity alone. Instead every resource gets its *dominant
role*: the role in which it performs most of its events. The label
``activity_role`` then tells which kind of worker did the activity, including
the informative cases where someone works outside their usual role.
"""
from collections import Counter

import pandas as pd
from pm4py.algo.organizational_mining.roles import algorithm as role_discovery
from pm4py.algo.organizational_mining.roles.variants.pandas import Parameters as RoleParameters

from . import config

DEFAULT_ROLES_THRESHOLD = 0.65  # pm4py's default, as in Burattin et al. (2013)
ROLE_NAME_PREFIX = "Role"


class ResourceRoleGrouper:
    """Maps every value of a resource attribute to one discovered role.

    Usage::

        grouper = ResourceRoleGrouper(threshold=0.65).fit(event_log, "org:resource")
        grouper.mapping          # {"User_1": "Role_3", ...}
        grouper.roles_table()    # one row per role
        grouper.resources_table()# one row per resource
    """

    def __init__(self, threshold=DEFAULT_ROLES_THRESHOLD):
        if not 0 < threshold < 1:
            raise ValueError("The roles threshold must be between 0 and 1.")
        self.threshold = threshold
        self.mapping = {}
        self._discovered_roles = []   # pm4py output: [[activities], {resource: events}]
        self._role_names = {}         # index in pm4py output -> "Role_k"
        self._dominant = {}           # resource -> (role index, events in that role)
        self._events_per_resource = Counter()

    def fit(self, event_log, attribute):
        """Discover the roles and assign every value of ``attribute`` to its dominant role."""
        frame = pd.DataFrame({
            "resource": event_log[attribute].fillna(config.MISSING_VALUE).astype(str),
            "activity": event_log[config.ACTIVITY_KEY].astype(str),
        })
        self._discovered_roles = role_discovery.apply(frame, parameters={
            RoleParameters.RESOURCE_KEY: "resource",
            RoleParameters.ACTIVITY_KEY: "activity",
            RoleParameters.ROLES_THRESHOLD_PARAMETER: self.threshold,
        })
        self._events_per_resource = Counter(frame["resource"])

        # Dominant role = the role with most events of that resource. On a tie
        # the role listed first by pm4py (alphabetical by activities) wins, so
        # the result is the same on every run.
        self._dominant = {}
        for role_index, (_, resource_counts) in enumerate(self._discovered_roles):
            for resource, events in resource_counts.items():
                if resource not in self._dominant or events > self._dominant[resource][1]:
                    self._dominant[resource] = (role_index, events)

        self._name_roles()
        self.mapping = {resource: self._role_names[role_index]
                        for resource, (role_index, _) in self._dominant.items()}
        return self

    def _name_roles(self):
        """Name the roles that are somebody's dominant role: Role_1 has the most events."""
        events_per_role = Counter()
        for resource, (role_index, _) in self._dominant.items():
            events_per_role[role_index] += self._events_per_resource[resource]
        ranked = sorted(events_per_role, key=lambda index: (-events_per_role[index], index))
        self._role_names = {index: f"{ROLE_NAME_PREFIX}_{rank}"
                            for rank, index in enumerate(ranked, start=1)}

    @property
    def n_roles(self):
        return len(self._role_names)

    def roles_table(self):
        """One row per discovered role; roles nobody has as dominant role have no name."""
        resources_assigned = Counter(self.mapping.values())
        events_assigned = Counter()
        for resource, role in self.mapping.items():
            events_assigned[role] += self._events_per_resource[resource]

        rows = []
        for index, (activities, resource_counts) in enumerate(self._discovered_roles):
            name = self._role_names.get(index, "")
            rows.append({
                "role": name,
                "resources_assigned": resources_assigned.get(name, 0),
                "events_of_assigned_resources": events_assigned.get(name, 0),
                "n_activities": len(activities),
                "activities": " | ".join(activities),
                "resources_performing_these_activities": len(resource_counts),
            })
        table = pd.DataFrame(rows)
        table["_unnamed"] = table["role"] == ""
        return (table.sort_values(["_unnamed", "events_of_assigned_resources"],
                                  ascending=[True, False])
                .drop(columns="_unnamed").reset_index(drop=True))

    def resources_table(self):
        """One row per resource: its role and how much of its work lies in that role."""
        rows = []
        for resource, role in self.mapping.items():
            total = self._events_per_resource[resource]
            in_role = self._dominant[resource][1]
            rows.append({
                "resource": resource,
                "role": role,
                "events": total,
                "events_in_role_activities": in_role,
                "share_in_role_pct": round(100 * in_role / total, 1),
            })
        return (pd.DataFrame(rows)
                .sort_values(["role", "events", "resource"], ascending=[True, False, True])
                .reset_index(drop=True))
