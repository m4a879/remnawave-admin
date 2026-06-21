"""Admin account table schema — re-exports from shared constants.

All inline-SQL functions that touch the admin_accounts table should
reference these constants instead of hardcoding column names.
"""

from shared.db_schema import (  # noqa: F401
    ADMIN_TABLE,
    ADMIN_COLUMNS,
    ADMIN_COLUMNS_SET,
    ADMIN_INSERT_COLUMNS,
    ADMIN_UPDATE_COLUMNS,
    ADMIN_UPDATE_COLUMNS_SET,
    ADMIN_COUNTER_COLUMNS,
    ADMIN_ROLES_TABLE,
    AUDIT_TABLE,
    ADMIN_DEVICES_TABLE,
    ADMIN_ACCESS_POLICIES_TABLE,
)
from shared.db_query import (  # noqa: F401
    select_sql,
    insert_sql,
    update_sql,
    delete_sql,
)