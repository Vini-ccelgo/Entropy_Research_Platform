"""Read-only projections for the Investigation Workspace."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

class WorkspaceQuery:
    def __init__(self,database:Path)->None:
        self.connection=sqlite3.connect(database); self.connection.row_factory=sqlite3.Row
    def context(self)->dict:
        return {"questions":self._records("research_questions"),"hypotheses":self._records("hypotheses"),"experiments":self._records("experiment_revisions"),"analyses":self._records("analysis_specifications")}
    def evidence(self,experiment_id:str|None=None)->dict:
        sql="SELECT payload_json FROM trial_executions"+(" WHERE experiment_id=?" if experiment_id else "")
        rows=self.connection.execute(sql,(experiment_id,) if experiment_id else ()).fetchall()
        executions=[json.loads(r["payload_json"]) for r in rows]
        return {"executions":executions,"count":len(executions),"disclosure":"Read-only persisted evidence; descriptive results do not assert scientific conclusions. A deterministic entropy stream does not guarantee deterministic provider output; inspect each model capability snapshot."}
    def provenance(self,kind:str,identifier:str,revision:int|None=None)->dict|None:
        tables={"question":"research_questions","hypothesis":"hypotheses","experiment":"experiment_revisions","analysis":"analysis_specifications","entropy_source":"entropy_source_specifications","prompt":"prompt_revisions","prompt_set":"prompt_set_revisions"}
        table=tables.get(kind)
        if not table:return None
        query=f"SELECT payload_json,content_hash FROM {table} WHERE id=?"+(" AND revision=?" if revision else "")+" ORDER BY revision DESC LIMIT 1"
        row=self.connection.execute(query,(identifier,revision) if revision else (identifier,)).fetchone()
        return {"record":json.loads(row["payload_json"]),"content_hash":row["content_hash"]} if row else None
    def graph(self)->dict:
        nodes=[]; edges=[]
        for table,kind in (("research_questions","question"),("hypotheses","hypothesis"),("experiment_revisions","experiment"),("journal_entries","journal"),("claims","claim")):
            for item in self._records(table): nodes.append({"id":f"{kind}:{item['id']}:{item.get('revision',1)}","type":kind,"label":item.get("title") or item.get("name") or item.get("question") or item.get("statement") or kind})
        for row in self.connection.execute("SELECT payload_json FROM scientific_relations"):
            relation=json.loads(row["payload_json"]); s=relation["source"];t=relation["target"]
            edges.append({"source":f"{s['record_type']}:{s['record_id']}:{s['revision']}","target":f"{t['record_type']}:{t['record_id']}:{t['revision']}","type":relation["relation_type"]})
        # These edges are explicit references in immutable operational/evidence
        # records; no semantic relationship is inferred by the workspace.
        for row in self.connection.execute("SELECT payload_json FROM experiment_runs"):
            run=json.loads(row["payload_json"]); ref=run["experiment_revision"]
            run_id=f"run:{run['id']}"; nodes.append({"id":run_id,"type":"run","label":run["state"]})
            edges.append({"source":f"experiment:{ref['record_id']}:{ref['revision']}","target":run_id,"type":"executed_as"})
        for row in self.connection.execute("SELECT payload_json FROM trial_executions"):
            execution=json.loads(row["payload_json"]); execution_id=f"execution:{execution['id']}"
            nodes.append({"id":execution_id,"type":"trial_execution","label":execution["status"]})
            edges.append({"source":f"run:{execution['experiment_run_id']}","target":execution_id,"type":"produced"})
        for row in self.connection.execute("SELECT payload_json FROM analysis_runs"):
            analysis=json.loads(row["payload_json"]); analysis_id=f"analysis_run:{analysis['id']}"
            nodes.append({"id":analysis_id,"type":"analysis_run","label":analysis["status"]})
            for member in analysis["cohort"]["members"]:
                edges.append({"source":f"execution:{member['execution_id']}","target":analysis_id,"type":"included_in"})
        return {"nodes":nodes,"edges":edges}
    def journal(self)->list[dict]: return self._records("journal_entries")
    def artifacts(self,run_id:str)->list[dict]:
        row=self.connection.execute("SELECT payload_json FROM analysis_results WHERE run_id=? ORDER BY rowid DESC LIMIT 1",(run_id,)).fetchone()
        return json.loads(row["payload_json"]).get("artifacts",[]) if row else []
    def _records(self,table:str)->list[dict]: return [json.loads(r["payload_json"]) for r in self.connection.execute(f"SELECT payload_json FROM {table} ORDER BY rowid")]
