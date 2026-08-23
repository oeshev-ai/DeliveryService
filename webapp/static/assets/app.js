(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    // Не берём text_color из темы Telegram: в тёмной теме он светлый,
    // а карточки у нас белые → белый текст на белом фоне.
    try {
      tg.setHeaderColor("#f3f1ec");
      tg.setBackgroundColor("#f3f1ec");
    } catch (_) {
      /* старые клиенты могут не поддерживать */
    }
  }

  const params = new URLSearchParams(window.location.search);
  const orderId = (params.get("order_id") || "").toUpperCase();

  const el = {
    loading: document.getElementById("state-loading"),
    error: document.getElementById("state-error"),
    order: document.getElementById("state-order"),
    errorText: document.getElementById("error-text"),
    retry: document.getElementById("btn-retry"),
    orderId: document.getElementById("order-id"),
    statusLabel: document.getElementById("status-label"),
    statusDot: document.getElementById("status-dot"),
    etaBlock: document.getElementById("eta-block"),
    etaMinutes: document.getElementById("eta-minutes"),
    slot: document.getElementById("delivery-slot"),
    address: document.getElementById("address"),
    courier: document.getElementById("courier"),
    total: document.getElementById("total"),
    items: document.getElementById("items-count"),
  };

  function show(name) {
    el.loading.hidden = name !== "loading";
    el.error.hidden = name !== "error";
    el.order.hidden = name !== "order";
  }

  function apiBase() {
    // UI на /ui/, API на том же origin: /webapp/v1
    return `${window.location.origin}/webapp/v1`;
  }

  async function loadOrder() {
    if (!orderId) {
      show("error");
      el.errorText.textContent = "В ссылке нет order_id.";
      return;
    }

    show("loading");
    const headers = { Accept: "application/json" };
    if (tg?.initData) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    } else {
      // Локальный просмотр в браузере (только при WEBAPP_DEV_BYPASS на API)
      headers["X-WebApp-Dev-User"] = params.get("dev_user") || "1";
    }

    try {
      const resp = await fetch(`${apiBase()}/orders/${encodeURIComponent(orderId)}`, {
        headers,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `Ошибка ${resp.status}`);
      }
      const data = await resp.json();
      render(data);
      show("order");
    } catch (err) {
      show("error");
      el.errorText.textContent =
        err?.message ||
        "Не удалось загрузить статус. Сначала подтвердите заказ в боте.";
    }
  }

  function render(data) {
    el.orderId.textContent = data.id;
    el.statusLabel.textContent = data.status_label;
    el.statusDot.style.background = data.status_color;
    document.documentElement.style.setProperty("--status", data.status_color);

    if (data.eta_minutes != null && data.status !== "delivered" && data.status !== "cancelled") {
      el.etaBlock.hidden = false;
      el.etaMinutes.textContent = String(data.eta_minutes);
    } else {
      el.etaBlock.hidden = true;
    }

    el.slot.textContent = data.delivery_slot || "—";
    el.address.textContent = data.address || "—";
    el.courier.textContent = data.courier_name || "ещё не назначен";
    el.total.textContent = `${data.total_amount} ₽`;
    el.items.textContent = String(data.items_count ?? 0);
  }

  el.retry.addEventListener("click", loadOrder);
  loadOrder();
})();
