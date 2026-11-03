"""Durable native setup workflow, with explicit per-generation approval."""
import json
from pathlib import Path
import re
import sqlite3
import threading
import traceback

from .exchange import canonical_json
from .native_coordinator import digest, now
from .native_errors import TransportUnavailable


class GenerationPending(Exception):
    def __init__(self, packet):
        self.packet = packet


class ReplayClient:
    model = 'gpt-6.1-sol'

    def __init__(self, calls, kind='ontology'):
        self.calls, self.kind, self.index = calls, kind, 0

    def chat_json(self, messages, **kwargs):
        packet = {'schema_version':1, 'kind':kwargs.get('purpose', self.kind), 'messages':messages}
        packet['request_sha256'] = digest(packet)
        index = self.index
        self.index += 1
        if index == len(self.calls):
            raise GenerationPending(packet)
        call = self.calls[index]
        if call['packet'] != packet or call.get('status') != 'succeeded':
            raise ValueError('Generation input or verified result changed')
        return call['response']['result']


class SetupCoordinator:
    def __init__(self, root, engine, compute):
        self.root, self.engine, self.compute = Path(root), engine, compute
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'setup.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, resource TEXT UNIQUE, body TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.database, timeout=10)

    def get(self, workflow_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM workflows WHERE id=?', (workflow_id,)).fetchone()
        if row is None:
            raise KeyError('Setup not found')
        return json.loads(row[0])

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM workflows ORDER BY rowid DESC')]

    def for_resource(self, resource):
        return next((w for w in self.list() if w['resource']==resource), None)

    def start(self, request_id, kind, resource, inputs):
        if (not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id)
                or kind not in ('ontology','simulation') or not re.fullmatch(r'(proj|sim)_[a-f0-9]{6,32}', resource)):
            raise ValueError('Invalid setup identity')
        encoded = canonical_json(inputs)
        if not isinstance(inputs, dict) or len(encoded.encode()) > 2097152:
            raise ValueError('Setup inputs exceed 2 MiB')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM workflows WHERE id=? OR resource=?', (request_id, resource)).fetchone()
            if row:
                saved = json.loads(row[0])
                if saved['kind'] != kind or saved['inputs'] != inputs or saved['resource'] != resource:
                    raise ValueError('Setup input changed; preserve the existing workflow')
                return saved
            for row in db.execute('SELECT body FROM workflows'):
                existing = json.loads(row[0])
                if existing['status'] not in ('completed','failed') or (existing.get('error') or {}).get('retryable'):
                    raise ValueError('Finish or reconcile the active setup first')
            workflow = {'id':request_id, 'resource':resource, 'kind':kind, 'inputs':inputs,
                'input_sha256':digest(inputs), 'source_fingerprint':self.compute.fingerprint(),
                'status':'generating', 'version':1, 'calls':[], 'result':None, 'error':None,
                'events':[{'at':now(), 'message':'Setup inputs saved; no jobs admitted'}]}
            db.execute('INSERT INTO workflows VALUES (?,?,?)', (request_id, resource, canonical_json(workflow)))
            return workflow

    def advance(self, workflow_id):
        with self.lock:
            w = self.get(workflow_id)
            if w['status'] in ('completed','failed','awaiting_approval'):
                return w
            try:
                return self._advance(w)
            except Exception as error:
                with (self.root / 'diagnostics.log').open('a') as log:
                    log.write(f"{now()} setup={w['id']} state={w['status']}\n{traceback.format_exc()}\n")
                w['error'] = {'code':'transport_unavailable' if isinstance(error, TransportUnavailable) else 'setup_failed',
                    'message':'Connection interrupted; reconcile the existing job.' if isinstance(error, TransportUnavailable) else
                    'Setup failed. Saved inputs and native evidence are preserved for inspection.',
                    'resume_status':w['status'], 'retryable':isinstance(error, TransportUnavailable)}
                w['status'] = 'failed'
                return self.save(w, w['error']['message'])

    def save(self, w, message):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            stored = json.loads(db.execute('SELECT body FROM workflows WHERE id=?', (w['id'],)).fetchone()[0])
            if stored['version'] != w['version']:
                raise ValueError('Setup changed; reload its current state')
            w['version'] += 1
            w['events'].append({'at':now(), 'message':message})
            db.execute('UPDATE workflows SET body=? WHERE id=?', (canonical_json(w),w['id']))
        return w

    def review(self, workflow_id):
        w = self.get(workflow_id)
        if not w['calls'] or not w['calls'][-1].get('review'):
            raise ValueError('No review ready')
        call = w['calls'][-1]
        return {'sha256':call['review_hash'], 'review':call['review']}

    def approve(self, workflow_id, review_hash):
        with self.lock:
            w = self.get(workflow_id)
            if not w['calls'] or not review_hash or w['calls'][-1].get('review_hash') != review_hash:
                raise ValueError('Exact current review required')
            call = w['calls'][-1]
            if call.get('approved_hash') == review_hash:
                return w
            if w['status'] != 'awaiting_approval' or self.compute.fingerprint() != w['source_fingerprint']:
                raise ValueError('Setup source or state changed')
            call.update(approved_hash=review_hash, approved_at=now())
            w['status'] = 'queued'
            return self.save(w, 'Exact generation review approved')

    def _advance(self, w):
        if self.compute.fingerprint() != w['source_fingerprint'] or digest(w['inputs']) != w['input_sha256']:
            raise ValueError('Setup source or inputs changed')
        if w['status'] == 'generating':
            client = ReplayClient(w['calls'])
            try:
                w['result'] = self.engine.generate(w['kind'], w['inputs'], client)
                if client.index != len(w['calls']):
                    raise ValueError('Saved generations were not consumed')
                w['status'] = 'applying'
                return self.save(w, 'All setup generation results verified')
            except GenerationPending as pending:
                if len(w['calls']) >= 64:
                    raise ValueError('Setup exceeds 64 reviewed generations')
                w['calls'].append({'packet':pending.packet, 'status':'unprepared'})
                w['status'] = 'preparing'
                return self.save(w, f"Preparing {pending.packet['kind']} review")
        if w['status'] == 'preparing':
            call = w['calls'][-1]
            task_id = f"mfs-{w['id']}-{len(w['calls']):03}"
            call['record'] = self.compute.prepare(task_id, call['packet']['kind'], call['packet'], w['source_fingerprint'])
            call['status'] = 'prepared'
            call['review'] = {'workflow_id':w['id'], 'resource':w['resource'], 'kind':call['packet']['kind'],
                'step':len(w['calls']), 'source_fingerprint':w['source_fingerprint'], 'task':call['record']}
            call['review_hash'] = digest(call['review'])
            w['status'] = 'awaiting_approval'
            return self.save(w, 'Inactive native task ready for review; no job admitted')
        if w['status'] in ('queued','running'):
            call = w['calls'][-1]
            if call.get('approved_hash') != digest(call['review']):
                raise ValueError('Generation lacks exact approval')
            self.compute.verify([call['record']])
            observed = self.compute.inspect(call['record'])
            if observed['status'] == 'prepared':
                # Reuse the same key after ambiguous admission or process loss.
                self.compute.admit(call['record'])
                observed = {'status':'queued'}
            if observed['status'] == 'failed':
                call.update(observed)
                raise ValueError('Native generation failed; no automatic new attempt')
            if w['status']=='running' and all(call.get(key)==value for key,value in observed.items()):
                return w
            call.update(observed)
            w['status'] = 'generating' if observed['status']=='succeeded' else 'running'
            return self.save(w, f"{call['packet']['kind']}: {observed['status']}")
        if w['status'] == 'applying':
            self.engine.apply(w)
            w['status'] = 'completed'
            return self.save(w, 'Verified setup saved to the application')
        raise ValueError('Unknown setup state')

    def reconcile(self, workflow_id, version):
        with self.lock:
            w = self.get(workflow_id)
            if type(version) is not int:
                raise ValueError('Expected failed setup version')
            if version in w.get('reconciled_versions', []):
                return w
            if w['version'] != version or w['status'] != 'failed' or not w['error']['retryable']:
                raise ValueError('Setup cannot be reconciled automatically')
            w['status'], w['error'] = w['error']['resume_status'], None
            w.setdefault('reconciled_versions', []).append(version)
            return self.save(w, 'Reconciling the existing native task and admission key')
