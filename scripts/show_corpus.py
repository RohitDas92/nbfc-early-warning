"""What is actually in the policy index."""

from nbfc_ews.db.engine import connect

SQL = """
select doc_id, section, version, effective_from, effective_to
from policy_chunk
where effective_to is not null
order by doc_id, section
"""

conn = connect()
for row in conn.execute(SQL):
    print(row)