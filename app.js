const elements = {
  symbol: document.querySelector("#symbol"),
  timeHorizon: document.querySelector("#timeHorizon"),
  entry: document.querySelector("#entry"),
  margin: document.querySelector("#margin"),
  leverage: document.querySelector("#leverage"),
  leverageValue: document.querySelector("#leverageValue"),
  stopLoss: document.querySelector("#stopLoss"),
  takeProfit: document.querySelector("#takeProfit"),
  planTakeProfit: document.querySelector("#planTakeProfit"),
  planStopLoss: document.querySelector("#planStopLoss"),
  username: document.querySelector("#username"),
  password: document.querySelector("#password"),
  avatarImage: document.querySelector("#avatarImage"),
  avatarInitial: document.querySelector("#avatarInitial"),
  avatarInput: document.querySelector("#avatarInput"),
  avatarUploadLabel: document.querySelector("#avatarUploadLabel"),
  sessionLabel: document.querySelector("#sessionLabel"),
  authMessage: document.querySelector("#authMessage"),
  authForm: document.querySelector("#authForm"),
  loginButton: document.querySelector("#loginButton"),
  registerButton: document.querySelector("#registerButton"),
  logoutButton: document.querySelector("#logoutButton"),
  trainingModeButton: document.querySelector("#trainingModeButton"),
  contestModeButton: document.querySelector("#contestModeButton"),
  modeTitle: document.querySelector("#modeTitle"),
  modeSubtitle: document.querySelector("#modeSubtitle"),
  parameterModeChip: document.querySelector("#parameterModeChip"),
  contestPanel: document.querySelector("#contestPanel"),
  contestTitle: document.querySelector("#contestTitle"),
  contestDates: document.querySelector("#contestDates"),
  joinContestButton: document.querySelector("#joinContestButton"),
  contestStartingBalance: document.querySelector("#contestStartingBalance"),
  contestCash: document.querySelector("#contestCash"),
  contestPnl: document.querySelector("#contestPnl"),
  contestLeaderboard: document.querySelector("#contestLeaderboard"),
  contestHistory: document.querySelector("#contestHistory"),
  contestHistoryToggle: document.querySelector("#contestHistoryToggle"),
  longButton: document.querySelector("#longButton"),
  shortButton: document.querySelector("#shortButton"),
  refreshButton: document.querySelector("#refreshButton"),
  analyzeButton: document.querySelector("#analyzeButton"),
  analyzeFeedback: document.querySelector("#analyzeFeedback"),
  startSimulationButton: document.querySelector("#startSimulationButton"),
  closeSimulationButton: document.querySelector("#closeSimulationButton"),
  closeReason: document.querySelector("#closeReason"),
  closingNote: document.querySelector("#closingNote"),
  currentPrice: document.querySelector("#currentPrice"),
  heroSymbol: document.querySelector("#heroSymbol"),
  marketPairLabel: document.querySelector("#marketPairLabel"),
  variation: document.querySelector("#variation"),
  pnl: document.querySelector("#pnl"),
  exposure: document.querySelector("#exposure"),
  walletTotal: document.querySelector("#walletTotal"),
  walletCash: document.querySelector("#walletCash"),
  walletInvested: document.querySelector("#walletInvested"),
  walletUnrealized: document.querySelector("#walletUnrealized"),
  walletOpenOps: document.querySelector("#walletOpenOps"),
  stateCard: document.querySelector("#stateCard"),
  stateText: document.querySelector("#stateText"),
  lastUpdate: document.querySelector("#lastUpdate"),
  historyCount: document.querySelector("#historyCount"),
  chartSubtitle: document.querySelector("#chartSubtitle"),
  binanceChartLink: document.querySelector("#binanceChartLink"),
  autoStatus: document.querySelector("#autoStatus"),
  nextUpdate: document.querySelector("#nextUpdate"),
  analysisHeadline: document.querySelector("#analysisHeadline"),
  tpProbability: document.querySelector("#tpProbability"),
  slProbability: document.querySelector("#slProbability"),
  rangeProbability: document.querySelector("#rangeProbability"),
  analysisDecision: document.querySelector("#analysisDecision"),
  analysisSummary: document.querySelector("#analysisSummary"),
  analysisHighlights: document.querySelector("#analysisHighlights"),
  analysisKeypoints: document.querySelector("#analysisKeypoints"),
  analysisToggle: document.querySelector("#analysisToggle"),
  analysisFull: document.querySelector("#analysisFull"),
  parameterAdvice: document.querySelector("#parameterAdvice"),
  analysisInterpretation: document.querySelector("#analysisInterpretation"),
  explainedMetrics: document.querySelector("#explainedMetrics"),
  dataSourcesBox: document.querySelector("#dataSourcesBox"),
  learningBox: document.querySelector("#learningBox"),
  analysisReasons: document.querySelector("#analysisReasons"),
  operationSelector: document.querySelector("#operationSelector"),
  operationSelectorMobile: document.querySelector("#operationSelectorMobile"),
  operationSelectorMobileLabel: document.querySelector("#operationSelectorMobile .op-select-mobile-label"),
  operationSelectorSheet: document.querySelector("#operationSelectorSheet"),
  operationSelectorSheetList: document.querySelector("#operationSelectorSheet .op-sheet-list"),
  newOperationQuickButton: document.querySelector("#newOperationQuickButton"),
  operationsList: document.querySelector("#operationsList"),
  selectedOperationDetail: document.querySelector("#selectedOperationDetail"),
  chart: document.querySelector("#tradeChart"),
  floatingNotice: document.querySelector("#floatingNotice"),
  floatingNoticeTitle: document.querySelector("#floatingNoticeTitle"),
  floatingNoticeBody: document.querySelector("#floatingNoticeBody"),
};

const ctx = elements.chart.getContext("2d");
const history = [];
const MAX_HISTORY_POINTS = 240;
const UPDATE_INTERVAL_MS = 120000;
const LIVE_PRICE_INTERVAL_MS = 15000;
const PROPOSAL_HISTORY_MINUTES = 60;
const TIME_HORIZON_LABELS = {
  intraday_short: "Intradia corto · 30 min-4 h",
  intraday_wide: "Intradia amplio · 4-24 h",
  short_swing: "Swing corto · 1-7 dias",
};
let side = "long";
let timerId = null;
let liveTimerId = null;
let countdownId = null;
let nextUpdateAt = null;
let isFetching = false;
let pendingManualFetch = false;
let pendingLiveFetchSymbol = null;
let currentPrice = null;
let currentPriceSymbol = "BTCUSDT";
let activeHistorySymbol = "BTCUSDT";
let currentUser = null;
let lastAnalysis = null;
let lastAnalysisPayload = null;
let lastPortfolio = null;
let allOperations = [];
let openOperations = [];
let selectedOperationId = null;
let entryMode = "market";
let operationMode = "training";
let fullAnalysisOpen = false;
let contestState = null;
let proposalDraft = null;
let newOperationViewActive = false;
let floatingNoticeTimer = null;
let contestHistoryOpen = false;

function numberValue(input) {
  return Number.parseFloat(input.value);
}

function getConfig() {
  syncMarketEntry();
  return {
    symbol: elements.symbol.value,
    time_horizon: elements.timeHorizon.value,
    side,
    entry: numberValue(elements.entry),
    margin: numberValue(elements.margin),
    leverage: numberValue(elements.leverage),
    stopLoss: numberValue(elements.stopLoss),
    takeProfit: numberValue(elements.takeProfit),
  };
}

function syncMarketEntry() {
  if (entryMode !== "market" || selectedOperationId !== null || !hasCurrentPriceForSymbol(elements.symbol.value)) {
    return;
  }
  elements.entry.value = currentPrice.toFixed(2);
}

function readFormDraft() {
  return {
    symbol: elements.symbol.value,
    timeHorizon: elements.timeHorizon.value,
    side,
    margin: elements.margin.value,
    leverage: elements.leverage.value,
    stopLoss: elements.stopLoss.value,
    takeProfit: elements.takeProfit.value,
  };
}

function saveProposalDraft() {
  if (selectedOperationId === null && !newOperationViewActive) {
    proposalDraft = readFormDraft();
  }
}

function applyProposalDraft() {
  setTradeFormLocked(false);
  const draft = proposalDraft || readFormDraft();
  elements.symbol.value = draft.symbol || "BTCUSDT";
  elements.timeHorizon.value = draft.timeHorizon || "";
  setSide(draft.side || "long", { silent: true });
  elements.margin.value = draft.margin || "200";
  elements.leverage.value = draft.leverage || "10";
  elements.stopLoss.value = draft.stopLoss || "";
  elements.takeProfit.value = draft.takeProfit || "";
  syncMarketEntry();
}

function applyOperationToForm(operation) {
  if (!operation) {
    return;
  }
  elements.symbol.value = operation.symbol;
  elements.timeHorizon.value = operation.time_horizon || operation.recommendation?.time_horizon || "intraday_short";
  setSide(operation.side, { silent: true });
  elements.entry.value = Number(operation.entry).toFixed(2);
  elements.margin.value = String(Number(operation.margin));
  elements.leverage.value = String(Number(operation.leverage));
  elements.stopLoss.value = Number(operation.stop_loss).toFixed(2);
  elements.takeProfit.value = Number(operation.take_profit).toFixed(2);
  setTradeFormLocked(true);
}

function setTradeFormLocked(locked) {
  for (const control of [elements.symbol, elements.timeHorizon, elements.margin, elements.leverage, elements.stopLoss, elements.takeProfit]) {
    control.disabled = locked;
  }
  elements.longButton.disabled = locked;
  elements.shortButton.disabled = locked;
  elements.analyzeButton.disabled = locked;
  elements.startSimulationButton.disabled = locked || openOperations.filter((operation) => (operation.mode || "training") === operationMode).length >= 2;
}

function getTradePayload() {
  const config = getConfig();
  return {
    symbol: config.symbol,
    time_horizon: config.time_horizon,
    side: config.side,
    entry: config.entry,
    margin: config.margin,
    leverage: config.leverage,
    stop_loss: config.stopLoss,
    take_profit: config.takeProfit,
  };
}

function validateTradeForm() {
  const config = getConfig();
  if (!Number.isFinite(config.entry)) {
    return { message: "Todavia no hay precio de entrada actualizado.", field: elements.entry };
  }
  if (!config.time_horizon) {
    return { message: "Selecciona un marco temporal antes de analizar.", field: elements.timeHorizon };
  }
  if (!Number.isFinite(config.margin) || config.margin <= 0) {
    return { message: "Introduce un margen valido.", field: elements.margin };
  }
  if (!Number.isFinite(config.leverage) || config.leverage <= 0 || config.leverage > 10) {
    return { message: "Introduce un apalancamiento valido entre x1 y x10.", field: elements.leverage };
  }
  if (!Number.isFinite(config.stopLoss)) {
    return { message: "Define un Stop Loss antes de analizar.", field: elements.stopLoss };
  }
  if (!Number.isFinite(config.takeProfit)) {
    return { message: "Define un Take Profit antes de analizar.", field: elements.takeProfit };
  }
  if (config.side === "long" && config.stopLoss >= config.entry) {
    return { message: "En una operacion long, el Stop Loss debe estar por debajo de la entrada.", field: elements.stopLoss };
  }
  if (config.side === "long" && config.takeProfit <= config.entry) {
    return { message: "En una operacion long, el Take Profit debe estar por encima de la entrada.", field: elements.takeProfit };
  }
  if (config.side === "short" && config.stopLoss <= config.entry) {
    return { message: "En una operacion short, el Stop Loss debe estar por encima de la entrada.", field: elements.stopLoss };
  }
  if (config.side === "short" && config.takeProfit >= config.entry) {
    return { message: "En una operacion short, el Take Profit debe estar por debajo de la entrada.", field: elements.takeProfit };
  }
  return null;
}

let formErrorClearTimer = null;

function clearFormError() {
  if (formErrorClearTimer) {
    clearTimeout(formErrorClearTimer);
    formErrorClearTimer = null;
  }
  if (elements.analyzeFeedback) {
    elements.analyzeFeedback.textContent = "";
    elements.analyzeFeedback.classList.remove("visible");
  }
  document.querySelectorAll(".field-error").forEach((el) => el.classList.remove("field-error"));
}

function showFormError(validationError) {
  const { message, field } = validationError;
  if (elements.analyzeFeedback) {
    elements.analyzeFeedback.textContent = message;
    elements.analyzeFeedback.classList.add("visible");
  }
  document.querySelectorAll(".field-error").forEach((el) => el.classList.remove("field-error"));
  if (field) {
    const label = field.closest("label") || field;
    label.classList.add("field-error");
    try {
      field.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (_) {
      field.scrollIntoView();
    }
    setTimeout(() => {
      try { field.focus({ preventScroll: true }); } catch (_) { field.focus(); }
    }, 350);
  }
  if (formErrorClearTimer) clearTimeout(formErrorClearTimer);
  formErrorClearTimer = setTimeout(clearFormError, 8000);
}

function getCreateOperationPayload() {
  return {
    ...getTradePayload(),
    recommendation_id: lastAnalysis ? lastAnalysis.recommendation_id : null,
    mode: operationMode,
  };
}

function isSameTradePayload(current, analyzed) {
  if (!current || !analyzed) {
    return false;
  }
  const numericKeys = ["margin", "leverage", "stop_loss", "take_profit"];
  const sameText = current.symbol === analyzed.symbol && current.side === analyzed.side && current.time_horizon === analyzed.time_horizon;
  const sameNumbers = numericKeys.every((key) => Math.abs(Number(current[key]) - Number(analyzed[key])) < 0.000001);
  if (!sameText || !sameNumbers) {
    return false;
  }

  const isMarketEntryAuto = Boolean(elements.entry?.readOnly);
  if (isMarketEntryAuto) {
    return true;
  }

  const currentEntry = Number(current.entry);
  const analyzedEntry = Number(analyzed.entry);
  if (!Number.isFinite(currentEntry) || !Number.isFinite(analyzedEntry)) {
    return false;
  }

  const entryDiffAbs = Math.abs(currentEntry - analyzedEntry);
  if (entryDiffAbs < 0.000001) {
    return true;
  }

  return false;
}

function showFloatingNotice(title, body, durationMs = 2000) {
  if (!elements.floatingNotice || !elements.floatingNoticeTitle || !elements.floatingNoticeBody) {
    return;
  }
  if (floatingNoticeTimer) {
    clearTimeout(floatingNoticeTimer);
    floatingNoticeTimer = null;
  }
  elements.floatingNoticeTitle.textContent = title;
  elements.floatingNoticeBody.textContent = body;
  elements.floatingNotice.classList.remove("hidden");
  elements.floatingNotice.classList.add("show");
  floatingNoticeTimer = setTimeout(() => {
    elements.floatingNotice.classList.remove("show");
    elements.floatingNotice.classList.add("hidden");
    floatingNoticeTimer = null;
  }, durationMs);
}

function scrollToAnalysisResult() {
  const analysis = document.querySelector("#analysisResult");
  if (!analysis) {
    return;
  }
  analysis.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    window.scrollBy({ top: -28, left: 0, behavior: "smooth" });
  }, 220);
}

