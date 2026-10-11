import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import MapPanel from './MapPanel'
import { api, ApiError, dateLabel, fieldLabel, queryString, safeSourceUrl } from './api'
import { Brand, Icon } from './icons'
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from './config'
import type { Answer, Bbox, CivicRecord, Filters, Freshness, RecordDetail, RecordResponse, Role, Session } from './types'

const INITIAL_FILTERS: Filters = { q: '', freshness: 'all', bbox: null }
const SUGGESTIONS = ['count facilities', 'stale facilities', 'conflicting reports', 'missing coordinates']

function errorText(error: unknown): string { return error instanceof Error ? error.message : 'Something went wrong. Please try again.' }
function FreshnessBadge({ value }: { value: CivicRecord['freshness'] }) { return <span className={`freshness-badge ${value}`}><i className={`dot ${value}`}/>{value === 'missing' ? 'Undated' : value === 'fresh' ? 'Fresh' : 'Stale'}</span> }
function Loading({ text }: { text: string }) { return <div className="loading" role="status"><span className="spinner"/>{text}</div> }
function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="error-notice" role="alert"><Icon name="alert"/><span>{message}</span>{onRetry && <button onClick={onRetry}>Try again</button>}</div> }

function SignIn({ loading, error, onLogin }: { loading: Role | 'session' | null; error: string; onLogin: (role: Role) => void }) {
  return <div className="login-page">
    <div className="login-top"><Brand/><span className="demo-label"><i/> SYNTHETIC DEMO</span></div>
    <main className="login-main">
      <section className="login-intro"><div className="eyebrow">A CLEARER VIEW OF CONNECTED DATA</div><h1>Find the place.<br/>Follow the evidence.</h1><p>A geospatial workspace for exploring civic facilities, connecting source records, and understanding what your data can actually tell you.</p>
        <div className="intro-features"><span><Icon name="layers"/>Linked records</span><span><Icon name="shield"/>Role-based views</span><span><Icon name="link"/>Traceable evidence</span></div>
        <div className="login-map" aria-hidden="true"><div className="login-map-grid"/><div className="login-river"/><span className="map-district d1">NORTH REACH</span><span className="map-district d2">RIVER QUARTER</span><span className="login-node n1"/><span className="login-node n2"/><span className="login-node n3"/><span className="login-node n4"/><span className="login-map-tag"><Icon name="pin" size={15}/> Civic discovery, connected.</span><span className="login-map-caption">FICTIONAL GEOGRAPHY · ILLUSTRATIVE ONLY</span></div>
      </section>
      <section className="login-card" aria-labelledby="login-title"><div className="login-card-icon"><Icon name="globe" size={26}/></div><div className="eyebrow">ENTER THE WORKSPACE</div><h2 id="login-title">Choose your perspective</h2><p>Try a demo role to see how access changes the records and evidence available to you.</p>
        {error && <ErrorNotice message={error}/>}
        {loading === 'session' ? <Loading text="Checking your demo session…"/> : <div className="role-options">
          <button className="role-card" aria-label="Explore as Reader" disabled={loading !== null} onClick={() => onLogin('reader')}><span className="role-icon"><Icon name="globe" size={23}/></span><span><strong>Explore as Reader</strong><small>Public synthetic facilities and sources</small></span>{loading === 'reader' ? <span className="spinner"/> : <Icon name="arrow"/>}</button>
          <button className="role-card" aria-label="Explore as Analyst" disabled={loading !== null} onClick={() => onLogin('analyst')}><span className="role-icon"><Icon name="layers" size={23}/></span><span><strong>Explore as Analyst</strong><small>Public + restricted synthetic records</small></span>{loading === 'analyst' ? <span className="spinner"/> : <Icon name="arrow"/>}</button>
        </div>}
        <div className="login-disclaimer"><Icon name="shield" size={17}/><p>No account or password required. Roles are selectable for demonstration only. This is not a production identity system.</p></div>
      </section>
    </main>
    <footer className="login-footer"><span>{PRODUCT_SUBTITLE}</span><span>Fictional data. No real operational information.</span></footer>
  </div>
}

