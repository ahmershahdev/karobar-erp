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


def permission_problems(raw: object) -> list[str]:
    """Describe what is wrong with a permissions object; an empty list means it is valid."""
    if not isinstance(raw, dict):
        return ["permissions must be an object of module to actions"]
    problems: list[str] = []
    for module, actions in raw.items():
        allowed = MODULES.get(module)
        if allowed is None:
            problems.append(f"unknown module: {module}")
        elif not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            problems.append(f"actions for {module} must be a list of strings")
        elif unknown := set(actions) - set(allowed):
            problems.append(f"unknown actions for {module}: {', '.join(sorted(unknown))}")
    return problems


def clean_permissions(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Canonical form of permissions that passed permission_problems(): known order, no empties."""
    return {
        module: [action for action in allowed if action in raw[module]]
        for module, allowed in MODULES.items()
        if raw.get(module)
    }
