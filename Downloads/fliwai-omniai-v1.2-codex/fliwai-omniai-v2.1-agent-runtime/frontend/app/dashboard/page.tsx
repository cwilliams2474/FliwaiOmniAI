'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

type User = { id: number; email: string; full_name: string; is_admin: boolean; is_active: boolean; mfa_enabled:boolean };
type Ticket = { id: number; title: string; description: string; status: string; priority: string; created_at: string };
type Asset = { id: number; name: string; asset_type: string; serial_number: string; status: string; notes: string; created_at: string };
type DocumentItem = { id: number; filename: string; content_type: string; indexed_chunks: number; created_at: string };
type ChatSummary = { id: number; title: string; created_at: string };
type CodeProject = { id: number; name: string; description: string; updated_at: string };
type CodeFile = { id: number; path: string; language: string; content: string; updated_at: string };
type CodeTask = { id: number; mode: string; instruction: string; status: string; model: string; result: { summary?: string; answer?: string; files?: { path: string; language?: string; content: string }[]; diffs?: {path:string; diff:string; is_new:boolean}[]; test_plan?: string[]; risks?: string[] }; created_at: string; applied_at?: string | null };
type CodeRevision = { id:number; task_id?:number|null; path:string; language:string; created_at:string; rolled_back_at?:string|null };
type Integration = { id:number; provider:string; name:string; config:Record<string,unknown>; enabled:boolean; has_secret:boolean; actions:string[] };
type Workflow = { id:number; name:string; description:string; enabled:boolean; steps:any[] };
type NotificationItem = { id:number; title:string; body:string; level:string; is_read:boolean; created_at:string };
type Organization = { id:number; name:string; slug:string; onboarding_complete:boolean; role:string|null; is_current:boolean };
type Subscription = { plan:string; status:string; seats:number; current_period_end?:string|null };
type PortalRequest = { id:number; subject:string; description:string; status:string; created_at:string };
type OrgMember = { id:number; user_id:number; email:string; full_name:string; role:string; active:boolean };
type AgentItem = { id:number; name:string; slug:string; description:string; enabled:boolean; is_system:boolean };
type AgentRunStep = { id:number; position:number; type:string; title:string; status:string; requires_approval:boolean; approved_at?:string|null; result:Record<string,unknown>; error:string };
type AgentRun = { id:number; agent_id:number; objective:string; status:string; summary:string; error:string; created_at:string; steps:AgentRunStep[] };
type Section = 'chat' | 'agents' | 'codex' | 'tickets' | 'assets' | 'documents' | 'workflows' | 'integrations' | 'notifications' | 'organization' | 'portal' | 'security' | 'admin';

