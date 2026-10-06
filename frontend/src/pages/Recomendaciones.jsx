import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Info, Search } from 'lucide-react'
import { getCategorias, getRecomendacionesCompras, getRecomendacionesTransferencias } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useSucursales } from '../hooks/useSucursales'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import DistintivoBodega from '../components/DistintivoBodega'
import { fmtCantidad, fmtCantidadConUnidad, fmtConteo, fmtDecimal, fmtFecha, fmtNumero } from '../utils/formato'
import {
  ACCIONES_ALERTA, BODEGA, etiquetaDe, GRUPOS_PEDIDO, MOTIVOS_COMPRA, nombreUbicacion, TIPOS_ALERTA_RECOMENDACION,
  TIPOS_DESTINO, URGENCIAS_RECOMENDACION,
} from '../utils/etiquetas'
import { aCSV, descargarCSV } from '../utils/csv'

/**
 * Recomendaciones (INV-27, Fase C): las compras a proveedor de INV-21 y los
 * traslados de INV-22 por el Core API (INV-23), con filtros, el calendario de
 * pedidos, el resumen y la exportación a CSV. La API no pagina: la tabla
 * pagina y busca en el cliente. Solo se consulta la pestaña abierta: la
 * primera consulta calcula toda la red y tarda cerca de 30 s.
 */
const TARJETA = 'bg-white p-4 rounded-xl shadow-xs border border-slate-100'
const CAMPO = 'h-9 px-3 text-xs rounded-lg border border-slate-200 bg-white outline-hidden'
// Las compras y los traslados van de a 50, como Alertas; los bloques de debajo, de a 10
const POR_PAGINA = 50
const POR_PAGINA_BLOQUE = 10
const PESTANAS = { compras: 'Compras', transferencias: 'Transferencias' }
// Compras rechaza "vigilancia" (422): solo la tienen los traslados de INV-22
const URGENCIAS_DE = { compras: ['urgente', 'alta', 'normal'], transferencias: ['urgente', 'alta', 'normal', 'vigilancia'] }
const AVISO_CARGA = 'La primera consulta calcula las recomendaciones de toda la red: tarda cerca de 30 s.'

// El color acompaña al texto de la urgencia, nunca lo reemplaza
const TONO_URGENCIA = {
  urgente: 'bg-red-50 text-red-700 border-red-200',
  alta: 'bg-amber-50 text-amber-700 border-amber-200',
  normal: 'bg-green-50 text-green-700 border-green-200',
  vigilancia: 'bg-blue-50 text-blue-700 border-blue-200',
}

