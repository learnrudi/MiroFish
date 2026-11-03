"""Loopback operator API for the bounded native experiment."""
import secrets
from urllib.parse import urlsplit
from flask import Flask, request
from werkzeug.exceptions import BadRequest, HTTPException


def snapshot(run):
    if run is None:
        return None
    return {**{key: run[key] for key in ('id', 'version', 'status', 'round', 'review_hash', 'display', 'error', 'events')},
        'agents': [{"name": name, **{key: agent[key] for key in ('attempt', 'status', 'job_id') if key in agent}}
                   for name, agent in run['rounds'][-1]['agents'].items()]}


def create_native_app(coordinator, options):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 4096
    token = secrets.token_urlsafe(32)
    hosts = {f"127.0.0.1:{options['port']}", f"localhost:{options['port']}"}
    origins = set(options['origins'])
    for origin in origins:
        url = urlsplit(origin)
        if url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1') or not url.port or url.path or url.query or url.fragment or url.username:
            raise ValueError('Only explicit loopback origins are supported')
    @app.before_request
    def boundary():
        if (request.host not in hosts or request.headers.get('Origin') not in (None, *origins)
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'):
            return {'error': 'forbidden_origin', 'message': 'Use the configured loopback UI.'}, 403
        if request.method not in ('GET', 'HEAD') and not secrets.compare_digest(request.headers.get('X-Native-Token', ''), token):
            return {'error': 'invalid_token', 'message': 'Reload the UI to refresh its operator session.'}, 403
    @app.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
    @app.get('/api/native-runs/session')
    def session():
        return {'runner': coordinator.compute.identity, 'token': token, 'run': snapshot(coordinator.active())}

    def body(key):
        data = request.get_json()
        if not isinstance(data, dict) or set(data) != {key}:
            raise BadRequest(f'Expected only {key}')
        return data[key]

    @app.post('/api/native-runs')
    def start():
        return snapshot(coordinator.start(body('request_id')))

    @app.get('/api/native-runs/<run_id>')
    def get_run(run_id):
        return snapshot(coordinator.get(run_id))

    @app.get('/api/native-runs/<run_id>/review')
    def review(run_id):
        return coordinator.review(run_id)

    @app.post('/api/native-runs/<run_id>/approve')
    def approve(run_id):
        return snapshot(coordinator.approve(run_id, body('review_hash')))

    @app.post('/api/native-runs/<run_id>/retry')
    def retry(run_id):
        return snapshot(coordinator.retry(run_id, body('version')))

    @app.errorhandler(ValueError)
    def conflict(_):
        return {'error': 'state_conflict', 'message': 'Run or review changed. Reload the current state before continuing.'}, 409

    @app.errorhandler(KeyError)
    def missing(_):
        return {'error': 'not_found', 'message': 'Run not found.'}, 404

    @app.errorhandler(HTTPException)
    def invalid_request(error):
        return {'error': 'invalid_request', 'message': 'Request could not be accepted.'}, error.code

    @app.errorhandler(Exception)
    def unavailable(error):
        app.logger.exception('Native operator API failed', exc_info=error)
        return {'error': 'unavailable', 'message': 'Local state unavailable. No new submission was authorized.'}, 503
    return app