function operationToConfig(operation) {
  return {
    symbol: operation.symbol,
    time_horizon: operation.time_horizon || "intraday_short",
    side: operation.side,
    entry: Number(operation.entry),
    margin: Number(operation.margin),
    leverage: Number(operation.leverage),
    stopLoss: Number(operation.stop_loss),
    takeProfit: Number(operation.take_profit),
  };
}

function getSelectedOperation() {
  return allOperations.find((operation) => operation.id === selectedOperationId) || null;
}

function clearPriceIfDifferentSymbol(symbol) {
  const normalized = normalizeSymbol(symbol);
  if (hasCurrentPriceForSymbol(normalized)) {
    return;
  }
  currentPrice = null;
  currentPriceSymbol = normalized;
  elements.currentPrice.textContent = "--";
}

function fetchVisibleOperationPrice(operation) {
  if (!operation?.symbol) {
    return;
  }
  clearPriceIfDifferentSymbol(operation.symbol);
  fetchPrice({ record: false, symbolOverride: operation.symbol });
}

function getActivePriceSymbol() {
  const selectedOperation = getSelectedOperation();
  if (selectedOperation?.symbol) {
    return normalizeSymbol(selectedOperation.symbol);
  }
  return normalizeSymbol(elements.symbol.value);
}

function getDisplayContext() {
  if (!currentUser) {
    return {
      mode: "none",
      operation: null,
      config: {
        symbol: elements.symbol.value,
        time_horizon: elements.timeHorizon.value,
        side,
        entry: NaN,
        margin: NaN,
        leverage: NaN,
        stopLoss: NaN,
        takeProfit: NaN,
      },
    };
  }
  const operation = getSelectedOperation();
  if (operation) {
    return {
      mode: "operation",
      operation,
      config: operationToConfig(operation),
    };
  }
  return {
    mode: "proposal",
    operation: null,
    config: getConfig(),
  };
}

function historyKey(symbol = activeHistorySymbol || elements.symbol.value) {
  return `trading-simulator-history-${normalizeSymbol(symbol)}`;
}

function loadHistory(symbol = elements.symbol.value) {
  const normalized = normalizeSymbol(symbol);
  activeHistorySymbol = normalized;
  history.length = 0;
  try {
    const stored = JSON.parse(localStorage.getItem(historyKey(normalized)) || "[]");
    for (const point of stored) {
      const price = Number(point.price);
      const time = new Date(point.time);
      if (Number.isFinite(price) && !Number.isNaN(time.getTime())) {
        history.push({ price, time });
      }
    }
  } catch {
    localStorage.removeItem(historyKey(normalized));
  }

  currentPrice = null;
  currentPriceSymbol = normalized;
}

function saveHistory(symbol = activeHistorySymbol || elements.symbol.value) {
  const normalized = normalizeSymbol(symbol);
  const compactHistory = history.map((point) => ({
    price: point.price,
    time: point.time.toISOString(),
  }));
  localStorage.setItem(historyKey(normalized), JSON.stringify(compactHistory));
}

function getChartHistory() {
  const operation = getSelectedOperation();
  if (operation && Array.isArray(operation.ticks) && operation.ticks.length) {
    const points = operation.ticks
      .map((tick) => ({ price: Number(tick.price), time: new Date(tick.captured_at), source: tick.source || "" }))
      .filter((point) => Number.isFinite(point.price) && !Number.isNaN(point.time.getTime()));
    return focusClosedOperationHistory(operation, points);
  }
  return recentProposalHistory();
}

function recentProposalHistory() {
  const cutoff = Date.now() - PROPOSAL_HISTORY_MINUTES * 60 * 1000;
  const recent = history.filter((point) => point.time.getTime() >= cutoff);
  return recent.length >= 2 ? recent : history.slice(-Math.min(history.length, 60));
}

function focusClosedOperationHistory(operation, points) {
  if (!operation || operation.status !== "CLOSED" || !["stop_loss", "take_profit"].includes(operation.close_reason)) {
    return points;
  }
  if (points.length <= 90) {
    return points;
  }
  const closeIndex = findClosePointIndex(operation, points);
  if (closeIndex < 0) {
    return points;
  }
  const start = Math.max(0, closeIndex - 65);
  const end = Math.min(points.length, closeIndex + 26);
  return points.slice(start, end);
}

function findClosePointIndex(operation, points) {
  const sourceIndex = points.findIndex((point) => point.source === "auto_exit");
  if (sourceIndex >= 0) {
    return sourceIndex;
  }
  return -1;
}

function updateHistoryCount() {
  elements.historyCount.textContent = String(getChartHistory().length);
}

function requestJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(options.method || "GET", url, true);
    request.responseType = "json";
    request.timeout = 30000;
    if (options.body) {
      request.setRequestHeader("Content-Type", "application/json");
    }
    request.onload = () => {
      const payload = request.response || JSON.parse(request.responseText || "{}");
      if (request.status >= 200 && request.status < 300) {
        resolve(payload);
      } else {
        reject(new Error(payload.detail || payload.error || `Error HTTP ${request.status}`));
      }
    };
    request.onerror = () => reject(new Error("No se pudo consultar el precio."));
    request.ontimeout = () => reject(new Error("La consulta del precio ha tardado demasiado."));
    request.send(options.body ? JSON.stringify(options.body) : undefined);
  });
}

function percent(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function safeMetricBias(value) {
  const bias = String(value || "neutral").toLowerCase();
  return ["favorable", "desfavorable", "alerta", "contexto", "neutral"].includes(bias) ? bias : "neutral";
}

function clampPercentValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return 50;
  }
  return Math.max(0, Math.min(100, number));
}

function probabilityLabel(recommendation, key, fallbackKey) {
  return recommendation?.probability_ranges?.[key]?.label || (recommendation ? percent(Number(recommendation[fallbackKey])) : "--");
}

function timeHorizonLabel(value) {
  return TIME_HORIZON_LABELS[value] || "Sin marco temporal";
}

function normalizeSymbol(symbol) {
  return String(symbol || "BTCUSDT").toUpperCase();
}

function symbolLabel(symbol) {
  const normalized = normalizeSymbol(symbol);
  if (normalized.endsWith("USDT")) {
    return `${normalized.slice(0, -4)}/USDT`;
  }
  return normalized;
}

function hasCurrentPriceForSymbol(symbol) {
  return Number.isFinite(currentPrice) && normalizeSymbol(currentPriceSymbol) === normalizeSymbol(symbol);
}

const adviceLabels = {
  entry: "Entrada",
  stop_loss: "Stop loss",
  take_profit: "Take profit",
  leverage: "Apalancamiento",
};

function renderAvatar(user) {
  const initial = user?.username ? user.username.slice(0, 1).toUpperCase() : "?";
  elements.avatarInitial.textContent = initial;
  if (user?.avatar_url) {
    elements.avatarImage.src = user.avatar_url;
    elements.avatarImage.classList.remove("hidden");
    elements.avatarInitial.classList.add("hidden");
  } else {
    elements.avatarImage.removeAttribute("src");
    elements.avatarImage.classList.add("hidden");
    elements.avatarInitial.classList.remove("hidden");
  }
}

function setSession(user) {
  currentUser = user;
  renderAvatar(user);
  if (user) {
    elements.sessionLabel.textContent = user.username;
    elements.authMessage.textContent = "Sesion activa.";
    elements.authForm.classList.add("hidden");
    elements.avatarUploadLabel.classList.remove("hidden");
    elements.logoutButton.classList.remove("hidden");
  } else {
    elements.sessionLabel.textContent = "Sin sesion";
    elements.authMessage.textContent = "Crea una cuenta o inicia sesion.";
    elements.authForm.classList.remove("hidden");
    elements.avatarUploadLabel.classList.add("hidden");
    elements.logoutButton.classList.add("hidden");
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.split(",", 2)[1] || "");
    };
    reader.onerror = () => reject(new Error("No se pudo leer la imagen."));
    reader.readAsDataURL(file);
  });
}

async function uploadAvatar() {
  const file = elements.avatarInput.files?.[0];
  if (!file) {
    return;
  }
  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
  if (!allowedTypes.includes(file.type)) {
    elements.authMessage.textContent = "Avatar no valido: usa JPG, PNG o WEBP.";
    elements.avatarInput.value = "";
    return;
  }
  if (file.size > 1_000_000) {
    elements.authMessage.textContent = "Avatar demasiado grande: maximo 1 MB.";
    elements.avatarInput.value = "";
    return;
  }
  try {
    elements.authMessage.textContent = "Subiendo avatar...";
    const dataBase64 = await readFileAsBase64(file);
    const user = await requestJson("/api/me/avatar", {
      method: "POST",
      body: {
        filename: file.name,
        mime_type: file.type,
        data_base64: dataBase64,
      },
    });
    setSession({ ...currentUser, ...user });
    elements.authMessage.textContent = "Avatar actualizado.";
  } catch (error) {
    elements.authMessage.textContent = error.message;
  } finally {
    elements.avatarInput.value = "";
  }
}

function chooseDefaultOperationId(operations) {
  return (operations[0] || {}).id || null;
}

function clearPrivateSessionView() {
  allOperations = [];
  openOperations = [];
  selectedOperationId = null;
  newOperationViewActive = true;
  proposalDraft = null;
  lastAnalysis = null;
  lastAnalysisPayload = null;
  renderOperationSelector();
  renderSelectedOperationDetail(null);
  renderPortfolio(null);
  elements.operationsList.innerHTML = "<div class=\"operation-row\"><div><strong>Sin usuario activo</strong><span>Inicia sesion para cargar tus operaciones.</span></div></div>";
  elements.stateText.textContent = "SIN SESION";
  elements.variation.textContent = "--";
  elements.pnl.textContent = "--";
  elements.exposure.textContent = "--";
  elements.analysisHeadline.textContent = "Pendiente";
  elements.analysisDecision.textContent = "Inicia sesion para recuperar tu ultima operacion.";
  elements.analysisSummary.textContent = "";
  elements.parameterAdvice.innerHTML = "";
  elements.analysisInterpretation.innerHTML = "";
  elements.explainedMetrics.innerHTML = "";
  elements.dataSourcesBox.innerHTML = "";
  elements.learningBox.innerHTML = "";
  elements.analysisReasons.innerHTML = "";
  drawChart();
}

function prepareNewOperationForm() {
  selectedOperationId = null;
  newOperationViewActive = true;
  proposalDraft = null;
  lastAnalysis = null;
  lastAnalysisPayload = null;
  setTradeFormLocked(false);
  elements.symbol.value = elements.symbol.value || "BTCUSDT";
  elements.margin.value = "200";
  elements.leverage.value = "10";
  elements.timeHorizon.value = "";
  syncMarketEntry();
  elements.stopLoss.value = "";
  elements.takeProfit.value = "";
  resetProposalChartToCurrentPrice();
  renderSelectedOperationDetail(null);
  elements.analysisHeadline.textContent = "Nueva operacion";
  elements.analysisDecision.textContent = "Define Stop Loss y Take Profit para analizar la nueva operacion.";
  elements.analysisSummary.textContent = "";
  updateMetrics();
}

function resetProposalChartToCurrentPrice() {
  const symbol = normalizeSymbol(elements.symbol.value);
  activeHistorySymbol = symbol;
  if (Number.isFinite(currentPrice) && currentPriceSymbol === symbol && (!history.length || Math.abs(history[history.length - 1].price - currentPrice) >= 0.01)) {
    history.push({ price: currentPrice, time: new Date() });
    if (history.length > MAX_HISTORY_POINTS) {
      history.shift();
    }
    saveHistory(symbol);
  }
  loadRecentMarketHistory(symbol);
}

async function loadRecentMarketHistory(symbol = elements.symbol.value) {
  const requestedSymbol = normalizeSymbol(symbol);
  activeHistorySymbol = requestedSymbol;
  try {
    const data = await requestJson(`/api/market-history?symbol=${encodeURIComponent(requestedSymbol)}&minutes=${PROPOSAL_HISTORY_MINUTES}`);
    if (normalizeSymbol(elements.symbol.value) !== requestedSymbol || selectedOperationId !== null) {
      return;
    }
    const points = Array.isArray(data.points) ? data.points : [];
    const parsed = points
      .map((point) => ({ price: Number(point.price), time: new Date(point.time) }))
      .filter((point) => Number.isFinite(point.price) && !Number.isNaN(point.time.getTime()));
    if (!parsed.length) {
      return;
    }
    history.length = 0;
    history.push(...parsed.slice(-MAX_HISTORY_POINTS));
    if (Number.isFinite(currentPrice) && currentPriceSymbol === requestedSymbol && Math.abs(history[history.length - 1].price - currentPrice) >= 0.01) {
      history.push({ price: currentPrice, time: new Date() });
    }
    saveHistory(requestedSymbol);
    updateMetrics();
  } catch {
    updateMetrics();
  }
}

async function loadSession() {
  try {
    const user = await requestJson("/api/me");
    setSession(user);
    renderPortfolio(user.portfolio);
    await loadContest();
    await loadOperations();
  } catch {
    setSession(null);
    clearPrivateSessionView();
  }
}

