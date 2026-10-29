import Cargando from './Cargando'
import MensajeError from './MensajeError'

/**
 * Muestra el estado de una consulta de useConsulta (INV-26 fix, A2.11):
 * cargando, error con "Reintentar" o el contenido con los datos.
 *
 *   <EstadoConsulta consulta={kpis}>{datos => <KPIs datos={datos} />}</EstadoConsulta>
 */
export default function EstadoConsulta({ consulta, children, aviso, alto }) {
  if (consulta.cargando) return <Cargando aviso={aviso} alto={alto} />
  if (consulta.error) return <MensajeError error={consulta.error} onReintentar={consulta.recargar} />
  if (consulta.datos === null) return null
  return children(consulta.datos)
}
