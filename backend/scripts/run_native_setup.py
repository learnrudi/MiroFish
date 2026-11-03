"""Run the local MiroFish application with reviewed native setup generation."""
import argparse
import fcntl
import logging
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.agent_runners.exchange import read_json
from app.agent_runners.setup_compute import SetupCompute
from app.agent_runners.setup_coordinator import SetupCoordinator
from app.agent_runners.setup_engine import SetupEngine
from app.config import Config
from app.models.project import ProjectManager
from app.services.simulation_manager import SimulationManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = read_json(args.config, limit=16384)
    root = Path(config['state_root'])
    if not root.is_absolute() or root.is_symlink() or '..' in root.parts:
        raise ValueError('State root must be an absolute local directory')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (root / 'owner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    Config.UPLOAD_FOLDER = str(root / 'uploads')
    ProjectManager.PROJECTS_DIR = str(root / 'uploads/projects')
    SimulationManager.SIMULATION_DATA_DIR = str(root / 'uploads/simulations')
    Config.OASIS_SIMULATION_DATA_DIR = SimulationManager.SIMULATION_DATA_DIR
    compute = SetupCompute({key:config[key] for key in ('target','remote_outputs_root','shared_roots')})
    coordinator = SetupCoordinator(root / 'coordinator', SetupEngine(), compute)
    app = create_app(setup_coordinator=coordinator, native_options=config['http'])
    stopped = threading.Event()

    def worker():
        while not stopped.is_set():
            try:
                for workflow in coordinator.list():
                    if workflow['status'] not in ('awaiting_approval','completed','failed'):
                        coordinator.advance(workflow['id'])
            except Exception:
                logging.exception('Setup worker interrupted; saved state preserved')
            stopped.wait(3)

    threading.Thread(target=worker, daemon=True, name='native-setup').start()
    try:
        app.run(host='127.0.0.1',port=config['http']['port'],debug=False,use_reloader=False)
    finally:
        stopped.set()
        lock.close()


if __name__ == '__main__':
    main()
