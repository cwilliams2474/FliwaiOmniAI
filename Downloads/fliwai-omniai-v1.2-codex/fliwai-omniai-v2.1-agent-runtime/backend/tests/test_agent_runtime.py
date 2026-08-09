import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agent_runtime
from app.database.session import Base
from app.models.core import Agent, AgentRun, AgentRunStep, Organization, User


def make_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_run_without_provider_completes_safe_ai_step(monkeypatch):
    db = make_db()
    org = Organization(name='A', slug='a')
    user = User(email='u@example.com', full_name='U', password_hash='x')
    agent = Agent(name='Analyst', slug='analyst', system_prompt='Analyze carefully and report facts.', enabled=True)
    db.add_all([org, user, agent]); db.commit()
    monkeypatch.setattr(agent_runtime, 'settings', SimpleNamespace(openai_api_key='', openai_model='test-model'))
    monkeypatch.setattr(agent_runtime, '_execute_step', lambda db, run, step, agent, user, context: ({'answer': 'done'}, 'done'))

    run = agent_runtime.create_run(db, agent, user, org.id, 'Review this situation')

    assert run.status == 'completed'
    steps = db.query(AgentRunStep).filter(AgentRunStep.run_id == run.id).all()
    assert len(steps) == 1
    assert steps[0].status == 'completed'


def test_external_step_stops_for_approval_before_execution():
    db = make_db()
    org = Organization(name='A', slug='a')
    user = User(email='u@example.com', full_name='U', password_hash='x')
    agent = Agent(name='Operator', slug='operator', system_prompt='Operate safely.', enabled=True)
    db.add_all([org, user, agent]); db.flush()
    run = AgentRun(organization_id=org.id, agent_id=agent.id, user_id=user.id, objective='Do external action', status='running', plan_json='[]')
    db.add(run); db.flush()
    step = AgentRunStep(run_id=run.id, position=1, step_type='integration_action', title='External action', config_json=json.dumps({'connection_id': 1, 'action': 'x'}), requires_approval=True)
    db.add(step); db.commit()

    agent_runtime.continue_run(db, run, agent, user)

    assert run.status == 'waiting_approval'
    assert step.status == 'waiting_approval'
    assert step.approved_at is None
