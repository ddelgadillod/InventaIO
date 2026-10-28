import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ChatProvider from './ChatProvider'
import BotonChat from './BotonChat'
import PanelChat from './PanelChat'
import Vera from './Vera'
import TablaDatos from './TablaDatos'
import BotonCopiar from './BotonCopiar'
import useChatPanel from '../../hooks/useChatPanel'
import { renderConUsuario, simularApi, textoSSE, USUARIOS } from '../../test/utils'
import { DONE, FLUJO_403, FLUJO_ALERTAS, META } from '../../test/vera'
import { PREGUNTAS_POR_PAGINA } from '../../utils/preguntasRapidas'
import { descargarCSV } from '../../utils/csv'

vi.mock('../../utils/csv', async original => ({ ...(await original()), descargarCSV: vi.fn() }))

const RUTA = 'POST /api/chat/message'
const SALUD = 'GET /api/chat/health'
// Las preguntas enviadas, sin la consulta de salud que se hace al abrir (M3)
const enviadas = api => api.llamadas.filter(l => l.ruta === '/api/chat/message')

// Como ColumnaChat de App.jsx, sin la carga diferida
function Columna() {
  const { abierto } = useChatPanel()
  return <>{abierto && <PanelChat />}<BotonChat /></>
}

async function abrirVera(usuario = USUARIOS.gerente) {
  renderConUsuario(<ChatProvider><Columna /></ChatProvider>, usuario)
  await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
  return screen.getByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
}

async function preguntar(texto) {
  const campo = screen.getByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
  await userEvent.type(campo, `${texto}{Enter}`)
}

const conversacion = () => screen.getByRole('log', { name: 'Conversación con Vera' })

// Un flujo que entrega estos eventos y se queda abierto: para ver los estados intermedios
function flujoAbierto(eventos) {
  vi.stubGlobal('fetch', vi.fn(async (_url, { signal }) => new Response(new ReadableStream({
    start(control) {
      if (eventos.length) control.enqueue(new TextEncoder().encode(textoSSE(eventos)))
      signal.addEventListener('abort', () => control.error(new DOMException('Aborted', 'AbortError')))
    },
  }), { status: 200 })))
}

