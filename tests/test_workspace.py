from dashboard.query import WorkspaceQuery
from database.sqlite_repository import SqliteRepository

def test_workspace_empty_read_models_are_consistent(tmp_path):
    SqliteRepository(tmp_path/'w.db').close()
    query=WorkspaceQuery(tmp_path/'w.db')
    assert query.evidence()['count']==0
    assert query.graph()=={'nodes':[],'edges':[]}
