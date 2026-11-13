(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#f3f1ec");
      tg.setBackgroundColor("#f3f1ec");
    } catch (_) {
      /* ignore */
    }
  }

  const params = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(
    (window.location.hash || "").replace(/^#/, "").replace(/^\?/, "")
  );
  const orderId = (
    params.get("order_id") ||
    hashParams.get("order_id") ||
    ""
  ).toUpperCase();
  const requestedTab = params.get("tab") || hashParams.get("tab");
  let activeTab = requestedTab === "map" ? "map" : requestedTab === "history" ? "history" : "status";

  const el = {
    tabs: document.getElementById("tabs"),
    loading: document.getElementById("state-loading"),
    error: document.getElementById("state-error"),
    panelStatus: document.getElementById("panel-status"),
    panelMap: document.getElementById("panel-map"),
    panelHistory: document.getElementById("panel-history"),
    historyList: document.getElementById("history-list"),
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
    courierPhone: document.getElementById("courier-phone"),
    total: document.getElementById("total"),
    items: document.getElementById("items-count"),
    mapNote: document.getElementById("map-note"),
    mapFallback: document.getElementById("map-fallback"),
    map: document.getElementById("map"),
  };

  let map = null;
  let destMarker = null;
  let courierMarker = null;
  let ymap = null;
  let yDest = null;
  let yCourier = null;
  let pollTimer = null;
  let lastData = null;

  function show(name) {
    el.loading.hidden = name !== "loading";
    el.error.hidden = name !== "error";
    const ok = name === "order";
    el.tabs.hidden = !ok;
    if (!ok) {
      el.panelStatus.hidden = true;
      el.panelMap.hidden = true;
      el.panelHistory.hidden = true;
      return;
    }
    // Не сбрасываем activeTab при loading/error — иначе tab=map теряется
    applyTab(activeTab);
  }

  function applyTab(tab) {
    if (tab === "map" || tab === "status" || tab === "history") {
      activeTab = tab;
    }
    document.querySelectorAll(".tab").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.tab === activeTab);
    });
    el.panelStatus.hidden = activeTab !== "status";
    el.panelMap.hidden = activeTab !== "map";
    el.panelHistory.hidden = activeTab !== "history";
    if (activeTab === "map" && lastData) {
      renderMap(lastData).then(() => {
        if (map) setTimeout(() => map.invalidateSize(), 50);
        if (ymap) setTimeout(() => ymap.container.fitToViewport(), 50);
      });
    }
    if (activeTab === "history") {
      loadHistory();
    }
  }

  function setHistoryMessage(text) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = text;
    el.historyList.replaceChildren(p);
  }

  function renderHistoryCard(order) {
    const article = document.createElement("article");
    article.className = "history-card";
    article.dataset.order = order.id;

    const title = document.createElement("strong");
    title.textContent = order.id;
    article.append(title, document.createTextNode(` · ${order.status_label}`));
    article.append(document.createElement("br"));

    const meta = document.createElement("span");
    meta.className = "muted";
    meta.textContent = `${order.delivery_slot || "—"} · ${order.total_amount} ₽`;
    article.append(meta);

    if (order.can_reorder) {
      article.append(document.createElement("br"));
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "можно повторить";
      article.append(tag);
    }
    if (order.can_review) {
      article.append(document.createElement("br"));
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "можно оценить";
      article.append(tag);
    }

    article.addEventListener("click", () => {
      const oid = article.dataset.order;
      if (oid) window.location.search = `?order_id=${oid}`;
      window.location.reload();
    });
    return article;
  }

  async function loadHistory() {
    setHistoryMessage("Загрузка…");
    try {
      const resp = await fetch(`${apiBase()}/history`, { headers: authHeaders() });
      if (!resp.ok) throw new Error(`Ошибка ${resp.status}`);
      const items = await resp.json();
      if (!items.length) {
        setHistoryMessage("История пуста. Подтвердите заказ в боте.");
        return;
      }
      el.historyList.replaceChildren(...items.map(renderHistoryCard));
    } catch (err) {
      setHistoryMessage(err?.message || "Не удалось загрузить историю");
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => applyTab(btn.dataset.tab));
  });

  function apiBase() {
    return `${window.location.origin}/webapp/v1`;
  }

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    } else {
      headers["X-WebApp-Dev-User"] = params.get("dev_user") || "1";
    }
    return headers;
  }

  async function loadOrder() {
    if (!orderId) {
      show("error");
      el.errorText.textContent = "В ссылке нет order_id.";
      return;
    }

    show("loading");
    try {
      const resp = await fetch(`${apiBase()}/orders/${encodeURIComponent(orderId)}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `Ошибка ${resp.status}`);
      }
      const data = await resp.json();
      lastData = data;
      renderStatus(data);
      show("order");
      if (activeTab === "map") await renderMap(data);
      startPolling();
    } catch (err) {
      show("error");
      el.errorText.textContent =
        err?.message ||
        "Не удалось загрузить статус. Сначала подтвердите заказ в боте.";
    }
  }

  function renderStatus(data) {
    el.orderId.textContent = data.id;
    el.statusLabel.textContent = data.status_label;
    el.statusDot.style.background = data.status_color;
    document.documentElement.style.setProperty("--status", data.status_color);

    if (
      data.eta_minutes != null &&
      data.status !== "delivered" &&
      data.status !== "cancelled"
    ) {
      el.etaBlock.hidden = false;
      el.etaMinutes.textContent = String(data.eta_minutes);
    } else {
      el.etaBlock.hidden = true;
    }

    el.slot.textContent = data.delivery_slot || "—";
    el.address.textContent = data.address || "—";
    el.courier.textContent = data.courier_name || "ещё не назначен";
    el.courierPhone.textContent = data.courier_phone || "—";
    el.total.textContent = `${data.total_amount} ₽`;
    el.items.textContent = String(data.items_count ?? 0);
  }

  async function ensureYandex(apiKey) {
    if (window.ymaps) {
      return new Promise((resolve) => window.ymaps.ready(() => resolve(window.ymaps)));
    }
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(apiKey)}&lang=ru_RU`;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return new Promise((resolve) => window.ymaps.ready(() => resolve(window.ymaps)));
  }

  async function renderMap(data) {
    if (data.yandex_maps_api_key) {
      try {
        await renderYandexMap(data);
        return;
      } catch (_) {
        el.mapNote.textContent = "Яндекс.Карты недоступны, показываем OpenStreetMap.";
      }
    }
    renderLeafletMap(data);
  }

  async function renderYandexMap(data) {
    const ymaps = await ensureYandex(data.yandex_maps_api_key);
    el.mapNote.textContent = "Карта: Яндекс.Карты";
    const dest = [data.dest_lat, data.dest_lon];

    if (!ymap) {
      ymap = new ymaps.Map(el.map, {
        center: dest,
        zoom: 14,
        controls: ["zoomControl"],
      });
      yDest = new ymaps.Placemark(dest, { balloonContent: "Адрес доставки" });
      ymap.geoObjects.add(yDest);
    } else {
      yDest.geometry.setCoordinates(dest);
    }

    if (data.gps_available && data.courier_lat != null && data.courier_lon != null) {
      el.mapFallback.hidden = true;
      const courier = [data.courier_lat, data.courier_lon];
      if (!yCourier) {
        yCourier = new ymaps.Placemark(
          courier,
          { balloonContent: data.courier_name || "Курьер" },
          { preset: "islands#blueCircleDotIcon" }
        );
        ymap.geoObjects.add(yCourier);
      } else {
        yCourier.geometry.setCoordinates(courier);
      }
      ymap.setBounds(ymaps.util.bounds.fromPoints([dest, courier]), {
        checkZoomRange: true,
        zoomMargin: 40,
      });
    } else {
      el.mapFallback.hidden = false;
      el.mapFallback.textContent =
        data.tracking_message ||
        "Геолокация курьера временно недоступна. Показан адрес доставки.";
      if (yCourier) {
        ymap.geoObjects.remove(yCourier);
        yCourier = null;
      }
      ymap.setCenter(dest, 14);
    }
  }

  function renderLeafletMap(data) {
    if (!window.L) {
      el.mapNote.textContent = "Карта недоступна в этом окружении.";
      return;
    }

    el.mapNote.textContent =
      "Карта: OpenStreetMap. Укажите YANDEX_MAPS_API_KEY для Яндекс.Карт.";

    const dest = [data.dest_lat, data.dest_lon];
    if (!map) {
      map = L.map(el.map, { zoomControl: true }).setView(dest, 14);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap",
      }).addTo(map);
      destMarker = L.marker(dest, { title: "Адрес доставки" })
        .addTo(map)
        .bindPopup("Адрес доставки");
    } else {
      destMarker.setLatLng(dest);
    }

    if (data.gps_available && data.courier_lat != null && data.courier_lon != null) {
      el.mapFallback.hidden = true;
      const courier = [data.courier_lat, data.courier_lon];
      if (!courierMarker) {
        courierMarker = L.circleMarker(courier, {
          radius: 9,
          color: "#0f766e",
          fillColor: "#14b8a6",
          fillOpacity: 0.9,
        })
          .addTo(map)
          .bindPopup(data.courier_name || "Курьер");
      } else {
        courierMarker.setLatLng(courier);
      }
      map.fitBounds(L.latLngBounds([dest, courier]).pad(0.35));
    } else {
      el.mapFallback.hidden = false;
      el.mapFallback.textContent =
        data.tracking_message ||
        "Геолокация курьера временно недоступна. Показан адрес доставки.";
      if (courierMarker) {
        map.removeLayer(courierMarker);
        courierMarker = null;
      }
      map.setView(dest, 14);
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const resp = await fetch(
          `${apiBase()}/orders/${encodeURIComponent(orderId)}`,
          { headers: authHeaders() }
        );
        if (!resp.ok) return;
        const data = await resp.json();
        lastData = data;
        renderStatus(data);
        if (activeTab === "map") await renderMap(data);
      } catch (_) {
        /* ignore */
      }
    }, 15000);
  }

  el.retry.addEventListener("click", loadOrder);
  loadOrder();
})();
