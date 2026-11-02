from django.db import models, transaction


def lock_rows[M: models.Model](queryset: models.QuerySet[M]) -> list[M]:
    """Lock the rows of `queryset` for the rest of the current transaction.

    Rows are always locked in primary-key order. Two transactions that lock the same rows in
    different orders deadlock; one global order makes that impossible.
    """
    if not transaction.get_connection(queryset.db).in_atomic_block:
        raise RuntimeError("lock_rows() must run inside transaction.atomic()")
    return list(queryset.select_for_update().order_by("pk"))
