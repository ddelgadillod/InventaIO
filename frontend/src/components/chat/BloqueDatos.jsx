import GraficoDatos from './GraficoDatos'
import TablaDatos from './TablaDatos'
import TarjetasDatos from './TarjetasDatos'
import { tieneVisual } from '../../utils/datosVera'

// INV-40 (contrato v1.2): cada consulta se muestra como conviene. Arriba, las tarjetas y la gráfica si el agente las
// mandó; debajo, la tabla con su CSV, plegada cuando hay algo visual (se abre con su título). Sin tarjetas ni
// gráfica, la tabla como antes: abierta la primera de la respuesta.
export default function BloqueDatos({ datos, abierta = true }) {
  if (!tieneVisual(datos)) return <TablaDatos datos={datos} abierta={abierta} />
  const titulo = datos.titulo || 'Datos consultados'
  return (
    <section className="mt-2" aria-label={titulo}>
      <p className="text-xs font-semibold text-brand-navy">{titulo}</p>
      {datos.tarjetas?.length > 0 && <TarjetasDatos tarjetas={datos.tarjetas} />}
      {datos.grafico?.datos?.length > 0 && <GraficoDatos grafico={datos.grafico} titulo={titulo} />}
      {datos.filas?.length > 0 && <TablaDatos datos={datos} abierta={false} rotulo={`Ver la tabla · ${titulo}`} />}
    </section>
  )
}
