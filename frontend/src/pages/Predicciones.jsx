import { useEffect, useState } from 'react'
import { Bar, BarChart, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Info, Search, Sparkles } from 'lucide-react'
import { getInventarioDetalle, getProductos, getVentasProducto, predecir } from '../api/client'
import { useSucursal } from '../hooks/useSucursal'
import { useConsulta } from '../hooks/useConsulta'
import SucursalSelector from '../components/SucursalSelector'
import EstadoConsulta from '../components/EstadoConsulta'
import { fmtCantidad, fmtCantidadConUnidad, fmtConteo, fmtDecimal, fmtFecha } from '../utils/formato'
import { barrasPronostico } from '../utils/graficas'
import {
  ESTADOS_INVENTARIO, etiquetaDe, RAMAS_MODELO, RIESGOS_PRONOSTICO, textoCobertura, textoUnidadVenta,
} from '../utils/etiquetas'
import { calcularRiesgo, HORIZONTE_DIAS_HABILES } from '../utils/riesgo'

/**
 * Predicciones (INV-26, Fase B): la demanda prevista de un producto en una
 * sucursal física a 15 días hábiles, junto a sus 8 ventanas de historia y su
 * stock. El riesgo se lee de dos formas, rotuladas por separado (V5): la
 * cobertura del semáforo de Inventario y el riesgo según el pronóstico.
 */
const TARJETA = 'bg-white p-4 rounded-xl shadow-xs border border-slate-100'
const VENTANAS = 8
const ESPERA_BUSQUEDA_MS = 300
const RESULTADOS = 20
const COLOR_VENTAS = '#2563EB'

// El color acompaña al texto del estado, nunca lo reemplaza (criterio 8)
const TONOS = {
  rojo: 'bg-red-50 text-red-700 border-red-200',
  ambar: 'bg-amber-50 text-amber-700 border-amber-200',
  verde: 'bg-green-50 text-green-700 border-green-200',
  violeta: 'bg-violet-50 text-violet-700 border-violet-200',
  gris: 'bg-slate-50 text-slate-600 border-slate-200',
}
const TONO_RIESGO = { urgente: 'rojo', alta: 'ambar', normal: 'verde', inconsistencia: 'violeta', sin_demanda: 'gris' }
const TONO_ESTADO = { critico: 'rojo', bajo: 'ambar', ok: 'verde', inconsistencia: 'violeta' }

