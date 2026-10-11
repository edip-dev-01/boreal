export type Role = 'reader' | 'analyst'
export type Freshness = 'all' | 'fresh' | 'stale' | 'missing'
export type Bbox = [number, number, number, number]
export interface Session { authenticated: boolean; role?: Role; csrf_token?: string }
export interface CivicRecord {
  id: string; name: string; kind: string; longitude: number | null; latitude: number | null;
  updated_at: string | null; freshness: Exclude<Freshness, 'all'>; access: 'public' | 'restricted';
  summary: string; status: string; conflict: boolean; missing_fields: string[]; source_ids: string[];
}
export interface RecordDetail extends CivicRecord {
  provenance: { field: string; value: unknown; source_id: string; source_title: string; observed_at: string | null }[];
  sources: { id: string; title: string; type: string; license: string; synthetic: true; url: string }[];
  links: { record_id: string; label: string }[];
  reports: { id: string; title: string; text: string; observed_at: string | null }[];
}
export interface RecordResponse { records: CivicRecord[]; count: number; as_of: string }
export interface Answer { answer: string; evidence: { record_id: string; label: string }[]; supported: boolean; engine: 'deterministic-rules'; as_of: string }
export interface Filters { q: string; freshness: Freshness; bbox: Bbox | null }
