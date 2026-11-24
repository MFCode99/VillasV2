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

function guardOfflineMutation(config) {
  const method = (config.method || 'get').toLowerCase()
  if (typeof navigator !== 'undefined' && !navigator.onLine && !['get', 'head', 'options'].includes(method)) {
    throw Object.assign(new Error('Sem ligação à Internet.'), { code: 'OFFLINE' })
  }
  return config
}

api.interceptors.request.use(config => {
  guardOfflineMutation(config)
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) config.headers['X-CSRF-Token'] = decodeURIComponent(cookie('villas_v2_csrf'))
  return config
})
api.interceptors.response.use(
  response => response,
  error => {
    if (error?.response?.status === 401 && error?.response?.data?.detail === 'login_required') {
      window.dispatchEvent(new CustomEvent('villas:session-expired'))
    }
    return Promise.reject(error)
  }
)
rootApi.interceptors.request.use(config => {
  guardOfflineMutation(config)
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) config.headers['X-CSRF-Token'] = decodeURIComponent(cookie('villas_v2_csrf'))
  return config
})

export function errorMessage(error) {
  if (error?.code === 'OFFLINE') return 'Sem ligação. Esta alteração não foi enviada; tente novamente quando estiver online.'
  if (error?.response?.status === 413) return 'A imagem é demasiado grande para ser enviada. Reduza o ficheiro para menos de 8 MB e tente novamente.'
  const requestId = error?.response?.data?.request_id || error?.response?.headers?.['x-request-id']
  if (Number(error?.response?.status || 0) >= 500) return `Ocorreu um erro interno. Tente novamente.${requestId ? ` Código: ${requestId}` : ''}`
  const detail = error?.response?.data?.detail
  const labels = {
    invalid_credentials: 'Utilizador ou password incorretos.', login_required: 'A sessão terminou. Volte a entrar.',
    forbidden: 'Não tem permissão para esta operação.', username_exists: 'Esse utilizador já existe.',
    user_has_history: 'Este utilizador tem histórico e não pode ser eliminado.', cannot_delete_self: 'Não pode eliminar a sua própria conta.',
    password_too_short: 'A password deve ter pelo menos 8 caracteres.', product_not_available: 'Este produto já não está disponível.',
    product_in_use: 'Este produto não pode ser eliminado porque já existe em carrinhos ou encomendas.',
    category_inactive: 'Não é possível ativar este produto enquanto a categoria estiver desativada.',
    category_parent_inactive: 'Não é possível ativar este produto enquanto a categoria principal estiver desativada.',
    catalog_not_found: 'O catálogo selecionado não existe ou está desativado.',
    catalog_forbidden: 'Este utilizador não tem acesso a este catálogo.',
    product_catalog_mismatch: 'Este produto pertence a outro catálogo. Abra o carrinho correto e tente novamente.',
    mixed_catalog_order: 'Uma encomenda não pode misturar produtos Villas e Utilidades.',
    category_catalog_mismatch: 'A categoria escolhida pertence a outro catálogo.',
    category_parent_not_found: 'A categoria principal escolhida já não existe.',
    category_parent_self: 'Uma categoria não pode ser subordinada a si própria.',
    category_depth_exceeded: 'Só são permitidos dois níveis: categoria e subcategoria.',
    category_not_found: 'Esta categoria já não existe.',
    catalog_has_products: 'Este catálogo ainda tem produtos. Elimine-os ou mova-os antes de apagar o catálogo.',
    system_catalog_protected: 'Os catálogos Villas e Utilidades são áreas base e não podem ser eliminados.',
    campaign_product_not_found: 'Um dos produtos selecionados já não existe.',
    campaign_invalid_period: 'A data final da campanha deve ser posterior à data inicial.',
    campaign_discount_invalid: 'O desconto indicado não é válido.',
    gift_promotion_not_found: 'Esta promoção já não existe.',
    gift_promotion_product_not_found: 'Um dos produtos elegíveis já não existe ou pertence a outro catálogo.',
    gift_promotion_brand_not_found: 'Uma das marcas selecionadas já não está disponível neste catálogo.',
    gift_promotion_gift_not_found: 'O produto oferecido já não existe ou pertence a outro catálogo.',
    gift_promotion_gift_is_eligible: 'O produto oferecido não pode também contar para atingir a promoção.',
    gift_promotion_threshold_required: 'Indique uma quantidade ou um valor mínimo válido.',
    gift_promotion_invalid_period: 'A data final deve ser posterior à data inicial.',
    customer_group_not_found: 'Um dos grupos selecionados já não existe.',
    customer_group_exists: 'Já existe um grupo de clientes com esse nome.',
    customer_group_user_invalid: 'O grupo contém um utilizador que não é um cliente válido.',
    import_file_empty: 'O ficheiro está vazio.',
    import_file_too_large: 'O ficheiro ultrapassa o limite permitido (10 MB para folhas de cálculo ou 40 MB para PDF).',
    import_file_type: 'Use um ficheiro Excel (.xlsx), CSV ou PDF.',
    import_columns_missing: 'Não encontrei as colunas obrigatórias: referência, descrição e preço.',
    invalid_pdf: 'O ficheiro PDF não é válido.',
    encrypted_pdf_not_supported: 'O PDF está protegido. Remova a password antes de importar.',
    invalid_pdf_page_count: 'O PDF está vazio ou tem demasiadas páginas.',
    pdf_text_not_detected: 'Este PDF parece ser apenas uma digitalização. É necessário texto pesquisável para reconhecer os produtos.',
    pdf_product_table_not_detected: 'Não foi encontrada uma tabela de produtos com referência, nome, quantidades e preço.',
    invalid_decimal_value: 'Um dos valores de preço não é válido.',
    cart_revision_mismatch: 'O carrinho foi alterado noutra janela ou sessão. Atualizámos os dados; reveja as quantidades antes de confirmar.',
    idempotency_key_conflict: 'Esta operação já foi processada com dados diferentes. Atualize a página e tente novamente.',
    cart_empty: 'O carrinho está vazio. Adicione pelo menos um produto antes de continuar.',
    invalid_quantity: 'A quantidade indicada não é válida.',
    product_not_available: 'Este produto deixou de estar disponível. Remova-o e escolha outro produto.',
    customer_required: 'Selecione o cliente para quem esta encomenda será criada.',
    customer_not_available: 'O cliente selecionado está inativo ou já não existe.',
    email_delivery_failed: 'A operação foi concluída, mas o email não pôde ser enviado. Verifique o estado do email e tente novamente.',
    minimum_order_total: 'A encomenda deve ter um mínimo de 250,00 €.',
    minimum_order_total_interpilhas: 'A encomenda de Utilidades deve ter um mínimo de 300,00 €.',
    cart_empty: 'O carrinho está vazio.', invalid_quantity_step: 'A quantidade não respeita o múltiplo definido.',
    invalid_image_format: 'O ficheiro escolhido não é uma imagem válida ou não pode ser convertido.',
    image_too_large: 'A imagem é demasiado grande. O limite é 8 MB.',
    image_dimensions_too_large: 'A imagem tem dimensões demasiado grandes.',
    invite_invalid: 'Este convite não é válido.',
    invite_expired: 'Este convite expirou. Peça um novo link de acesso.',
    invite_used: 'Este convite já foi utilizado. Entre com a password que definiu.',
    invite_duration_invalid: 'Escolha uma validade entre 1 hora e 30 dias.',
    update_not_ready: 'A atualização ainda não está pronta para ser instalada.',
    pending_update_not_found: 'Não existe uma atualização pendente para configurar.',
    invalid_update_channel: 'Escolha um canal de atualização válido.',
    update_release_not_found: 'A versão escolhida já não está disponível no histórico.',
    update_announcement_notes_invalid: 'Escolha pelo menos uma alteração válida para anunciar.',
    update_announcement_not_found: 'Este aviso já não existe.',
    user_not_available: 'Este utilizador está inativo ou já não está disponível.',
    password_mismatch: 'As passwords não coincidem.', current_password_invalid: 'A password atual não está correta.',
    repeat_order_no_available_products: 'Nenhum dos produtos desta encomenda está atualmente disponível.',
    import_batch_not_found: 'Este registo de importação já não existe.',
    import_batch_already_rolled_back: 'Esta importação já foi revertida.',
    cloudflare_not_configured: 'A ligação ao Cloudflare ainda não está configurada.',
    cloudflare_permission_denied: 'O token não tem permissões suficientes para esta operação.',
    cloudflare_zone_not_found: 'O token não permite aceder à zona vitorgouveia.com.',
    cloudflare_token_invalid: 'O token Cloudflare indicado não é válido.',
    cloudflare_unavailable: 'Não foi possível contactar o Cloudflare. Tente novamente.',
    cloudflare_request_failed: 'O Cloudflare recusou a operação. Confirme os dados e as permissões do token.',
    cloudflare_record_invalid: 'O registo DNS contém dados inválidos.',
    cloudflare_record_outside_zone: 'O nome do registo tem de pertencer a vitorgouveia.com.',
    cloudflare_identifier_invalid: 'O identificador enviado ao Cloudflare não é válido.',
    cloudflare_email_unavailable: 'O encaminhamento de email não está disponível nesta conta.',
    cloudflare_email_rule_invalid: 'Indique um endereço @vitorgouveia.com e um destino válido.',
    portal_email_not_configured: 'O portal ainda não tem um email configurado para receber mensagens.'
  }
  if (typeof detail === 'string') return labels[detail] || detail.replaceAll('_', ' ')
  return error?.message || 'Ocorreu um erro inesperado.'
}

export function idempotencyKey(prefix = 'web') {
  return `${prefix}-${crypto.randomUUID()}`
}
