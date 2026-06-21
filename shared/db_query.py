"""Generic SQL command builders.

Provides reusable functions for building parameterized SQL queries
that work with any table. All SQL commands built by these functions
use $N placeholders compatible with asyncpg/psycopg parameter binding.
"""


def select_sql(
    table: str,
    columns: str = "*",
    suffix: str = "",
) -> str:
    """Build SELECT {columns} FROM {table}{suffix}.

    Args:
        table:   Table name
        columns: Column expression (default '*')
        suffix:  Everything after table name
                 (alias, JOIN, WHERE, ORDER BY, etc.)

    Returns:
        "SELECT {columns} FROM {table}{suffix}"
    """
    return f"SELECT {columns} FROM {table}" + (f" {suffix}" if suffix else "")


def insert_sql(
    table: str,
    columns: list,
    values: str = "",
    returning: str = "",
    suffix: str = "",
) -> str:
    """Build INSERT INTO {table} ({cols}) VALUES ({expr}){suffix}{returning}.

    Args:
        table:     Table name
        columns:   Column names for the INSERT
        values:    Custom VALUES expression (overrides auto $1..$N)
        returning: Optional RETURNING clause (e.g. "*")
        suffix:    Optional suffix (e.g. ON CONFLICT ... DO UPDATE ...)

    Returns:
        "INSERT INTO {table} ({cols}) VALUES ({expr}){suffix} RETURNING {returning}"
    """
    cols = ", ".join(columns)
    expr = values or ", ".join(f"${i+1}" for i in range(len(columns)))
    ret = f" RETURNING {returning}" if returning else ""
    tail = f" {suffix}" if suffix else ""
    return f"INSERT INTO {table} ({cols}) VALUES ({expr}){tail}{ret}"


def update_sql(
    table: str,
    assignments: str,
    where: str,
    returning: str = "",
) -> str:
    """Build UPDATE {table} SET {assignments} WHERE {where}{returning}.

    Args:
        table:       Table name
        assignments: SET clause content (e.g. "col = $1, col2 = $2")
        where:       WHERE clause content (e.g. "id = $3")
        returning:   Optional RETURNING clause (e.g. "*")

    Returns:
        "UPDATE {table} SET {assignments} WHERE {where} RETURNING {returning}"
    """
    ret = f" RETURNING {returning}" if returning else ""
    return f"UPDATE {table} SET {assignments} WHERE {where}{ret}"


def delete_sql(
    table: str,
    where: str,
) -> str:
    """Build DELETE FROM {table} WHERE {where}.

    Args:
        table: Table name
        where: WHERE clause content (e.g. "id = $1")

    Returns:
        "DELETE FROM {table} WHERE {where}"
    """
    return f"DELETE FROM {table} WHERE {where}"


# ── JOIN builders ────────────────────────────────────────────────


def left_join_sql(
    table: str,
    alias: str,
    on: str,
) -> str:
    """Build LEFT JOIN {table} {alias} ON {on}.

    Args:
        table: Table name to join
        alias: Table alias
        on:    ON condition (e.g. "r.id = a.role_id")

    Returns:
        "LEFT JOIN {table} {alias} ON {on}"
    """
    return f"LEFT JOIN {table} {alias} ON {on}"


def join_sql(
    table: str,
    alias: str,
    on: str,
    join_type: str = "LEFT",
) -> str:
    """Build {join_type} JOIN {table} {alias} ON {on}.

    Args:
        table:     Table name to join
        alias:     Table alias
        on:        ON condition (e.g. "r.id = a.role_id")
        join_type: Type of join (LEFT, RIGHT, INNER, FULL, etc.)

    Returns:
        "{join_type} JOIN {table} {alias} ON {on}"
    """
    return f"{join_type.upper()} JOIN {table} {alias} ON {on}"