async function authenticate(mode) {
  const username = elements.username.value.trim().toLowerCase();
  const password = elements.password.value;
  if (username.length < 2) {
    elements.authMessage.textContent = "El nombre debe tener al menos 2 caracteres.";
    return;
  }
  if (password.length < 6) {
    elements.authMessage.textContent = "La contrasena debe tener al menos 6 caracteres.";
    return;
  }

  try {
    elements.authMessage.textContent = mode === "register" ? "Creando usuario..." : "Entrando...";
    const user = await requestJson(`/api/auth/${mode}`, {
      method: "POST",
      body: {
        username,
        password,
      },
    });
    elements.password.value = "";
    setSession(user);
    selectedOperationId = null;
    await loadContest();
    await loadOperations();
    await loadPortfolio();
    if (!getSelectedOperation()) {
      elements.analysisDecision.textContent = "Sesion iniciada. Ya puedes analizar operaciones.";
    }
  } catch (error) {
    elements.authMessage.textContent = error.message;
    elements.analysisDecision.textContent = error.message;
  }
}

async function logout() {
  await requestJson("/api/auth/logout", { method: "POST" });
  setSession(null);
  clearPrivateSessionView();
  renderContest(null);
  elements.authMessage.textContent = "Sesion cerrada.";
}

function formatSeconds(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function updateCountdown() {
  if (!nextUpdateAt) {
    elements.nextUpdate.textContent = "--";
    return;
  }

  const remainingMs = nextUpdateAt - Date.now();
  // Self-heal: if the scheduled setTimeout was throttled (background tab) or
  // never fired and we're > 2s past due with no fetch in flight, kick one now
  // so the countdown never gets visually stuck at 0:00.
  if (remainingMs <= -2000 && !isFetching) {
    fetchPrice({ resetTimer: true, record: true });
    return;
  }
  elements.nextUpdate.textContent = `Proxima en ${formatSeconds(Math.max(0, Math.ceil(remainingMs / 1000)))}`;
}

function scheduleNextFetch() {
  if (timerId) {
    window.clearTimeout(timerId);
  }
  if (countdownId) {
    window.clearInterval(countdownId);
  }

  nextUpdateAt = Date.now() + UPDATE_INTERVAL_MS;
  updateCountdown();
  countdownId = window.setInterval(updateCountdown, 1000);
  timerId = window.setTimeout(() => fetchPrice({ resetTimer: true, record: true }), UPDATE_INTERVAL_MS);
  scheduleLivePriceFetch();
}

function scheduleLivePriceFetch() {
  if (liveTimerId) {
    window.clearTimeout(liveTimerId);
  }
  liveTimerId = window.setTimeout(() => fetchPrice({ record: false }), LIVE_PRICE_INTERVAL_MS);
}

function money(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return `${value.toLocaleString("es-ES", { maximumFractionDigits: 2, minimumFractionDigits: 2 })} USDT`;
}

function priceText(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  const abs = Math.abs(value);
  let digits = 2;
  if (abs < 0.01) digits = 8;
  else if (abs < 1) digits = 6;
  else if (abs < 10) digits = 4;
  else if (abs < 100) digits = 3;
  return value.toLocaleString("es-ES", {
    maximumFractionDigits: digits,
    minimumFractionDigits: Math.min(2, digits),
  });
}

function signedPct(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(4)}%`;
}

function calculate(config, price) {
  const rawVariation = ((price - config.entry) / config.entry) * 100;
  const directionVariation = config.side === "long" ? rawVariation : -rawVariation;
  const pnl = config.margin * config.leverage * (directionVariation / 100);

  let state = "ABIERTA";
  if (config.side === "long") {
    if (price <= config.stopLoss) state = "STOP LOSS";
    if (price >= config.takeProfit) state = "TAKE PROFIT";
  } else {
    if (price >= config.stopLoss) state = "STOP LOSS";
    if (price <= config.takeProfit) state = "TAKE PROFIT";
  }

  return { rawVariation, directionVariation, pnl, state };
}

function plannedOutcome(config) {
  if (!isValidTradeConfig(config) || !Number.isFinite(config.margin) || !Number.isFinite(config.leverage)) {
    return { tpPnl: NaN, slPnl: NaN };
  }
  return {
    tpPnl: calculate(config, config.takeProfit).pnl,
    slPnl: calculate(config, config.stopLoss).pnl,
  };
}

function setTone(node, value) {
  node.classList.remove("positive", "negative", "neutral");
  node.classList.add(value > 0 ? "positive" : value < 0 ? "negative" : "neutral");
}

function getOperationStateLabel(operation, result) {
  if (!operation) {
    return result.state === "ABIERTA" ? "PROPUESTA" : result.state;
  }
  if (operation.status === "OPEN") {
    return `ABIERTA #${operation.id}`;
  }
  if (operation.close_reason === "stop_loss") {
    return `STOP LOSS #${operation.id}`;
  }
  if (operation.close_reason === "take_profit") {
    return `TAKE PROFIT #${operation.id}`;
  }
  if (operation.observation_status === "OBSERVING") {
    return `OBSERVACION #${operation.id}`;
  }
  if (operation.observation_status === "OBSERVATION_CLOSED") {
    return `OBSERVACION CERRADA #${operation.id}`;
  }
  return `CERRADA #${operation.id}`;
}

function getOperationVisualStatus(operation) {
  if (!operation) {
    return { label: "PROPUESTA", headline: "Operacion propuesta pendiente de iniciar", htmlHeadline: "Operacion propuesta pendiente de iniciar", className: "state-proposal", result: "Sin abrir" };
  }
  if (operation.status === "OPEN") {
    return { label: `ABIERTA #${operation.id}`, headline: `Operacion #${operation.id} abierta en seguimiento`, htmlHeadline: `Operacion #${operation.id} abierta en seguimiento`, className: "state-open", result: "Operacion en curso" };
  }
  const finalPnl = Number(operation.final_pnl);
  const isProfit = Number.isFinite(finalPnl) && finalPnl > 0;
  const isLoss = Number.isFinite(finalPnl) && finalPnl < 0;
  if (operation.close_reason === "stop_loss") {
    return { label: `STOP LOSS #${operation.id}`, headline: `Operacion #${operation.id} cerrada con perdidas por alcanzar STOP LOSS`, htmlHeadline: `Operacion #${operation.id} cerrada con <span class="keyword-loss">perdidas</span> por alcanzar <span class="keyword-loss">STOP LOSS</span>`, className: "state-stop", result: "Operacion cerrada con perdidas por stop loss" };
  }
  if (operation.close_reason === "take_profit") {
    return { label: `TAKE PROFIT #${operation.id}`, headline: `Operacion #${operation.id} cerrada con ganancias por alcanzar TAKE PROFIT`, htmlHeadline: `Operacion #${operation.id} cerrada con <span class="keyword-profit">ganancias</span> por alcanzar <span class="keyword-profit">TAKE PROFIT</span>`, className: "state-target", result: "Operacion cerrada con ganancias por take profit" };
  }
  if (operation.close_reason === "take_partial" || (operation.close_reason === "manual" && isProfit)) {
    return { label: `GANANCIA MANUAL #${operation.id}`, headline: `Operacion #${operation.id} cerrada por usuario en ganancias antes de alcanzar TAKE PROFIT`, htmlHeadline: `Operacion #${operation.id} cerrada por usuario en <span class="keyword-profit">ganancias</span> antes de alcanzar <span class="keyword-profit">TAKE PROFIT</span>`, className: "state-target", result: "Toma de ganancias manual pendiente de comparar con el plan" };
  }
  if (operation.close_reason === "cut_loss" || operation.close_reason === "emotion" || (operation.close_reason === "manual" && isLoss)) {
    return { label: `PERDIDA MANUAL #${operation.id}`, headline: `Operacion #${operation.id} cerrada por usuario en perdidas antes de alcanzar STOP LOSS`, htmlHeadline: `Operacion #${operation.id} cerrada por usuario en <span class="keyword-loss">perdidas</span> antes de alcanzar <span class="keyword-loss">STOP LOSS</span>`, className: "state-observing", result: "Corte manual de perdida pendiente de comparar con el plan" };
  }
  if (operation.close_reason === "invalidated") {
    return { label: `SETUP INVALIDADO #${operation.id}`, headline: `Operacion #${operation.id} cerrada por usuario porque el setup fue invalidado`, htmlHeadline: `Operacion #${operation.id} cerrada por usuario porque el setup fue invalidado`, className: "state-observing", result: "Cierre manual por invalidacion del plan" };
  }
  if (operation.observation_status === "OBSERVING") {
    return { label: `OBSERVACION #${operation.id}`, headline: `Operacion #${operation.id} cerrada por usuario pendiente de observacion`, htmlHeadline: `Operacion #${operation.id} cerrada por usuario pendiente de observacion`, className: "state-observing", result: "Cierre manual pendiente de evaluar" };
  }
  if (operation.observation_status === "OBSERVATION_CLOSED") {
    return { label: `OBSERVACION CERRADA #${operation.id}`, headline: `Operacion #${operation.id} con observacion finalizada`, htmlHeadline: `Operacion #${operation.id} con observacion finalizada`, className: "state-closed", result: operation.observation_summary || "Observacion cerrada y lista para aprendizaje" };
  }
  return { label: `CERRADA #${operation.id}`, headline: `Operacion #${operation.id} cerrada sin clasificacion especifica`, htmlHeadline: `Operacion #${operation.id} cerrada sin clasificacion especifica`, className: "state-closed", result: "Operacion cerrada" };
}

function updateMetrics() {
  const formConfig = getConfig();
  const { config, operation } = getDisplayContext();
  const displaySymbol = config.symbol || elements.symbol.value;
  const displayLabel = symbolLabel(displaySymbol);
  const hasDisplayPrice = hasCurrentPriceForSymbol(displaySymbol);
  const displayPrice = hasDisplayPrice ? currentPrice : null;
  updateBinanceChartLink(config.symbol || elements.symbol.value);
  if (elements.heroSymbol) {
    elements.heroSymbol.textContent = displayLabel;
  }
  if (elements.marketPairLabel) {
    elements.marketPairLabel.textContent = `${displayLabel} Binance Spot`;
  }
  document.title = `Simulador Trading ${displayLabel}`;
  elements.leverageValue.textContent = `x${formConfig.leverage}`;
  updatePlanPreview(formConfig);
  elements.exposure.textContent = currentUser ? money(config.margin * config.leverage) : "--";
  elements.chartSubtitle.textContent = !currentUser
    ? "Inicia sesion para ver operaciones, analisis y niveles de riesgo."
    : operation
      ? `Viendo operacion #${operation.id} en ${symbolLabel(operation.symbol)}. Historial registrado cada 120 segundos.`
      : `Viendo nueva operacion. Grafica ${symbolLabel(config.symbol)} con velas de Binance Spot 1m de los ultimos 60 minutos.`;
  updateHistoryCount();

  if (!currentUser) {
    elements.currentPrice.textContent = hasDisplayPrice ? `${priceText(displayPrice)} USDT` : "--";
    elements.variation.textContent = "--";
    elements.pnl.textContent = "--";
    elements.stateText.textContent = "SIN SESION";
  elements.stateCard.classList.remove("state-open", "state-stop", "state-target", "state-proposal", "state-closed", "state-observing");
  elements.stateCard.classList.add("state-closed");
    drawChart();
    return;
  }

  if (!hasDisplayPrice) {
    elements.currentPrice.textContent = "--";
    elements.variation.textContent = "--";
    elements.pnl.textContent = operation && operation.status === "CLOSED" && Number.isFinite(Number(operation.final_pnl))
      ? money(Number(operation.final_pnl))
      : "--";
    elements.stateText.textContent = operation ? getOperationStateLabel(operation, { state: "ABIERTA" }) : "PROPUESTA";
    drawChart();
    return;
  }

  const result = calculate(config, displayPrice);
  elements.currentPrice.textContent = `${priceText(displayPrice)} USDT`;
  elements.variation.textContent = signedPct(result.rawVariation);
  elements.pnl.textContent = operation && operation.status === "CLOSED" && Number.isFinite(Number(operation.final_pnl))
    ? money(Number(operation.final_pnl))
    : money(result.pnl);
  if (operation) {
    elements.stateText.innerHTML = getOperationVisualStatus(operation).htmlHeadline;
  } else {
    elements.stateText.textContent = getOperationStateLabel(operation, result);
  }

  setTone(elements.variation, result.rawVariation);
  setTone(elements.pnl, operation && operation.status === "CLOSED" ? Number(operation.final_pnl || 0) : result.pnl);

  elements.stateCard.classList.remove("state-open", "state-stop", "state-target", "state-proposal", "state-closed", "state-observing");
  if (operation) {
    elements.stateCard.classList.add(getOperationVisualStatus(operation).className);
  } else if (result.state === "STOP LOSS") elements.stateCard.classList.add("state-stop");
  else if (result.state === "TAKE PROFIT") elements.stateCard.classList.add("state-target");
  else elements.stateCard.classList.add("state-proposal");

  renderPortfolio(lastPortfolio);

  drawChart();
}

function updateBinanceChartLink(symbol) {
  if (!elements.binanceChartLink) {
    return;
  }
  const normalized = normalizeSymbol(symbol);
  const pair = normalized.endsWith("USDT")
    ? `${normalized.slice(0, -4)}_USDT`
    : normalized;
  elements.binanceChartLink.href = `https://www.binance.com/es/trade/${encodeURIComponent(pair)}?type=spot`;
  elements.binanceChartLink.textContent = `Ver grafica ${pair.replace("_", "/")} en Binance Spot`;
}

function updatePlanPreview(config) {
  const outcome = plannedOutcome(config);
  elements.planTakeProfit.textContent = Number.isFinite(outcome.tpPnl) ? money(outcome.tpPnl) : "--";
  elements.planStopLoss.textContent = Number.isFinite(outcome.slPnl) ? money(outcome.slPnl) : "--";
  setTone(elements.planTakeProfit, Number.isFinite(outcome.tpPnl) ? outcome.tpPnl : 0);
  setTone(elements.planStopLoss, Number.isFinite(outcome.slPnl) ? outcome.slPnl : 0);
}

