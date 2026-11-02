"""The permission matrix: which actions exist on which module.

Roles store a subset of this as {"module": ["action", ...]}. Modules that aren't built yet are
listed so roles can be set up once and keep working as the modules arrive.
"""

ACTIONS = ("view", "create", "update", "delete", "post")

MODULES: dict[str, tuple[str, ...]] = {
    "members": ("view", "create", "update", "delete"),
    "roles": ("view", "create", "update", "delete"),
    "audit": ("view",),
    "accounting": ACTIONS,
    "inventory": ACTIONS,
    "purchasing": ACTIONS,
    "sales": ACTIONS,
    "pos": ACTIONS,
    "hr": ACTIONS,
    "payroll": ACTIONS,
    "reports": ("view",),
}

FULL_ACCESS = {module: list(actions) for module, actions in MODULES.items()}
READ_ONLY = {module: ["view"] for module in MODULES}


def clean_permissions(raw: object) -> dict[str, list[str]]:
    """Return the permissions in canonical form, or raise ValueError naming the bad entry."""
    if not isinstance(raw, dict):
        raise ValueError("permissions must be an object of module to actions")
    cleaned: dict[str, list[str]] = {}
    for module, actions in raw.items():
        allowed = MODULES.get(module)
        if allowed is None:
            raise ValueError(f"unknown module: {module}")
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            raise ValueError(f"actions for {module} must be a list of strings")
        unknown = set(actions) - set(allowed)
        if unknown:
            raise ValueError(f"unknown actions for {module}: {', '.join(sorted(unknown))}")
        if actions:
            cleaned[module] = [action for action in allowed if action in actions]
    return cleaned
