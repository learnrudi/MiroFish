"""Native setup controls attached to the application's normal setup routes."""
import hashlib
from pathlib import Path
import re
import tempfile

from flask import request
from werkzeug.exceptions import BadRequest, HTTPException

from .native_http import install_operator_boundary
from .setup_engine import materialize_project
from ..config import Config
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.locale import get_locale


def public(workflow):
    return {**{key:workflow[key] for key in ('id','resource','kind','version','status','error')},
            'events':workflow['events'][-100:],
            'calls':[{'kind':c['packet']['kind'], 'status':c['status'], 'job_id':c.get('job_id')}
                     for c in workflow['calls']]}


def ok(data, status=200):
    return {'success':True, 'data':data}, status


def identifier(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r'[a-f0-9]{6,32}', value):
        raise BadRequest('Invalid resource identifier')
    return value


def body(keys):
    data = request.get_json()
    if not isinstance(data, dict) or set(data) != set(keys):
        raise BadRequest('Invalid request fields')
    return data


def install_setup(app, coordinator, options):
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    token = install_operator_boundary(app, options)
    app.extensions['native_setup'] = coordinator

    @app.get('/api/native-setup/session')
    def session():
        return ok({'token':token, 'runner':coordinator.compute.identity,
                   'zep_configured':bool(Config.ZEP_API_KEY),
                   'workflows':[public(w) for w in coordinator.list()[:50]]})

    @app.get('/api/native-setup/<workflow_id>')
    def get_setup(workflow_id):
        return ok(public(coordinator.get(workflow_id)))

    @app.get('/api/native-setup/<workflow_id>/review')
    def review(workflow_id):
        return ok(coordinator.review(workflow_id))

    @app.post('/api/native-setup/<workflow_id>/approve')
    def approve(workflow_id):
        return ok(public(coordinator.approve(workflow_id, body(['review_hash'])['review_hash'])))

    @app.post('/api/native-setup/<workflow_id>/reconcile')
    def reconcile(workflow_id):
        return ok(public(coordinator.reconcile(workflow_id, body(['version'])['version'])))

    @app.before_request
    def native_routes():
        # Validate identifiers even on legacy read routes before they reach
        # path-based stores or graph lookups.
        for key,value in (request.view_args or {}).items():
            if key in ('project_id','simulation_id'):
                identifier(value, 'proj_' if key=='project_id' else 'sim_')
            elif not re.fullmatch(r'[a-zA-Z0-9_.-]{1,160}',str(value)) or value in ('.','..'):
                raise BadRequest('Invalid route identifier')
        if request.path == '/api/graph/ontology/generate' and request.method == 'POST':
            return upload_ontology(coordinator)
        if request.method == 'POST':
            from .setup_simulation import create_simulation, prepare, progress
            if request.path == '/api/simulation/create':
                with coordinator.lock:
                    return ok(create_simulation(request.get_json()))
            if request.path == '/api/simulation/prepare':
                if not Config.ZEP_API_KEY:
                    return {'success':False, 'error':'Set up a Zep Cloud project before preparing graph-based agents.'}, 409
                workflow = prepare(coordinator,request.get_json())
                return ok(progress(workflow,workflow['resource']),202)
            if request.path == '/api/simulation/prepare/status':
                data = request.get_json()
                if not isinstance(data,dict) or not set(data)<= {'simulation_id','task_id'}:
                    raise BadRequest('Invalid progress request')
                sid = data.get('simulation_id')
                workflow = coordinator.for_resource(identifier(sid,'sim_')) if sid else coordinator.get(data.get('task_id'))
                if workflow and (workflow['kind']!='simulation' or (data.get('task_id') and data['task_id']!=workflow['id'])):
                    raise BadRequest('Task does not belong to this simulation')
                return ok(progress(workflow,sid or workflow['resource']))
            if request.path == '/api/graph/build':
                if not Config.ZEP_API_KEY:
                    return {'success':False, 'error':'Ontology is ready. Set up a Zep Cloud project to build its graph.'}, 409
                data = request.get_json()
                if not isinstance(data,dict) or not set(data)<= {'project_id','graph_name','chunk_size','chunk_overlap','force'}:
                    raise BadRequest('Invalid graph build request')
                identifier(data.get('project_id'),'proj_')
                if data.get('force',False) is not False:
                    raise BadRequest('Native setup preserves existing graphs')
                return None
        # All unconverted model operations and destructive legacy operations
        # remain unavailable in this explicit setup-only process.
        if request.path.startswith('/api/report'):
            return {'success':False, 'error':'Reports are not connected to the native runner yet.'}, 409
        if request.method not in ('GET','HEAD') and not request.path.startswith('/api/native-setup/'):
            return {'success':False, 'error':'This operation is not connected to native setup yet.'}, 409

    @app.errorhandler(ValueError)
    def conflict(_):
        return {'success':False, 'error':'Setup inputs or state changed. Reload the saved setup; no new job was authorized.'}, 409

    @app.errorhandler(KeyError)
    def missing(_):
        return {'success':False, 'error':'Saved setup or resource not found.'}, 404

    @app.errorhandler(HTTPException)
    def invalid(error):
        return {'success':False, 'error':error.description}, error.code

    @app.errorhandler(Exception)
    def unavailable(error):
        app.logger.exception('Native setup request failed', exc_info=error)
        return {'success':False, 'error':'Setup unavailable. Saved state is preserved; inspect local diagnostics.'}, 503


def upload_ontology(coordinator):
    request_id = request.form.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id):
        raise BadRequest('A stable setup request ID is required')
    requirement = request.form.get('simulation_requirement', '')
    name = request.form.get('project_name', 'Native setup')
    context = request.form.get('additional_context', '')
    if not requirement.strip() or len(requirement)>16000 or len(context)>16000 or not 1<=len(name)<=200:
        raise BadRequest('Provide a bounded project name, requirement and context')
    files = request.files.getlist('files')
    if not 1 <= len(files) <= 10:
        raise BadRequest('Upload 1–10 PDF, Markdown or text documents')
    inputs = {'project_id':'proj_' + request_id, 'project_name':name,
              'simulation_requirement':requirement, 'additional_context':context or None,
              'locale':get_locale(), 'document_texts':[], 'files':[]}
    with tempfile.TemporaryDirectory() as temporary:
        for index, upload in enumerate(files):
            extension = Path(upload.filename or '').suffix.lower()
            if extension not in ('.txt','.md','.pdf') or len(upload.filename)>255:
                raise BadRequest('Unsupported document format or filename')
            path = Path(temporary) / f'{index}{extension}'
            upload.save(path)
            inputs['files'].append({'filename':upload.filename, 'size':path.stat().st_size,
                                   'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            extracted = TextProcessor.preprocess_text(FileParser.extract_text(str(path)))
            if not extracted.strip(): raise BadRequest('Document contains no readable text')
            inputs['document_texts'].append(extracted)
    with coordinator.lock:
        workflow = coordinator.start(request_id, 'ontology', inputs['project_id'], inputs)
        project = materialize_project(workflow['inputs'])
    return ok({'project_id':project.project_id, 'setup':public(workflow)}, 202)