async function fetchPrice({ resetTimer = false, record = true, symbolOverride = null } = {}) {
  const requestedSymbol = normalizeSymbol(symbolOverride || elements.symbol.value);
  if (isFetching) {
    // Critical: don't drop the 120s schedule if an auto tick collides with an
    // in-flight live fetch — otherwise the countdown stays frozen forever.
    if (resetTimer) {
      nextUpdateAt = Date.now() + UPDATE_INTERVAL_MS;
      updateCountdown();
    }
    // Manual recording requests (refresh button) queue and run as soon as the
    // current fetch finishes, so the user's click is never silently ignored.
    if (record) {
      pendingManualFetch = true;
    } else {
      pendingLiveFetchSymbol = requestedSymbol;
    }
    return;
  }

  isFetching = true;
  const symbol = requestedSymbol;
  elements.autoStatus.textContent = record ? "Consultando" : "Precio vivo";
  elements.lastUpdate.textContent = record ? "Consultando precio..." : "Actualizando precio vivo...";

  try {
    const data = await requestJson(`/api/price?symbol=${encodeURIComponent(symbol)}&record=${record ? "true" : "false"}`);
    if (getActivePriceSymbol() !== symbol) {
      return;
    }

    currentPrice = Number(data.price);
    currentPriceSymbol = symbol;
    if (selectedOperationId === null) {
      activeHistorySymbol = symbol;
    }
    syncMarketEntry();
    const capturedAt = new Date();
    if (record) {
      if (selectedOperationId === null && activeHistorySymbol === symbol) {
        history.push({ price: currentPrice, time: new Date() });
        if (history.length > MAX_HISTORY_POINTS) {
          history.shift();
        }
        saveHistory(symbol);
      }
      appendOperationTicks(data.operation_ids || [], currentPrice, capturedAt);
    }

    elements.lastUpdate.textContent = new Date().toLocaleString("es-ES");
    elements.autoStatus.textContent = record ? "Auto ON" : "Live ON";
    if (currentUser && Array.isArray(data.closed_operations) && data.closed_operations.length) {
      const closedText = data.closed_operations
        .map((operation) => `#${operation.id} ${operation.reason === "stop_loss" ? "cerrada por stop loss" : "cerrada por take profit"}`)
        .join(" · ");
      elements.analysisDecision.textContent = closedText;
      await loadOperations();
      await loadPortfolio();
      if (operationMode === "contest") {
        await loadContest();
      }
    } else if (currentUser && selectedOperationId !== null) {
      await loadOperations();
      await loadPortfolio();
      if (operationMode === "contest") {
        await loadContest();
      }
    } else {
      updateMetrics();
      renderSelectedOperationDetail(getSelectedOperation());
      if (currentUser && operationMode === "contest") {
        await loadContest();
      }
    }
  } catch (error) {
    elements.stateText.textContent = "SIN DATOS";
    elements.autoStatus.textContent = "Error API";
    elements.lastUpdate.textContent = error.message;
    drawChart();
  } finally {
    isFetching = false;
    if (resetTimer) {
      scheduleNextFetch();
    } else if (!record) {
      scheduleLivePriceFetch();
    }
    // Drain a queued manual refresh that arrived while we were busy.
    if (pendingManualFetch) {
      pendingManualFetch = false;
      setTimeout(() => fetchPrice({ resetTimer: true, record: true, symbolOverride: elements.symbol.value }), 50);
    } else if (pendingLiveFetchSymbol) {
      const queuedSymbol = pendingLiveFetchSymbol;
      pendingLiveFetchSymbol = null;
      setTimeout(() => fetchPrice({ record: false, symbolOverride: queuedSymbol }), 50);
    }
  }
}

function appendOperationTicks(operationIds, price, capturedAt) {
  const ids = new Set(operationIds.map((id) => Number(id)));
  for (const operation of allOperations) {
    if (!ids.has(Number(operation.id))) {
      continue;
    }
    if (!Array.isArray(operation.ticks)) {
      operation.ticks = [];
    }
    operation.ticks.push({
      price,
      source: "binance",
      captured_at: capturedAt.toISOString(),
    });
    if (operation.ticks.length > MAX_HISTORY_POINTS) {
      operation.ticks.shift();
    }
  }
}

async function analyzeOperation() {
  if (!currentUser) {
    showFormError({ message: "Inicia sesion antes de analizar la operacion.", field: null });
    elements.analysisDecision.textContent = "Inicia sesion antes de analizar la operacion.";
    return;
  }
  const validationError = validateTradeForm();
  if (validationError) {
    elements.analysisHeadline.textContent = "Pendiente";
    elements.analysisDecision.textContent = validationError.message;
    showFormError(validationError);
    return;
  }
  clearFormError();

  elements.analysisHeadline.textContent = "Analizando...";
  elements.analysisSummary.textContent = "";
  elements.parameterAdvice.innerHTML = "";
  elements.analysisInterpretation.innerHTML = "";
  elements.explainedMetrics.innerHTML = "";
  elements.dataSourcesBox.innerHTML = "";
  elements.learningBox.innerHTML = "";
  elements.analysisReasons.innerHTML = "";
  scrollToAnalysisResult();
  showFloatingNotice("Analisis en curso", "Empieza el analisis de la simulacion...", 2000);

  try {
    const payload = getTradePayload();
    const analysis = await requestJson("/api/analyze", {
      method: "POST",
      body: payload,
    });
    lastAnalysis = analysis;
    lastAnalysisPayload = payload;
    selectedOperationId = null;
    renderAnalysisPayload(analysis);
    updateMetrics();
  } catch (error) {
    elements.analysisHeadline.textContent = "Error";
    elements.analysisDecision.textContent = error.message;
  }
}

function renderParameterAdvice(advice) {
  elements.parameterAdvice.innerHTML = "";
  for (const [key, value] of Object.entries(advice)) {
    const row = document.createElement("div");
    const label = adviceLabels[key] || key;
    row.innerHTML = `<strong>${escapeHtml(label)}: ${escapeHtml(value.action)}</strong>${escapeHtml(value.reason)} Valor sugerido: ${escapeHtml(value.suggested_value)}`;
    elements.parameterAdvice.appendChild(row);
  }
}

function renderExplainedMetrics(metrics) {
  elements.explainedMetrics.innerHTML = "";
  if (metrics.length) {
    const intro = document.createElement("div");
    intro.className = "technical-dashboard-title";
    intro.innerHTML = `
      <span class="label">Dashboard tecnico</span>
      <strong>Datos brutos y lectura de cada metrica</strong>
    `;
    elements.explainedMetrics.appendChild(intro);
  }
  for (const metric of metrics) {
    const card = document.createElement("article");
    card.className = "explain-card";
    const biasClass = safeMetricBias(metric.bias);
    card.innerHTML = `
      <div class="explain-head">
        <strong>${escapeHtml(metric.label)}</strong>
        <span>${escapeHtml(metric.value)}</span>
      </div>
      <span class="metric-bias ${biasClass}">${biasLabel(biasClass)}</span>
      <div class="mini-bar" aria-hidden="true">
        <div class="mini-bar-fill ${biasClass}" style="width: ${clampPercentValue(metric.score)}%"></div>
      </div>
      <p>${escapeHtml(metric.explanation)}</p>
      <span class="explain-source">Fuente: ${escapeHtml(metric.source)}</span>
    `;
    elements.explainedMetrics.appendChild(card);
  }
}

function biasLabel(bias) {
  return {
    favorable: "A favor",
    desfavorable: "En contra",
    alerta: "Alerta",
    contexto: "Contexto",
    neutral: "Neutro",
  }[bias] || "Neutro";
}

function renderAnalysisPayload(analysis, fallbackSummary = "") {
  if (!analysis) {
    fullAnalysisOpen = false;
    updateAnalysisFullVisibility(false);
    elements.analysisHeadline.textContent = "Sin analisis asociado";
    elements.tpProbability.textContent = "--";
    elements.slProbability.textContent = "--";
    elements.rangeProbability.textContent = "--";
    elements.analysisDecision.textContent = fallbackSummary || "Esta operacion no tiene un analisis previo enlazado.";
    elements.analysisSummary.textContent = "";
    elements.analysisHighlights.innerHTML = "";
    elements.analysisKeypoints.innerHTML = "";
  elements.parameterAdvice.innerHTML = "";
  elements.analysisInterpretation.innerHTML = "";
  elements.explainedMetrics.innerHTML = "";
    elements.dataSourcesBox.innerHTML = "";
    elements.learningBox.innerHTML = "";
    elements.analysisReasons.innerHTML = "";
    return;
  }

  updateAnalysisFullVisibility(true);
  elements.analysisHeadline.textContent = `Setup ${analysis.setup_grade} · Riesgo ${analysis.risk_level}`;
  elements.tpProbability.textContent = analysis.probability_ranges?.tp?.label || percent(analysis.tp_probability);
  elements.slProbability.textContent = analysis.probability_ranges?.sl?.label || percent(analysis.sl_probability);
  elements.rangeProbability.textContent = analysis.probability_ranges?.range?.label || percent(analysis.range_probability);
  const evLabel = analysis.expected_value ? ` · EV ${analysis.expected_value.label}` : "";
  const regimeLabel = analysis.market_regime ? ` · ${String(analysis.market_regime.name).replaceAll("_", " ")}` : "";
  elements.analysisDecision.textContent = `${analysis.training_decision} · confianza ${analysis.confidence}${evLabel}${regimeLabel}`;
  elements.analysisSummary.textContent = analysis.plain_summary || fallbackSummary || "";
  renderAnalysisHighlights(analysis);
  renderAnalysisKeypoints(analysis);
  renderParameterAdvice(analysis.parameter_advice || {});
  renderAnalysisInterpretation(analysis, analysis.explained_metrics || []);
  renderExplainedMetrics(analysis.explained_metrics || []);
  renderDataSources(analysis.snapshot?.availability || {}, analysis.snapshot?.source || {});
  renderLearningBox(analysis.learning_adjustment || analysis.snapshot?.learning_adjustment || null);
  elements.analysisReasons.innerHTML = "";
  for (const reason of [...(analysis.reasons || []), ...(analysis.alerts || [])]) {
    const item = document.createElement("li");
    item.textContent = reason;
    elements.analysisReasons.appendChild(item);
  }
  if (Array.isArray(analysis.invalidation_rules) && analysis.invalidation_rules.length) {
    const title = document.createElement("li");
    title.textContent = "Invalidaciones dinamicas a vigilar:";
    elements.analysisReasons.appendChild(title);
    for (const rule of analysis.invalidation_rules) {
      const item = document.createElement("li");
      item.textContent = rule;
      elements.analysisReasons.appendChild(item);
    }
  }
}

function renderAnalysisInterpretation(analysis, metrics) {
  if (!elements.analysisInterpretation) {
    return;
  }
  const buckets = {
    favorable: [],
    desfavorable: [],
    alerta: [],
    neutral: [],
    contexto: [],
  };
  for (const metric of metrics) {
    const bias = String(metric.bias || "neutral").toLowerCase();
    const bucket = buckets[bias] ? bias : "neutral";
    buckets[bucket].push(metric);
  }
  const primary = [
    ...buckets.desfavorable.map((metric) => ({ metric, tone: "desfavorable" })),
    ...buckets.alerta.map((metric) => ({ metric, tone: "alerta" })),
    ...buckets.favorable.map((metric) => ({ metric, tone: "favorable" })),
  ]
    .sort((a, b) => impactLevel(b.metric) - impactLevel(a.metric))
    .slice(0, 6);
  const sideLabel = analysis?.snapshot?.side || side;
  const headline = buildInterpretationHeadline(analysis, buckets);
  elements.analysisInterpretation.innerHTML = `
    <section class="interpretation-panel">
      <div class="interpretation-head">
        <span class="label">Lectura explicada</span>
        <strong>${escapeHtml(headline)}</strong>
        <p>Traduccion operativa para esta propuesta ${escapeHtml(String(sideLabel).toUpperCase())}: que datos ayudan, cuales molestan y donde esta el riesgo.</p>
      </div>
      <div class="interpretation-summary-grid">
        ${renderInterpretationBucket("A favor", buckets.favorable, "favorable")}
        ${renderInterpretationBucket("En contra", buckets.desfavorable, "desfavorable")}
        ${renderInterpretationBucket("Alertas", buckets.alerta, "alerta")}
        ${renderInterpretationBucket("Contexto", [...buckets.contexto, ...buckets.neutral], "contexto")}
      </div>
      ${primary.length ? `
        <div class="evidence-list">
          <span class="label">Evidencias principales</span>
          ${primary.map(({ metric, tone }) => renderEvidenceItem(metric, tone)).join("")}
        </div>
      ` : ""}
    </section>
  `;
}

function impactLevel(metric) {
  const score = Number(metric.score);
  if (!Number.isFinite(score)) {
    return 0;
  }
  return Math.abs(score - 50);
}

function buildInterpretationHeadline(analysis, buckets) {
  const favorable = buckets.favorable.length;
  const pressure = buckets.desfavorable.length + buckets.alerta.length;
  const confidence = String(analysis?.confidence || "").toLowerCase();
  if (pressure >= favorable + 2) {
    return "Predominan riesgos o contradicciones: revisar antes de simular.";
  }
  if (favorable >= pressure + 2 && !confidence.includes("baja")) {
    return "La lectura acompana la operacion, pero sigue condicionada al riesgo.";
  }
  return "Lectura mixta: hay senales utiles, pero no todas apuntan en la misma direccion.";
}

function renderInterpretationBucket(label, metrics, tone) {
  const count = metrics.length;
  const examples = metrics.slice(0, 2).map((metric) => metric.label).join(" · ");
  return `
    <article class="interpretation-bucket ${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${count}</strong>
      <p>${escapeHtml(examples || "Sin senales relevantes")}</p>
    </article>
  `;
}

function renderEvidenceItem(metric, tone) {
  const impactText = tone === "favorable"
    ? "Aporta valor a favor"
    : tone === "desfavorable"
      ? "Resta valor"
      : "Exige prudencia";
  return `
    <article class="evidence-item ${tone}">
      <div>
        <span>${impactText}</span>
        <strong>${escapeHtml(metric.label)}</strong>
      </div>
      <b>${escapeHtml(metric.value)}</b>
      <p>${escapeHtml(metric.explanation)}</p>
    </article>
  `;
}

function renderAnalysisKeypoints(analysis) {
  const combined = [
    ...(analysis.alerts || []),
    ...(analysis.reasons || []),
    ...(analysis.invalidation_rules || []).map((rule) => `Invalidacion: ${rule}`),
  ].filter(Boolean);
  const visible = combined.slice(0, 5);
  if (!visible.length) {
    elements.analysisKeypoints.innerHTML = "";
    return;
  }
  elements.analysisKeypoints.innerHTML = `
    <span class="label">Puntos criticos</span>
    <ul>
      ${visible.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
  `;
}

