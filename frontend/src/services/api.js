import axios from 'axios'

export function cookie(name) {
  return document.cookie.split('; ').find(row => row.startsWith(`${name}=`))?.split('=').slice(1).join('=') || ''
}

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: { Accept: 'application/json' }
})

export const rootApi = axios.create({ withCredentials: true, headers: { Accept: 'application/json' } })

api.interceptors.request.use(config => {
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) config.headers['X-CSRF-Token'] = decodeURIComponent(cookie('villas_v2_csrf'))
  return config
})
rootApi.interceptors.request.use(config => {
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) config.headers['X-CSRF-Token'] = decodeURIComponent(cookie('villas_v2_csrf'))
  return config
})

export function errorMessage(error) {
  if (error?.response?.status === 413) return 'A imagem é demasiado grande para ser enviada. Reduza o ficheiro para menos de 8 MB e tente novamente.'
  const detail = error?.response?.data?.detail
  const labels = {
    invalid_credentials: 'Utilizador ou password incorretos.', login_required: 'A sessão terminou. Volte a entrar.',
    forbidden: 'Não tem permissão para esta operação.', username_exists: 'Esse utilizador já existe.',
    user_has_history: 'Este utilizador tem histórico e não pode ser eliminado.', cannot_delete_self: 'Não pode eliminar a sua própria conta.',
    password_too_short: 'A password deve ter pelo menos 8 caracteres.', product_not_available: 'Este produto já não está disponível.',
    product_in_use: 'Este produto não pode ser eliminado porque já existe em carrinhos ou encomendas.',
    category_inactive: 'Não é possível ativar este produto enquanto a categoria estiver desativada.',
    cart_revision_mismatch: 'O carrinho foi alterado noutra janela ou sessão. Atualizámos os dados; reveja as quantidades antes de confirmar.',
    idempotency_key_conflict: 'Esta operação já foi processada com dados diferentes. Atualize a página e tente novamente.',
    cart_empty: 'O carrinho está vazio. Adicione pelo menos um produto antes de continuar.',
    invalid_quantity: 'A quantidade indicada não é válida.',
    product_not_available: 'Este produto deixou de estar disponível. Remova-o e escolha outro produto.',
    customer_required: 'Selecione o cliente para quem esta encomenda será criada.',
    customer_not_available: 'O cliente selecionado está inativo ou já não existe.',
    email_delivery_failed: 'A operação foi concluída, mas o email não pôde ser enviado. Verifique o estado do email e tente novamente.',
    minimum_order_total: 'A encomenda deve ter um mínimo de 250,00 €.',
    cart_empty: 'O carrinho está vazio.', invalid_quantity_step: 'A quantidade não respeita o múltiplo definido.',
    invalid_image_format: 'O ficheiro escolhido não é uma imagem válida ou não pode ser convertido.',
    image_too_large: 'A imagem é demasiado grande. O limite é 8 MB.',
    image_dimensions_too_large: 'A imagem tem dimensões demasiado grandes.'
  }
  if (typeof detail === 'string') return labels[detail] || detail.replaceAll('_', ' ')
  return error?.message || 'Ocorreu um erro inesperado.'
}

export function idempotencyKey(prefix = 'web') {
  return `${prefix}-${crypto.randomUUID()}`
}
