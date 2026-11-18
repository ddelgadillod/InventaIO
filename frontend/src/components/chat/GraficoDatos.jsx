import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import useMedia from '../../hooks/useMedia'
import { colorSerie, etiquetaEje, valorCorto, valorLargo } from '../../utils/datosVera'

// INV-40 (contrato v1.2): la gráfica de una consulta, con los valores numéricos que manda el agente (las filas
// llevan texto). Tipos: barras, barras_h (ranking), linea (muchos periodos) y apiladas (estados por sucursal).
// La tabla, debajo, es la alternativa accesible con todas las cifras.
export default function GraficoDatos({ grafico, titulo }) {
  const quieto = useMedia('(prefers-reduced-motion: reduce)')
  const { tipo, x, series = [], datos = [], unidad = '', referencias = [] } = grafico
  const horizontal = tipo === 'barras_h'
  const alto = horizontal ? Math.max(140, datos.length * 26 + 40) : 190
  const nombres = series.map(s => s.etiqueta).join(', ')
  const descripcion = `${titulo ? `${titulo}: ` : ''}gráfica de ${nombres} por ${horizontal ? 'producto' : x}, `
    + `${datos.length} ${datos.length === 1 ? 'dato' : 'datos'}. Las cifras exactas están en la tabla.`
  const comun = {
    data: datos,
    margin: { top: 4, right: 8, bottom: 0, left: horizontal ? 4 : 0 },
  }
  const ejes = horizontal
    ? [
        <XAxis key="x" type="number" tickFormatter={v => valorCorto(v, unidad)} tick={{ fontSize: 10 }} />,
        <YAxis key="y" type="category" dataKey={x} width={118} tickFormatter={etiquetaEje} tick={{ fontSize: 10 }} />,
      ]
    : [
        <XAxis key="x" dataKey={x} tickFormatter={etiquetaEje} tick={{ fontSize: 10 }} interval="preserveStartEnd" />,
        <YAxis key="y" tickFormatter={v => valorCorto(v, unidad)} tick={{ fontSize: 10 }} width={52} />,
      ]
  const extras = [
    <CartesianGrid key="g" strokeDasharray="3 3" stroke="#E2E8F0" vertical={!horizontal} horizontal={horizontal ? false : true} />,
    <Tooltip key="t" formatter={(v, nombre) => [valorLargo(v, unidad), nombre]} labelFormatter={etiquetaEje} />,
    ...(series.length > 1 ? [<Legend key="l" wrapperStyle={{ fontSize: 11 }} />] : []),
    ...referencias.map(r => (
      <ReferenceLine key={`r-${r.etiqueta}`} y={horizontal ? undefined : r.valor} x={horizontal ? r.valor : undefined}
        stroke="#F97316" strokeDasharray="4 3" label={{ value: r.etiqueta, fontSize: 10, fill: '#C2410C' }} />
    )),
  ]
  return (
    <figure className="mt-2 rounded-lg border border-slate-200 bg-white p-2" aria-label={descripcion}>
      <div style={{ height: alto }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          {tipo === 'linea' ? (
            <LineChart {...comun}>
              {ejes}{extras}
              {series.map((s, i) => (
                <Line key={s.clave} type="monotone" dataKey={s.clave} name={s.etiqueta} stroke={colorSerie(s.clave, i)}
                  strokeWidth={2} dot={false} isAnimationActive={!quieto} />
              ))}
            </LineChart>
          ) : (
            <BarChart {...comun} layout={horizontal ? 'vertical' : 'horizontal'}>
              {ejes}{extras}
              {series.map((s, i) => (
                <Bar key={s.clave} dataKey={s.clave} name={s.etiqueta} fill={colorSerie(s.clave, i)}
                  stackId={tipo === 'apiladas' ? 'pila' : undefined} isAnimationActive={!quieto}
                  radius={tipo === 'apiladas' ? 0 : horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} maxBarSize={28} />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">{descripcion}</figcaption>
    </figure>
  )
}
