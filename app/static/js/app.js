(() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const drawer = document.querySelector('[data-drawer]');
  const drawerBackdrop = document.querySelector('[data-drawer-backdrop]');
  const drawerContent = document.querySelector('[data-drawer-content]');
  const cartCountNodes = Array.from(document.querySelectorAll('[data-cart-count]'));
  const cartOpenButtons = Array.from(document.querySelectorAll('[data-cart-open]'));
  const toast = createToast();

  const state = {
    cart: { revision: 0, units: 0, lines: 0, total: '0.00', subtotal: '0.00', items: [] },
    openKind: null,
    openSequence: 0,
    cartSequence: 0,
    cartLoaded: false,
  };

  function uid() {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }
    return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  }

  function money(value) {
    const amount = Number.parseFloat(value ?? 0);
    return new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number.isFinite(amount) ? amount : 0);
  }

  function setCartCount(value) {
    cartCountNodes.forEach((node) => {
      node.textContent = String(value ?? 0);
    });
  }

  function createToast() {
    const node = document.createElement('div');
    node.className = 'toast';
    node.hidden = true;
    document.body.appendChild(node);
    return node;
  }

  let toastTimer = null;
  function showToast(message, kind = 'ok') {
    if (!toast) return;
    toast.className = `toast toast-${kind}`;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 2200);
  }

  function openDrawer() {
    if (!drawer || !drawerBackdrop) return;
    if (state.openKind) {
      drawer.dataset.kind = state.openKind;
    } else {
      delete drawer.dataset.kind;
    }
    drawer.classList.add('is-open');
    drawerBackdrop.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
  }

  function closeDrawer() {
    if (!drawer || !drawerBackdrop) return;
    drawer.classList.remove('is-open');
    drawerBackdrop.hidden = true;
    drawer.setAttribute('aria-hidden', 'true');
    state.openKind = null;
    delete drawer.dataset.kind;
  }

  function renderLoading(title = 'A carregar...') {
    if (!drawerContent) return;
    drawerContent.innerHTML = `
      <section class="card drawer-card">
        <div class="page-heading">
          <div>
            <h1>${escapeHtml(title)}</h1>
            <p>Aguarda um momento.</p>
          </div>
        </div>
      </section>
    `;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set('X-CSRF-Token', csrfToken);
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }
    if (options.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers,
    });
    return response;
  }

  function updateCatalogChromeFromDocument(doc, activeLabel) {
    const heading = document.querySelector('.catalog-head h1');
    if (heading && activeLabel) {
      heading.textContent = activeLabel;
    }

    const sub = document.querySelector('.catalog-sub');
    const meta = doc.querySelector('.catalog-meta');
    const totalSpan = meta?.querySelector('span:first-child');
    if (sub && totalSpan) {
      sub.textContent = totalSpan.textContent.trim();
    }

    const info = document.getElementById('srch-info');
    if (info && totalSpan) {
      const totalValue = (totalSpan.textContent.match(/\d+/) || ['0'])[0];
      info.innerHTML = `<b>${totalValue}</b> resultados`;
    }

    const tabs = Array.from(document.querySelectorAll('.tabs .tab'));
    tabs.forEach((tab) => {
      tab.classList.toggle('on', tab.textContent.trim() === activeLabel);
    });
  }

  async function loadCatalog(url, activeLabel, activeButton) {
    const parsed = new URL(url, window.location.origin);
    for (const [key, value] of Array.from(parsed.searchParams.entries())) {
      if (!value) {
        parsed.searchParams.delete(key);
      }
    }
    parsed.pathname = '/catalogo/list';
    const listUrl = parsed.toString();
    const response = await apiFetch(listUrl, { headers: { Accept: 'text/html' } });
    const html = await response.text();
    if (!response.ok) {
      throw new Error(`catalog_load_${response.status}`);
    }
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const results = doc.querySelector('#catalog-results');
    const target = document.getElementById('catalog-results');
    if (results && target) {
      target.innerHTML = results.innerHTML;
    } else if (target) {
      target.innerHTML = html;
    }
    updateCatalogChromeFromDocument(doc, activeLabel);
    if (activeButton) {
      const tabs = Array.from(document.querySelectorAll('.tabs .tab'));
      tabs.forEach((tab) => tab.classList.remove('on'));
      activeButton.classList.add('on');
    }
    const publicUrl = listUrl.replace('/catalogo/list', '/catalogo');
    window.history.replaceState({}, '', publicUrl);
  }

  async function fetchCart({ open = false } = {}) {
    const seq = ++state.cartSequence;
    const response = await apiFetch('/me/cart?output=json');
    const payload = await response.json();
    if (seq < state.cartSequence) {
      return;
    }
    if (!payload.ok || !payload.cart) {
      return;
    }
    if (payload.cart.revision < state.cart.revision) {
      return;
    }
    state.cart = payload.cart;
    state.cartLoaded = true;
    setCartCount(payload.cart.units);
    if (open && state.openKind === 'cart') {
      renderCart(payload.cart);
    }
  }

  function normalizeItem(item) {
    return {
      id: item.id,
      ref: item.ref,
      name: item.name,
      type: item.type,
      color: item.color || '',
      size: item.size || '',
      quantity: Number(item.quantity || 0),
      quantity_step: Number(item.quantity_step || 1),
      unit_price: item.unit_price ?? '0.00',
      line_total: item.line_total ?? '0.00',
      image_path: item.image_path || '',
      available: item.available !== false,
      warning: item.warning || '',
    };
  }

  function renderCart(cart) {
    if (!drawerContent) return;
    const items = Array.isArray(cart.items) ? cart.items.map(normalizeItem) : [];
    const empty = items.length === 0;
    const lines = items.map((item) => `
      <article class="cart-line ${item.available ? '' : 'is-muted'}" data-cart-item-id="${item.id}">
        <div class="cart-line-media">
          ${item.image_path ? `<img src="/media/${escapeHtml(item.image_path)}" alt="${escapeHtml(item.name)}">` : '<div class="product-placeholder">Sem imagem</div>'}
        </div>
        <div class="cart-line-body">
          <div class="cart-line-top">
            <div>
              <div class="cart-line-ref">REF. ${escapeHtml(item.ref)}</div>
              <h3>${escapeHtml(item.name)}</h3>
              <p class="muted">${escapeHtml(item.type)}</p>
            </div>
            <button class="cart-remove" type="button" data-cart-remove aria-label="Remover item">×</button>
          </div>
          <div class="chip-row">
            <span class="chip">Cor ${escapeHtml(item.color || '-')}</span>
            <span class="chip">Tamanho ${escapeHtml(item.size || '-')}</span>
            <span class="chip">${item.available ? 'Disponível' : 'Indisponível'}</span>
          </div>
          ${item.warning ? `<p class="alert alert-error">${escapeHtml(item.warning)}</p>` : ''}
          <div class="cart-line-price">
            <strong>${money(item.line_total)}</strong>
            <span>${money(item.unit_price)} / un.</span>
          </div>
          <form class="cart-item-form stack" data-cart-update-form>
            <input type="hidden" name="item_id" value="${item.id}">
            <input type="hidden" name="cart_revision" value="${cart.revision}">
            <input type="hidden" name="idempotency_key" value="">
            <div class="quantity-stepper">
              <button class="btn btn-secondary quantity-button" type="button" data-cart-qty-dec>-</button>
              <input type="number" name="quantity" value="${item.quantity}" min="${item.quantity_step}" step="${item.quantity_step}" data-quantity-input data-quantity-step="${item.quantity_step}">
              <button class="btn btn-secondary quantity-button" type="button" data-cart-qty-inc>+</button>
            </div>
            <div class="cart-line-actions">
              <button class="btn btn-secondary" type="submit">Atualizar</button>
            </div>
          </form>
        </div>
      </article>
    `).join('');

    drawerContent.innerHTML = `
      <section class="drawer-card" data-cart-revision="${cart.revision}">
        <div class="drawer-head">
          <div>
            <h2>Carrinho de Encomendas</h2>
            <p class="drawer-sub">Revisão ${cart.revision}</p>
          </div>
          <div class="drawer-summary">
            <span><strong>${cart.lines}</strong> Linhas</span>
            <span><strong>${cart.units}</strong> Unidades</span>
            <span><strong>${money(cart.total)}</strong> Total</span>
          </div>
        </div>
        ${empty ? '<div class="empty-state">A encomenda está vazia.</div>' : `<div class="drawer-items">${lines}</div>`}
        <form class="cart-submit-form" data-order-submit-form>
          <input type="hidden" name="idempotency_key" value="${uid()}">
          <input type="hidden" name="cart_revision" value="${cart.revision}">
          <label class="stack">
            <span>Notas da encomenda</span>
            <textarea name="notes" rows="3" placeholder="Instruções, observações ou referência interna"></textarea>
          </label>
          <div class="cart-actions">
            <button class="btn" type="submit" ${empty ? 'disabled' : ''}>Enviar encomenda</button>
            <button class="btn btn-secondary" type="button" data-cart-refresh>Atualizar</button>
            <button class="btn btn-secondary cart-clear-btn" type="button" data-cart-clear>Limpar carrinho</button>
          </div>
        </form>
      </section>
    `;
    state.cart = cart;
    state.cartLoaded = true;
    setCartCount(cart.units);
  }

  async function openCartDrawer() {
    state.openKind = 'cart';
    renderLoading('Encomenda');
    openDrawer();
    const seq = ++state.openSequence;
    const response = await apiFetch('/me/cart?output=json');
    const payload = await response.json();
    if (seq < state.openSequence) {
      return;
    }
    if (!payload.ok || !payload.cart) {
      showToast('Não foi possível carregar a encomenda.', 'error');
      return;
    }
    if (payload.cart.revision < state.cart.revision) {
      payload.cart = state.cart;
    }
    renderCart(payload.cart);
  }

  async function openProductPanel(url) {
    state.openKind = 'product';
    renderLoading('Produto');
    openDrawer();
    const seq = ++state.openSequence;
    const response = await fetch(url, { credentials: 'same-origin' });
    const html = await response.text();
    if (seq < state.openSequence) {
      return;
    }
    if (!response.ok) {
      showToast('Não foi possível carregar o produto.', 'error');
      return;
    }
    if (drawerContent) {
      drawerContent.innerHTML = html;
    }
  }

  async function submitCartAdd(form) {
    const data = new FormData(form);
    const body = {
      idempotency_key: data.get('idempotency_key') || uid(),
      cart_revision: Number.parseInt(data.get('cart_revision') || '0', 10) || 0,
      ref: String(data.get('ref') || ''),
      color: String(data.get('color') || ''),
      size: String(data.get('size') || ''),
      quantity: Number.parseInt(data.get('quantity') || '', 10) || null,
      csrf_token: String(data.get('csrf_token') || csrfToken || ''),
    };
    form.querySelector('input[name="idempotency_key"]').value = body.idempotency_key;
    const response = await apiFetch('/me/cart/items', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw payload;
    }
    if (payload.cart.revision >= state.cart.revision) {
      state.cart = payload.cart;
      setCartCount(payload.cart.units);
    }
    showToast('Produto adicionado à encomenda.');
    if (state.openKind === 'cart') {
      renderCart(payload.cart);
    } else {
      form.querySelector('input[name="cart_revision"]').value = String(payload.cart.revision);
    }
    return payload.cart;
  }

  async function submitCartUpdate(form, itemId, quantity) {
    const body = {
      idempotency_key: form.querySelector('input[name="idempotency_key"]').value || uid(),
      cart_revision: Number.parseInt(form.querySelector('input[name="cart_revision"]').value || '0', 10) || 0,
      quantity: Number.parseInt(quantity, 10),
      csrf_token: String(form.querySelector('input[name="csrf_token"]')?.value || csrfToken || ''),
    };
    form.querySelector('input[name="idempotency_key"]').value = body.idempotency_key;
    const response = await apiFetch(`/me/cart/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw payload;
    }
    state.cart = payload.cart;
    setCartCount(payload.cart.units);
    renderCart(payload.cart);
  }

  async function submitCartRemove(form, itemId) {
    const body = {
      idempotency_key: form.querySelector('input[name="idempotency_key"]').value || uid(),
      cart_revision: Number.parseInt(form.querySelector('input[name="cart_revision"]').value || '0', 10) || 0,
      csrf_token: String(form.querySelector('input[name="csrf_token"]')?.value || csrfToken || ''),
    };
    form.querySelector('input[name="idempotency_key"]').value = body.idempotency_key;
    const response = await apiFetch(`/me/cart/items/${itemId}`, {
      method: 'DELETE',
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw payload;
    }
    state.cart = payload.cart;
    setCartCount(payload.cart.units);
    renderCart(payload.cart);
  }

  async function clearCart() {
    const response = await apiFetch('/me/cart', {
      method: 'DELETE',
      body: JSON.stringify({
        idempotency_key: uid(),
        cart_revision: state.cart.revision || 0,
        csrf_token: csrfToken || '',
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw payload;
    }
    state.cart = payload.cart;
    setCartCount(payload.cart.units);
    renderCart(payload.cart);
    showToast('Carrinho limpo.');
  }


  async function submitOrder(form) {
    const data = new FormData(form);
    const body = {
      idempotency_key: String(data.get('idempotency_key') || uid()),
      cart_revision: Number.parseInt(data.get('cart_revision') || '0', 10) || 0,
      notes: String(data.get('notes') || '').trim() || null,
      csrf_token: String(data.get('csrf_token') || csrfToken || ''),
    };
    const keyField = form.querySelector('input[name="idempotency_key"]');
    if (keyField) {
      keyField.value = body.idempotency_key;
    }
    const response = await apiFetch('/me/orders', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw payload;
    }
    state.cart = payload.cart || { revision: body.cart_revision + 1, units: 0, lines: 0, total: '0.00', subtotal: '0.00', items: [] };
    setCartCount(state.cart.units || 0);
    if (state.openKind === 'cart') {
      renderCart(state.cart);
    }
    if (payload.order?.url) {
      window.location.assign(payload.order.url);
      return payload.order;
    }
    showToast('Encomenda criada.');
    return payload.order;
  }

  function stepQuantity(input, delta) {
    const step = Number.parseInt(input.dataset.quantityStep || input.step || '1', 10) || 1;
    const current = Number.parseInt(input.value || String(step), 10) || step;
    const next = Math.max(step, current + delta * step);
    input.value = String(next);
  }

  function submitSearchForm(input) {
    const form = input?.closest('form');
    if (!form) return;
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
      return;
    }
    form.submit();
  }

  document.addEventListener('click', async (event) => {
    const catalogLink = event.target.closest('[data-catalog-url], [data-catalog-link]');
    if (catalogLink) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
        return;
      }
      event.preventDefault();
      try {
        await loadCatalog(catalogLink.dataset.catalogUrl || catalogLink.href, catalogLink.textContent.trim(), catalogLink);
      } catch (error) {
        console.warn('CATALOG_LOAD_FAIL', error);
        showToast(`Não foi possível atualizar o catálogo.${error?.message ? ` ${error.message}` : ''}`, 'error');
      }
      return;
    }

    const cartOpen = event.target.closest('[data-cart-open]');
    if (cartOpen) {
      event.preventDefault();
      try {
        await openCartDrawer();
      } catch (error) {
        showToast('Não foi possível carregar a encomenda.', 'error');
      }
      return;
    }

    const close = event.target.closest('[data-drawer-close]');
    if (close) {
      event.preventDefault();
      closeDrawer();
      return;
    }

    const backdrop = event.target.closest('[data-drawer-backdrop]');
    if (backdrop) {
      closeDrawer();
      return;
    }

    const productOpen = event.target.closest('[data-product-open]');
    if (productOpen) {
      event.preventDefault();
      try {
        await openProductPanel(productOpen.dataset.panelUrl || `${productOpen.href}${productOpen.href.includes('?') ? '&' : '?'}panel=1`);
      } catch (error) {
        showToast('Não foi possível carregar o produto.', 'error');
      }
      return;
    }

    const qtyInc = event.target.closest('[data-cart-qty-inc], [data-qty-inc]');
    if (qtyInc) {
      event.preventDefault();
      const form = qtyInc.closest('form');
      const input = form?.querySelector('[data-quantity-input]');
      if (input) {
        stepQuantity(input, 1);
      }
      return;
    }

    const qtyDec = event.target.closest('[data-cart-qty-dec], [data-qty-dec]');
    if (qtyDec) {
      event.preventDefault();
      const form = qtyDec.closest('form');
      const input = form?.querySelector('[data-quantity-input]');
      if (input) {
        stepQuantity(input, -1);
      }
      return;
    }

    const removeButton = event.target.closest('[data-cart-remove]');
    if (removeButton) {
      event.preventDefault();
      const form = removeButton.closest('form');
      const itemId = form?.querySelector('input[name="item_id"]')?.value;
      if (form && itemId) {
        try {
          await submitCartRemove(form, itemId);
        } catch (error) {
          showToast('Não foi possível remover o item.', 'error');
        }
      }
      return;
    }

    const refreshButton = event.target.closest('[data-cart-refresh]');
    if (refreshButton) {
      event.preventDefault();
      try {
        await fetchCart({ open: true });
      } catch (error) {
        showToast('Não foi possível atualizar a encomenda.', 'error');
      }
      return;
    }

    const clearButton = event.target.closest('[data-cart-clear]');
    if (clearButton) {
      event.preventDefault();
      try {
        await clearCart();
      } catch (error) {
        showToast('Não foi possível limpar a encomenda.', 'error');
      }
    }
  });

  document.addEventListener('submit', async (event) => {
    const addForm = event.target.closest('[data-cart-add-form]');
    if (addForm) {
      event.preventDefault();
      try {
        await submitCartAdd(addForm);
      } catch (error) {
        showToast(error?.detail || 'Não foi possível adicionar o produto.', 'error');
      }
      return;
    }

    const orderForm = event.target.closest('[data-order-submit-form]');
    if (orderForm) {
      event.preventDefault();
      try {
        await submitOrder(orderForm);
      } catch (error) {
        showToast(error?.detail || 'Não foi possível enviar a encomenda.', 'error');
      }
      return;
    }

    const updateForm = event.target.closest('[data-cart-update-form]');
    if (updateForm) {
      event.preventDefault();
      const itemId = updateForm.querySelector('input[name="item_id"]').value;
      const quantity = updateForm.querySelector('input[name="quantity"]').value;
      try {
        if (Number.parseInt(quantity, 10) <= 0) {
          await submitCartRemove(updateForm, itemId);
        } else {
          await submitCartUpdate(updateForm, itemId, quantity);
        }
      } catch (error) {
        showToast(error?.detail || 'Não foi possível atualizar o item.', 'error');
      }
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      const searchInput = event.target.closest?.('[data-search-input]');
      if (searchInput) {
        event.preventDefault();
        submitSearchForm(searchInput);
        return;
      }
    }
    if (event.key === 'Escape') {
      closeDrawer();
    }
  });

  document.addEventListener('click', (event) => {
    const searchClear = event.target.closest('[data-search-clear]');
    if (!searchClear) return;
    const form = searchClear.closest('form');
    const input = form?.querySelector('[data-search-input]');
    if (input) {
      input.value = '';
    }
    if (form) {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }
  });

  document.body.addEventListener('htmx:configRequest', (event) => {
    if (csrfToken) {
      event.detail.headers['X-CSRF-Token'] = csrfToken;
    }
  });

  if (cartOpenButtons.length) {
    fetchCart({ open: false }).catch(() => {});
  }
})();
document.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-password-reveal]');
  if (!trigger) return;
  const form = trigger.closest('[data-password-reset]');
  const input = form?.querySelector('[data-password-input]');
  if (!input) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  trigger.textContent = reveal ? 'Ocultar' : 'Mostrar';
});

(() => {
  const page = document.querySelector('[data-users-page]');
  if (page) return; // Isolated in admin-users.js so other app features cannot block it.
  if (!page) return;
  const filters = page.querySelector('[data-user-filters]');
  const modal = page.querySelector('[data-user-modal]');
  const loading = page.querySelector('[data-user-loading]');
  let searchTimer = null;
  let requestSequence = 0;

  function setModal(open) {
    if (!modal) return;
    modal.hidden = !open;
    document.body.classList.toggle('has-user-modal', open);
    if (open) window.setTimeout(() => modal.querySelector('input[name="username"]')?.focus(), 30);
  }

  async function refreshUsers() {
    const sequence = ++requestSequence;
    const params = new URLSearchParams(new FormData(filters));
    for (const [key, value] of Array.from(params.entries())) {
      if (!value || (key === 'status' && value === 'all')) params.delete(key);
    }
    const url = `${window.location.pathname}${params.size ? `?${params}` : ''}`;
    loading?.classList.add('is-loading');
    try {
      const response = await fetch(url, { headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error('user_search_failed');
      const html = await response.text();
      if (sequence !== requestSequence) return;
      const next = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-user-results]');
      const current = page.querySelector('[data-user-results]');
      if (next && current) current.replaceWith(next);
      window.history.replaceState({}, '', url);
      const role = filters.elements.role.value;
      page.querySelectorAll('[data-user-role]').forEach((item) => item.classList.toggle('is-active', item.dataset.userRole === role));
    } finally {
      if (sequence === requestSequence) loading?.classList.remove('is-loading');
    }
  }

  filters?.addEventListener('submit', (event) => { event.preventDefault(); refreshUsers().catch(() => {}); });
  filters?.querySelector('[data-user-search]')?.addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => refreshUsers().catch(() => {}), 220);
  });
  filters?.querySelectorAll('[data-user-filter]').forEach((select) => select.addEventListener('change', () => refreshUsers().catch(() => {})));

  page.addEventListener('click', (event) => {
    const roleLink = event.target.closest('[data-user-role]');
    if (roleLink) {
      event.preventDefault();
      filters.elements.role.value = roleLink.dataset.userRole || '';
      refreshUsers().catch(() => {});
      return;
    }
    if (event.target.closest('[data-user-modal-open]')) setModal(true);
    if (event.target.closest('[data-user-modal-close]')) setModal(false);
  });

  page.addEventListener('submit', async (event) => {
    const toggleForm = event.target.closest('[data-user-toggle]');
    if (!toggleForm) return;
    event.preventDefault();
    const button = toggleForm.querySelector('.toggle-switch');
    const label = toggleForm.querySelector('span');
    const row = toggleForm.closest('[data-user-row]');
    button.disabled = true;
    try {
      const response = await fetch(toggleForm.action, { method: 'POST', body: new FormData(toggleForm) });
      if (!response.ok) throw new Error('user_toggle_failed');
      const active = !button.classList.contains('is-on');
      button.classList.toggle('is-on', active);
      button.setAttribute('aria-checked', String(active));
      label.textContent = active ? 'Ativo' : 'Inativo';
      row.classList.toggle('is-inactive', !active);
    } finally {
      button.disabled = false;
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && modal && !modal.hidden) setModal(false);
  });
})();