export default function Recomendaciones() {
  const { rawSucursalId, setSucursalId, showSelector, sucursalNombre } = useSucursal()
  const { porNombre } = useSucursales()
  const [pestana, setPestana] = useState('compras')
  const [categoria, setCategoria] = useState('')
  const [urgencia, setUrgencia] = useState('')
  const [busqueda, setBusqueda] = useState('')

  // El nombre canónico de dim_sucursal (V2), no el rótulo "Bodega Central";
  // a un admin_sucursal la API le aplica el suyo
  const sucursal = showSelector ? (sucursalNombre ?? undefined) : undefined
  const filtros = { sucursal, categoria: categoria || undefined, urgencia: urgencia || undefined }
  const deps = [sucursal, categoria, urgencia]
  const compras = useConsulta(op => getRecomendacionesCompras({ ...filtros, incluirDetalle: false }, op), deps,
    { activo: pestana === 'compras' })
  const transferencias = useConsulta(op => getRecomendacionesTransferencias({ ...filtros, incluirBalance: false }, op), deps,
    { activo: pestana === 'transferencias' })
  const categorias = useConsulta(op => getCategorias(op), [])
  const nombresCategorias = useMemo(
    () => (categorias.datos?.items ?? []).map(c => c.categoria).sort((a, b) => a.localeCompare(b, 'es')),
    [categorias.datos],
  )

  const cambiarPestana = clave => {
    setPestana(clave)
    if (urgencia && !URGENCIAS_DE[clave].includes(urgencia)) setUrgencia('')
  }
  // Volver a la primera página cuando cambia lo que se muestra
  const claveTabla = [pestana, sucursal, categoria, urgencia, busqueda].join('|')
  const nombreDe = nombre => nombreUbicacion({ nombre, tipo: porNombre[nombre]?.tipo })
  const esBodega = nombre => porNombre[nombre]?.tipo === BODEGA
  const esFisica = nombre => !!porNombre[nombre] && !esBodega(nombre)

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Recomendaciones</h2>
          <p className="text-xs text-slate-500">Compras a proveedor y traslados entre ubicaciones</p>
        </div>
        {showSelector && <SucursalSelector value={rawSucursalId} onChange={setSucursalId} />}
      </div>

      <div role="tablist" aria-label="Tipo de recomendación" className="flex gap-1 border-b border-slate-200">
        {Object.entries(PESTANAS).map(([clave, etiqueta]) => (
          <button key={clave} role="tab" aria-selected={pestana === clave} onClick={() => cambiarPestana(clave)}
            className={`px-4 py-2 text-sm font-semibold -mb-px border-b-2 ${pestana === clave
              ? 'border-brand-blue text-brand-blue' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {etiqueta}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Categoría" value={categoria} onChange={e => setCategoria(e.target.value)} className={CAMPO}>
          <option value="">Todas las categorías</option>
          {nombresCategorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select aria-label="Urgencia" value={urgencia} onChange={e => setUrgencia(e.target.value)} className={CAMPO}>
          <option value="">Todas las urgencias</option>
          {URGENCIAS_DE[pestana].map(u => <option key={u} value={u}>{URGENCIAS_RECOMENDACION[u]}</option>)}
        </select>
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-3" />
          <input type="search" aria-label="Buscar producto" value={busqueda} onChange={e => setBusqueda(e.target.value)}
            placeholder="Buscar producto por nombre o código" className={`${CAMPO} w-72 pl-8`} />
        </div>
      </div>

      <EstadoConsulta consulta={pestana === 'compras' ? compras : transferencias} aviso={AVISO_CARGA}>
        {d => (pestana === 'compras'
          ? <Compras datos={d} busqueda={busqueda} claveTabla={claveTabla} nombreDe={nombreDe} esBodega={esBodega}
            esFisica={esFisica} />
          : <Transferencias datos={d} busqueda={busqueda} claveTabla={claveTabla} nombreDe={nombreDe} esBodega={esBodega} />)}
      </EstadoConsulta>
    </div>
  )
}

// ── Compras ────────────────────────────────────────
function Compras({ datos, busqueda, claveTabla, nombreDe, esBodega, esFisica }) {
  const sucursal = datos.filtros_aplicados.sucursal
  // Con una sucursal física (elegida o la del admin_sucursal), las líneas de la Bodega se ven desde ella
  const vistaSucursal = !!sucursal && esFisica(sucursal)
  const lineas = useMemo(() => buscar(datos.compras, busqueda), [datos.compras, busqueda])
  const cubrir = useMemo(() => buscar(datos.cubrir_con_traslado, busqueda), [datos.cubrir_con_traslado, busqueda])
  const alertas = useMemo(() => buscar(datos.alertas, busqueda), [datos.alertas, busqueda])
  const conBodega = lineas.some(l => l.tipo_destino === BODEGA)
  const p = datos.politicas
  const politicas = `INV-21 v${p.inv21.version} (${fmtFecha(p.inv21.fecha)}) e INV-22 v${p.inv22.version} (${fmtFecha(p.inv22.fecha)})`

  const columnas = [
    { titulo: 'Producto', celda: l => <Producto fila={l} /> },
    { titulo: 'Destino', celda: l => (
      <>{nombreUbicacion({ nombre: l.destino, tipo: l.tipo_destino })}{l.tipo_destino === BODEGA && <DistintivoBodega />}</>
    ) },
    { titulo: 'Grupo', celda: l => etiquetaDe(GRUPOS_PEDIDO, l.grupo) },
    { titulo: 'Cantidad', derecha: true, unaLinea: true, celda: l => fmtCantidadConUnidad(l.cantidad, l.unidad) },
    { titulo: 'Urgencia', celda: l => <Urgencia valor={l.urgencia} /> },
    { titulo: 'Días hasta agotarse', derecha: true, celda: l => fmtDecimal(l.dias_hasta_agotarse) },
    { titulo: 'Pedido', unaLinea: true, celda: l => fmtFecha(l.fecha_pedido) },
    { titulo: 'Llega', unaLinea: true, celda: l => (
      <>
        {fmtFecha(l.fecha_llegada_sucursal)}
        {l.tipo_destino === BODEGA && <p className="text-slate-400">a la Bodega: {fmtFecha(l.fecha_llegada)}</p>}
      </>
    ) },
    { titulo: 'Llega tarde', celda: l => (l.llega_tarde ? <LlegaTarde /> : '') },
    { titulo: 'Motivo', celda: l => etiquetaDe(MOTIVOS_COMPRA, l.motivo) },
    ...(vistaSucursal
      ? [{ titulo: 'Necesidad de la sucursal', derecha: true, unaLinea: true,
        celda: l => fmtCantidadConUnidad(l.necesidad_sucursal, l.unidad) }]
      : []),
  ]
  const csv = [
    ['Código', l => l.producto_id], ['Producto', l => l.nombre_producto], ['Categoría', l => l.categoria],
    ['Destino', l => nombreUbicacion({ nombre: l.destino, tipo: l.tipo_destino })],
    ['Grupo', l => etiquetaDe(GRUPOS_PEDIDO, l.grupo)], ['Cantidad', l => l.cantidad], ['Unidad', l => l.unidad],
    ['Urgencia', l => etiquetaDe(URGENCIAS_RECOMENDACION, l.urgencia)],
    ['Días hasta agotarse (hábiles)', l => l.dias_hasta_agotarse], ['Pedido', l => l.fecha_pedido],
    ['Llega a la sucursal', l => l.fecha_llegada_sucursal],
    ['Llega a la Bodega', l => (l.tipo_destino === BODEGA ? l.fecha_llegada : null)],
    ['Llega tarde', l => l.llega_tarde], ['Motivo', l => etiquetaDe(MOTIVOS_COMPRA, l.motivo)],
    ...(vistaSucursal ? [['Necesidad de la sucursal', l => l.necesidad_sucursal]] : []),
    ['Foto de inventario', () => datos.fecha_inventario], ['Calculado en', () => datos.calculado_en],
  ]

  return (
    <div className="space-y-4">
      <Contexto datos={datos} politicas={politicas} nombreDe={nombreDe} />
      <Calendario calendario={datos.calendario} plazo={datos.lead_time_dias} />
      <ResumenCompras resumen={datos.resumen} sucursal={vistaSucursal ? sucursal : null} />
      {vistaSucursal && conBodega && (
        <Aviso>La urgencia y los días se calculan desde {sucursal}; la cantidad es la de toda la compra a la Bodega.</Aviso>
      )}
      <TablaPaginada key={claveTabla} titulo="Compras a proveedor" unidad={['línea', 'líneas']} columnas={columnas}
        filas={lineas} csv={{ columnas: csv, nombre: nombreArchivo('compras', datos) }} />
      <TablaPaginada key={`cubrir|${claveTabla}`} titulo="Cubrir con traslado desde la Bodega"
        unidad={['producto', 'productos']} filas={cubrir} porPagina={POR_PAGINA_BLOQUE} columnas={[
          { titulo: 'Producto', celda: c => <Producto fila={c} /> },
          { titulo: 'Necesidad', derecha: true, celda: c => fmtCantidadConUnidad(c.necesidad, c.unidad) },
          { titulo: 'Sobrante en la Bodega', derecha: true, celda: c => fmtCantidadConUnidad(c.sobrante_bodega, c.unidad) },
          { titulo: 'Urgencia', celda: c => <Urgencia valor={c.urgencia} /> },
          { titulo: 'Días hasta agotarse', derecha: true, celda: c => fmtDecimal(c.dias_hasta_agotarse) },
        ]} />
      <AlertasRecomendacion filas={alertas} claveTabla={claveTabla} nombreDe={nombreDe} esBodega={esBodega} />
    </div>
  )
}

// ── Transferencias ─────────────────────────────────
function Transferencias({ datos, busqueda, claveTabla, nombreDe, esBodega }) {
  const traslados = useMemo(() => buscar(datos.traslados, busqueda), [datos.traslados, busqueda])
  const alertas = useMemo(() => buscar(datos.alertas, busqueda), [datos.alertas, busqueda])
  const politicas = `INV-22 v${datos.politicas.version} (${fmtFecha(datos.politicas.fecha)})`
  const ubicacion = nombre => <>{nombreDe(nombre)}{esBodega(nombre) && <DistintivoBodega />}</>

  const columnas = [
    { titulo: 'Producto', celda: t => <Producto fila={t} /> },
    { titulo: 'Origen', celda: t => ubicacion(t.origen) },
    { titulo: 'Destino', celda: t => ubicacion(t.destino) },
    { titulo: 'Cantidad', derecha: true, unaLinea: true, celda: t => fmtCantidadConUnidad(t.cantidad, t.unidad) },
    { titulo: 'Urgencia', celda: t => <Urgencia valor={t.urgencia} /> },
    { titulo: 'Días hasta agotarse', derecha: true, celda: t => fmtDecimal(t.dias_hasta_agotarse) },
    { titulo: 'Llega', unaLinea: true, celda: t => (
      <>
        {fmtFecha(t.fecha_llegada)}
        <p className="text-slate-400">en {fmtConteo(t.dias_habiles_llegada, 'día hábil', 'días hábiles')}</p>
      </>
    ) },
    { titulo: 'Llega tarde', celda: t => (t.llega_tarde ? <LlegaTarde /> : '') },
  ]
  const csv = [
    ['Código', t => t.producto_id], ['Producto', t => t.nombre_producto], ['Categoría', t => t.categoria],
    ['Origen', t => nombreDe(t.origen)], ['Destino', t => nombreDe(t.destino)],
    ['Cantidad', t => t.cantidad], ['Unidad', t => t.unidad],
    ['Urgencia', t => etiquetaDe(URGENCIAS_RECOMENDACION, t.urgencia)],
    ['Días hasta agotarse (hábiles)', t => t.dias_hasta_agotarse], ['Llega', t => t.fecha_llegada],
    ['Días hábiles hasta la llegada', t => t.dias_habiles_llegada], ['Llega tarde', t => t.llega_tarde],
    ['Foto de inventario', () => datos.fecha_inventario], ['Calculado en', () => datos.calculado_en],
  ]

  return (
    <div className="space-y-4">
      <Contexto datos={datos} politicas={politicas} nombreDe={nombreDe} />
      <ResumenTransferencias resumen={datos.resumen} />
      <TablaPaginada key={claveTabla} titulo="Traslados" unidad={['traslado', 'traslados']} columnas={columnas}
        filas={traslados} csv={{ columnas: csv, nombre: nombreArchivo('transferencias', datos) }} />
      <AlertasRecomendacion filas={alertas} claveTabla={claveTabla} nombreDe={nombreDe} esBodega={esBodega}
        sinPronostico={datos.resumen.alertas_sin_pronostico} />
    </div>
  )
}

// ── Piezas ─────────────────────────────────────────
function Contexto({ datos, politicas, nombreDe }) {
  const { sucursal } = datos.filtros_aplicados
  const hora = datos.calculado_en?.slice(11, 16)
  return (
    <p className="text-xs text-slate-500">
      {sucursal ? nombreDe(sucursal) : 'Toda la red'} · Foto de inventario del {fmtFecha(datos.fecha_inventario)} ·
      Calculado el {fmtFecha(datos.calculado_en)}{hora && ` a las ${hora} UTC`} · Políticas {politicas}
    </p>
  )
}

function Calendario({ calendario, plazo }) {
  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm">Calendario de pedidos</h3>
      <p className="text-xs text-slate-500 mb-2">El proveedor entrega en {fmtConteo(plazo, 'día', 'días')}.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[640px]">
          <thead>
            <tr className="text-slate-500 text-left">
              {['Grupo', 'Destino', 'Pedido', 'Llega', 'Llega a la sucursal', 'Siguiente', 'Cubre hasta'].map(t => (
                <th key={t} className="py-1 pr-3 font-semibold">{t}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {calendario.map(c => (
              <tr key={c.grupo} className="border-t border-slate-100">
                <td className="py-1.5 pr-3">{etiquetaDe(GRUPOS_PEDIDO, c.grupo)}</td>
                <td className="py-1.5 pr-3">{etiquetaDe(TIPOS_DESTINO, c.tipo_destino)}</td>
                <td className="py-1.5 pr-3">{fmtFecha(c.fecha_pedido)}</td>
                <td className="py-1.5 pr-3">{fmtFecha(c.fecha_llegada)}</td>
                <td className="py-1.5 pr-3">{fmtFecha(c.fecha_llegada_sucursal)}</td>
                <td className="py-1.5 pr-3">{fmtFecha(c.pedido_siguiente)}</td>
                <td className="py-1.5 pr-3">{fmtFecha(c.cubre_hasta)} ({fmtConteo(c.dias_cubiertos, 'día', 'días')})</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Tarjeta({ etiqueta, children, detalle }) {
  return (
    <div className={TARJETA}>
      <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">{etiqueta}</p>
      <div className="text-lg font-bold text-slate-800 leading-snug">{children}</div>
      {detalle && <div className="text-xs text-slate-500 mt-1">{detalle}</div>}
    </div>
  )
}

// Unidades y kilos nunca se suman: cada cantidad va con su unidad
const cantidades = c => `${fmtCantidadConUnidad(c.unidad, 'unidad')} · ${fmtCantidadConUnidad(c.kg, 'kg')}`

function ResumenCompras({ resumen: r, sucursal }) {
  const conNecesidad = !!sucursal && !!r.necesidad_via_bodega
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-3 ${conNecesidad ? 'lg:grid-cols-5' : 'lg:grid-cols-4'}`}>
      <Tarjeta etiqueta="Líneas de compra"
        detalle={`${fmtNumero(r.lineas_sucursal)} a sucursales · ${fmtNumero(r.lineas_bodega)} a la Bodega`}>
        {fmtNumero(r.lineas)}
      </Tarjeta>
      <Tarjeta etiqueta="Cantidad a comprar"
        detalle={<>Directa: {cantidades(r.cantidad_directa)}<br />A la Bodega: {cantidades(r.cantidad_bodega)}</>}>
        <p>{fmtCantidadConUnidad(r.cantidad.unidad, 'unidad')}</p>
        <p>{fmtCantidadConUnidad(r.cantidad.kg, 'kg')}</p>
      </Tarjeta>
      <Tarjeta etiqueta="Cubiertos por la Bodega" detalle="Productos que se cubren con un traslado, sin comprar">
        {fmtNumero(r.cubiertos_por_bodega)}
      </Tarjeta>
      <Tarjeta etiqueta="Alertas" detalle="Inconsistencias de inventario: stock negativo en la foto">
        {fmtNumero(r.alertas)}
      </Tarjeta>
      {conNecesidad && (
        <Tarjeta etiqueta="Necesidad vía la Bodega" detalle={`La parte de ${sucursal} en las compras a la Bodega`}>
          <p>{fmtCantidadConUnidad(r.necesidad_via_bodega.unidad, 'unidad')}</p>
          <p>{fmtCantidadConUnidad(r.necesidad_via_bodega.kg, 'kg')}</p>
        </Tarjeta>
      )}
    </div>
  )
}

function ResumenTransferencias({ resumen: r }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <Tarjeta etiqueta="Traslados">{fmtNumero(r.traslados)}</Tarjeta>
      <Tarjeta etiqueta="Cantidad trasladada">
        <p>{fmtCantidadConUnidad(r.cantidad_trasladada.unidad, 'unidad')}</p>
        <p>{fmtCantidadConUnidad(r.cantidad_trasladada.kg, 'kg')}</p>
      </Tarjeta>
      <Tarjeta etiqueta="Déficit neto" detalle="Lo que los traslados no cubren: queda para las compras">
        <p>{fmtCantidadConUnidad(r.deficit_neto.unidad, 'unidad')}</p>
        <p>{fmtCantidadConUnidad(r.deficit_neto.kg, 'kg')}</p>
      </Tarjeta>
      <Tarjeta etiqueta="Alertas" detalle="Stock negativo en la foto">{fmtNumero(r.alertas)}</Tarjeta>
    </div>
  )
}

function AlertasRecomendacion({ filas, claveTabla, nombreDe, esBodega, sinPronostico }) {
  return (
    <div className="space-y-1">
      <TablaPaginada key={`alertas|${claveTabla}`} titulo="Alertas de inventario" unidad={['alerta', 'alertas']} filas={filas}
        porPagina={POR_PAGINA_BLOQUE}
        columnas={[
          { titulo: 'Producto', celda: a => <Producto fila={a} /> },
          { titulo: 'Sucursal', celda: a => <>{nombreDe(a.sucursal)}{esBodega(a.sucursal) && <DistintivoBodega />}</> },
          { titulo: 'Stock', derecha: true, celda: a => fmtCantidad(a.stock) },
          { titulo: 'Tipo', celda: a => etiquetaDe(TIPOS_ALERTA_RECOMENDACION, a.tipo) },
          { titulo: 'Acción', celda: a => etiquetaDe(ACCIONES_ALERTA, a.accion) },
        ]} />
      {sinPronostico > 0 && (
        <p className="text-xs text-slate-500">
          Además hay {fmtConteo(sinPronostico, 'par', 'pares')} sin pronóstico (acción: {ACCIONES_ALERTA.ninguna.toLowerCase()}):
          solo se listan con el balance completo, que esta vista no carga.
        </p>
      )}
    </div>
  )
}

function TablaPaginada({ titulo, unidad: [singular, plural], columnas, filas, csv, porPagina = POR_PAGINA }) {
  const [pagina, setPagina] = useState(1)
  const paginas = Math.max(1, Math.ceil(filas.length / porPagina))
  const visibles = filas.slice((pagina - 1) * porPagina, pagina * porPagina)

  return (
    <section aria-label={titulo} className="bg-white rounded-xl shadow-xs border border-slate-100 overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-100">
        <div>
          <h3 className="font-bold text-slate-800 text-sm">{titulo}</h3>
          <p className="text-xs text-slate-500">{fmtConteo(filas.length, singular, plural)}</p>
        </div>
        {csv && filas.length > 0 && (
          <button onClick={() => descargarCSV(csv.nombre, aCSV(csv.columnas.map(([t, valor]) => ({ titulo: t, valor })), filas))}
            className="h-8 px-3 text-xs font-semibold rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 flex items-center gap-1.5">
            <Download className="w-3.5 h-3.5" />Exportar CSV
          </button>
        )}
      </div>
      {filas.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[1000px]">
            <thead>
              <tr className="text-slate-500 font-semibold uppercase border-b border-slate-100">
                {columnas.map(c => (
                  <th key={c.titulo} className={`px-3 py-2 ${c.derecha ? 'text-right' : 'text-left'}`}>{c.titulo}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {visibles.map((fila, i) => (
                <tr key={i} className="hover:bg-slate-50 align-top">
                  {columnas.map(c => (
                    <td key={c.titulo} className={`px-3 py-2 ${c.derecha ? 'text-right' : ''} ${c.unaLinea ? 'whitespace-nowrap' : ''}`}>
                      {c.celda(fila)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-6 text-center text-sm text-slate-500">Sin resultados para estos filtros.</p>
      )}
      {paginas > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
          <p className="text-xs text-slate-500">Página {pagina} de {paginas} · {fmtConteo(filas.length, singular, plural)}</p>
          <div className="flex gap-1">
            <button aria-label="Página anterior" onClick={() => setPagina(pagina - 1)} disabled={pagina === 1}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button aria-label="Página siguiente" onClick={() => setPagina(pagina + 1)} disabled={pagina >= paginas}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

function Producto({ fila }) {
  return (
    <>
      <p className="font-medium text-slate-800">{fila.nombre_producto}</p>
      <p className="text-slate-400">{fila.producto_id} · {fila.categoria}</p>
    </>
  )
}

function Urgencia({ valor }) {
  return (
    <span className={`inline-block px-2 py-0.5 font-bold rounded-full border whitespace-nowrap
      ${TONO_URGENCIA[valor] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>
      {etiquetaDe(URGENCIAS_RECOMENDACION, valor)}
    </span>
  )
}

function LlegaTarde() {
  return (
    <span className="inline-block px-2 py-0.5 font-bold rounded-full bg-orange-50 text-orange-700 border border-orange-200 whitespace-nowrap">
      Llega tarde
    </span>
  )
}

function Aviso({ children }) {
  return (
    <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-100 rounded-xl text-xs text-blue-800">
      <Info className="w-4 h-4 shrink-0" />{children}
    </div>
  )
}

// Búsqueda local por nombre o código, sin distinguir mayúsculas ni tildes
const normalizar = t => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function buscar(filas, busqueda) {
  const b = normalizar(busqueda.trim())
  if (!b) return filas
  return filas.filter(f => normalizar(`${f.nombre_producto} ${f.producto_id}`).includes(b))
}

function nombreArchivo(tipo, datos) {
  const sucursal = datos.filtros_aplicados.sucursal
  return `recomendaciones-${tipo}${sucursal ? `-${sucursal.replace(/\s+/g, '_')}` : ''}-${datos.fecha_inventario}.csv`
}
