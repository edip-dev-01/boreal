import type { FeatureCollection, Feature, LineString, Polygon } from 'geojson'
// Original schematic fictional geography. No network tiles or geographic dataset.
const line = (coordinates: number[][], kind: string): Feature<LineString> => ({ type: 'Feature', properties: { kind }, geometry: { type: 'LineString', coordinates } })
const polygon = (coordinates: number[][], kind: string): Feature<Polygon> => ({ type: 'Feature', properties: { kind }, geometry: { type: 'Polygon', coordinates: [coordinates] } })
const features: Feature<LineString | Polygon>[] = [
  polygon([[-75.93,45.37],[-75.82,45.386],[-75.76,45.416],[-75.70,45.432],[-75.64,45.438],[-75.56,45.474],[-75.43,45.49],[-75.43,45.478],[-75.56,45.462],[-75.64,45.429],[-75.70,45.422],[-75.76,45.408],[-75.82,45.376],[-75.93,45.36],[-75.93,45.37]], 'water'),
  polygon([[-75.78,45.446],[-75.75,45.448],[-75.738,45.468],[-75.77,45.48],[-75.791,45.463],[-75.78,45.446]], 'park'),
  polygon([[-75.665,45.369],[-75.627,45.372],[-75.61,45.397],[-75.64,45.409],[-75.67,45.395],[-75.665,45.369]], 'park'),
  polygon([[-75.84,45.332],[-75.784,45.341],[-75.77,45.359],[-75.827,45.37],[-75.84,45.332]], 'park'),
  line([[-75.82,45.347],[-75.78,45.386],[-75.724,45.408],[-75.693,45.438],[-75.60,45.48]], 'main-road'),
  line([[-75.83,45.46],[-75.78,45.432],[-75.725,45.394],[-75.66,45.367],[-75.58,45.35]], 'main-road'),
]
for (let i = 0; i < 17; i++) {
  const lon = -75.846 + i * .018
  features.push(line([[lon,45.327],[lon+.014,45.385],[lon+.007,45.426],[lon+.019,45.496]], 'road'))
}
for (let i = 0; i < 17; i++) {
  const lat = 45.322 + i * .011
  features.push(line([[-75.85,lat],[-75.75,lat+.009],[-75.68,lat+.004],[-75.56,lat+.012]], 'road'))
}
export const geography: FeatureCollection = { type: 'FeatureCollection', features }
export const districts = [
  { name: 'NORTH REACH', coordinates: [-75.74,45.464] as [number, number] },
  { name: 'RIVER QUARTER', coordinates: [-75.693,45.411] as [number, number] },
  { name: 'EAST COMMON', coordinates: [-75.623,45.446] as [number, number] },
  { name: 'SOUTH GARDENS', coordinates: [-75.76,45.366] as [number, number] },
]
