"""Serve the bounded, loopback-only native operator API. See docs/native-ui.md."""
import argparse
import fcntl
import logging
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.agent_runners.exchange import read_json
from app.agent_runners.native_compute import NativeCompute
from app.agent_runners.native_coordinator import NativeCoordinator
from app.agent_runners.native_engine import OasisEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = read_json(args.config, limit=16384)
    root = Path(config['state_root'])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('State root must be an absolute, local directory')
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'owner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    compute = NativeCompute({key: config[key] for key in ('target', 'remote_outputs_root', 'shared_roots')})
    coordinator = NativeCoordinator(root, OasisEngine(compute.identity), compute)
    app = create_app(native_coordinator=coordinator, native_options=config['http'])
    stopped = threading.Event()

    def worker():
        while not stopped.is_set():
            try:
                run = coordinator.active()
                if run and run['status'] not in ('awaiting_approval', 'completed', 'failed'):
                    coordinator.advance(run['id'])
            except Exception:
                logging.exception('Native coordinator worker could not advance; state preserved')
            stopped.wait(1)

    threading.Thread(target=worker, daemon=True, name='native-coordinator').start()
    try:
        app.run(host='127.0.0.1', port=config['http']['port'], debug=False, use_reloader=False)
    finally:
        stopped.set()
        lock.close()


if __name__ == '__main__':
    main()