function renderAnalysisHighlights(analysis) {
  const scores = analysis.layered_scores || analysis.snapshot?.layered_scores || {};
  const expectedValue = analysis.expected_value || analysis.snapshot?.expected_value;
  const regime = analysis.market_regime || analysis.snapshot?.market_regime;
  const snapshot = analysis.snapshot || {};
  const horizon = analysis.time_horizon || snapshot.time_horizon;
  const rrRatio = snapshot.risk_reward_ratio;
  const marginRisk = snapshot.margin_risk_pct;
  const marginReward = snapshot.margin_reward_pct;
  const items = [
    {
      label: "Marco temporal",
      value: timeHorizonLabel(horizon),
      tone: "neutral",
    },
    {
      label: "Direccion",
      value: scores.direction_score !== undefined ? `${scores.direction_score}/100` : "--",
      tone: Number(scores.direction_score) >= 55 ? "positive" : Number(scores.direction_score) <= 45 ? "negative" : "neutral",
    },
    {
      label: "Confianza",
      value: `${analysis.confidence || "--"}${scores.confidence_score !== undefined ? ` · ${scores.confidence_score}/100` : ""}`,
      tone: String(analysis.confidence).includes("baja") ? "negative" : String(analysis.confidence).includes("alta") ? "positive" : "neutral",
    },
    {
      label: "Esperanza neta",
      value: expectedValue ? `${expectedValue.label} · ${money(Number(expectedValue.expected_value_usdt))}` : "--",
      tone: expectedValue && Number(expectedValue.expected_value_usdt) > 0 ? "positive" : expectedValue && Number(expectedValue.expected_value_usdt) < 0 ? "negative" : "neutral",
    },
    {
      label: "Regimen",
      value: regime ? String(regime.name).replaceAll("_", " ") : "--",
      tone: "neutral",
    },
    {
      label: "R/R",
      value: Number.isFinite(Number(rrRatio)) ? Number(rrRatio).toFixed(2) : "--",
      tone: Number(rrRatio) >= 1.5 ? "positive" : "negative",
    },
    {
      label: "Riesgo margen",
      value: Number.isFinite(Number(marginRisk)) ? `${Number(marginRisk).toFixed(2)}%` : "--",
      tone: Number(marginRisk) >= 12 ? "negative" : Number(marginRisk) <= 6 ? "positive" : "neutral",
    },
    {
      label: "Recompensa margen",
      value: Number.isFinite(Number(marginReward)) ? `${Number(marginReward).toFixed(2)}%` : "--",
      tone: "positive",
    },
    {
      label: "Aprendizaje",
      value: analysis.learning_adjustment?.mode === "descriptivo_sin_ajuste_automatico" ? "descriptivo" : "sin ajuste",
      tone: "neutral",
    },
  ];
  elements.analysisHighlights.innerHTML = items
    .map((item) => `
      <article>
        <span>${escapeHtml(item.label)}</span>
        <strong class="${item.tone}">${escapeHtml(item.value)}</strong>
      </article>
    `)
    .join("");
}

function updateAnalysisFullVisibility(hasAnalysis = true) {
  if (!elements.analysisToggle || !elements.analysisFull) {
    return;
  }
  elements.analysisToggle.classList.toggle("hidden", !hasAnalysis);
  elements.analysisToggle.textContent = fullAnalysisOpen ? "Ocultar analisis completo" : "Ver analisis completo";
  elements.analysisFull.classList.toggle("hidden", !hasAnalysis || !fullAnalysisOpen);
  document.querySelector("#analysisResult")?.classList.toggle("analysis-expanded", fullAnalysisOpen);
}

function renderDataSources(availability, sources) {
  const labels = {
    spot_price: "Precio spot",
    spot_klines: "Velas multi-TF",
    order_book: "Order book",
    spot_trade_flow: "CVD/delta spot",
    ticker_24h: "Ticker 24h",
    funding: "Funding",
    open_interest: "Open interest",
    long_short_ratio: "Long/short",
    taker_futures_ratio: "Taker futuros",
    fear_greed: "Fear & Greed",
    global_crypto_market: "Mercado global",
  };
  const sourceText = Object.entries(sources)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ");
  const chips = Object.entries(labels)
    .map(([key, label]) => `<span class="${availability[key] ? "source-on" : "source-off"}">${escapeHtml(label)}</span>`)
    .join("");
  elements.dataSourcesBox.innerHTML = `
    <span class="label">Datos usados en el analisis</span>
    <div class="source-chips">${chips}</div>
    <p>${escapeHtml(sourceText)}</p>
  `;
}

function renderLearningBox(learning) {
  if (!learning) {
    elements.learningBox.innerHTML = `
      <span class="label">Aprendizaje</span>
      <p>Aun no hay modificador aplicado a este analisis.</p>
    `;
    return;
  }
  const delta = Number(learning.tp_probability_delta || 0);
  const suggestedDelta = Number(learning.suggested_tp_probability_delta || 0);
  const deltaText = delta > 0 ? `+${percent(delta)}` : percent(delta);
  const suggestedText = suggestedDelta > 0 ? `+${percent(suggestedDelta)}` : percent(suggestedDelta);
  elements.learningBox.innerHTML = `
    <span class="label">Aprendizaje ${learning.mode === "descriptivo_sin_ajuste_automatico" ? "descriptivo" : "aplicado"}</span>
    <div class="learning-grid">
      <article><span>Casos similares</span><strong>${learning.matching_cases}</strong></article>
      <article><span>Planes resueltos</span><strong>${learning.resolved_plan_cases}/${learning.minimum_cases_to_adjust || 10}</strong></article>
      <article><span>Ganaron / fallaron</span><strong>${learning.plan_successes}/${learning.plan_failures}</strong></article>
      <article><span>Ajuste aplicado</span><strong class="${delta > 0 ? "positive" : delta < 0 ? "negative" : "neutral"}">${deltaText}</strong></article>
      <article><span>Sugerencia futura</span><strong class="${suggestedDelta > 0 ? "positive" : suggestedDelta < 0 ? "negative" : "neutral"}">${suggestedText}</strong></article>
    </div>
    <p>${escapeHtml(learning.plain_text)}</p>
    ${learning.manual_close_explanation ? `<p>${escapeHtml(learning.manual_close_explanation)}</p>` : ""}
  `;
}

async function startSimulation() {
  if (!currentUser) {
    elements.analysisDecision.textContent = "Inicia sesion antes de iniciar simulacion.";
    return;
  }
  if (!lastAnalysis) {
    elements.analysisDecision.textContent = "Analiza la operacion antes de iniciar simulacion.";
    return;
  }
  const validationError = validateTradeForm();
  if (validationError) {
    elements.analysisDecision.textContent = validationError;
    return;
  }
  const payload = getTradePayload();
  if (!isSameTradePayload(payload, lastAnalysisPayload)) {
    elements.analysisDecision.textContent = "Has cambiado parametros desde el ultimo analisis. Vuelve a analizar antes de iniciar.";
    return;
  }
  const openInMode = openOperations.filter((operation) => (operation.mode || "training") === operationMode);
  if (openInMode.length >= 2) {
    elements.analysisDecision.textContent = "Ya tienes 2 operaciones abiertas en este modo. Cierra una antes de iniciar otra.";
    return;
  }

  // Immediate visual feedback so the user sees the click registered while the
  // backend round-trip + UI refresh happen.
  const button = elements.startSimulationButton;
  const originalLabel = button.textContent;
  button.classList.add("is-loading");
  button.disabled = true;
  button.textContent = "Iniciando simulacion...";
  elements.analysisDecision.textContent = "Iniciando simulacion...";

  try {
    const preview = getCreateOperationPayload();
    const operation = await requestJson("/api/operations", {
      method: "POST",
      body: preview,
    });
    selectedOperationId = operation.id;
    newOperationViewActive = false;
    proposalDraft = null;
    lastAnalysis = null;
    lastAnalysisPayload = null;
    elements.analysisDecision.textContent = `Simulacion registrada #${operation.id}.`;
    const outcome = plannedOutcome(getConfig());
    const sideLabel = String(preview.side || side).toUpperCase();
    const detailText =
      `${preview.symbol} ${sideLabel} · ${timeHorizonLabel(preview.time_horizon)} · ` +
      `Entrada ${priceText(preview.entry)} · Margen ${money(preview.margin)} · x${Number(preview.leverage).toFixed(0)} · ` +
      `SL ${priceText(preview.stop_loss)} · TP ${priceText(preview.take_profit)} · ` +
      `TP ${money(outcome.tpPnl)} / SL ${money(outcome.slPnl)}.`;
    showFloatingNotice(`Comienza la simulacion #${operation.id}`, detailText, 6000);
    await loadOperations();
    await loadPortfolio();
    await loadContest();
  } catch (error) {
    elements.analysisDecision.textContent = error.message;
  } finally {
    button.classList.remove("is-loading");
    button.textContent = originalLabel;
    // Re-enable only if the simulation slot is still available; subsequent
    // render passes (updateMetrics / renderOperations) will reconcile this.
    const openNow = openOperations.filter((op) => (op.mode || "training") === operationMode);
    button.disabled = openNow.length >= 2;
  }
}

async function closeSimulation() {
  if (!currentUser) {
    elements.analysisDecision.textContent = "Inicia sesion antes de cerrar una simulacion.";
    return;
  }
  const selectedOperation = getSelectedOperation();
  const activeOperation = selectedOperation && selectedOperation.status === "OPEN" ? selectedOperation : openOperations[0];
  if (!activeOperation) {
    elements.analysisDecision.textContent = "No hay simulacion abierta para cerrar.";
    return;
  }
  await closeOperationById(activeOperation.id);
}

async function closeOperationById(operationId) {
  const operation = allOperations.find((item) => Number(item.id) === Number(operationId));
  const closeSymbol = operation?.symbol || elements.symbol.value;
  if (!hasCurrentPriceForSymbol(closeSymbol)) {
    elements.analysisDecision.textContent = "No hay precio actual para cerrar.";
    fetchPrice({ record: false, symbolOverride: closeSymbol });
    return;
  }

  // Immediate visual feedback so the user perceives the click while the
  // backend round-trip happens (same shimmer pattern as #startSimulationButton).
  const button = elements.closeSimulationButton;
  const originalLabel = button ? button.textContent : null;
  if (button) {
    button.classList.add("is-loading");
    button.disabled = true;
    button.textContent = "Cerrando simulacion...";
  }
  elements.analysisDecision.textContent = "Cerrando simulacion...";

  try {
    const result = await requestJson(`/api/operations/${operationId}/close`, {
      method: "POST",
      body: {
        close_price: currentPrice,
        close_reason: elements.closeReason.value,
        closing_note: elements.closingNote.value,
      },
    });
    selectedOperationId = result.id;
    elements.analysisDecision.textContent = `Operacion #${result.id} cerrada. PnL aprox: ${money(result.final_pnl)}. Queda 2 dias en observacion.`;
    await loadOperations();
    await loadPortfolio();
    await loadContest();
  } catch (error) {
    elements.analysisDecision.textContent = error.message;
  } finally {
    if (button) {
      button.classList.remove("is-loading");
      if (originalLabel !== null) button.textContent = originalLabel;
      // Re-enable only if there are still open operations; subsequent render
      // passes will reconcile anyway.
      button.disabled = !openOperations.length;
    }
  }
}

async function loadPortfolio() {
  if (!currentUser) {
    renderPortfolio(null);
    return;
  }
  try {
    const portfolio = await requestJson("/api/portfolio");
    renderPortfolio(portfolio);
  } catch {
    renderPortfolio(null);
  }
}

async function loadContest() {
  if (!currentUser) {
    contestState = null;
    renderContest(null);
    return;
  }
  try {
    contestState = await requestJson("/api/contest/current");
    renderContest(contestState);
  } catch {
    contestState = null;
    renderContest(null);
  }
}

async function joinContest() {
  if (!currentUser) {
    elements.authMessage.textContent = "Inicia sesion para participar en el concurso.";
    return;
  }
  try {
    elements.joinContestButton.disabled = true;
    elements.joinContestButton.textContent = "Iniciando...";
    contestState = await requestJson("/api/contest/join", { method: "POST" });
    renderContest(contestState);
    await loadPortfolio();
  } catch (error) {
    elements.authMessage.textContent = error.message;
  } finally {
    elements.joinContestButton.disabled = false;
  }
}

function renderContest(state) {
  if (!elements.contestPanel) {
    return;
  }
  elements.contestPanel.classList.toggle("hidden", operationMode !== "contest");
  if (!state) {
    elements.contestTitle.textContent = "Concurso mensual";
    elements.contestDates.textContent = "Inicia sesion para ver el concurso activo.";
    elements.joinContestButton.textContent = "Iniciar concurso del mes";
    elements.joinContestButton.disabled = true;
    elements.contestStartingBalance.textContent = "--";
    elements.contestCash.textContent = "--";
    elements.contestPnl.textContent = "--";
    elements.contestLeaderboard.innerHTML = "<div class=\"contest-empty\">Sin datos de concurso.</div>";
    if (elements.contestHistory) {
      elements.contestHistory.innerHTML = "<div class=\"contest-empty\">Sin historial cerrado.</div>";
    }
    return;
  }
  const season = state.season || {};
  const portfolio = state.portfolio || {};
  elements.contestTitle.textContent = season.name || "Concurso mensual";
  const starts = season.starts_at ? new Date(season.starts_at).toLocaleDateString("es-ES") : "--";
  const ends = season.ends_at ? new Date(season.ends_at).toLocaleDateString("es-ES") : "--";
  elements.contestDates.textContent = `Del ${starts} al ${ends}. Capital inicial mensual: ${money(Number(season.starting_balance || 1000))}.`;
  elements.joinContestButton.textContent = state.participating ? "Participando este mes" : "Iniciar concurso del mes";
  elements.joinContestButton.disabled = Boolean(state.participating);
  elements.contestStartingBalance.textContent = money(Number(portfolio.starting_balance || season.starting_balance || 1000));
  elements.contestCash.textContent = state.participating ? money(Number(portfolio.cash_balance || 0)) : "--";
  const contestPnl = Number(portfolio.total_pnl ?? portfolio.closed_pnl ?? 0);
  elements.contestPnl.textContent = state.participating ? money(contestPnl) : "--";
  setTone(elements.contestPnl, contestPnl);
  renderContestLeaderboard(state.leaderboard || []);
  renderContestHistory(state.history || []);
}

