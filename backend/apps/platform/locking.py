from collections.abc import Callable
from functools import wraps

from django.db import OperationalError, models, transaction


def lock_rows[M: models.Model](queryset: models.QuerySet[M]) -> list[M]:
    """Lock the rows of `queryset` for the rest of the current transaction.

    Rows are always locked in primary-key order. Two transactions that lock the same rows in
    different orders deadlock; one global order makes that impossible.
    """
    if not transaction.get_connection(queryset.db).in_atomic_block:
        raise RuntimeError("lock_rows() must run inside transaction.atomic()")
    return list(queryset.select_for_update().order_by("pk"))


# MySQL error codes for "Deadlock found" and "Lock wait timeout exceeded".
RETRYABLE_LOCK_ERRORS = {1213, 1205}


def retry_on_deadlock[**P, R](call: Callable[P, R], attempts: int = 3) -> Callable[P, R]:
    """Run `call` again when InnoDB picks it as a deadlock victim.

    InnoDB rolls the whole transaction back in that case, so the safe response is to start over.
    Only the outermost transaction can do that: inside an outer atomic block the retry would run
    on a transaction that is already rolled back, so there the error is passed on unchanged.
    """

    @wraps(call)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for attempt in range(1, attempts + 1):
            try:
                return call(*args, **kwargs)
            except OperationalError as exc:
                code = exc.args[0] if exc.args else None
                if code not in RETRYABLE_LOCK_ERRORS or attempt == attempts:
                    raise
                if transaction.get_connection().in_atomic_block:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    return wrapper
