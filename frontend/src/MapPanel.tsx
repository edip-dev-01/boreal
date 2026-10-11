import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import type { FeatureCollection, Point } from 'geojson'
import type { Bbox, CivicRecord } from './types'
import { geography, districts } from './geography'
import { Icon } from './icons'
interface Props { records: CivicRecord[]; selectedId: string | null; onSelect: (id: string) => void; onBbox: (bbox: Bbox) => void; bboxActive: boolean }
export default function MapPanel({ records, selectedId, onSelect, onBbox, bboxActive }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const onSelectRef = useRef(onSelect)
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])
  useEffect(() => {
    if (!container.current) return
    let instance: maplibregl.Map
    try {
      instance = new maplibregl.Map({
        container: container.current, center: [-75.705,45.414], zoom: 11.7, minZoom: 10, maxZoom: 16,
        maxBounds: [[-75.94,45.25],[-75.43,45.57]], attributionControl: false,
        style: { version: 8, sources: { geography: { type: 'geojson', data: geography }, facilities: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } },
          layers: [
            { id: 'background', type: 'background', paint: { 'background-color': '#142630' } },
            { id: 'park', type: 'fill', source: 'geography', filter: ['==',['get','kind'],'park'], paint: { 'fill-color': '#1c3b36', 'fill-opacity': .85 } },
            { id: 'roads', type: 'line', source: 'geography', filter: ['==',['get','kind'],'road'], paint: { 'line-color': '#2b414a', 'line-width': 1 } },
            { id: 'water-edge', type: 'line', source: 'geography', filter: ['==',['get','kind'],'water'], paint: { 'line-color': '#345962', 'line-width': 2 } },
            { id: 'water', type: 'fill', source: 'geography', filter: ['==',['get','kind'],'water'], paint: { 'fill-color': '#0b1d26' } },
            { id: 'main-roads', type: 'line', source: 'geography', filter: ['==',['get','kind'],'main-road'], paint: { 'line-color': '#536069', 'line-width': 2, 'line-opacity': .7 } },
            { id: 'facility-halo', type: 'circle', source: 'facilities', paint: { 'circle-radius': 14, 'circle-color': '#73e1b3', 'circle-opacity': .1 } },
            { id: 'facility-points', type: 'circle', source: 'facilities', paint: { 'circle-radius': 5.5, 'circle-color': ['match',['get','freshness'],'stale','#f4be6a','missing','#abafd0','#79e4b7'], 'circle-stroke-width': 2, 'circle-stroke-color': '#10212a' } },
            { id: 'selected-point', type: 'circle', source: 'facilities', filter: ['==',['get','id'],''], paint: { 'circle-radius': 11, 'circle-color': '#79e4b7', 'circle-opacity': .15, 'circle-stroke-width': 2, 'circle-stroke-color': '#b8ffdf' } },
          ] },
      })
      map.current = instance
      instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      instance.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-left')
      instance.on('load', () => {
        setLoaded(true)
        for (const district of districts) {
          const element = document.createElement('span'); element.className = 'district-label'; element.textContent = district.name
          new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(district.coordinates).addTo(instance)
        }
      })
      instance.on('click', 'facility-points', (event) => {
        const id = event.features?.[0]?.properties?.id
        if (typeof id === 'string') onSelectRef.current(id)
      })
      instance.on('mouseenter','facility-points', () => { instance.getCanvas().style.cursor = 'pointer' })
      instance.on('mouseleave','facility-points', () => { instance.getCanvas().style.cursor = '' })
      instance.on('error', () => setFailed(true))
      const resizeObserver = new ResizeObserver(() => instance.resize())
      resizeObserver.observe(container.current)
      return () => { resizeObserver.disconnect(); instance.remove(); map.current = null }
    } catch { setFailed(true) }
  }, [])
  useEffect(() => {
    if (!loaded || !map.current) return
    const points: FeatureCollection<Point> = { type: 'FeatureCollection', features: records.flatMap(record => record.longitude === null || record.latitude === null ? [] : [{ type: 'Feature' as const, properties: { id: record.id, freshness: record.freshness }, geometry: { type: 'Point' as const, coordinates: [record.longitude, record.latitude] } }]) }
    ;(map.current.getSource('facilities') as maplibregl.GeoJSONSource).setData(points)
  }, [loaded, records])
  useEffect(() => {
    if (!loaded || !map.current) return
    map.current.setFilter('selected-point', ['==', ['get','id'], selectedId || ''])
    const selected = records.find(record => record.id === selectedId)
    if (selected?.longitude != null && selected.latitude != null) map.current.easeTo({ center: [selected.longitude, selected.latitude], duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 650 })
  }, [loaded, selectedId, records])
  const missing = records.filter(record => record.longitude === null || record.latitude === null).length
  return <section className="map-panel" aria-label="Interactive facility map">
    <div ref={container} className="map-canvas" role="region" aria-label="Schematic map of fictional civic facilities. Use the results table for keyboard selection." />
    <div className="map-topline"><span className="map-location"><span className="live-dot"/> FICTIONAL CITY <span className="map-coordinate">45.414° N · 75.705° W</span></span><button className={`map-button ${bboxActive ? 'active' : ''}`} disabled={!loaded || failed} onClick={() => { const bounds = map.current?.getBounds(); if (bounds) onBbox([bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()]) }}><Icon name="target" size={15}/> Search this view</button></div>
    {failed && <div className="map-fallback" role="status"><Icon name="globe" size={36}/><strong>Map rendering unavailable</strong><span>Your browser may not support WebGL. All facilities remain available in the results table.</span></div>}
    <div className="map-legend"><span><i className="dot fresh"/>Fresh</span><span><i className="dot stale"/>Stale</span><span><i className="dot missing"/>Undated</span>{missing > 0 && <span className="unmapped">{missing} without coordinates</span>}</div>
    <div className="map-caption">LOCAL SCHEMATIC · SYNTHETIC GEOGRAPHY</div>
  </section>
}