function renderContestLeaderboard(rows) {
  if (!rows.length) {
    elements.contestLeaderboard.innerHTML = "<div class=\"contest-empty\">Todavia no hay participantes en el ranking.</div>";
    return;
  }
  elements.contestLeaderboard.innerHTML = rows.map((row) => `
    <article class="contest-row">
      ${renderContestAvatar(row)}
      <div class="contest-row-body">
        <div class="contest-user-line">
          <span class="contest-rank">#${escapeHtml(row.rank)}</span>
          <strong>${escapeHtml(row.username)}</strong>
        </div>
        <div class="contest-row-stats">
          <span>Operaciones: ${row.operation_count || 0}</span>
          <span>PnL total: <b class="${Number(row.pnl_accumulated || 0) >= 0 ? "positive" : "negative"}">${money(Number(row.pnl_accumulated || 0))}</b></span>
          <span>Flotante: <b class="${Number(row.unrealized_pnl || 0) >= 0 ? "positive" : "negative"}">${money(Number(row.unrealized_pnl || 0))}</b></span>
          <span>Capital estimado: <b>${money(Number(row.estimated_equity ?? row.equity_without_unrealized ?? 0))}</b></span>
        </div>
        <small>${escapeHtml(row.operations_description || "Sin operaciones de concurso todavia.")}</small>
      </div>
    </article>
  `).join("");
}

function renderContestAvatar(row) {
  const username = String(row.username || "?");
  const initial = escapeHtml(username.slice(0, 1).toUpperCase() || "?");
  if (row.avatar_url) {
    return `<span class="contest-avatar"><img src="${escapeHtml(row.avatar_url)}" alt="" loading="lazy"></span>`;
  }
  return `<span class="contest-avatar empty">${initial}</span>`;
}

function renderContestHistory(rows) {
  if (!elements.contestHistory) {
    return;
  }
  updateContestHistoryVisibility(rows.length);
  if (!rows.length) {
    elements.contestHistory.innerHTML = "<div class=\"contest-empty\">Todavia no hay concursos mensuales cerrados.</div>";
    return;
  }
  elements.contestHistory.innerHTML = rows.map((season) => {
    const starts = season.starts_at ? new Date(season.starts_at).toLocaleDateString("es-ES") : "--";
    const ends = season.ends_at ? new Date(season.ends_at).toLocaleDateString("es-ES") : "--";
    const winner = season.winner_username || "Sin ganador";
    const pnl = Number(season.winner_pnl || 0);
    const leaderboard = Array.isArray(season.final_leaderboard) ? season.final_leaderboard.slice(0, 5) : [];
    return `
      <article class="contest-history-card">
        <div class="contest-history-head">
          <div>
            <span>${escapeHtml(season.name || season.code || "Concurso mensual")}</span>
            <strong>Ganador: ${escapeHtml(winner)}</strong>
            <small>${starts} - ${ends}</small>
          </div>
          <b class="${pnl >= 0 ? "positive" : "negative"}">${money(pnl)}</b>
        </div>
        <div class="contest-history-ranking">
          ${leaderboard.map((row) => `
            <div>
              <span>#${escapeHtml(row.rank || "")} ${escapeHtml(row.username || "")}</span>
              <b>${money(Number(row.estimated_equity ?? 0))}</b>
            </div>
          `).join("") || "<small>Ranking final no disponible.</small>"}
        </div>
      </article>
    `;
  }).join("");
}

function updateContestHistoryVisibility(count = 0) {
  if (!elements.contestHistory || !elements.contestHistoryToggle) {
    return;
  }
  elements.contestHistory.classList.toggle("hidden", !contestHistoryOpen);
  elements.contestHistoryToggle.setAttribute("aria-expanded", String(contestHistoryOpen));
  elements.contestHistoryToggle.textContent = contestHistoryOpen
    ? "Ocultar historial"
    : count > 0
      ? `Ver historial (${count})`
      : "Ver historial";
}

function renderPortfolio(portfolio) {
  lastPortfolio = portfolio;
  if (!portfolio) {
    elements.walletTotal.textContent = "--";
    elements.walletCash.textContent = "--";
    elements.walletInvested.textContent = "--";
    elements.walletUnrealized.textContent = "--";
    elements.walletOpenOps.textContent = "--";
    return;
  }
  const modePortfolio = portfolio[operationMode] || portfolio;
  const floatingPnl = calculateFloatingPnl(operationMode);
  const equity = Number(modePortfolio.total_equity_without_unrealized) + floatingPnl;
  elements.walletTotal.textContent = money(equity);
  elements.walletCash.textContent = money(modePortfolio.cash_balance);
  elements.walletInvested.textContent = money(modePortfolio.invested_margin);
  elements.walletUnrealized.textContent = money(floatingPnl);
  setTone(elements.walletUnrealized, floatingPnl);
  elements.walletOpenOps.textContent = `${modePortfolio.open_operations}/${modePortfolio.max_open_operations}`;
}

function calculateFloatingPnl(mode = operationMode) {
  if (!hasCurrentPriceForSymbol(elements.symbol.value)) {
    return 0;
  }
  return openOperations.reduce((total, operation) => {
    if ((operation.mode || "training") !== mode) {
      return total;
    }
    if (operation.symbol !== elements.symbol.value) {
      return total;
    }
    return total + calculate(operationToConfig(operation), currentPrice).pnl;
  }, 0);
}

async function loadOperations() {
  if (!currentUser) {
    renderOperations([]);
    return;
  }
  try {
    const data = await requestJson("/api/operations");
    renderOperations(data.operations || []);
  } catch {
    renderOperations([]);
  }
}

function renderOperations(operations) {
  allOperations = operations;
  openOperations = operations.filter((operation) => operation.status === "OPEN");
  const selectedStillExists = operations.some((operation) => operation.id === selectedOperationId);
  if (!selectedStillExists) {
    if (!(selectedOperationId === null && newOperationViewActive)) {
      selectedOperationId = chooseDefaultOperationId(operations);
      newOperationViewActive = false;
    }
  }
  syncModeWithSelectedOperation(getSelectedOperation());
  const openInMode = openOperations.filter((operation) => (operation.mode || "training") === operationMode);
  elements.startSimulationButton.disabled = openInMode.length >= 2;
  elements.closeSimulationButton.disabled = !openOperations.length;
  elements.operationsList.innerHTML = "";
  renderOperationSelector();

  if (!operations.length) {
    selectedOperationId = null;
    newOperationViewActive = true;
    renderOperationSelector();
    elements.operationsList.innerHTML = "<div class=\"operation-row\"><div><strong>Sin operaciones registradas</strong><span>Define una nueva operacion, analizala e inicia una simulacion.</span></div></div>";
    renderSelectedOperationDetail(null);
    updateMetrics();
    return;
  }

  for (const operation of operations.slice(0, 8)) {
    const row = document.createElement("div");
    const visualStatus = getOperationVisualStatus(operation);
    row.className = operation.id === selectedOperationId ? `operation-row selected ${visualStatus.className}` : `operation-row ${visualStatus.className}`;
    const observation = operation.observation_status === "OBSERVING" ? ` · observacion hasta ${new Date(operation.observation_until).toLocaleString("es-ES")}` : "";
    row.innerHTML = `
      <div>
        <strong>#${operation.id} ${escapeHtml(operation.symbol)} ${escapeHtml(operation.side.toUpperCase())} · ${(operation.mode || "training") === "contest" ? "CONCURSO" : "ENTRENAMIENTO"} · ${escapeHtml(visualStatus.label.replace(`#${operation.id}`, "").trim())}</strong>
        <span>${timeHorizonLabel(operation.time_horizon || "intraday_short")} · Entrada ${priceText(operation.entry)} · SL ${priceText(operation.stop_loss)} · TP ${priceText(operation.take_profit)}${observation}</span>
      </div>
      <div class="operation-actions">
        <span>${operation.final_pnl === null || operation.final_pnl === undefined ? "--" : money(operation.final_pnl)}</span>
        <button class="row-action select-operation" data-operation-id="${operation.id}" type="button">${operation.id === selectedOperationId ? "Vista" : "Ver"}</button>
      </div>
    `;
    elements.operationsList.appendChild(row);
  }
  renderSelectedOperationDetail(getSelectedOperation());
  updateMetrics();
}

function renderOperationSelector() {
  const selectedValue = selectedOperationId === null ? "proposal" : String(selectedOperationId);
  if (!currentUser) {
    elements.operationSelector.innerHTML = `<option value="proposal">Sin usuario activo</option>`;
    elements.operationSelector.value = "proposal";
    elements.operationSelector.disabled = true;
    elements.newOperationQuickButton.disabled = true;
    return;
  }
  const options = [
    `<option value="proposal">Nueva operacion</option>`,
    ...allOperations.map((operation) => {
      const status = getOperationVisualStatus(operation).label.replace(`#${operation.id}`, "").trim().toLowerCase();
      const mode = operation.mode || "training";
      const modeLabel = mode === "contest" ? "concurso" : "entrenamiento";
      const horizon = timeHorizonLabel(operation.time_horizon || operation.recommendation?.time_horizon || "intraday_short").split(" · ")[0].toLowerCase();
      const selected = String(operation.id) === selectedValue ? " selected" : "";
      // Visual cues: light-green background for OPEN operations, yellow text
      // for contest mode and dark blue for training mode — quick at-a-glance ID.
      // Native <option> only supports background-color and color (and only on
      // Chromium/Firefox desktop), so we encode the mode color as the row color.
      const isOpen = String(operation.status).toUpperCase() === "OPEN";
      const classes = isOpen
        ? ` class="op-opt is-open ${mode === "contest" ? "is-contest" : "is-training"}"`
        : "";
      return `<option${classes} value="${operation.id}"${selected}>#${operation.id} · ${escapeHtml(operation.symbol)} · ${escapeHtml(operation.side.toUpperCase())} · ${modeLabel} · ${escapeHtml(horizon)} · ${escapeHtml(status)}</option>`;
    }),
  ];
  elements.operationSelector.innerHTML = options.join("");
  elements.operationSelector.value = selectedValue;
  elements.operationSelector.disabled = false;
  elements.newOperationQuickButton.disabled = false;
  renderOperationSelectorMobile(selectedValue);
}

function renderOperationSelectorMobile(selectedValue) {
  if (!elements.operationSelectorSheetList || !elements.operationSelectorMobileLabel) return;
  const items = [
    { value: "proposal", label: "Nueva operacion", isOpen: false, mode: null },
    ...allOperations.map((operation) => {
      const status = getOperationVisualStatus(operation).label.replace(`#${operation.id}`, "").trim().toLowerCase();
      const mode = operation.mode || "training";
      const modeLabel = mode === "contest" ? "concurso" : "entrenamiento";
      const horizon = timeHorizonLabel(operation.time_horizon || operation.recommendation?.time_horizon || "intraday_short").split(" · ")[0].toLowerCase();
      const isOpen = String(operation.status).toUpperCase() === "OPEN";
      const label = `#${operation.id} · ${operation.symbol} · ${operation.side.toUpperCase()} · ${modeLabel} · ${horizon} · ${status}`;
      return { value: String(operation.id), label, isOpen, mode };
    }),
  ];
  elements.operationSelectorSheetList.innerHTML = items
    .map((item) => {
      const cls = ["op-sheet-item"];
      if (item.isOpen) {
        cls.push("is-open");
        cls.push(item.mode === "contest" ? "is-contest" : "is-training");
      }
      const selected = item.value === selectedValue ? ' aria-selected="true"' : "";
      return `<li class="${cls.join(" ")}" role="option" data-value="${item.value}"${selected}>${escapeHtml(item.label)}</li>`;
    })
    .join("");
  const current = items.find((i) => i.value === selectedValue) || items[0];
  elements.operationSelectorMobileLabel.textContent = current.label;
}