export default function Dashboard() {
  const router = useRouter();
  const [section, setSection] = useState<Section>('chat');
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const [tool, setTool] = useState('general');
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');
  const [chatId, setChatId] = useState<number | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketTitle, setTicketTitle] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [ticketPriority, setTicketPriority] = useState('normal');

  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetName, setAssetName] = useState('');
  const [assetType, setAssetType] = useState('device');
  const [serialNumber, setSerialNumber] = useState('');

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [documentQuestion, setDocumentQuestion] = useState('');
  const [documentAnswer, setDocumentAnswer] = useState('');
  const [selectedDocument, setSelectedDocument] = useState<number | ''>('');

  const [users, setUsers] = useState<User[]>([]);
  const [adminSystem, setAdminSystem] = useState<any>(null);
  const [adminUsage, setAdminUsage] = useState<any>(null);
  const [adminSettings, setAdminSettings] = useState<any>(null);

  const [codeProjects, setCodeProjects] = useState<CodeProject[]>([]);
  const [codeProjectId, setCodeProjectId] = useState<number | null>(null);
  const [codeProjectName, setCodeProjectName] = useState('');
  const [codeFiles, setCodeFiles] = useState<CodeFile[]>([]);
  const [codeFilePath, setCodeFilePath] = useState('');
  const [codeFileLanguage, setCodeFileLanguage] = useState('text');
  const [codeFileContent, setCodeFileContent] = useState('');
  const [codeMode, setCodeMode] = useState('ask');
  const [codeInstruction, setCodeInstruction] = useState('');
  const [codeTasks, setCodeTasks] = useState<CodeTask[]>([]);
  const [codeResult, setCodeResult] = useState<CodeTask | null>(null);
  const [codeRevisions,setCodeRevisions]=useState<CodeRevision[]>([]);

  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [integrationProvider, setIntegrationProvider] = useState('github');
  const [integrationName, setIntegrationName] = useState('');
  const [integrationSecret, setIntegrationSecret] = useState('');
  const [integrationConfig, setIntegrationConfig] = useState('{}');
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowPrompt, setWorkflowPrompt] = useState('Process this input: {input}');
  const [workflowInput, setWorkflowInput] = useState('');
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [currentOrganization, setCurrentOrganization] = useState<Organization | null>(null);
  const [organizationName, setOrganizationName] = useState('');
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [memberEmail, setMemberEmail] = useState('');
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [portalSummary, setPortalSummary] = useState<any>(null);
  const [portalRequests, setPortalRequests] = useState<PortalRequest[]>([]);
  const [portalSubject, setPortalSubject] = useState('');
  const [portalDescription, setPortalDescription] = useState('');
  const [monitoring, setMonitoring] = useState<any>(null);
  const [mfaSetup,setMfaSetup]=useState<any>(null); const [mfaCode,setMfaCode]=useState(''); const [inviteRole,setInviteRole]=useState('member');
  const [agents,setAgents]=useState<AgentItem[]>([]); const [agentRuns,setAgentRuns]=useState<AgentRun[]>([]); const [selectedAgentId,setSelectedAgentId]=useState<number|null>(null); const [agentObjective,setAgentObjective]=useState('');

  function token() {
    return typeof window === 'undefined' ? null : localStorage.getItem('omniai_token');
  }

  async function api(path: string, init?: RequestInit) {
    const currentToken = token();
    if (!currentToken) {
      router.replace('/login');
      throw new Error('Not signed in');
    }
    const headers = new Headers(init?.headers || {});
    headers.set('Authorization', `Bearer ${currentToken}`);
    const res = await fetch(`${API_URL}${path}`, { ...init, headers });
    if (res.status === 401) {
      localStorage.removeItem('omniai_token');
      localStorage.removeItem('omniai_user');
      router.replace('/login');
    }
    return res;
  }

  async function jsonApi(path: string, init?: RequestInit) {
    const headers = new Headers(init?.headers || {});
    if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const res = await api(path, { ...init, headers });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
    return body;
  }

  async function loadAll() {
    setError('');
    try {
      const me = await jsonApi('/auth/me');
      setUser(me);
      const [chatData, ticketData, assetData, documentData, codeProjectData, workflowData, integrationData, notificationData, orgData, currentOrgData, subscriptionData, portalData, requestData, memberData, agentData, agentRunData] = await Promise.all([
        jsonApi('/ai/chats'), jsonApi('/tickets'), jsonApi('/assets'), jsonApi('/documents'), jsonApi('/codex/projects'), jsonApi('/workflows'), jsonApi('/integrations'), jsonApi('/notifications'), jsonApi('/organizations'), jsonApi('/organizations/current'), jsonApi('/billing/current'), jsonApi('/portal/summary'), jsonApi('/portal/requests'), jsonApi('/organizations/current/members'), jsonApi('/agents'), jsonApi('/agents/runs/recent')
      ]);
      setChats(chatData);
      setTickets(ticketData);
      setAssets(assetData);
      setDocuments(documentData);
      setCodeProjects(codeProjectData); setWorkflows(workflowData); setIntegrations(integrationData); setNotifications(notificationData);
      setOrganizations(orgData); setCurrentOrganization(currentOrgData); setSubscription(subscriptionData); setPortalSummary(portalData); setPortalRequests(requestData); setMembers(memberData); setAgents(agentData); setAgentRuns(agentRunData); if (!selectedAgentId && agentData.length) setSelectedAgentId(agentData[0].id);
      if (me.is_admin) {
        const [userData, systemData, usageData, settingsData, monitoringData] = await Promise.all([jsonApi('/admin/users'), jsonApi('/admin/system'), jsonApi('/admin/usage'), jsonApi('/admin/settings'), jsonApi('/monitoring/metrics')]);
        setUsers(userData); setAdminSystem(systemData); setAdminUsage(usageData); setAdminSettings(settingsData); setMonitoring(monitoringData);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load dashboard');
    }
  }

  useEffect(() => { loadAll(); }, []);

  async function startAgentRun() {
    if (!selectedAgentId || !agentObjective.trim()) return;
    setBusy(true); setError('');
    try {
      await jsonApi(`/agents/${selectedAgentId}/runs`, { method: 'POST', body: JSON.stringify({ objective: agentObjective }) });
      setAgentObjective(''); setAgentRuns(await jsonApi('/agents/runs/recent'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Agent run failed'); }
    finally { setBusy(false); }
  }

  async function approveAgentStep(runId:number, stepId:number, approve:boolean) {
    setBusy(true); setError('');
    try {
      await jsonApi(`/agents/runs/${runId}/steps/${stepId}/approval`, { method: 'POST', body: JSON.stringify({ approve }) });
      setAgentRuns(await jsonApi('/agents/runs/recent'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Approval failed'); }
    finally { setBusy(false); }
  }

  async function sendMessage() {
    if (!message.trim()) return;
    setBusy(true); setError('');
    try {
      const data = await jsonApi('/ai/chat', {
        method: 'POST', body: JSON.stringify({ message, tool, chat_id: chatId })
      });
      setResponse(data.response); setChatId(data.chat_id); setMessage('');
      setChats(await jsonApi('/ai/chats'));
    } catch (err) { setError(err instanceof Error ? err.message : 'AI request failed'); }
    finally { setBusy(false); }
  }

  async function createTicket() {
    if (!ticketTitle.trim()) return;
    setBusy(true); setError('');
    try {
      await jsonApi('/tickets', { method: 'POST', body: JSON.stringify({ title: ticketTitle, description: ticketDescription, priority: ticketPriority }) });
      setTicketTitle(''); setTicketDescription(''); setTickets(await jsonApi('/tickets'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Ticket creation failed'); }
    finally { setBusy(false); }
  }

  async function updateTicket(id: number, status: string) {
    try {
      await jsonApi(`/tickets/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
      setTickets(await jsonApi('/tickets'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Ticket update failed'); }
  }

  async function createAsset() {
    if (!assetName.trim()) return;
    setBusy(true); setError('');
    try {
      await jsonApi('/assets', { method: 'POST', body: JSON.stringify({ name: assetName, asset_type: assetType, serial_number: serialNumber, notes: '' }) });
      setAssetName(''); setSerialNumber(''); setAssets(await jsonApi('/assets'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Asset creation failed'); }
    finally { setBusy(false); }
  }

  async function uploadDocument(file: File | undefined) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const form = new FormData(); form.append('file', file);
      const res = await api('/documents/upload', { method: 'POST', body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Upload failed');
      setDocuments(await jsonApi('/documents'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Upload failed'); }
    finally { setBusy(false); }
  }

  async function askDocuments() {
    if (!documentQuestion.trim()) return;
    setBusy(true); setError('');
    try {
      const body: { question: string; document_id?: number } = { question: documentQuestion };
      if (selectedDocument !== '') body.document_id = Number(selectedDocument);
      const data = await jsonApi('/documents/ask', { method: 'POST', body: JSON.stringify(body) });
      setDocumentAnswer(data.answer);
    } catch (err) { setError(err instanceof Error ? err.message : 'Document question failed'); }
    finally { setBusy(false); }
  }


  async function createCodeProject() {
    if (!codeProjectName.trim()) return;
    setBusy(true); setError('');
    try {
      const project = await jsonApi('/codex/projects', { method: 'POST', body: JSON.stringify({ name: codeProjectName, description: 'OmniAI Codex workspace' }) });
      setCodeProjectName('');
      setCodeProjects(await jsonApi('/codex/projects'));
      await openCodeProject(project.id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create Codex project'); }
    finally { setBusy(false); }
  }

  async function openCodeProject(id: number) {
    setCodeProjectId(id); setCodeResult(null); setError('');
    try {
      const [files, tasks, revisions] = await Promise.all([jsonApi(`/codex/projects/${id}/files`), jsonApi(`/codex/projects/${id}/tasks`), jsonApi(`/codex/projects/${id}/revisions`)]);
      setCodeFiles(files); setCodeTasks(tasks); setCodeRevisions(revisions);
      if (files.length) selectCodeFile(files[0]); else { setCodeFilePath(''); setCodeFileLanguage('text'); setCodeFileContent(''); }
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not open Codex project'); }
  }

  function selectCodeFile(file: CodeFile) {
    setCodeFilePath(file.path); setCodeFileLanguage(file.language || 'text'); setCodeFileContent(file.content);
  }

  async function saveCodeFile() {
    if (!codeProjectId || !codeFilePath.trim()) return;
    setBusy(true); setError('');
    try {
      await jsonApi(`/codex/projects/${codeProjectId}/files`, { method: 'PUT', body: JSON.stringify({ path: codeFilePath, language: codeFileLanguage, content: codeFileContent }) });
      const files = await jsonApi(`/codex/projects/${codeProjectId}/files`); setCodeFiles(files);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save code file'); }
    finally { setBusy(false); }
  }

  async function runCodeTask() {
    if (!codeProjectId || !codeInstruction.trim()) return;
    setBusy(true); setError('');
    try {
      const task = await jsonApi(`/codex/projects/${codeProjectId}/tasks`, { method: 'POST', body: JSON.stringify({ mode: codeMode, instruction: codeInstruction }) });
      setCodeResult(task); setCodeInstruction('');
      setCodeTasks(await jsonApi(`/codex/projects/${codeProjectId}/tasks`)); setCodeRevisions(await jsonApi(`/codex/projects/${codeProjectId}/revisions`));
    } catch (err) { setError(err instanceof Error ? err.message : 'Codex task failed'); }
    finally { setBusy(false); }
  }

  async function rollbackCodeRevision(revisionId:number) {
    if (!codeProjectId) return;
    setBusy(true); setError('');
    try {
      await jsonApi(`/codex/projects/${codeProjectId}/revisions/${revisionId}/rollback`, { method: 'POST' });
      await openCodeProject(codeProjectId);
    } catch (err) { setError(err instanceof Error ? err.message : 'Rollback failed'); }
    finally { setBusy(false); }
  }

  async function applyCodeTask(taskId: number) {
    if (!codeProjectId) return;
    setBusy(true); setError('');
    try {
      const data = await jsonApi(`/codex/projects/${codeProjectId}/tasks/${taskId}/apply`, { method: 'POST' });
      setCodeFiles(await jsonApi(`/codex/projects/${codeProjectId}/files`));
      setCodeTasks(await jsonApi(`/codex/projects/${codeProjectId}/tasks`)); setCodeRevisions(await jsonApi(`/codex/projects/${codeProjectId}/revisions`));
      setCodeResult((current) => current ? { ...current, applied_at: new Date().toISOString() } : current);
      setResponse(`Codex applied ${data.applied_files.length} file(s): ${data.applied_files.join(', ')}`);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not apply Codex changes'); }
    finally { setBusy(false); }
  }

  async function updateUser(target: User, changes: Partial<Pick<User,'is_admin'|'is_active'>>) {
    try {
      await jsonApi(`/admin/users/${target.id}`, { method: 'PATCH', body: JSON.stringify(changes) });
      setUsers(await jsonApi('/admin/users'));
    } catch (err) { setError(err instanceof Error ? err.message : 'User update failed'); }
  }

  async function saveAdminSettings() {
    if (!adminSettings) return;
    try {
      setAdminSettings(await jsonApi('/admin/settings', { method: 'PATCH', body: JSON.stringify({ organization_name: adminSettings.organization_name, default_ai_model: adminSettings.default_ai_model, default_code_model: adminSettings.default_code_model }) }));
    } catch (err) { setError(err instanceof Error ? err.message : 'Settings update failed'); }
  }


  async function createIntegration() {
    if (!integrationName.trim()) return;
    setBusy(true); setError('');
    try {
      let config = {}; try { config = JSON.parse(integrationConfig || '{}'); } catch { throw new Error('Integration config must be valid JSON'); }
      await jsonApi('/integrations', { method:'POST', body:JSON.stringify({ provider:integrationProvider, name:integrationName, secret:integrationSecret, config }) });
      setIntegrationName(''); setIntegrationSecret(''); setIntegrationConfig('{}'); setIntegrations(await jsonApi('/integrations'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Integration creation failed'); } finally { setBusy(false); }
  }

  async function testIntegration(id:number) {
    setBusy(true); setError('');
    try { const data=await jsonApi(`/integrations/${id}/test`, {method:'POST'}); setResponse(`Connection test successful: ${data.identity || 'ready'}`); }
    catch (err) { setError(err instanceof Error ? err.message : 'Connection test failed'); } finally { setBusy(false); }
  }

  async function createWorkflow() {
    if (!workflowName.trim()) return;
    setBusy(true); setError('');
    try { await jsonApi('/workflows', {method:'POST', body:JSON.stringify({name:workflowName, description:'Created in OmniAI', steps:[{type:'ai_prompt',config:{prompt:workflowPrompt,tool:'general'}},{type:'notify',config:{title:'Workflow complete',body:'{context}',level:'success'}}]})}); setWorkflowName(''); setWorkflows(await jsonApi('/workflows')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Workflow creation failed'); } finally { setBusy(false); }
  }

  async function runWorkflow(id:number) {
    setBusy(true); setError('');
    try { const data=await jsonApi(`/workflows/${id}/run`, {method:'POST', body:JSON.stringify({input_text:workflowInput})}); setResponse(JSON.stringify(data,null,2)); setNotifications(await jsonApi('/notifications')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Workflow failed'); } finally { setBusy(false); }
  }

  async function scheduleWorkflow(id:number) {
    setBusy(true); setError('');
    try { await jsonApi(`/workflows/${id}/schedules`, {method:'POST', body:JSON.stringify({interval_minutes:60,input_text:workflowInput})}); setResponse('Workflow scheduled to run every 60 minutes.'); }
    catch (err) { setError(err instanceof Error ? err.message : 'Scheduling failed'); } finally { setBusy(false); }
  }

  async function markNotification(id:number) {
    try { await jsonApi(`/notifications/${id}`, {method:'PATCH',body:JSON.stringify({is_read:true})}); setNotifications(await jsonApi('/notifications')); } catch {}
  }

  async function createOrganization() {
    if (!organizationName.trim()) return;
    setBusy(true); setError('');
    try { await jsonApi('/organizations', {method:'POST', body:JSON.stringify({name:organizationName})}); setOrganizationName(''); await loadAll(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Organization creation failed'); } finally { setBusy(false); }
  }

  async function switchOrganization(id:number) {
    setBusy(true); setError('');
    try { const data=await jsonApi(`/organizations/${id}/switch`, {method:'POST'}); localStorage.setItem('omniai_token', data.access_token); await loadAll(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Organization switch failed'); } finally { setBusy(false); }
  }

  async function completeOnboarding() {
    if (!currentOrganization) return;
    try { const org=await jsonApi('/organizations/current', {method:'PATCH', body:JSON.stringify({onboarding_complete:true})}); setCurrentOrganization(org); setOrganizations(await jsonApi('/organizations')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Onboarding update failed'); }
  }

  async function addOrganizationMember() {
    if (!memberEmail.trim()) return;
    try { const data=await jsonApi('/organizations/current/invitations', {method:'POST', body:JSON.stringify({email:memberEmail,role:inviteRole})}); setMemberEmail(''); setResponse(data.email_delivered?'Invitation email sent.':'Invitation created. Configure SMTP to deliver it automatically.'); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not invite member'); }
  }
  async function setupMfa(){try{setMfaSetup(await jsonApi('/security/mfa/setup',{method:'POST'}))}catch(err){setError(err instanceof Error?err.message:'MFA setup failed')}}
  async function confirmMfa(){try{await jsonApi('/security/mfa/confirm',{method:'POST',body:JSON.stringify({code:mfaCode})});localStorage.removeItem('omniai_token');router.replace('/login')}catch(err){setError(err instanceof Error?err.message:'MFA confirmation failed')}}
  async function disableMfa(){try{await jsonApi('/security/mfa',{method:'DELETE',body:JSON.stringify({code:mfaCode})});localStorage.removeItem('omniai_token');router.replace('/login')}catch(err){setError(err instanceof Error?err.message:'MFA disable failed')}}
  async function startCheckout(plan:string){try{const data=await jsonApi('/billing/checkout',{method:'POST',body:JSON.stringify({plan,seats:subscription?.seats||5})});if(data.checkout_url)window.location.href=data.checkout_url}catch(err){setError(err instanceof Error?err.message:'Checkout unavailable')}}

  async function createPortalRequest() {
    if (!portalSubject.trim()) return;
    setBusy(true); setError('');
    try { await jsonApi('/portal/requests', {method:'POST', body:JSON.stringify({subject:portalSubject,description:portalDescription})}); setPortalSubject(''); setPortalDescription(''); setPortalRequests(await jsonApi('/portal/requests')); setPortalSummary(await jsonApi('/portal/summary')); setTickets(await jsonApi('/tickets')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not create request'); } finally { setBusy(false); }
  }

  async function logout() {
    try { await jsonApi('/auth/logout', { method: 'POST' }); } catch {}
    localStorage.removeItem('omniai_token'); localStorage.removeItem('omniai_user'); router.replace('/login');
  }

  const openTickets = useMemo(() => tickets.filter((t) => !['resolved', 'closed'].includes(t.status)).length, [tickets]);
  const activeAssets = useMemo(() => assets.filter((a) => a.status === 'active').length, [assets]);

  return (
    <main className="shell">
      <a className="skipLink" href="#main-workspace">Skip to main content</a>
      <aside className="sidebar" aria-label="Application sidebar">
        <div><div className="brandMark">O</div><h2>FLIWAI OmniAI</h2><p className="muted">{user?.full_name || user?.email || 'Loading...'}</p>{user?.is_admin && <span className="badge">ADMIN</span>}</div>
        <nav className="nav" aria-label="Primary navigation">
          {(['chat','agents','codex','tickets','assets','documents','workflows','integrations','notifications','organization','portal','security'] as Section[]).map((item) => <button key={item} aria-current={section === item ? 'page' : undefined} className={section === item ? 'navActive' : ''} onClick={() => setSection(item)}>{item}</button>)}
          {user?.is_admin && <button aria-current={section === 'admin' ? 'page' : undefined} className={section === 'admin' ? 'navActive' : ''} onClick={() => setSection('admin')}>admin</button>}
        </nav>
        <button className="secondary" onClick={logout}>Sign out</button>
      </aside>

      <section className="workspace" id="main-workspace" tabIndex={-1}>
        <header className="topbar"><div><p className="eyebrow">AI OPERATING SYSTEM</p><h1>{section === 'chat' ? 'Command Center' : section[0].toUpperCase()+section.slice(1)}</h1></div><div className="metrics"><span>{openTickets} open tickets</span><span>{activeAssets} active assets</span><span>{documents.length} docs</span><span>{notifications.filter(n=>!n.is_read).length} alerts</span><span>{currentOrganization?.name || 'No org'}</span></div></header>
        {error && <div className="errorBanner" role="alert">{error}</div>}

        {section === 'chat' && <div className="grid2">
          <div className="card"><div className="toolRow">{['general','it','business','creative'].map((item) => <button key={item} aria-pressed={tool === item} className={tool === item ? 'pill active' : 'pill'} onClick={() => setTool(item)}>{item}</button>)}</div><textarea value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Message OmniAI" placeholder="Ask OmniAI to troubleshoot, plan, analyze, or create..."/><div className="actions"><button onClick={sendMessage} disabled={busy || !message.trim()}>{busy ? 'Working...' : 'Send'}</button><button className="secondary" onClick={() => { setChatId(null); setResponse(''); }}>New chat</button></div><div className="answer"><pre>{response || 'Your AI response will appear here.'}</pre></div></div>
          <div className="card"><h3>Recent conversations</h3><div className="list">{chats.slice(0,10).map((chat) => <button className="listItem" key={chat.id} onClick={async () => { const data=await jsonApi(`/ai/chats/${chat.id}`); setChatId(chat.id); setResponse(data.messages.map((m:{role:string;content:string}) => `${m.role.toUpperCase()}: ${m.content}`).join('\n\n')); }}>{chat.title}</button>)}</div></div>
        </div>}


        {section === 'agents' && <div className="grid2"><div className="card"><h3>Agent Runtime 2.0</h3><p className="muted">Agents plan work, execute safe internal steps, and pause for approval before external integration actions.</p><select value={selectedAgentId ?? ''} onChange={(e)=>setSelectedAgentId(Number(e.target.value))}>{agents.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><textarea value={agentObjective} onChange={(e)=>setAgentObjective(e.target.value)} placeholder="Describe the objective for this agent"/><button onClick={startAgentRun} disabled={busy || !selectedAgentId || !agentObjective.trim()}>Start agent run</button><div className="list">{agents.map(a=><div className="record" key={a.id}><div><strong>{a.name}</strong><p>{a.description || a.slug}</p></div><span className="badge">{a.is_system?'system':'custom'}</span></div>)}</div></div><div className="card"><h3>Recent runs</h3><div className="list">{agentRuns.length===0?<p className="muted">No agent runs yet.</p>:agentRuns.map(r=><div className="record" key={r.id}><div style={{width:'100%'}}><strong>#{r.id} {r.objective}</strong><p>{r.summary || r.error || r.status}</p><div className="list">{r.steps.map(step=><div className="record" key={step.id}><div><strong>{step.position}. {step.title}</strong><p>{step.type} · {step.status}</p></div>{step.status==='waiting_approval'&&<div className="actions"><button onClick={()=>approveAgentStep(r.id,step.id,true)}>Approve</button><button className="danger" onClick={()=>approveAgentStep(r.id,step.id,false)}>Reject</button></div>}</div>)}</div></div><span className="badge">{r.status}</span></div>)}</div></div></div>}

        {section === 'codex' && <div className="codexLayout">
          <div className="card codexProjects"><h3>Codex projects</h3><div className="actions"><input value={codeProjectName} onChange={(e)=>setCodeProjectName(e.target.value)} placeholder="New project name"/><button onClick={createCodeProject} disabled={busy || !codeProjectName.trim()}>Create</button></div><div className="list">{codeProjects.map((p)=><button className={codeProjectId===p.id?'listItem selected':'listItem'} key={p.id} onClick={()=>openCodeProject(p.id)}><strong>{p.name}</strong><span className="smallText">{p.description || 'Code workspace'}</span></button>)}</div></div>
          <div className="card codexEditor"><h3>Workspace files</h3>{!codeProjectId ? <p className="muted">Create or select a project to start coding with Codex.</p> : <><div className="fileTabs">{codeFiles.map((f)=><button key={f.id} className="fileTab" onClick={()=>selectCodeFile(f)}>{f.path}</button>)}<button className="fileTab" onClick={()=>{setCodeFilePath('');setCodeFileContent('');setCodeFileLanguage('text')}}>+ new</button></div><div className="inlineFields"><input value={codeFilePath} onChange={(e)=>setCodeFilePath(e.target.value)} placeholder="src/example.ts"/><input value={codeFileLanguage} onChange={(e)=>setCodeFileLanguage(e.target.value)} placeholder="typescript"/></div><textarea className="codeEditor" value={codeFileContent} onChange={(e)=>setCodeFileContent(e.target.value)} placeholder="Paste or write project code here..."/><button onClick={saveCodeFile} disabled={busy || !codeFilePath.trim()}>Save file</button></>}</div>
          <div className="card codexAgent"><h3>Codex Developer</h3><p className="muted">Ask questions, review the workspace, propose implementations, or generate a test plan. Proposed edits are not applied until you approve them.</p><div className="toolRow">{['ask','review','implement','test_plan'].map((m)=><button key={m} className={codeMode===m?'pill active':'pill'} onClick={()=>setCodeMode(m)}>{m.replace('_',' ')}</button>)}</div><textarea value={codeInstruction} onChange={(e)=>setCodeInstruction(e.target.value)} placeholder="Example: Add a secure password reset flow and explain the changes."/><button onClick={runCodeTask} disabled={busy || !codeProjectId || !codeInstruction.trim()}>{busy?'Codex working...':'Run Codex task'}</button>{codeResult && <div className="answer codexAnswer"><h4>{codeResult.result.summary || 'Codex result'}</h4><pre>{codeResult.result.answer || ''}</pre>{(codeResult.result.files?.length||0)>0 && <><p><strong>Proposed files:</strong> {codeResult.result.files?.map((f)=>f.path).join(', ')}</p>{(codeResult.result.diffs?.length||0)>0&&<div>{codeResult.result.diffs?.map((d)=><div key={d.path}><strong>{d.path}</strong><pre>{d.diff}</pre></div>)}</div>}<button onClick={()=>applyCodeTask(codeResult.id)} disabled={busy || !!codeResult.applied_at}>{codeResult.applied_at?'Changes applied':'Apply proposed changes'}</button></>}{(codeResult.result.test_plan?.length||0)>0 && <div><strong>Test plan</strong><ul>{codeResult.result.test_plan?.map((x,i)=><li key={i}>{x}</li>)}</ul></div>}{(codeResult.result.risks?.length||0)>0 && <div><strong>Risks</strong><ul>{codeResult.result.risks?.map((x,i)=><li key={i}>{x}</li>)}</ul></div>}</div>}</div>
          <div className="card codexHistory"><h3>Task history</h3><div className="list">{codeTasks.map((t)=><button className="listItem" key={t.id} onClick={()=>setCodeResult(t)}><strong>{t.mode.replace('_',' ')}</strong><span className="smallText">{t.instruction}</span><span className="smallText">{t.model}{t.applied_at?' · applied':''}</span></button>)}</div><h3>Revisions</h3><div className="list">{codeRevisions.map(r=><div className="record" key={r.id}><div><strong>{r.path}</strong><p>{new Date(r.created_at).toLocaleString()}</p></div><button className="secondary" onClick={()=>rollbackCodeRevision(r.id)} disabled={busy||!!r.rolled_back_at}>{r.rolled_back_at?'Rolled back':'Rollback'}</button></div>)}</div></div>
        </div>}

        {section === 'tickets' && <div className="grid2"><div className="card"><h3>Create ticket</h3><input value={ticketTitle} onChange={(e)=>setTicketTitle(e.target.value)} placeholder="Ticket title"/><textarea value={ticketDescription} onChange={(e)=>setTicketDescription(e.target.value)} placeholder="Describe the issue"/><select value={ticketPriority} onChange={(e)=>setTicketPriority(e.target.value)}><option>low</option><option>normal</option><option>high</option><option>critical</option></select><button onClick={createTicket} disabled={busy}>Create ticket</button></div><div className="card"><h3>Ticket queue</h3><div className="list">{tickets.map((t)=><div className="record" key={t.id}><div><strong>#{t.id} {t.title}</strong><p>{t.description || 'No description'}</p><span className="badge">{t.priority}</span></div><select value={t.status} onChange={(e)=>updateTicket(t.id,e.target.value)}><option value="open">open</option><option value="in_progress">in progress</option><option value="resolved">resolved</option><option value="closed">closed</option></select></div>)}</div></div></div>}

        {section === 'assets' && <div className="grid2"><div className="card"><h3>Add asset</h3><input value={assetName} onChange={(e)=>setAssetName(e.target.value)} placeholder="Asset name"/><input value={assetType} onChange={(e)=>setAssetType(e.target.value)} placeholder="Type (laptop, server, printer...)"/><input value={serialNumber} onChange={(e)=>setSerialNumber(e.target.value)} placeholder="Serial number"/><button onClick={createAsset} disabled={busy}>Add asset</button></div><div className="card"><h3>Inventory</h3><div className="list">{assets.map((a)=><div className="record" key={a.id}><div><strong>{a.name}</strong><p>{a.asset_type} · {a.serial_number || 'No serial'}</p></div><span className="badge">{a.status}</span></div>)}</div></div></div>}

        {section === 'documents' && <div className="grid2"><div className="card"><h3>Knowledge base</h3><label className="upload">Upload PDF, DOCX, TXT, or CSV<input type="file" onChange={(e)=>uploadDocument(e.target.files?.[0])}/></label><div className="list">{documents.map((d)=><div className="record" key={d.id}><div><strong>{d.filename}</strong><p>{d.indexed_chunks} indexed chunks</p></div></div>)}</div></div><div className="card"><h3>Ask your documents</h3><select value={selectedDocument} onChange={(e)=>setSelectedDocument(e.target.value ? Number(e.target.value) : '')}><option value="">All documents</option>{documents.map((d)=><option key={d.id} value={d.id}>{d.filename}</option>)}</select><textarea value={documentQuestion} onChange={(e)=>setDocumentQuestion(e.target.value)} placeholder="What do these documents say about...?"/><button onClick={askDocuments} disabled={busy}>{busy ? 'Searching...' : 'Ask knowledge base'}</button><div className="answer"><pre>{documentAnswer || 'Document-grounded answers will appear here.'}</pre></div></div></div>}


        {section === 'workflows' && <div className="grid2"><div className="card"><h3>Create automation</h3><input value={workflowName} onChange={(e)=>setWorkflowName(e.target.value)} placeholder="Workflow name"/><textarea value={workflowPrompt} onChange={(e)=>setWorkflowPrompt(e.target.value)} placeholder="AI prompt with {input}"/><input value={workflowInput} onChange={(e)=>setWorkflowInput(e.target.value)} placeholder="Default/run input"/><button onClick={createWorkflow} disabled={busy}>Create workflow</button></div><div className="card"><h3>Automations</h3><div className="list">{workflows.map(w=><div className="record" key={w.id}><div><strong>{w.name}</strong><p>{w.description || 'Automation workflow'}</p></div><div className="actions"><button onClick={()=>runWorkflow(w.id)}>Run</button><button className="secondary" onClick={()=>scheduleWorkflow(w.id)}>Schedule hourly</button></div></div>)}</div></div></div>}

        {section === 'integrations' && <div className="grid2"><div className="card"><h3>Connect a service</h3><select value={integrationProvider} onChange={(e)=>setIntegrationProvider(e.target.value)}><option value="github">GitHub</option><option value="google">Google Workspace</option><option value="microsoft">Microsoft 365</option><option value="webhook">Webhook</option></select><input value={integrationName} onChange={(e)=>setIntegrationName(e.target.value)} placeholder="Connection name"/><input type="password" value={integrationSecret} onChange={(e)=>setIntegrationSecret(e.target.value)} placeholder="Access token / bearer secret"/><textarea value={integrationConfig} onChange={(e)=>setIntegrationConfig(e.target.value)} placeholder='{"repo":"owner/repo"}'/><button onClick={createIntegration} disabled={busy || !user?.is_admin}>Add integration</button>{!user?.is_admin && <p className="muted">Administrator access is required to add or change connections.</p>}</div><div className="card"><h3>Connections</h3><div className="list">{integrations.map(i=><div className="record" key={i.id}><div><strong>{i.name}</strong><p>{i.provider} · {i.enabled?'enabled':'disabled'} · {i.has_secret?'secret configured':'no secret'}</p><span className="smallText">{i.actions.join(', ')}</span></div>{user?.is_admin && <button className="secondary" onClick={()=>testIntegration(i.id)}>Test</button>}</div>)}</div></div></div>}

        {section === 'notifications' && <div className="card"><h3>Notifications</h3><div className="list">{notifications.length===0?<p className="muted">No notifications yet.</p>:notifications.map(n=><button className="listItem" key={n.id} onClick={()=>markNotification(n.id)}><strong>{n.is_read?'':'● '}{n.title}</strong><span className="smallText">{n.body}</span><span className="smallText">{n.level} · {new Date(n.created_at).toLocaleString()}</span></button>)}</div></div>}

        {section === 'organization' && <div className="grid2"><div className="card"><h3>Current organization</h3><h2>{currentOrganization?.name || 'Organization'}</h2><p className="muted">Role: {currentOrganization?.role || 'member'} · {currentOrganization?.onboarding_complete ? 'Onboarding complete' : 'Setup incomplete'}</p>{!currentOrganization?.onboarding_complete && <button onClick={completeOnboarding}>Complete onboarding</button>}<h3>Your organizations</h3><div className="list">{organizations.map(o=><div className="record" key={o.id}><div><strong>{o.name}</strong><p>{o.role} · {o.slug}</p></div>{!o.is_current && <button className="secondary" onClick={()=>switchOrganization(o.id)}>Switch</button>}</div>)}</div><input value={organizationName} onChange={(e)=>setOrganizationName(e.target.value)} placeholder="New organization name"/><button onClick={createOrganization} disabled={busy}>Create organization</button></div><div className="card"><h3>Members</h3><div className="list">{members.map(m=><div className="record" key={m.id}><div><strong>{m.full_name || m.email}</strong><p>{m.email}</p></div><span className="badge">{m.role}</span></div>)}</div><input value={memberEmail} onChange={(e)=>setMemberEmail(e.target.value)} placeholder="Invite email"/><select value={inviteRole} onChange={(e)=>setInviteRole(e.target.value)}><option value="member">Member</option><option value="admin">Admin</option><option value="customer">Customer</option></select><button onClick={addOrganizationMember}>Send invitation</button><h3>Subscription</h3><div className="metricGrid"><div><strong>{subscription?.plan || '-'}</strong><span>plan</span></div><div><strong>{subscription?.status || '-'}</strong><span>status</span></div><div><strong>{subscription?.seats ?? '-'}</strong><span>seats</span></div></div><div className="actions"><button className="secondary" onClick={()=>startCheckout("professional")}>Upgrade to Professional</button><button className="secondary" onClick={()=>startCheckout("enterprise")}>Upgrade to Enterprise</button></div><p className="muted">Stripe Checkout activates when Stripe keys and plan price IDs are configured.</p></div></div>}

        {section === 'portal' && <div className="grid2"><div className="card"><h3>Customer portal</h3><div className="metricGrid"><div><strong>{portalSummary?.open_tickets ?? '-'}</strong><span>open tickets</span></div><div><strong>{portalSummary?.assets ?? '-'}</strong><span>assets</span></div><div><strong>{portalSummary?.documents ?? '-'}</strong><span>documents</span></div><div><strong>{portalSummary?.my_requests ?? '-'}</strong><span>my requests</span></div></div><input value={portalSubject} onChange={(e)=>setPortalSubject(e.target.value)} placeholder="Request subject"/><textarea value={portalDescription} onChange={(e)=>setPortalDescription(e.target.value)} placeholder="How can we help?"/><button onClick={createPortalRequest} disabled={busy}>Submit request</button></div><div className="card"><h3>My requests</h3><div className="list">{portalRequests.length===0?<p className="muted">No portal requests yet.</p>:portalRequests.map(r=><div className="record" key={r.id}><div><strong>{r.subject}</strong><p>{r.description || 'No description'}</p></div><span className="badge">{r.status}</span></div>)}</div></div></div>}


        {section === 'security' && <div className="grid2"><div className="card"><h3>Multi-factor authentication</h3><p className="muted">Protect your account with a 6-digit authenticator-app code.</p><p>Status: <strong>{user?.mfa_enabled?'Enabled':'Not enabled'}</strong></p>{!user?.mfa_enabled && !mfaSetup && <button onClick={setupMfa}>Set up MFA</button>}{mfaSetup && <><p>In your authenticator app, add this secret:</p><div className="answer"><pre>{mfaSetup.secret}</pre></div><p className="muted">You can also use the provisioning URI in an authenticator that supports manual URI import.</p><input placeholder="6-digit code" value={mfaCode} onChange={e=>setMfaCode(e.target.value.replace(/\D/g,'').slice(0,6))}/><button onClick={confirmMfa} disabled={mfaCode.length!==6}>Confirm and enable</button></>}{user?.mfa_enabled && <><input placeholder="6-digit code" value={mfaCode} onChange={e=>setMfaCode(e.target.value.replace(/\D/g,'').slice(0,6))}/><button className="danger" onClick={disableMfa} disabled={mfaCode.length!==6}>Disable MFA</button></>}</div><div className="card"><h3>Enterprise identity</h3><p className="muted">Generic OpenID Connect SSO is available when an administrator configures OIDC issuer/client credentials in the production environment.</p><h3>Session security</h3><p className="muted">Password changes, logout, account disablement, and MFA changes revoke existing access tokens.</p></div></div>}
        {section === 'admin' && user?.is_admin && <div className="adminGrid"><div className="card"><h3>System</h3><div className="metricGrid"><div><strong>{adminSystem?.users ?? '-'}</strong><span>users</span></div><div><strong>{adminSystem?.active_users ?? '-'}</strong><span>active</span></div><div><strong>{adminUsage?.events ?? '-'}</strong><span>30-day events</span></div><div><strong>{adminSystem?.openai_configured ? 'Ready' : 'Missing'}</strong><span>AI provider</span></div></div><p className="muted">Version {adminSystem?.version || '2.1.0'} · {adminSystem?.environment || 'development'} · {monitoring?.organizations ?? '-'} orgs · {monitoring?.enabled_schedules ?? '-'} schedules</p></div><div className="card"><h3>Platform settings</h3><input value={adminSettings?.organization_name || ''} onChange={(e)=>setAdminSettings({...adminSettings,organization_name:e.target.value})} placeholder="Organization name"/><input value={adminSettings?.default_ai_model || ''} onChange={(e)=>setAdminSettings({...adminSettings,default_ai_model:e.target.value})} placeholder="Default AI model"/><input value={adminSettings?.default_code_model || ''} onChange={(e)=>setAdminSettings({...adminSettings,default_code_model:e.target.value})} placeholder="Default code model"/><button onClick={saveAdminSettings}>Save settings</button></div><div className="card adminUsers"><h3>User administration</h3><p className="muted">Disabling an account immediately invalidates its current sessions.</p><div className="list">{users.map((u)=><div className="record" key={u.id}><div><strong>{u.full_name || u.email}</strong><p>{u.email} · {u.is_active ? 'active' : 'disabled'}</p></div><div className="actions"><button className={u.is_admin ? 'danger' : 'secondary'} onClick={()=>updateUser(u,{is_admin:!u.is_admin})}>{u.is_admin ? 'Remove admin' : 'Make admin'}</button><button className={u.is_active ? 'danger' : 'secondary'} onClick={()=>updateUser(u,{is_active:!u.is_active})}>{u.is_active ? 'Disable' : 'Enable'}</button></div></div>)}</div></div></div>}
      </section>
    </main>
  );
}