export default function Predicciones() {
  const { sucursalId, rawSucursalId, setSucursalId, showSelector, sucursalNombre } = useSucursal()
  const [producto, setProducto] = useState(null)

  const listo = producto !== null && sucursalId !== null
  const idProducto = producto?.id_producto
  const deps = [idProducto, sucursalId]
  const prediccion = useConsulta(op => predecir({ idProducto, idSucursal: sucursalId }, op), deps, { activo: listo })
  const ventas = useConsulta(
    op => getVentasProducto(idProducto, { sucursalId, ventanas: VENTANAS }, op), deps, { activo: listo })
  const inventario = useConsulta(op => getInventarioDetalle(idProducto, sucursalId, op), deps, { activo: listo })
  // La unidad del producto elegido: predict no la trae (C1)
  const unidad = producto?.unidad

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Predicciones</h2>
          <p className="text-xs text-slate-500">Demanda prevista a {HORIZONTE_DIAS_HABILES} días hábiles</p>
        </div>
        {showSelector && (
          <SucursalSelector value={rawSucursalId} onChange={setSucursalId} incluirBodega={false}
            opcionVacia="Elegir sucursal" />
        )}
      </div>

      <BuscadorProducto onElegir={setProducto} />

      {producto && (
        <div>
          <p className="font-semibold text-slate-800">{producto.nombre}</p>
          <p className="text-xs text-slate-500">
            Código {producto.codigo_item} · {producto.categoria} · {textoUnidadVenta(unidad)}
            {sucursalNombre && ` · ${sucursalNombre}`}
          </p>
        </div>
      )}

      {listo ? (
        <>
          <section aria-label="Pronóstico" className="space-y-3">
            <h3 className="text-sm font-bold text-slate-700">Pronóstico a {HORIZONTE_DIAS_HABILES} días hábiles</h3>
            <EstadoConsulta consulta={prediccion} alto="h-24" aviso="Calculando el pronóstico…">
              {d => (
                <TarjetasPronostico datos={d} unidad={unidad} stock={inventario.datos?.stock_actual}
                  sinStock={inventario.error !== null} />
              )}
            </EstadoConsulta>
          </section>

          <section aria-label="Inventario" className="space-y-3">
            <h3 className="text-sm font-bold text-slate-700">
              Inventario{inventario.datos && ` · foto del ${fmtFecha(inventario.datos.historial.at(-1)?.fecha)}`}
            </h3>
            <EstadoConsulta consulta={inventario} alto="h-24">
              {d => <TarjetasInventario datos={d} unidad={unidad} />}
            </EstadoConsulta>
          </section>

          <EstadoConsulta consulta={ventas}>
            {d => (
              <Grafico ventas={d} prediccion={prediccion.datos} stock={inventario.datos?.stock_actual} unidad={unidad} />
            )}
          </EstadoConsulta>

          {prediccion.datos && (
            <p className="text-xs text-slate-400">
              Features al {fmtFecha(prediccion.datos.fecha_features)} · Modelo entrenado el{' '}
              {fmtFecha(prediccion.datos.modelo_entrenado_en)}
            </p>
          )}
        </>
      ) : (
        <Ayuda falta={{ producto: producto === null, sucursal: sucursalId === null }} />
      )}
    </div>
  )
}

function Ayuda({ falta }) {
  const texto = falta.producto && falta.sucursal
    ? 'Busque un producto por nombre o código y elija una sucursal para ver su pronóstico.'
    : falta.producto ? 'Busque un producto por nombre o código para ver su pronóstico.'
      : 'Elija una sucursal para ver el pronóstico del producto.'
  return (
    <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-100 rounded-xl text-xs text-blue-800">
      <Info className="w-4 h-4 shrink-0" />{texto}
    </div>
  )
}

// Busca 300 ms después de la última tecla y muestra 20 resultados (V11:
// nombre, familia o código)
function BuscadorProducto({ onElegir }) {
  const [texto, setTexto] = useState('')
  const [busqueda, setBusqueda] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim()), ESPERA_BUSQUEDA_MS)
    return () => clearTimeout(t)
  }, [texto])

  const resultados = useConsulta(
    op => getProductos({ busqueda, pageSize: RESULTADOS }, op), [busqueda], { activo: busqueda !== '' })
  const abierto = texto.trim() !== '' && busqueda !== ''

  const elegir = p => {
    onElegir(p)
    setTexto('')
    setBusqueda('')
  }

  return (
    <div className="relative max-w-xl">
      <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
      <input type="search" aria-label="Buscar producto" value={texto} autoComplete="off"
        onChange={e => setTexto(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') setTexto('') }}
        placeholder="Buscar producto por nombre o código"
        className="h-9 w-full pl-9 pr-3 text-sm rounded-lg border border-slate-200 bg-white outline-hidden" />
      {abierto && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-lg max-h-80 overflow-y-auto">
          <EstadoConsulta consulta={resultados} alto="h-16">
            {d => <Resultados datos={d} busqueda={busqueda} onElegir={elegir} />}
          </EstadoConsulta>
        </div>
      )}
    </div>
  )
}

