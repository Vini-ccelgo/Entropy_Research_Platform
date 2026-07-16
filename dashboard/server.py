"""Dependency-free, read-only Investigation Workspace HTTP server."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from dashboard.query import WorkspaceQuery

PAGE='''<!doctype html><title>Investigation Workspace</title><style>body{margin:0;background:#101318;color:#dce5ef;font:14px system-ui}header{padding:14px;background:#171d26;position:sticky;top:0}select{margin:4px;background:#26303c;color:white}main{display:grid;grid-template-columns:2fr 1fr;gap:10px;padding:10px}.panel{background:#171d26;padding:12px;border:1px solid #2b3948}pre{white-space:pre-wrap;max-height:380px;overflow:auto}.wide{grid-column:1/-1}</style><header><b>Investigation Workspace</b> · Research Context <select id=e></select><select id=h></select><select id=x></select></header><main><section class="panel"><h3>Evidence View</h3><pre id=evidence></pre></section><section class="panel"><h3>Provenance Inspector</h3><pre id=prov>Select a context object.</pre></section><section class="panel"><h3>Relationship Graph</h3><pre id=graph></pre></section><section class="panel"><h3>Research Journal</h3><pre id=journal></pre></section><section class="panel wide"><h3>Disclosures</h3>Every view is read-only and derived solely from persisted evidence, artifacts, and immutable scientific records.</section></main><script>async function j(x){return(await fetch(x)).json()} async function load(){let c=await j('/api/context');for(let[k,id]of [['experiments','x'],['hypotheses','h'],['questions','e']]){let s=document.getElementById(id);c[k].forEach(v=>s.add(new Option(v.name||v.title||v.question||v.id,v.id)))}document.getElementById('evidence').textContent=JSON.stringify(await j('/api/evidence'),null,2);document.getElementById('graph').textContent=JSON.stringify(await j('/api/graph'),null,2);document.getElementById('journal').textContent=JSON.stringify(await j('/api/journal'),null,2)}load()</script>'''
def serve(database:Path,port:int=8080)->None:
    query=WorkspaceQuery(database)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urlparse(self.path); params=parse_qs(path.query)
            if path.path=='/': body=PAGE.encode(); typ='text/html'
            elif path.path=='/api/context': body=json.dumps(query.context()).encode();typ='application/json'
            elif path.path=='/api/evidence': body=json.dumps(query.evidence(params.get('experiment',[None])[0])).encode();typ='application/json'
            elif path.path=='/api/graph': body=json.dumps(query.graph()).encode();typ='application/json'
            elif path.path=='/api/journal': body=json.dumps(query.journal()).encode();typ='application/json'
            elif path.path=='/api/provenance': body=json.dumps(query.provenance(params.get('kind',[''])[0],params.get('id',[''])[0],int(params['revision'][0]) if 'revision' in params else None)).encode();typ='application/json'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    ThreadingHTTPServer(('',port),Handler).serve_forever()
