from rest_framework.pagination import CursorPagination


# Cursor pagination keeps deep pages as cheap as the first one and can't be pushed into a
# full table scan with ?page=999999.
class DefaultPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-id"
