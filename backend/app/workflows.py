import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.time_utils import utcnow
from app.ai.service import get_ai_response
from app.integrations import execute_integration_action
from app.models.core import IntegrationConnection, MemoryEntry, Notification, Ticket, User, Workflow, WorkflowRun


def execute_workflow(db: Session, workflow: Workflow, user: User, input_text: str) -> WorkflowRun:
    run = WorkflowRun(workflow_id=workflow.id, user_id=user.id, input_text=input_text, status='running')
    db.add(run); db.flush()
    outputs = []
    try:
        steps = json.loads(workflow.steps_json)
        context = input_text
        for index, step in enumerate(steps):
            step_type = step.get('type'); config = step.get('config') or {}
            if step_type == 'ai_prompt':
                template = str(config.get('prompt', 'Process this input: {input}'))
                prompt = template.replace('{input}', input_text).replace('{context}', context)
                result, model = get_ai_response(prompt, str(config.get('tool', 'general')))
                context = result
                outputs.append({'step': index + 1, 'type': step_type, 'result': result, 'model': model})
            elif step_type == 'create_ticket':
                title = str(config.get('title', 'Workflow ticket')).replace('{input}', input_text).replace('{context}', context)[:255]
                description = str(config.get('description', context)).replace('{input}', input_text).replace('{context}', context)[:10000]
                ticket = Ticket(organization_id=workflow.organization_id, title=title, description=description, priority=str(config.get('priority', 'normal')))
                db.add(ticket); db.flush(); outputs.append({'step': index + 1, 'type': step_type, 'ticket_id': ticket.id, 'title': ticket.title})
            elif step_type == 'memory_write':
                key = str(config.get('key', workflow.name)).replace('{input}', input_text)[:160]
                value = str(config.get('value', context)).replace('{input}', input_text).replace('{context}', context)[:12000]
                entry = MemoryEntry(user_id=user.id, category=str(config.get('category', 'workflow'))[:80], key=key, value=value)
                db.add(entry); db.flush(); outputs.append({'step': index + 1, 'type': step_type, 'memory_id': entry.id, 'key': key})
            elif step_type == 'notify':
                title = str(config.get('title', workflow.name)).replace('{input}', input_text).replace('{context}', context)[:255]
                body = str(config.get('body', context)).replace('{input}', input_text).replace('{context}', context)[:12000]
                note = Notification(user_id=user.id, title=title, body=body, level=str(config.get('level', 'info'))[:30])
                db.add(note); db.flush(); outputs.append({'step': index + 1, 'type': step_type, 'notification_id': note.id})
            elif step_type == 'integration_action':
                connection_id = int(config.get('connection_id', 0))
                action = str(config.get('action', ''))
                params = config.get('params') or {}
                params = json.loads(json.dumps(params).replace('{input}', input_text).replace('{context}', context))
                connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id, IntegrationConnection.organization_id == workflow.organization_id).first()
                if not connection:
                    raise ValueError(f'Integration connection {connection_id} not found')
                result = execute_integration_action(connection, action, params)
                context = json.dumps(result)
                outputs.append({'step': index + 1, 'type': step_type, 'connection_id': connection_id, 'action': action, 'result': result})
            else:
                raise ValueError(f'Unsupported workflow step: {step_type}')
        run.status = 'completed'; run.output_json = json.dumps(outputs); run.completed_at = utcnow()
    except Exception as exc:
        run.status = 'failed'; run.error = str(exc)[:12000]; run.output_json = json.dumps(outputs); run.completed_at = utcnow()
    db.commit(); db.refresh(run)
    return run
