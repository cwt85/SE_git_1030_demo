"""Initial activity/registration schema, shared with the Adminer bootstrap SQL.

Keep sql/001_initial.sql immutable after this revision has been deployed.
"""
from pathlib import Path
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[2] / "sql" / "001_initial.sql").read_text(encoding="utf-8")
    # This frozen script contains plain DDL only, with no semicolons in literals.
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement and statement.upper() not in {"BEGIN", "COMMIT"}:
            op.execute(statement)


def downgrade():
    raise RuntimeError("初始版本降版會刪除活動及報名資料；請先備份並另行規劃，這裡不自動刪表。")
