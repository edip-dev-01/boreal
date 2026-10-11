import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App'
import type { RecordDetail } from './types'
vi.mock('./MapPanel', () => ({ default: () => <div aria-label="Mock facility map"/> }))
const base: RecordDetail = { id: 'FAC-001', name: 'North Library', kind: 'library', longitude: -75.7, latitude: 45.4, updated_at: '2026-10-10', freshness: 'fresh', access: 'public', summary: 'A fictional library.', status: 'open', conflict: false, missing_fields: [], source_ids: ['SRC-001'], provenance: [{field:'name',value:'North Library',source_id:'SRC-001',source_title:'Synthetic register',observed_at:'2026-10-10'}], sources:[{id:'SRC-001',title:'Synthetic register',type:'register',license:'Synthetic demonstration data',synthetic:true,url:'/api/sources/SRC-001'}], links:[], reports:[] }
const restricted = { ...base, id: 'FAC-SECRET', name: 'Restricted canary', access: 'restricted' as const }
let role: 'reader'|'analyst' | null = null
const fetchMock = vi.fn()
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }) }
beforeEach(() => {
  role = null
  Element.prototype.scrollIntoView = vi.fn()
  fetchMock.mockImplementation(async (input: string, init: RequestInit = {}) => {
    if (input === '/api/session') return json({authenticated:false})
    if (input === '/api/login') { role = JSON.parse(String(init.body)).role; return json({authenticated:true,role,csrf_token:'demo-csrf'}) }
    if (input === '/api/logout') { role = null; return new Response(null,{status:204}) }
    if (input.startsWith('/api/records?')) return json({records:role === 'analyst' ? [base,restricted] : [base],count:role === 'analyst' ? 2 : 1,as_of:'2026-10-11'})
    if (input === '/api/records/FAC-001') return json(base)
    if (input === '/api/records/FAC-SECRET') return json(restricted)
    if (input === '/api/ask') return json({answer:'There is 1 visible facility.',evidence:[{record_id:'FAC-001',label:'North Library'}],supported:true,engine:'deterministic-rules',as_of:'2026-10-11'})
    return json({detail:'Not found'},404)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); fetchMock.mockReset() })
describe('demo workspace', () => {
  it('enters reader view and links a facility to its local provenance', async () => {
    render(<App/>); fireEvent.click(await screen.findByRole('button',{name:'Explore as Reader'}))
    expect(await screen.findByRole('heading',{name:'North Library'})).toBeInTheDocument()
    expect(screen.queryByText('Restricted canary')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab',{name:/Evidence/}))
    expect(await screen.findByRole('link',{name:'Source reference'})).toHaveAttribute('href','/api/sources/SRC-001')
    expect(screen.getByText('This record and all linked evidence are fictional.')).toBeInTheDocument()
  })
  it('clears analyst data and answers on logout before reader sign-in', async () => {
    render(<App/>); fireEvent.click(await screen.findByRole('button',{name:'Explore as Analyst'}))
    expect(await screen.findByText('Restricted canary')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Count facilities'}))
    expect(await screen.findByTestId('question-answer')).toHaveTextContent('There is 1 visible facility.')
    fireEvent.click(screen.getByRole('button',{name:'Sign out'}))
    expect(screen.queryByText('Restricted canary')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button',{name:'Explore as Reader'}))
    await screen.findByRole('heading',{name:'North Library'})
    expect(screen.queryByText('Restricted canary')).not.toBeInTheDocument()
    expect(screen.queryByTestId('question-answer')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/logout',expect.objectContaining({headers:{'X-CSRF-Token':'demo-csrf'}}))
  })
  it('sends filters to the server and clears a prior answer when filters change', async () => {
    render(<App/>); fireEvent.click(await screen.findByRole('button',{name:'Explore as Reader'}))
    await screen.findByRole('heading',{name:'North Library'})
    fireEvent.click(screen.getByRole('button',{name:'Count facilities'}))
    await screen.findByTestId('question-answer')
    fireEvent.change(screen.getByLabelText('Freshness'),{target:{value:'stale'}})
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/records?q=&freshness=stale',expect.anything()))
    expect(screen.queryByTestId('question-answer')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search facilities'),{target:{value:'library'}})
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/records?q=library&freshness=stale',expect.anything()))
    fireEvent.click(screen.getByRole('button',{name:'Reset'}))
    expect(screen.getByLabelText('Search facilities')).toHaveValue('')
  })
  it('adds CSRF and exact supported question to deterministic requests', async () => {
    render(<App/>); fireEvent.click(await screen.findByRole('button',{name:'Explore as Reader'}))
    await screen.findByRole('heading',{name:'North Library'})
    fireEvent.click(screen.getByRole('button',{name:'Missing coordinates'}))
    const answer = await screen.findByTestId('question-answer')
    expect(within(answer).getByRole('button',{name:/North Library/})).toBeInTheDocument()
    const askCall = fetchMock.mock.calls.find(([url]) => url === '/api/ask')
    expect(askCall?.[1].headers['X-CSRF-Token']).toBe('demo-csrf')
    expect(JSON.parse(askCall?.[1].body).question).toBe('missing coordinates')
  })
})