describe('Panel de Vera', () => {
  it.each([
    ['gerente', USUARIOS.gerente, 'Dame un ranking de alertas por sucursal'],
    ['admin_bodega', USUARIOS.bodega, 'Dame el estado general de sucursales'],
    ['admin_sucursal', USUARIOS.adminNorte, 'Dame un reporte general de inventario'],
  ])('el %s ve el saludo y sus preguntas rápidas; el foco queda en el campo', async (_rol, usuario, primera) => {
    const campo = await abrirVera(usuario)
    expect(campo).toHaveFocus()
    expect(screen.getByRole('heading', { name: 'Vera' })).toBeInTheDocument()
    expect(screen.getByText('Pregúntale a tu inventario')).toBeInTheDocument()
    expect(screen.getByText(/la asistente de InventAI\/o/)).toBeInTheDocument()
    const rapidas = within(screen.getByRole('group', { name: 'Preguntas rápidas' })).getAllByRole('button')
    expect(rapidas).toHaveLength(4)
    expect(rapidas[0]).toHaveTextContent(primera)
    expect(campo).toHaveAttribute('maxLength', '2000')
  })

  it('una pregunta rápida llega con la tabla, las herramientas, la fecha y las sugerencias', async () => {
    const api = simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    await userEvent.click(screen.getByRole('button', { name: 'Dame el estado de alertas de Glorieta' }))
    expect(screen.getByRole('textbox', { name: 'Escribe tu pregunta a Vera' })).toHaveFocus()
    const sugerencia = await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(enviadas(api)[0].body.mensajes).toEqual([{ rol: 'usuario', texto: 'Dame el estado de alertas de Glorieta' }])

    const log = conversacion()
    expect(within(log).getByText('243', { selector: 'strong' })).toBeInTheDocument()
    // Los valores de `data` van tal cual, alineados a la derecha si son números (C7)
    const tabla = within(log).getByRole('table')
    expect(within(tabla).getByRole('columnheader', { name: 'Crítica' })).toHaveClass('text-right')
    expect(within(tabla).getByRole('cell', { name: '1.092' })).toHaveClass('text-right')
    expect(within(log).getByText(/Consultado:/).parentElement).toHaveTextContent('Resumen de alertas · GLORIETA')
    // M5: el tiempo de `done.ms_total`, junto a la fecha
    expect(within(log).getByText('Datos al 31 dic 2025 · Respondió en 3,0 s')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Preguntas rápidas' })).not.toBeInTheDocument()

    // La sugerencia se envía como pregunta, con el turno anterior
    await userEvent.click(sugerencia)
    await waitFor(() => expect(enviadas(api)).toHaveLength(2))
    expect(enviadas(api)[1].body.mensajes.map(m => m.rol)).toEqual(['usuario', 'agente', 'usuario'])
    expect(enviadas(api)[1].body.mensajes[2].texto).toBe('¿Quieres ver las alertas críticas?')
  })

  it('Enter envía y Mayús+Enter salta de línea; vacío no se envía', async () => {
    const api = simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    const campo = await abrirVera()
    expect(screen.getByRole('button', { name: 'Enviar pregunta' })).toBeDisabled()
    await userEvent.type(campo, '{Enter}')
    await userEvent.type(campo, 'línea uno{Shift>}{Enter}{/Shift}línea dos')
    expect(campo).toHaveValue('línea uno\nlínea dos')
    expect(enviadas(api)).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pregunta' }))
    expect(campo).toHaveValue('')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(enviadas(api)[0].body.mensajes[0].texto).toBe('línea uno\nlínea dos')
  })

  it('muestra el contador cerca del límite de 2.000 caracteres', async () => {
    const campo = await abrirVera()
    await userEvent.click(campo)
    await userEvent.paste('x'.repeat(1850))
    expect(screen.getByText('1850/2000')).toBeInTheDocument()
  })

  it('estados: conectando, analizando, consultando, recomendaciones lentas y verificando', async () => {
    const estado = () => screen.getByRole('status')
    flujoAbierto([])
    await abrirVera()
    await preguntar('a')
    await waitFor(() => expect(estado()).toHaveTextContent('Conectando con Vera…'))
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))

    flujoAbierto([META])
    await preguntar('b')
    await waitFor(() => expect(estado()).toHaveTextContent('Analizando tu pregunta…'))
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))

    flujoAbierto(FLUJO_ALERTAS.slice(0, 2))
    await preguntar('c')
    await waitFor(() => expect(estado()).toHaveTextContent('Consultando Resumen de alertas · GLORIETA…'))
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))

    flujoAbierto([META, ['tool', { id: '1-1', nombre: 'recomendar_compras', estado: 'inicio', etiqueta: 'Compras', lenta: true }]])
    await preguntar('d')
    await waitFor(() => expect(estado()).toHaveTextContent('Calculando recomendaciones… puede tardar hasta 40 s'))
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))

    flujoAbierto(FLUJO_ALERTAS.slice(0, 5))
    await preguntar('e')
    await waitFor(() => expect(estado()).toHaveTextContent('Verificando la respuesta…'))
    expect(conversacion()).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getAllByText('Detenida.')).toHaveLength(1)
  })

  it('con otro flujo en curso (429) avisa que reintentará', async () => {
    simularApi({ [RUTA]: { status: 429, body: {}, headers: { 'Retry-After': '3' } } })
    await abrirVera()
    await preguntar('a')
    expect(await screen.findByRole('status')).toHaveTextContent('Vera está atendiendo otra consulta. Reintentando en 3 s…')
  })

  it('el 403 dentro del flujo se marca en la respuesta y en la herramienta', async () => {
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_403) } })
    await abrirVera(USUARIOS.adminNorte)
    await preguntar('Dame un resumen de inventario de GLORIETA')
    expect(await screen.findByText('Tu rol no tiene permiso para parte de esta consulta')).toBeInTheDocument()
    expect(screen.getByText(/Consultado:/).parentElement).toHaveTextContent('Resumen del inventario · GLORIETA (sin permiso)')
    expect(screen.queryByRole('group', { name: 'Sugerencias de seguimiento' })).not.toBeInTheDocument()
  })

  it('la respuesta de respaldo se marca; con varias tablas solo la primera llega abierta', async () => {
    const tabla = (id, titulo) => ['data', { id, titulo, columnas: [{ clave: 'a', titulo: 'A', tipo: 'texto' }], filas: [{ a: 'x' }, {}], total: 9, mostrando: 2 }]
    simularApi({
      [RUTA]: {
        sse: textoSSE([META, tabla('1-1', 'Primera'), tabla('1-2', ''), ['token', { texto: 'No pude redactar una respuesta verificada…' }],
          ['done', { ...DONE, respaldo: true, fidelidad: 'respaldo', sugerencias: [] }]]),
      },
    })
    await abrirVera()
    await preguntar('a')
    expect(await screen.findByText('Respuesta de respaldo: Vera no pudo verificar su redacción')).toBeInTheDocument()
    const [primera, segunda] = conversacion().querySelectorAll('details')
    expect(primera).toHaveAttribute('open')
    expect(segunda).not.toHaveAttribute('open')
    expect(within(segunda).getByText('Datos consultados')).toBeInTheDocument()
    expect(screen.getAllByText('Se muestran 2 de 9.')).toHaveLength(2)
    expect(screen.getAllByRole('cell', { name: '—' })).toHaveLength(2)
    // Sin herramientas no hay «Consultado:», pero sí la fecha y el tiempo del `done`
    expect(screen.queryByText(/Consultado:/)).not.toBeInTheDocument()
    expect(screen.getByText('Datos al 31 dic 2025 · Respondió en 3,0 s')).toBeInTheDocument()
  })

  it('el Markdown del modelo nunca se vuelve HTML', async () => {
    const malicioso = '<img src=x onerror="alert(1)"><script>alert(2)</script> **ok**\n\n# Título\n1. `uno`\n- dos'
    simularApi({ [RUTA]: { sse: textoSSE([META, ['token', { texto: malicioso }], ['done', DONE]]) } })
    await abrirVera()
    await preguntar('a')
    const log = conversacion()
    await within(log).findByText('ok', { selector: 'strong' })
    expect(log.querySelector('img, script')).toBeNull()
    expect(log).toHaveTextContent('<img src=x onerror="alert(1)"><script>alert(2)</script>')
    expect(within(log).getByText('Título')).toHaveClass('font-bold')
    expect(within(log).getByText('uno', { selector: 'code' })).toBeInTheDocument()
    expect(within(log).getAllByRole('list').map(l => l.tagName)).toEqual(['OL', 'UL'])
  })

  it('un error reintentable ofrece reintentar; uno de validación, no', async () => {
    let n = 0
    simularApi({ [RUTA]: () => (++n === 1 ? { status: 503, body: {} } : { sse: textoSSE(FLUJO_ALERTAS) }) })
    await abrirVera()
    await preguntar('a')
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('Vera no está disponible')
    await userEvent.click(within(alerta).getByRole('button', { name: 'Reintentar' }))
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    simularApi({ [RUTA]: { status: 422, body: { detail: 'Mensaje demasiado largo' } } })
    await preguntar('b')
    expect(await screen.findByRole('alert')).toHaveTextContent('Mensaje demasiado largo')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
  })

  it('pasados 6 turnos avisa que Vera no recuerda lo anterior', async () => {
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    for (let i = 0; i < 7; i++) {
      await preguntar(`p${i}`)
      await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar pregunta' })).toBeInTheDocument())
    }
    expect(screen.getByText(/Vera recuerda solo los últimos 6 turnos/)).toBeInTheDocument()
  })

  it('«Nueva conversación» vacía el chat; Escape cierra y devuelve el foco al botón', async () => {
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    const nueva = screen.getByRole('button', { name: 'Nueva conversación' })
    expect(nueva).toBeDisabled()
    await preguntar('a')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    await userEvent.click(nueva)
    expect(screen.getByRole('group', { name: 'Preguntas rápidas' })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Chat con Vera' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir el chat con Vera' })).toHaveFocus()
  })

  it('el botón «Cerrar el chat» cierra el panel', async () => {
    await abrirVera()
    expect(screen.getByRole('dialog', { name: 'Chat con Vera' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar el chat' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('flota sin tapar la página y se maximiza; el fondo oscuro la restaura', async () => {
    await abrirVera()
    const ventana = screen.getByRole('dialog', { name: 'Chat con Vera' })
    expect(ventana).toHaveAttribute('aria-modal', 'false')
    expect(ventana).toHaveClass('sm:w-[26rem]')
    await userEvent.click(screen.getByRole('button', { name: 'Maximizar' }))
    expect(ventana).toHaveAttribute('aria-modal', 'true')
    expect(ventana).toHaveClass('sm:inset-4')
    expect(ventana).not.toHaveClass('sm:w-[26rem]')
    // La conversación maximizada va en una columna legible
    expect(screen.getByRole('log').firstChild).toHaveClass('sm:max-w-4xl')
    const fondo = document.querySelector('.bg-slate-900\\/40')
    await userEvent.click(fondo)
    expect(ventana).toHaveAttribute('aria-modal', 'false')
    await userEvent.click(screen.getByRole('button', { name: 'Maximizar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Restaurar el tamaño' }))
    expect(screen.getByRole('button', { name: 'Maximizar' })).toBeInTheDocument()
  })

  it('en pantallas angostas ocupa toda la pantalla, como un diálogo modal', async () => {
    vi.stubGlobal('matchMedia', media => ({ matches: false, media, addEventListener() {}, removeEventListener() {} }))
    await abrirVera()
    expect(screen.getByRole('dialog', { name: 'Chat con Vera' })).toHaveAttribute('aria-modal', 'true')
  })

  it('sigue lo que llega solo si el usuario no subió a leer algo anterior', async () => {
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    const log = conversacion()
    // jsdom no calcula alturas: se simulan 1.000 px de contenido en 300 px de alto
    Object.defineProperty(log, 'scrollHeight', { configurable: true, value: 1000 })
    Object.defineProperty(log, 'clientHeight', { configurable: true, value: 300 })
    await preguntar('a')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(log.scrollTop).toBe(1000)
    // Sube a leer: lo que llegue después no lo mueve
    log.scrollTop = 100
    log.dispatchEvent(new Event('scroll'))
    await userEvent.click(screen.getByRole('button', { name: 'Nueva conversación' }))
    expect(log.scrollTop).toBe(100)
    // Una pregunta nueva vuelve a seguir el final
    await preguntar('b')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(log.scrollTop).toBe(1000)
  })
})

describe('Mejoras del 27-oct', () => {
  it('M2: tras 10 s sin eventos avisa la demora, salvo con la herramienta lenta', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    flujoAbierto([META])
    await abrirVera()
    await preguntar('a')
    expect(await screen.findByText('Analizando tu pregunta…')).toBeInTheDocument()
    expect(screen.queryByText(/Está tardando más de lo normal/)).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(screen.getByRole('status')).toHaveTextContent(
      'Está tardando más de lo normal: la primera pregunta después de iniciar el modelo puede tardar uno o dos minutos.')
    await userEvent.click(screen.getByRole('button', { name: 'Detener la respuesta' }))

    flujoAbierto([META, ['tool', { id: '1-1', nombre: 'recomendar_compras', estado: 'inicio', etiqueta: 'Compras', lenta: true }]])
    await preguntar('b')
    await screen.findByText('Calculando recomendaciones… puede tardar hasta 40 s')
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(screen.queryByText(/Está tardando más de lo normal/)).not.toBeInTheDocument()
  })

  it('M3: si Vera no está disponible al abrir, lo avisa con el motivo y no deja enviar', async () => {
    const api = simularApi({
      [SALUD]: { status: 503, body: { detail: { motivo: 'modelo_no_descargado' } } },
      [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) },
    })
    const campo = await abrirVera()
    const aviso = await screen.findByRole('alert')
    expect(aviso).toHaveTextContent('Vera no está disponible')
    expect(aviso).toHaveTextContent('El modelo de lenguaje no está instalado en el servidor.')
    within(screen.getByRole('group', { name: 'Preguntas rápidas' })).getAllByRole('button')
      .forEach(b => expect(b).toBeDisabled())
    await userEvent.type(campo, 'Hola{Enter}')
    expect(campo).toHaveValue('Hola')
    expect(screen.getByRole('button', { name: 'Enviar pregunta' })).toBeDisabled()
    expect(enviadas(api)).toHaveLength(0)

    // Vuelve el agente: «Volver a comprobar» habilita el envío
    simularApi({ [SALUD]: { body: { estado: 'listo', modelo: 'qwen3:8b' } }, [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await userEvent.click(within(aviso).getByRole('button', { name: 'Volver a comprobar' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Enviar pregunta' })).toBeEnabled()
  })

  it.each([
    ['ollama_no_alcanzable', 'El modelo de lenguaje no está encendido.'],
    ['agente_no_disponible', 'El servicio de Vera no responde.'],
    ['otro', 'El servicio de Vera no responde.'],
  ])('M3: el motivo %s se explica', async (motivo, texto) => {
    simularApi({ [SALUD]: { status: 503, body: { detail: { motivo } } } })
    await abrirVera()
    expect(await screen.findByRole('alert')).toHaveTextContent(texto)
  })

  it('M3: sin conexión también se avisa', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await abrirVera()
    expect(await screen.findByRole('alert')).toHaveTextContent('No hay conexión con el servidor.')
  })

  it('M3: una respuesta que no dice nada (500) no bloquea', async () => {
    const api = simularApi({ [SALUD]: { status: 500, body: {} }, [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    await waitFor(() => expect(api.llamadas.some(l => l.ruta === '/api/chat/health')).toBe(true))
    await preguntar('a')
    await screen.findByRole('button', { name: '¿Quieres ver las alertas críticas?' })
    expect(screen.queryByText('Vera no está disponible')).not.toBeInTheDocument()
  })

  it('M4: cada tabla se descarga en CSV con las cifras como números; las cantidades van a la derecha', async () => {
    simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
    await abrirVera()
    await preguntar('a')
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar Resumen de alertas · GLORIETA en CSV' }))
    const [nombre, texto] = descargarCSV.mock.calls.at(-1)
    expect(nombre).toBe('vera-resumen-de-alertas-glorieta.csv')
    expect(texto.replace('\uFEFF', '').trimEnd().split('\r\n')).toEqual(['Sucursal;Crítica;Media', 'GLORIETA;243;1092'])

    render(<TablaDatos datos={{ titulo: 'Stock', columnas: [{ clave: 's', titulo: 'Stock', tipo: 'cantidad' }], filas: [{ s: '5 unidades' }] }} />)
    expect(screen.getByRole('cell', { name: '5 unidades' })).toHaveClass('text-right')
    expect(screen.getByRole('columnheader', { name: 'Stock' })).toHaveClass('text-right')
  })
})

describe('Segunda tanda del 27-oct', () => {
  it('M9: copia la respuesta sin marcas de Markdown y avisa «Copiada»', async () => {
    // jsdom no trae portapapeles: uno simulado mientras dura la prueba
    const escribir = vi.fn().mockResolvedValue()
    Object.defineProperty(window.navigator, 'clipboard', { configurable: true, value: { writeText: escribir } })
    try {
      simularApi({ [RUTA]: { sse: textoSSE(FLUJO_ALERTAS) } })
      await abrirVera()
      await preguntar('a')
      const copiar = await screen.findByRole('button', { name: 'Copiar' })
      await act(async () => { fireEvent.click(copiar) })
      expect(escribir).toHaveBeenCalledWith('En GLORIETA hay 243 alertas críticas.')
      expect(screen.getByRole('button', { name: 'Copiada' })).toBeInTheDocument()
    } finally {
      delete window.navigator.clipboard
    }
  })

  it('M9: el aviso vuelve a «Copiar» a los 2 s; sin portapapeles no hay botón', async () => {
    vi.useFakeTimers()
    const escribir = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText: escribir } })
    const { unmount } = render(<BotonCopiar texto="**Hola**" />)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copiar' })) })
    expect(escribir).toHaveBeenCalledWith('Hola')
    expect(screen.getByRole('button', { name: 'Copiada' })).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(screen.getByRole('button', { name: 'Copiar' })).toBeInTheDocument()
    // Si el navegador lo niega, no cambia nada
    escribir.mockRejectedValueOnce(new Error('negado'))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copiar' })) })
    expect(screen.getByRole('button', { name: 'Copiar' })).toBeInTheDocument()
    unmount()
    vi.stubGlobal('navigator', {})
    render(<BotonCopiar texto="Hola" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it.each([
    ['gerente', USUARIOS.gerente, 'red'],
    ['admin_sucursal', USUARIOS.adminNorte, 'sucursal'],
  ])('M12: en Alertas, el %s ve las preguntas de esa página', async (_rol, usuario, grupo) => {
    renderConUsuario(<ChatProvider><Columna /></ChatProvider>, usuario, { ruta: '/alertas' })
    await userEvent.click(screen.getByRole('button', { name: 'Abrir el chat con Vera' }))
    expect(screen.getByText('Sobre Alertas:')).toBeInTheDocument()
    const botones = within(screen.getByRole('group', { name: 'Preguntas rápidas' })).getAllByRole('button')
    expect(botones.map(b => b.textContent)).toEqual(PREGUNTAS_POR_PAGINA['/alertas'][grupo])
  })

  it('M10: el campo crece con el texto', async () => {
    const campo = await abrirVera()
    Object.defineProperty(campo, 'scrollHeight', { configurable: true, value: 120 })
    await userEvent.type(campo, 'una{Shift>}{Enter}{/Shift}dos{Shift>}{Enter}{/Shift}tres')
    expect(campo.style.height).toBe('120px')
    expect(campo).toHaveClass('max-h-36', 'overflow-y-auto')
  })

  it('M11: Alt+V abre Vera, lleva el foco al campo y la cierra', async () => {
    renderConUsuario(<><button type="button">afuera</button><ChatProvider><Columna /></ChatProvider></>)
    const vera = screen.getByRole('button', { name: 'Abrir el chat con Vera' })
    expect(vera).toHaveAttribute('aria-keyshortcuts', 'Alt+V')
    expect(vera).toHaveAttribute('title', 'Abrir el chat con Vera (Alt+V)')
    await userEvent.keyboard('{Alt>}v{/Alt}')
    const campo = await screen.findByRole('textbox', { name: 'Escribe tu pregunta a Vera' })
    expect(campo).toHaveFocus()
    // Abierta y con el foco afuera: lo trae al campo, sin cerrarla
    screen.getByRole('button', { name: 'afuera' }).focus()
    await userEvent.keyboard('{Alt>}v{/Alt}')
    expect(campo).toHaveFocus()
    // Con el foco adentro: la cierra
    await userEvent.keyboard('{Alt>}v{/Alt}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // Otras combinaciones no hacen nada
    await userEvent.keyboard('{Control>}{Alt>}v{/Alt}{/Control}')
    await userEvent.keyboard('v')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('Vera (ícono y avatar)', () => {
  it('dibuja cada variante, anima las barras al pensar y cae al ícono si la variante no existe', () => {
    const { container } = render(<>
      <Vera variante="avatar-claro" pensando titulo="Avatar" />
      <Vera variante="otra" />
    </>)
    const [avatar, icono] = container.querySelectorAll('svg')
    expect(avatar.querySelector('circle')).toHaveAttribute('fill', '#EFF6FF')
    expect(avatar.querySelectorAll('.vera-pensando')).toHaveLength(3)
    expect(icono.querySelector('path')).toHaveAttribute('fill', '#1E3A5F')
    expect(icono.querySelectorAll('.vera-pensando')).toHaveLength(0)
    expect(screen.getByRole('img', { name: 'Avatar' })).toBeInTheDocument()
  })

  it('useChatPanel fuera del proveedor avisa', () => {
    const Suelto = () => { useChatPanel(); return null }
    // React y jsdom reportan el error esperado; se silencian para no ensuciar la salida
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const callar = e => e.preventDefault()
    window.addEventListener('error', callar)
    expect(() => render(<Suelto />)).toThrow('useChatPanel must be inside ChatProvider')
    window.removeEventListener('error', callar)
  })
})