function renderSelectedOperationDetail(operation) {
  if (!operation) {
    setTradeFormLocked(false);
    elements.selectedOperationDetail.innerHTML = `
      <div class="detail-grid compact">
        <article><span>Vista actual</span><strong>${currentUser ? "Nueva operacion" : "Sin sesion"}</strong></article>
        <article><span>Marco temporal</span><strong>${timeHorizonLabel(elements.timeHorizon.value)}</strong></article>
        <article><span>Fuente de grafica</span><strong>${currentUser ? "Historial general" : "--"}</strong></article>
        <article><span>Analisis</span><strong>${lastAnalysis ? `#${lastAnalysis.recommendation_id}` : "Pendiente"}</strong></article>
        <article><span>Resultado</span><strong>${currentUser ? "Sin abrir" : "--"}</strong></article>
      </div>
    `;
    if (lastAnalysis) {
      renderAnalysisPayload(lastAnalysis);
    } else {
      renderAnalysisPayload(null, "Selecciona una operacion o analiza una nueva operacion para ver su lectura aqui.");
    }
    return;
  }

  applyOperationToForm(operation);
  const config = operationToConfig(operation);
  const liveResult = hasCurrentPriceForSymbol(config.symbol) ? calculate(config, currentPrice) : null;
  const finalPnl = operation.final_pnl === null || operation.final_pnl === undefined ? null : Number(operation.final_pnl);
  const displayPnl = operation.status === "CLOSED" && Number.isFinite(finalPnl) ? finalPnl : liveResult?.pnl;
  const displayVariation = liveResult ? liveResult.rawVariation : null;
  const displayExposure = Number(operation.margin) * Number(operation.leverage);
  const outcome = plannedOutcome(config);
  const ticks = Array.isArray(operation.ticks) ? operation.ticks : [];
  const firstTick = ticks[0];
  const lastTick = ticks[ticks.length - 1];
  const recommendation = operation.recommendation;
  const visualStatus = getOperationVisualStatus(operation);
  const operationIdentity = `Operacion ${symbolLabel(operation.symbol)} en ${String(operation.side).toUpperCase()}`;
  const modeLabel = (operation.mode || "training") === "contest" ? "Concurso mensual" : "Entrenamiento";
  const horizonLabel = timeHorizonLabel(operation.time_horizon || recommendation?.time_horizon || "intraday_short");
  const closePrice = Number(operation.close_price);
  const closeInfo = operation.status === "CLOSED" && Number.isFinite(closePrice)
    ? `Cierre ${priceText(closePrice)}`
    : "Sin cierre";
  const observationSummary = operation.observation_summary
    ? `<div class="observation-summary"><span>Conclusion de observacion</span><p>${escapeHtml(operation.observation_summary)}</p></div>`
    : "";
  const learningSummary = operation.learning_summary
    ? `<div class="learning-conclusion"><span>Conclusion para aprendizaje</span><p>${escapeHtml(operation.learning_summary)}</p></div>`
    : "";
  const exitEvidence = renderExitEvidence(operation);

  elements.selectedOperationDetail.innerHTML = `
    <div class="result-banner ${visualStatus.className}">
      <strong>${escapeHtml(operationIdentity)}</strong>
      <span>#${operation.id} · ${modeLabel} · ${escapeHtml(visualStatus.headline)}</span>
      <em>${escapeHtml(horizonLabel)}</em>
    </div>
    ${exitEvidence}
    ${learningSummary}
    ${observationSummary}
    <div class="detail-grid">
      <article><span>Entrada</span><strong>${priceText(operation.entry)}</strong></article>
      <article><span>Cierre</span><strong>${closeInfo}</strong></article>
      <article><span>Stop loss</span><strong>${priceText(operation.stop_loss)}</strong></article>
      <article><span>Take profit</span><strong>${priceText(operation.take_profit)}</strong></article>
      <article><span>Margen</span><strong>${money(Number(operation.margin))}</strong></article>
      <article><span>Apalancamiento</span><strong>x${Number(operation.leverage).toFixed(0)}</strong></article>
      <article><span>Marco temporal</span><strong>${escapeHtml(horizonLabel)}</strong></article>
      <article><span>Resultado</span><strong class="${displayPnl > 0 ? "positive" : displayPnl < 0 ? "negative" : "neutral"}">${money(displayPnl)}</strong></article>
      <article class="outcome-profit"><span>Ganancia en TP</span><strong>${money(outcome.tpPnl)}</strong></article>
      <article class="outcome-loss"><span>Perdida en SL</span><strong>${money(outcome.slPnl)}</strong></article>
      <article><span>Variacion precio</span><strong class="${displayVariation > 0 ? "positive" : displayVariation < 0 ? "negative" : "neutral"}">${signedPct(displayVariation)}</strong></article>
      <article><span>Exposicion</span><strong>${money(displayExposure)}</strong></article>
      <article><span>Prob. TP</span><strong>${probabilityLabel(recommendation, "tp", "tp_probability")}</strong></article>
      <article><span>Prob. SL</span><strong>${probabilityLabel(recommendation, "sl", "sl_probability")}</strong></article>
      <article><span>Registros grafica</span><strong>${ticks.length}</strong></article>
    </div>
    <details class="tick-table-wrap">
      <summary>Tabla de datos de la operacion seleccionada</summary>
      <table class="tick-table">
        <thead>
          <tr>
            <th>Dato</th>
            <th>Valor</th>
            <th>Lectura</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Registros de precio</td>
            <td>${ticks.length}</td>
            <td>Solo ticks asociados a esta operacion.</td>
          </tr>
          <tr>
            <td>Primer registro</td>
            <td>${firstTick ? `${priceText(Number(firstTick.price))} · ${new Date(firstTick.captured_at).toLocaleString("es-ES")}` : "--"}</td>
            <td>Punto inicial real capturado por la API.</td>
          </tr>
          <tr>
            <td>Ultimo registro</td>
            <td>${lastTick ? `${priceText(Number(lastTick.price))} · ${new Date(lastTick.captured_at).toLocaleString("es-ES")}` : "--"}</td>
            <td>Ultimo precio usado en la grafica de esta operacion.</td>
          </tr>
          <tr>
            <td>Analisis previo</td>
            <td>${recommendation ? `#${recommendation.id} · ${recommendation.engine_version}` : "--"}</td>
            <td>Prediccion guardada antes de iniciar esta operacion.</td>
          </tr>
        </tbody>
      </table>
    </details>
  `;

  renderAnalysisPayload(
    recommendation,
    `Operacion #${operation.id}: analisis y resultados separados del resto de operaciones.`
  );
}

function renderExitEvidence(operation) {
  const evidence = operation.exit_evidence;
  if (!evidence || operation.status !== "CLOSED" || !["stop_loss", "take_profit"].includes(operation.close_reason)) {
    return "";
  }
  const market = evidence.market_data || {};
  const sourceLabel = {
    binance_spot_1m_kline: "Binance Spot · vela 1 minuto",
    binance_spot_agg_trade: "Binance Spot · trade agregado",
    binance_spot_ticker: "Binance Spot · precio vivo",
    recorded_close_price: "Precio de cierre registrado",
  }[evidence.source] || evidence.source || "Fuente registrada";
  const reason = evidence.reason === "take_profit" ? "TAKE PROFIT" : "STOP LOSS";
  const proofText = evidence.source === "binance_spot_1m_kline"
    ? `La vela contiene minimo ${priceText(Number(market.low))} y maximo ${priceText(Number(market.high))}; el nivel ${reason} estaba en ${priceText(Number(evidence.level))}.`
    : `El precio registrado fue ${priceText(Number(market.price))}; el nivel ${reason} estaba en ${priceText(Number(evidence.level))}.`;
  return `
    <section class="exit-evidence ${operation.close_reason === "take_profit" ? "target" : "stop"}">
      <div>
        <span>Evidencia de cierre</span>
        <strong>${reason} confirmado</strong>
        <p>${escapeHtml(proofText)}</p>
      </div>
      <div class="exit-evidence-grid">
        <article><span>Fuente</span><strong>${escapeHtml(sourceLabel)}</strong></article>
        <article><span>Hora evento</span><strong>${escapeHtml(formatEvidenceTime(evidence.trigger_time || market.open_time))}</strong></article>
        <article><span>Apertura</span><strong>${priceText(Number(market.open))}</strong></article>
        <article><span>Minimo</span><strong>${priceText(Number(market.low))}</strong></article>
        <article><span>Maximo</span><strong>${priceText(Number(market.high))}</strong></article>
        <article><span>Cierre vela</span><strong>${priceText(Number(market.close ?? market.price))}</strong></article>
      </div>
    </section>
  `;
}

function formatEvidenceTime(value) {
  if (!value || value === "precio_actual") {
    return "Precio vivo";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("es-ES");
}

function resetHistory({ fetchLatest = true } = {}) {
  const symbol = normalizeSymbol(elements.symbol.value);
  activeHistorySymbol = symbol;
  history.length = 0;
  currentPrice = null;
  currentPriceSymbol = symbol;
  loadHistory(symbol);
  elements.currentPrice.textContent = "--";
  elements.variation.textContent = "--";
  elements.pnl.textContent = "--";
  if (Number.isFinite(currentPrice)) {
    updateMetrics();
  }
  if (fetchLatest) {
    fetchPrice({ resetTimer: true, symbolOverride: symbol });
  }
}

function resizeCanvas() {
  const rect = elements.chart.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  // Backing-store size must match the actual CSS box (times DPR for crispness).
  // Hard-coded minimums (was 720x430) caused stretching/distortion on phones
  // where the rendered CSS width was ~340px.
  elements.chart.width = Math.max(1, Math.floor(rect.width * scale));
  elements.chart.height = Math.max(1, Math.floor(rect.height * scale));
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  drawChart();
}

function drawChart() {
  const { config, operation } = getDisplayContext();
  const chartHistory = getChartHistory();
  const livePrice = hasCurrentPriceForSymbol(config.symbol) ? currentPrice : null;
  const rect = elements.chart.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  // Responsive paddings: on narrow screens the side gutters were eating ~55%
  // of the canvas width, squashing the curve and overlapping axis labels.
  const isNarrow = width < 560;
  // On mobile the left gutter was pure empty space (Y-axis labels live on the
  // right edge). Shrink it so the curve spans almost the full width.
  const pad = isNarrow
    ? { top: 20, right: 58, bottom: 30, left: 10 }
    : { top: 28, right: 124, bottom: 46, left: 58 };
  const chartWidth = width - pad.left - pad.right;
  const chartHeight = height - pad.top - pad.bottom;
  const historyPrices = chartHistory.map((point) => point.price);
  const prices = historyPrices.length ? [...historyPrices] : [];

  if (Number.isFinite(livePrice)) {
    prices.push(livePrice);
  }
  if (Number.isFinite(config.entry)) {
    const anchorPrice = Number.isFinite(livePrice) ? livePrice : config.entry;
    const entryDistancePct = Math.abs((config.entry - anchorPrice) / anchorPrice);
    if (entryDistancePct < 0.015) {
      prices.push(config.entry);
    }
  }
  if (isValidTradeConfig(config)) {
    const anchorPrice = Number.isFinite(livePrice) ? livePrice : config.entry;
    for (const level of [config.stopLoss, config.takeProfit]) {
      const levelDistancePct = Math.abs((level - anchorPrice) / Math.max(Math.abs(anchorPrice), 0.000001));
      if (levelDistancePct <= 0.35) {
        prices.push(level);
      }
    }
  }

  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const visibleRange = Math.max(maxPrice - minPrice, maxPrice * 0.0015, 0.000001);
  const padding = Math.max(visibleRange * 0.28, maxPrice * 0.0012);
  const yMin = Math.max(0, minPrice - padding);
  const yMax = maxPrice + padding;
  const yFor = (price) => pad.top + ((yMax - price) / (yMax - yMin)) * chartHeight;
  const xFor = (index) => {
    if (chartHistory.length <= 1) return pad.left + chartWidth * 0.5;
    return pad.left + (index / (chartHistory.length - 1)) * chartWidth;
  };

  ctx.clearRect(0, 0, width, height);
  drawBackground(width, height, pad, chartWidth, chartHeight);
  if (isValidTradeConfig(config)) {
    drawRiskZones(config, yFor, pad, chartWidth, yMin, yMax);
    drawReferenceLine(config.stopLoss, "Stop loss", "#d64b4b", yFor, pad, chartWidth, yMin, yMax, { tag: false });
    drawReferenceLine(config.takeProfit, "Take profit", "#1f9d68", yFor, pad, chartWidth, yMin, yMax, { tag: false });
    drawReferenceLine(config.entry, "Entrada", "#2f3847", yFor, pad, chartWidth, yMin, yMax, { tag: false });
  }

  if (chartHistory.length) {
    drawTimeAxis(chartHistory, pad, chartWidth, chartHeight);

    if (chartHistory.length === 1) {
      const y = yFor(chartHistory[0].price);
      ctx.strokeStyle = "rgba(31, 122, 140, 0.45)";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartWidth, y);
      ctx.stroke();
    } else {
      ctx.beginPath();
      chartHistory.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point.price);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#1f7a8c";
      ctx.lineWidth = 4;
      ctx.stroke();
    }

    chartHistory.forEach((point, index) => {
      const x = xFor(index);
      const y = yFor(point.price);
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(x, y, 4.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#1f7a8c";
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    const lastX = xFor(chartHistory.length - 1);
    const lastY = yFor(chartHistory[chartHistory.length - 1].price);
    const lastPrice = Number(chartHistory[chartHistory.length - 1].price);
    const livePriceWillBeDrawn =
      Number.isFinite(livePrice) &&
      isInScale(livePrice, yMin, yMax) &&
      (!Number.isFinite(lastPrice) || Math.abs(lastPrice - livePrice) >= 0.01);
    ctx.fillStyle = "#1f7a8c";
    ctx.beginPath();
    ctx.arc(lastX, lastY, 6, 0, Math.PI * 2);
    ctx.fill();
    if (!isClosedByPlan(operation) && !livePriceWillBeDrawn) {
      drawTag(`Precio ${priceText(lastPrice)}`, lastX - 130, lastY - 50, getLivePriceTagColor(config, lastPrice), "#ffffff");
    }
    drawSampleSummary(chartHistory, pad, chartHeight);
    drawCloseMarker(operation, chartHistory, xFor, yFor, pad, chartHeight);
  } else {
    ctx.fillStyle = "#657066";
    ctx.font = "700 16px Inter, sans-serif";
    ctx.fillText("Esperando precio en vivo", pad.left + 20, pad.top + 40);
  }

  if (isValidTradeConfig(config)) {
    drawReferenceTag(config.stopLoss, "Stop loss", "#d64b4b", yFor, pad, yMin, yMax);
    drawReferenceTag(config.takeProfit, "Take profit", "#1f9d68", yFor, pad, yMin, yMax);
    drawReferenceTag(config.entry, "Entrada", "#2f3847", yFor, pad, yMin, yMax, { yOffset: -40 });
  }

  drawLivePriceMarker(chartHistory, operation, yFor, pad, chartWidth, chartHeight, yMin, yMax);
  drawAxisLabels(yMin, yMax, yFor, pad, width);
}

function isClosedByPlan(operation) {
  return operation?.status === "CLOSED" && ["stop_loss", "take_profit"].includes(operation.close_reason);
}

function drawCloseMarker(operation, chartHistory, xFor, yFor, pad, chartHeight) {
  if (!operation || operation.status !== "CLOSED" || !["stop_loss", "take_profit"].includes(operation.close_reason)) {
    return;
  }
  const index = findClosePointIndex(operation, chartHistory);
  const closePrice = Number(operation.close_price);
  if (index < 0 || !Number.isFinite(closePrice)) {
    return;
  }
  const x = xFor(index);
  const y = yFor(closePrice);
  const color = operation.close_reason === "take_profit" ? "#1f9d68" : "#d64b4b";
  const label = operation.close_reason === "take_profit" ? "Cierre TAKE PROFIT" : "Cierre STOP LOSS";

  ctx.save();
  ctx.setLineDash([4, 6]);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(x, pad.top);
  ctx.lineTo(x, pad.top + chartHeight);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 3;
  ctx.stroke();
  drawTag(`${label} ${priceText(closePrice)}`, x - 132, y - 62, color, "#ffffff");
  ctx.restore();
}

function drawLivePriceMarker(chartHistory, operation, yFor, pad, chartWidth, chartHeight, yMin, yMax) {
  const { config } = getDisplayContext();
  if (!hasCurrentPriceForSymbol(config.symbol) || !isInScale(currentPrice, yMin, yMax)) {
    return;
  }
  const lastPoint = chartHistory[chartHistory.length - 1];
  if (lastPoint && Math.abs(Number(lastPoint.price) - currentPrice) < 0.01) {
    return;
  }
  const y = yFor(currentPrice);
  ctx.save();
  ctx.setLineDash([5, 7]);
  ctx.strokeStyle = "rgba(16, 24, 19, 0.5)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(pad.left, y);
  ctx.lineTo(pad.left + chartWidth, y);
  ctx.stroke();
  ctx.setLineDash([]);
  const tagX = pad.left + chartWidth - 174;
  let tagY = y - 26;
  const closePrice = Number(operation?.close_price);
  if (isClosedByPlan(operation) && Number.isFinite(closePrice) && isInScale(closePrice, yMin, yMax)) {
    const closeY = yFor(closePrice);
    tagY = currentPrice >= closePrice ? closeY - 78 : closeY + 48;
  }
  tagY = Math.max(pad.top + 8, Math.min(tagY, pad.top + chartHeight - 48));
  drawTag(`${symbolLabel(config.symbol)} ${priceText(currentPrice)}`, tagX, tagY, getLivePriceTagColor(config, currentPrice), "#ffffff");
  ctx.restore();
}

function getLivePriceTagColor(config, price) {
  if (!Number.isFinite(price) || !Number.isFinite(config?.entry) || !config?.side) {
    return "#1f7a8c";
  }
  const favorable = config.side === "long" ? price >= config.entry : price <= config.entry;
  return favorable ? "#1f7a8c" : "#c58a2b";
}

function isValidTradeConfig(config) {
  return [config.entry, config.stopLoss, config.takeProfit].every(Number.isFinite);
}

function drawBackground(width, height, pad, chartWidth, chartHeight) {
  ctx.fillStyle = "#fbfcf9";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#e2e7dd";
  ctx.lineWidth = 1;

  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (chartHeight / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + chartWidth, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#cfd7cc";
  ctx.strokeRect(pad.left, pad.top, chartWidth, chartHeight);
}

function drawRiskZones(config, yFor, pad, chartWidth, yMin, yMax) {
  if (!isInScale(config.entry, yMin, yMax)) {
    return;
  }

  const entryY = yFor(config.entry);
  const stopY = yFor(clamp(config.stopLoss, yMin, yMax));
  const targetY = yFor(clamp(config.takeProfit, yMin, yMax));

  ctx.fillStyle = "rgba(214, 75, 75, 0.09)";
  ctx.fillRect(pad.left, Math.min(entryY, stopY), chartWidth, Math.abs(entryY - stopY));
  ctx.fillStyle = "rgba(31, 157, 104, 0.10)";
  ctx.fillRect(pad.left, Math.min(entryY, targetY), chartWidth, Math.abs(entryY - targetY));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function isInScale(price, yMin, yMax) {
  return price >= yMin && price <= yMax;
}

function drawReferenceLine(price, label, color, yFor, pad, chartWidth, yMin, yMax, options = {}) {
  const visible = isInScale(price, yMin, yMax);
  const y = yFor(clamp(price, yMin, yMax));
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash(visible ? [8, 8] : [3, 6]);
  ctx.beginPath();
  ctx.moveTo(pad.left, y);
  ctx.lineTo(pad.left + chartWidth, y);
  ctx.stroke();
  ctx.setLineDash([]);
  if (options.tag === false) {
    return;
  }
  drawReferenceTag(price, label, color, yFor, pad, yMin, yMax);
}

function drawReferenceTag(price, label, color, yFor, pad, yMin, yMax, options = {}) {
  const visible = isInScale(price, yMin, yMax);
  const y = yFor(clamp(price, yMin, yMax));
  const prefix = visible ? label : price > yMax ? `${label} arriba` : `${label} abajo`;
  const defaultOffset = price > yMax ? 8 : -28;
  const yOffset = Number.isFinite(options.yOffset) ? options.yOffset : defaultOffset;
  drawTag(`${prefix} ${priceText(price)}`, pad.left + 10, y + yOffset, color, "#ffffff");
}

function drawAxisLabels(yMin, yMax, yFor, pad, width) {
  ctx.fillStyle = "#657066";
  ctx.font = "700 12px Inter, sans-serif";
  for (let i = 0; i <= 4; i += 1) {
    const price = yMax - ((yMax - yMin) / 4) * i;
    const y = yFor(price);
    ctx.fillText(priceText(price), width - pad.right + 12, y + 4);
  }
}

function drawTimeAxis(chartHistory, pad, chartWidth, chartHeight) {
  const first = chartHistory[0];
  const last = chartHistory[chartHistory.length - 1];
  const y = pad.top + chartHeight + 24;

  ctx.fillStyle = "#657066";
  ctx.font = "700 12px Inter, sans-serif";
  ctx.fillText(first.time.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }), pad.left, y);
  ctx.textAlign = "right";
  ctx.fillText(last.time.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }), pad.left + chartWidth, y);
  ctx.textAlign = "left";
}

