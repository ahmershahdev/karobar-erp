from django.dispatch import Signal

# Sent inside the transaction that creates a business, with the business active, so receivers
# can set up their own data (a chart of accounts, a first fiscal year) atomically with it.
# Arguments: tenant, owner.
tenant_created = Signal()
