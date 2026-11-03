"""Browser smoke ONLY. No SSH, native runner or provider calls. Uses real OASIS.

Run from backend: python tests/native_ui_fixture.py /absolute/fresh/state/root
Proxy the frontend /api to port5002. The UI visibly says TEST TRANSPORT.
"""
import json
from pathlib import Path
import sys
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.agent_runners.native_coordinator import NativeCoordinator
from app.agent_runners.native_engine import OasisEngine


class FixtureCompute:
    identity = {"identity": "test-transport", "model": "fixture", "effort": "low"}

    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True)

    def fingerprint(self):
        return "browser-fixture-v1"

    def prepare(self, task_id, name, packet, source):
        return {"task_id": task_id, "name": name, "packet": packet, "profile": {"mode": "test only; no execution"},
            "instructions_text": "Synthetic UI smoke response for " + name, "task": {"id": task_id},
            "definition_sha256": "a" * 64, "target": {"host": {"name": "Test transport (no native jobs)"}}}

    def verify(self, records):
        pass

    def admit(self, record):
        (self.root / record['task_id']).write_text('queued')

    def inspect(self, record):
        path = self.root / record['task_id']
        if not path.exists():
            return {"status": "prepared"}
        if path.read_text() == 'queued':
            path.write_text('running')
            return {"status": "running", "job_id": record['task_id']}
        if record['task_id'].endswith('r1-bob-a1'):
            return {"status": "failed", "job_id": record['task_id']}
        name = record['name']
        number = 2 if '-r2-' in record['task_id'] else 1
        contents = {"alice": "The higher price exceeds my budget. I will compare alternatives.",
            "bob": "I rely on it daily for work and can afford $30, but I want an explanation.",
            "casey": "Our team needs clearer pricing and export options before deciding."}
        content = contents[name] if number == 1 else f"After reading the shared feed, {name.title()} wants clear pricing and easy export before the next increase."
        return {"status": "succeeded", "job_id": record['task_id'], "response": {
            "schema_version": 1, "request_sha256": record['packet']['request_sha256'],
            "tool_call": {"name": "create_post", "arguments": {"content": content}}}}


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve()
    compute = FixtureCompute(root / 'fixture-admissions')
    coordinator = NativeCoordinator(root, OasisEngine(compute.identity), compute)
    def worker():
        while True:
            run = coordinator.active()
            if run:
                coordinator.advance(run['id'])
            threading.Event().wait(1)
    threading.Thread(target=worker, daemon=True).start()
    create_app(native_coordinator=coordinator, native_options={"port": 5002, "origins": ["http://127.0.0.1:5180"]}).run(host='127.0.0.1', port=5002, debug=False)