function drawSampleSummary(chartHistory, pad, chartHeight) {
  const label = `${chartHistory.length} registro${chartHistory.length === 1 ? "" : "s"} de precio`;
  ctx.fillStyle = "#657066";
  ctx.font = "800 12px Inter, sans-serif";
  ctx.fillText(label, pad.left, pad.top + chartHeight + 42);
}

function drawTag(text, x, y, bg, fg) {
  // 1.5x bigger price capsules on desktop; smaller on mobile to prevent overlap.
  const rect = elements.chart.getBoundingClientRect();
  const isMobile = rect.width < 560;
  const fontSize = isMobile ? 13 : 18;
  const paddingX = isMobile ? 8 : 14;
  const paddingY = isMobile ? 5 : 9;
  const boxHeight = isMobile ? 26 : 39;
  const radius = isMobile ? 6 : 9;
  const baselineOffset = isMobile ? 11 : 16;

  ctx.font = `800 ${fontSize}px Inter, sans-serif`;
  const metrics = ctx.measureText(text);
  const boxWidth = metrics.width + paddingX * 2;
  const safeX = Math.max(4, Math.min(x, rect.width - boxWidth - 4));
  const safeY = Math.max(4, Math.min(y, rect.height - boxHeight - 4));

  ctx.fillStyle = bg;
  roundedRect(safeX, safeY, boxWidth, boxHeight, radius);
  ctx.fill();
  ctx.fillStyle = fg;
  ctx.fillText(text, safeX + paddingX, safeY + paddingY + baselineOffset);
}

function roundedRect(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function setSide(nextSide, options = {}) {
  side = nextSide;
  elements.longButton.classList.toggle("active", side === "long");
  elements.shortButton.classList.toggle("active", side === "short");
  if (selectedOperationId === null && !newOperationViewActive) {
    proposalDraft = readFormDraft();
  }
  if (options.silent) {
    return;
  }
  updateMetrics();
}

function setOperationMode(nextMode) {
  operationMode = nextMode === "contest" ? "contest" : "training";
  elements.trainingModeButton.classList.toggle("active", operationMode === "training");
  elements.contestModeButton.classList.toggle("active", operationMode === "contest");
  elements.modeTitle.textContent = operationMode === "contest" ? "Concurso mensual" : "Entrenamiento";
  elements.modeSubtitle.textContent = operationMode === "contest"
    ? "Capital mensual separado: 1.000 USDT para competir en igualdad de condiciones."
    : "Cartera normal del usuario. Las recargas futuras quedaran registradas.";
  elements.parameterModeChip.textContent = operationMode === "contest" ? "Modo concurso mensual" : "Modo entrenamiento";
  renderPortfolio(lastPortfolio);
  renderContest(contestState);
  if (operationMode === "contest") {
    loadContest();
  }
  const openInMode = openOperations.filter((operation) => (operation.mode || "training") === operationMode);
  elements.startSimulationButton.disabled = selectedOperationId !== null || openInMode.length >= 2;
}

function syncModeWithSelectedOperation(operation) {
  if (!operation) {
    return;
  }
  const modeFromOperation = (operation.mode || "training") === "contest" ? "contest" : "training";
  if (operationMode !== modeFromOperation) {
    // Keep mode-of-use strictly aligned with the selected operation.
    setOperationMode(modeFromOperation);
  }
}

for (const input of [elements.timeHorizon, elements.margin, elements.leverage, elements.stopLoss, elements.takeProfit]) {
  input.addEventListener("input", () => {
    if (selectedOperationId === null && !newOperationViewActive) {
      proposalDraft = readFormDraft();
    }
    updateMetrics();
  });
}

elements.symbol.addEventListener("change", () => {
  if (selectedOperationId === null && !newOperationViewActive) {
    proposalDraft = readFormDraft();
  }
  const symbol = normalizeSymbol(elements.symbol.value);
  activeHistorySymbol = symbol;
  currentPrice = null;
  currentPriceSymbol = symbol;
  resetHistory({ fetchLatest: false });
  updateMetrics();
  if (selectedOperationId === null) {
    loadRecentMarketHistory(symbol);
    fetchPrice({ resetTimer: true, record: true, symbolOverride: symbol });
  }
});
elements.refreshButton.addEventListener("click", async () => {
  const button = elements.refreshButton;
  const originalLabel = button.textContent;
  button.classList.add("is-loading");
  button.disabled = true;
  button.textContent = "Actualizando...";
  try {
    await fetchPrice({ resetTimer: true, record: true });
    // If the call was queued because another fetch was in-flight, wait for the
    // drained follow-up so the button stays in "loading" until fresh data lands.
    let guard = 0;
    while ((isFetching || pendingManualFetch) && guard < 80) {
      await new Promise((r) => setTimeout(r, 100));
      guard += 1;
    }
  } finally {
    button.classList.remove("is-loading");
    button.textContent = originalLabel;
    button.disabled = false;
  }
});
elements.loginButton.addEventListener("click", () => authenticate("login"));
elements.registerButton.addEventListener("click", () => authenticate("register"));
elements.authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  authenticate("login");
});
elements.avatarInput.addEventListener("change", uploadAvatar);
elements.logoutButton.addEventListener("click", logout);
elements.analyzeButton.addEventListener("click", analyzeOperation);
elements.startSimulationButton.addEventListener("click", startSimulation);
elements.closeSimulationButton.addEventListener("click", closeSimulation);
elements.analysisToggle.addEventListener("click", () => {
  fullAnalysisOpen = !fullAnalysisOpen;
  updateAnalysisFullVisibility();
});
elements.operationsList.addEventListener("click", (event) => {
  const selectButton = event.target.closest(".select-operation");
  const closeButton = event.target.closest(".close-operation");
  if (selectButton) {
    saveProposalDraft();
    selectedOperationId = Number(selectButton.dataset.operationId);
    newOperationViewActive = false;
    const operation = getSelectedOperation();
    syncModeWithSelectedOperation(operation);
    if (operation?.symbol) {
      elements.operationSelector.value = String(operation.id);
    }
    renderOperations(allOperations);
    fetchVisibleOperationPrice(operation);
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  if (closeButton) {
    selectedOperationId = Number(closeButton.dataset.operationId);
    closeOperationById(selectedOperationId);
  }
});
function openOperationSheet() {
  if (!elements.operationSelectorSheet) return;
  elements.operationSelectorSheet.hidden = false;
  elements.operationSelectorMobile?.setAttribute("aria-expanded", "true");
  document.body.style.overflow = "hidden";
}
function closeOperationSheet() {
  if (!elements.operationSelectorSheet) return;
  elements.operationSelectorSheet.hidden = true;
  elements.operationSelectorMobile?.setAttribute("aria-expanded", "false");
  document.body.style.overflow = "";
}
elements.operationSelectorMobile?.addEventListener("click", () => {
  if (elements.operationSelector.disabled) return;
  openOperationSheet();
});
elements.operationSelectorSheet?.addEventListener("click", (event) => {
  const target = event.target;
  if (target.closest(".op-sheet-backdrop") || target.closest(".op-sheet-close")) {
    closeOperationSheet();
    return;
  }
  const item = target.closest(".op-sheet-item");
  if (!item) return;
  const value = item.dataset.value;
  if (elements.operationSelector.value !== value) {
    elements.operationSelector.value = value;
    elements.operationSelector.dispatchEvent(new Event("change", { bubbles: true }));
  }
  closeOperationSheet();
});
elements.operationSelector.addEventListener("change", () => {
  saveProposalDraft();
  selectedOperationId = elements.operationSelector.value === "proposal" ? null : Number(elements.operationSelector.value);
  if (selectedOperationId === null) {
    prepareNewOperationForm();
    setOperationMode(operationMode);
    return;
  }
  newOperationViewActive = false;
  const operation = getSelectedOperation();
  const modeFromOperation = (operation?.mode || "training") === "contest" ? "contest" : "training";
  setOperationMode(modeFromOperation);
  syncModeWithSelectedOperation(operation);
  renderOperationSelector();
  renderSelectedOperationDetail(operation);
  updateMetrics();
  fetchVisibleOperationPrice(operation);
});
elements.newOperationQuickButton.addEventListener("click", () => {
  if (!currentUser) {
    return;
  }
  saveProposalDraft();
  elements.operationSelector.value = "proposal";
  prepareNewOperationForm();
  renderOperationSelector();
  updateMetrics();
  window.scrollTo({ top: 0, behavior: "smooth" });
});
elements.longButton.addEventListener("click", () => setSide("long"));
elements.shortButton.addEventListener("click", () => setSide("short"));
elements.trainingModeButton.addEventListener("click", () => setOperationMode("training"));
elements.contestModeButton.addEventListener("click", () => setOperationMode("contest"));
elements.joinContestButton.addEventListener("click", joinContest);
elements.contestHistoryToggle?.addEventListener("click", () => {
  const historyCount = Array.isArray(contestState?.history) ? contestState.history.length : 0;
  contestHistoryOpen = !contestHistoryOpen;
  updateContestHistoryVisibility(historyCount);
});
window.addEventListener("resize", resizeCanvas);

loadSession();
loadHistory();
resizeCanvas();
setOperationMode("training");
updateMetrics();
loadRecentMarketHistory();
fetchPrice({ resetTimer: true, record: true });