function DetailPanel({ detail, loading, error, onSelect, onRetry }: { detail: RecordDetail | null; loading: boolean; error: string; onSelect: (id: string) => void; onRetry: () => void }) {
  const [tab, setTab] = useState<'overview' | 'evidence'>('overview')
  useEffect(() => setTab('overview'), [detail?.id])
  return <aside className="detail-panel" aria-label="Selected facility details">
    <div className="panel-heading"><span className="eyebrow">RECORD INSPECTOR</span><Icon name="layers" size={17}/></div>
    {loading ? <Loading text="Loading record evidence…"/> : error ? <ErrorNotice message={error} onRetry={onRetry}/> : !detail ? <div className="empty-state detail-empty"><span className="empty-icon"><Icon name="pin" size={28}/></span><h3>A place to look closer</h3><p>Select a map point or a result to inspect its sources, freshness, and connected records.</p></div> : <>
      <div className="detail-title"><div className="record-id">{detail.id}<span className={`access-tag ${detail.access}`}><Icon name="shield" size={11}/>{detail.access}</span></div><h2>{detail.name}</h2><div className="detail-meta"><span>{fieldLabel(detail.kind)}</span><FreshnessBadge value={detail.freshness}/></div></div>
      <div className="detail-tabs" role="tablist" aria-label="Record details"><button role="tab" aria-selected={tab === 'overview'} onClick={() => setTab('overview')}>Overview</button><button role="tab" aria-selected={tab === 'evidence'} onClick={() => setTab('evidence')}>Evidence <span>{detail.provenance.length}</span></button></div>
      <div className="detail-content" role="tabpanel" aria-label={tab === 'overview' ? 'Overview' : 'Evidence'}>
        {tab === 'overview' ? <>
          <p className="record-summary">{detail.summary}</p>
          {(detail.conflict || detail.missing_fields.length > 0) && <div className="quality-note"><Icon name="alert" size={17}/><div>{detail.conflict && <strong>Source conflict requires review</strong>}{detail.conflict && <p>Reported values differ. Check the evidence before relying on this record.</p>}{detail.missing_fields.length > 0 && <p>Missing: {detail.missing_fields.map(fieldLabel).join(', ')}.</p>}</div></div>}
          <dl className="record-facts"><div><dt>Status</dt><dd><span className="status-dot"/>{fieldLabel(detail.status)}</dd></div><div><dt>Last updated</dt><dd>{dateLabel(detail.updated_at)}</dd></div><div><dt>Coordinates</dt><dd className="coordinate-value">{detail.latitude !== null && detail.longitude !== null ? `${detail.latitude.toFixed(4)}, ${detail.longitude.toFixed(4)}` : 'Not reported'}</dd></div><div><dt>Visible sources</dt><dd>{detail.sources.length} linked {detail.sources.length === 1 ? 'source' : 'sources'}</dd></div></dl>
          <section className="detail-section"><h3><Icon name="link" size={15}/> Connected records <span>{detail.links.length}</span></h3>{detail.links.length ? <div className="connected-list">{detail.links.map(link => <button key={link.record_id} onClick={() => onSelect(link.record_id)}><span><small>{link.record_id}</small>{link.label}</span><Icon name="chevron" size={16}/></button>)}</div> : <p className="muted small">No connected records visible to this role.</p>}</section>
          <section className="detail-section"><h3><Icon name="clock" size={15}/> Reports <span>{detail.reports.length}</span></h3>{detail.reports.length ? detail.reports.map(report => <article className="report" key={report.id}><h4>{report.title}</h4><p>{report.text}</p><time>{dateLabel(report.observed_at)}</time></article>) : <p className="muted small">No reports visible to this role.</p>}</section>
        </> : <>
          <p className="evidence-intro">Field-level provenance links each reported value to its source. Conflicting values are retained for review.</p>
          <div className="provenance-list">{detail.provenance.map((item,index) => <article className="provenance-item" key={`${item.field}-${item.source_id}-${index}`}><div className="provenance-field">{fieldLabel(item.field)}</div><div className="provenance-value">{item.value === null ? 'Not reported' : typeof item.value === 'object' ? JSON.stringify(item.value) : String(item.value)}</div><a href={`#source-${item.source_id}`}><Icon name="link" size={12}/>{item.source_title}</a><time>{dateLabel(item.observed_at)}</time></article>)}</div>
          <section className="detail-section"><h3>Source register <span>{detail.sources.length}</span></h3>{detail.sources.map(source => <article id={`source-${source.id}`} className="source-card" key={source.id}><div className="source-title">{source.title}</div><div className="source-kind">{source.type} · SYNTHETIC</div><p>{source.license}</p>{safeSourceUrl(source.url) && <a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer">Source reference <Icon name="arrow" size={12}/></a>}</article>)}</section>
        </>}
        <div className="synthetic-footnote"><Icon name="shield" size={13}/> This record and all linked evidence are fictional.</div>
      </div>
    </>}
  </aside>
}

function QuestionPanel({ filters, csrfToken, onSelect, onExpired }: { filters: Filters; csrfToken?: string; onSelect: (id: string) => void; onExpired: () => void }) {
  const [question,setQuestion] = useState('')
  const [answer,setAnswer] = useState<Answer | null>(null)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const request = useRef<AbortController | null>(null)
  useEffect(() => { request.current?.abort(); setAnswer(null); setError(''); setBusy(false) }, [filters])
  useEffect(() => () => request.current?.abort(), [])
  async function ask(value: string) {
    if (!value.trim() || busy) return
    request.current?.abort()
    const controller = new AbortController(); request.current = controller
    setQuestion(value); setAnswer(null); setError(''); setBusy(true)
    try {
      const response = await api<Answer>('/ask', { method: 'POST', signal: controller.signal, headers: { 'X-CSRF-Token': csrfToken || '' }, body: JSON.stringify({ question: value.trim(), q: filters.q, freshness: filters.freshness, ...(filters.bbox ? { bbox: filters.bbox.join(',') } : {}) }) })
      if (!controller.signal.aborted) setAnswer(response)
    } catch (err) { if (!controller.signal.aborted) { if (err instanceof ApiError && err.status === 401) onExpired(); else setError(errorText(err)) } }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <section className="question-panel" aria-labelledby="question-heading"><div className="question-heading"><div className="question-icon"><Icon name="spark" size={22}/></div><div><h2 id="question-heading">Ask this view</h2><p>Evidence-backed answers from your visible, filtered records.</p></div><span className="rules-tag">DETERMINISTIC RULES</span></div>
    <form className="question-form" onSubmit={(event: FormEvent) => { event.preventDefault(); void ask(question) }}><label className="sr-only" htmlFor="question">Question about visible facilities</label><input id="question" maxLength={500} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Which facilities need a closer look?"/><button disabled={busy || !question.trim()} type="submit">{busy ? <span className="spinner"/> : <Icon name="arrow"/>}<span className="sr-only">Ask question</span></button></form>
    <div className="question-suggestions">{SUGGESTIONS.map((suggestion,index) => <button disabled={busy} key={suggestion} onClick={() => void ask(suggestion)}>{['Count facilities','Stale records','Conflicting reports','Missing coordinates'][index]}<Icon name="arrow" size={13}/></button>)}</div>
    {busy && <Loading text="Checking the visible records…"/>}{error && <ErrorNotice message={error}/>}
    {answer && <div className={`answer ${answer.supported ? '' : 'unsupported'}`} aria-live="polite" data-testid="question-answer"><div className="answer-label"><Icon name={answer.supported ? 'check' : 'alert'} size={15}/>{answer.supported ? 'ANSWER FROM VISIBLE DATA' : 'OUTSIDE DEMO QUESTION SCOPE'}</div><p>{answer.answer}</p>{answer.evidence.length > 0 && <div className="answer-evidence">{answer.evidence.map((evidence,index) => <button key={`${evidence.record_id}-${index}`} onClick={() => onSelect(evidence.record_id)}><span>{index + 1}</span>{evidence.label}<Icon name="chevron" size={12}/></button>)}</div>}<small>Dataset as of {dateLabel(answer.as_of)} · Rule-based response, no language model</small></div>}
    <p className="question-note">Supports facility counts, freshness, conflicts, and missing coordinates. No forecasting or operational advice.</p>
  </section>
}

export default function App() {
  const [session,setSession] = useState<Session>({ authenticated: false })
  const [authBusy,setAuthBusy] = useState<Role | 'session' | null>('session')
  const [authError,setAuthError] = useState('')
  const [filters,setFilters] = useState<Filters>(INITIAL_FILTERS)
  const [search,setSearch] = useState('')
  const [records,setRecords] = useState<CivicRecord[]>([])
  const [asOf,setAsOf] = useState('')
  const [recordsBusy,setRecordsBusy] = useState(false)
  const [recordsError,setRecordsError] = useState('')
  const [selectedId,setSelectedId] = useState<string | null>(null)
  const [detail,setDetail] = useState<RecordDetail | null>(null)
  const [detailBusy,setDetailBusy] = useState(false)
  const [detailError,setDetailError] = useState('')
  const [retry,setRetry] = useState(0)
  const generation = useRef(0)
  useEffect(() => { document.title = `${PRODUCT_NAME} · Geospatial discovery demo` }, [])
  useEffect(() => {
    const controller = new AbortController()
    api<Session>('/session',{ signal: controller.signal }).then(setSession).catch(err => { if (!controller.signal.aborted) setAuthError(errorText(err)) }).finally(() => { if (!controller.signal.aborted) setAuthBusy(null) })
    return () => controller.abort()
  }, [])
  useEffect(() => { const timer = window.setTimeout(() => setFilters(current => current.q === search ? current : { ...current, q: search }),250); return () => window.clearTimeout(timer) },[search])
  function clearData() { generation.current++; setRecords([]); setDetail(null); setSelectedId(null); setAsOf(''); setRecordsError(''); setDetailError(''); setFilters(INITIAL_FILTERS); setSearch('') }
  function expired() { clearData(); setSession({ authenticated: false }); setAuthError('Your demo session has ended. Choose a role to continue.') }
  async function login(role: Role) {
    if (authBusy !== null) return
    clearData(); setAuthBusy(role); setAuthError(''); setSession({ authenticated: false })
    try { setSession(await api<Session>('/login',{ method: 'POST', body: JSON.stringify({ role }) })) }
    catch (err) { setAuthError(errorText(err)) }
    finally { setAuthBusy(null) }
  }
  async function logout() {
    const token = session.csrf_token
    clearData(); setSession({ authenticated: false }); setAuthBusy('session'); setAuthError('')
    try { await api<Session>('/logout',{ method: 'POST', headers: { 'X-CSRF-Token': token || '' } }) }
    catch (err) { setAuthError(`The local view was cleared, but logout could not be confirmed. ${errorText(err)}`) }
    finally { setAuthBusy(null) }
  }
  useEffect(() => {
    if (!session.authenticated) return
    const controller = new AbortController(); const currentGeneration = generation.current
    setRecordsBusy(true); setRecordsError('')
    api<RecordResponse>(`/records?${queryString(filters)}`,{ signal: controller.signal }).then(response => {
      if (controller.signal.aborted || generation.current !== currentGeneration) return
      // The API is the authorization boundary; this check also prevents accidental UI disclosure.
      const visible = session.role === 'reader' ? response.records.filter(record => record.access === 'public') : response.records
      setRecords(visible); setAsOf(response.as_of)
      setSelectedId(current => visible.some(record => record.id === current) ? current : visible[0]?.id || null)
    }).catch(err => { if (!controller.signal.aborted) { setRecords([]); setSelectedId(null); if (err instanceof ApiError && err.status === 401) { generation.current++; setSession({authenticated:false}); setDetail(null); setAuthError('Your demo session has ended. Choose a role to continue.') } else setRecordsError(errorText(err)) } }).finally(() => { if (!controller.signal.aborted) setRecordsBusy(false) })
    return () => controller.abort()
  }, [session.authenticated, session.role, filters, retry])
  useEffect(() => {
    setDetail(null); setDetailError('')
    if (!session.authenticated || !selectedId) { setDetailBusy(false); return }
    const controller = new AbortController(); const currentGeneration = generation.current
    setDetailBusy(true)
    api<RecordDetail>(`/records/${encodeURIComponent(selectedId)}`,{ signal: controller.signal }).then(response => { if (!controller.signal.aborted && currentGeneration === generation.current && !(session.role === 'reader' && response.access === 'restricted')) setDetail(response) }).catch(err => { if (!controller.signal.aborted) setDetailError(errorText(err)) }).finally(() => { if (!controller.signal.aborted) setDetailBusy(false) })
    return () => controller.abort()
  }, [session.authenticated, session.role, selectedId, retry])
  function selectRecord(id: string) { setSelectedId(id); document.getElementById('workspace')?.scrollIntoView({ block: 'start', behavior: 'smooth' }) }
  function resetFilters() { setSearch(''); setFilters(INITIAL_FILTERS) }
  if (!session.authenticated) return <SignIn loading={authBusy} error={authError} onLogin={role => void login(role)}/>
  const hasFilters = filters.q || filters.freshness !== 'all' || filters.bbox !== null
  const staleCount = records.filter(record => record.freshness === 'stale').length
  const conflictCount = records.filter(record => record.conflict).length
  return <div className="app-shell">
    <div className="synthetic-banner"><span><i/> SYNTHETIC DEMO</span><p>Fictional civic data and schematic geography. For demonstration only.</p><span className="banner-right">NO LIVE DATA</span></div>
    <header className="app-header"><Brand small/><div className="header-divider"/><div className="workspace-label">Discovery workspace</div><div className="header-right"><span className="session-role"><Icon name="shield" size={15}/>{session.role === 'analyst' ? 'Analyst' : 'Reader'}<span>DEMO</span></span><button className="logout-button" onClick={() => void logout()}><span>Switch role</span></button><button className="logout-button signout-button" onClick={() => void logout()} aria-label="Sign out"><Icon name="logout" size={17}/><span>Sign out</span></button></div></header>
    <main className="workspace" id="workspace">
      <section className="page-title"><div><div className="eyebrow">CIVIC INFRASTRUCTURE / FICTIONAL CITY</div><h1>Every record has a place.</h1><p>Explore facilities. Inspect the evidence. Know what needs a second look.</p></div><div className="dataset-stamp"><span className="live-dot"/><div>DEMO SNAPSHOT<small>{asOf ? dateLabel(asOf) : 'Loading dataset'}</small></div></div></section>
      <section className="metrics" aria-label="Current filtered results summary"><div className="metric"><span className="metric-icon"><Icon name="pin" size={20}/></span><div><span className="metric-label">Visible facilities</span><strong data-testid="records-count">{recordsBusy ? '—' : records.length}<small>in current view</small></strong></div></div><div className="metric"><span className="metric-icon amber"><Icon name="clock" size={20}/></span><div><span className="metric-label">Stale records</span><strong>{recordsBusy ? '—' : staleCount}<small>freshness flagged</small></strong></div></div><div className="metric"><span className="metric-icon violet"><Icon name="layers" size={20}/></span><div><span className="metric-label">Source conflicts</span><strong>{recordsBusy ? '—' : conflictCount}<small>require review</small></strong></div></div><div className="metric access-metric"><span className="metric-icon"><Icon name="shield" size={20}/></span><div><span className="metric-label">Access scope</span><strong>{session.role === 'analyst' ? 'Extended' : 'Public'}<small>{session.role === 'analyst' ? 'includes restricted demo data' : 'public demo data only'}</small></strong></div></div></section>
      <section className="filter-bar" aria-label="Filter facilities"><div className="search-field"><Icon name="search" size={18}/><label className="sr-only" htmlFor="facility-search">Search facilities</label><input id="facility-search" placeholder="Search facilities, types, or keywords…" value={search} maxLength={200} onChange={event => setSearch(event.target.value)}/>{search && <button aria-label="Clear search" onClick={() => setSearch('')}><Icon name="close" size={15}/></button>}</div><div className="freshness-filter"><Icon name="clock" size={15}/><label htmlFor="freshness">Freshness</label><select id="freshness" value={filters.freshness} onChange={event => setFilters(current => ({ ...current, freshness: event.target.value as Freshness }))}><option value="all">All records</option><option value="fresh">Fresh</option><option value="stale">Stale</option><option value="missing">Undated</option></select></div>{filters.bbox && <button className="bbox-chip" onClick={() => setFilters(current => ({ ...current, bbox: null }))}><Icon name="target" size={14}/>Map bounds<Icon name="close" size={13}/></button>}{hasFilters && <button className="clear-filters" onClick={resetFilters}>Reset</button>}</section>
      <div className="work-grid"><div className="discovery-column"><MapPanel records={records} selectedId={selectedId} onSelect={selectRecord} onBbox={(bbox: Bbox) => setFilters(current => ({ ...current, bbox }))} bboxActive={filters.bbox !== null}/>
        <section className="results-panel" aria-labelledby="results-title"><div className="results-heading"><h2 id="results-title"><Icon name="table" size={16}/>Results <span>{records.length}</span></h2><span className="results-hint">Select a record to inspect</span></div>
          {recordsError ? <ErrorNotice message={recordsError} onRetry={() => setRetry(value => value + 1)}/> : recordsBusy ? <Loading text="Finding matching facilities…"/> : !records.length ? <div className="empty-state"><Icon name="search" size={26}/><h3>No facilities match this view</h3><p>Try a broader search or remove a filter.</p>{hasFilters && <button className="secondary-button" onClick={resetFilters}>Clear filters</button>}</div> : <div className="table-scroll"><table><thead><tr><th scope="col">Facility</th><th scope="col">Type</th><th scope="col">Freshness</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Quality flags</span></th></tr></thead><tbody>{records.map(record => <tr key={record.id} className={selectedId === record.id ? 'selected' : ''}><td><button className="record-select" onClick={() => selectRecord(record.id)} aria-pressed={selectedId === record.id}><span className="table-pin"><Icon name="pin" size={16}/></span><span><strong>{record.name}</strong><small>{record.id}{record.access === 'restricted' && ' · RESTRICTED'}</small></span></button></td><td className="kind-cell">{fieldLabel(record.kind)}</td><td><FreshnessBadge value={record.freshness}/></td><td className="updated-cell">{dateLabel(record.updated_at)}</td><td>{record.conflict && <span className="table-warning" title="Conflicting source reports" aria-label="Conflicting source reports"><Icon name="alert" size={15}/></span>}{(record.latitude === null || record.longitude === null) && <span className="unmapped-icon" title="Coordinates missing" aria-label="Coordinates missing"><Icon name="target" size={15}/></span>}</td></tr>)}</tbody></table></div>}
          <div className="results-footer"><span><Icon name="shield" size={12}/>Visibility enforced by the API</span><span>{records.length} records · {records.filter(record => record.latitude !== null && record.longitude !== null).length} mapped</span></div>
        </section>
      </div><DetailPanel detail={detail} loading={detailBusy} error={detailError} onSelect={selectRecord} onRetry={() => setRetry(value => value + 1)}/></div>
      <QuestionPanel key={session.role} filters={filters} csrfToken={session.csrf_token} onSelect={selectRecord} onExpired={expired}/>
      <footer className="workspace-footer"><span>{PRODUCT_NAME} · {PRODUCT_SUBTITLE}</span><span>Original demo · Not for operational decisions</span></footer>
    </main>
  </div>
}