function Resultados({ datos, busqueda, onElegir }) {
  if (!datos.items.length) {
    return <p className="p-3 text-xs text-slate-500">Ningún producto coincide con «{busqueda}».</p>
  }
  return (
    <>
      <ul aria-label="Productos encontrados">
        {datos.items.map(p => (
          <li key={p.id_producto}>
            <button type="button" onClick={() => onElegir(p)} className="w-full text-left px-3 py-2 hover:bg-slate-50">
              <span className="text-sm font-medium text-slate-800">{p.nombre}</span>
              <span className="text-xs text-slate-500"> · {p.codigo_item} · {p.categoria}</span>
            </button>
          </li>
        ))}
      </ul>
      {datos.total > datos.items.length && (
        // Fijo al pie de la lista, que se desplaza: sin eso solo se ve al llegar al último resultado
        <p className="sticky bottom-0 bg-white px-3 py-2 text-xs text-slate-500 border-t border-slate-100">
          Se muestran {datos.items.length} de {fmtConteo(datos.total, 'producto', 'productos')}: escriba más para acotar.
        </p>
      )}
    </>
  )
}

function Tarjeta({ etiqueta, valor, children }) {
  return (
    <div className={TARJETA}>
      <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">{etiqueta}</p>
      <p className="text-xl font-bold text-slate-800">{valor}</p>
      <div className="text-xs text-slate-500 space-y-1 mt-1">{children}</div>
    </div>
  )
}

function Insignia({ tono, children }) {
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-bold rounded-full border whitespace-nowrap ${TONOS[tono] ?? TONOS.gris}`}>
      {children}
    </span>
  )
}

// El límite es un cuantil de negocio, no un intervalo (V4). En perecederos
// (α = 0,167) queda bajo la mediana
function TarjetasPronostico({ datos, unidad, stock, sinStock }) {
  const { limite_superior: limite, alpha_negocio: alpha } = datos.intervalo_confianza
  const riesgo = stock === undefined ? null : calcularRiesgo(stock, datos.prediccion_q50)
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Tarjeta etiqueta="Demanda prevista" valor={fmtCantidadConUnidad(datos.prediccion_q50, unidad)}>
          <p>Mediana (q50) en {HORIZONTE_DIAS_HABILES} días hábiles</p>
        </Tarjeta>
        <Tarjeta etiqueta="Límite de negocio" valor={fmtCantidadConUnidad(limite, unidad)}>
          <p>Cuantil de negocio (α = {fmtDecimal(alpha, 3)})</p>
          {alpha < 0.5 && (
            <p className="text-amber-700">
              Cuantil bajo: queda bajo la mediana para evitar merma en un perecedero. No es una cota de reposición.
            </p>
          )}
        </Tarjeta>
        <Tarjeta etiqueta="Riesgo según el pronóstico"
          valor={riesgo?.dias == null ? '—' : `${fmtDecimal(riesgo.dias)} días hábiles`}>
          {riesgo ? (
            <>
              <Insignia tono={TONO_RIESGO[riesgo.nivel]}>{etiquetaDe(RIESGOS_PRONOSTICO, riesgo.nivel)}</Insignia>
              <p>Hasta agotar el stock con la demanda prevista</p>
            </>
          ) : <p>{sinStock ? 'Necesita el stock de la foto de inventario' : 'Esperando el stock de la foto…'}</p>}
        </Tarjeta>
      </div>
      <div className={TARJETA}>
        <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">Interpretación</p>
        <p className="text-sm text-slate-700 mt-1">{datos.interpretacion}</p>
        <p className="text-xs text-slate-500 mt-2">
          <Sparkles className="w-3.5 h-3.5 inline mr-1 text-brand-blue" />
          Rama del modelo: {etiquetaDe(RAMAS_MODELO, datos.rama)}
        </p>
      </div>
    </div>
  )
}

function TarjetasInventario({ datos, unidad }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <Tarjeta etiqueta="Stock actual" valor={fmtCantidadConUnidad(datos.stock_actual, unidad)}>
        <p>Foto del {fmtFecha(datos.historial.at(-1)?.fecha)}</p>
      </Tarjeta>
      <Tarjeta etiqueta="Cobertura del inventario" valor={textoCobertura(datos.dias_cobertura, datos.stock_actual)}>
        <Insignia tono={TONO_ESTADO[datos.semaforo]}>{etiquetaDe(ESTADOS_INVENTARIO, datos.semaforo)}</Insignia>
        <p>Con la demanda observada, como en el semáforo de Inventario</p>
      </Tarjeta>
    </div>
  )
}

// Barras sólidas para las ventas y una punteada para el pronóstico; el límite
// y el stock son líneas de referencia, sin bandas ni sombreado (V4)
function Grafico({ ventas, prediccion, stock, unidad }) {
  const barras = barrasPronostico(ventas.ventanas, prediccion?.prediccion_q50, HORIZONTE_DIAS_HABILES)
  const intervalo = prediccion?.intervalo_confianza
  const sinVentas = ventas.ventanas.every(v => v.unidades === 0)
  const cantidad = v => fmtCantidadConUnidad(v, unidad)

  return (
    <div className={TARJETA}>
      <h3 className="font-bold text-slate-800 text-sm">
        Ventas en ventanas de {HORIZONTE_DIAS_HABILES} días hábiles y pronóstico
      </h3>
      <p className="text-xs text-slate-500 mb-3">
        Ventas sin devoluciones. La última ventana termina el {fmtFecha(ventas.fecha_fin)}
        {prediccion ? ' y el pronóstico la sigue.' : '.'}
      </p>
      {sinVentas && (
        <p className="flex items-center gap-2 p-3 mb-3 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-800">
          <Info className="w-4 h-4 shrink-0" />
          El producto no vendió en {ventas.sucursal} entre el {fmtFecha(ventas.ventanas[0]?.desde)} y
          el {fmtFecha(ventas.fecha_fin)}.
        </p>
      )}
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={barras}>
          <XAxis dataKey="etiqueta" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={55}
            tickFormatter={v => fmtCantidad(v, unidad)} />
          {/* El valor en gris oscuro: con el color de la barra del pronóstico no se lee */}
          <Tooltip formatter={(v, nombre) => [cantidad(v), nombre]} labelFormatter={(_, filas) => filas?.[0]?.payload.periodo}
            itemStyle={{ color: '#334155' }} />
          {/* El texto de la leyenda en gris: con el color de la barra del pronóstico no se lee */}
          <Legend wrapperStyle={{ fontSize: 11 }} formatter={nombre => <span className="text-slate-600">{nombre}</span>} />
          <Bar dataKey="ventas" name="Ventas" stackId="u" fill={COLOR_VENTAS} radius={[4, 4, 0, 0]} />
          {prediccion && (
            <Bar dataKey="pronostico" name="Pronóstico IA (q50)" stackId="u" fill="#DBEAFE" stroke={COLOR_VENTAS}
              strokeDasharray="4 3" radius={[4, 4, 0, 0]} />
          )}
          {intervalo && (
            <ReferenceLine y={intervalo.limite_superior} ifOverflow="extendDomain" stroke="#D97706" strokeDasharray="6 3" />
          )}
          {stock !== undefined && <ReferenceLine y={stock} ifOverflow="extendDomain" stroke="#059669" />}
        </BarChart>
      </ResponsiveContainer>
      <ul className="text-xs text-slate-600 mt-2 space-y-0.5">
        {intervalo && (
          <li>
            <span aria-hidden="true" className="text-amber-600 font-bold">- - </span>
            Cuantil de negocio (α = {fmtDecimal(intervalo.alpha_negocio, 3)}): {cantidad(intervalo.limite_superior)}
            {intervalo.alpha_negocio < 0.5 && ', bajo la mediana: no es una cota de reposición'}
          </li>
        )}
        {stock !== undefined && (
          <li><span aria-hidden="true" className="text-emerald-600 font-bold">—— </span>Stock actual: {cantidad(stock)}</li>
        )}
      </ul>
    </div>
  )
}
