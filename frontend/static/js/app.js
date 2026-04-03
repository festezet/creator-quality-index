/* ============================================================
   YouTube Creator Quality Index — Frontend Application
   ============================================================ */

(function () {
    "use strict";

    // --- Weight defaults (matches backend config.py) ---
    const DEFAULT_WEIGHTS = {
        research_depth: 20,
        production: 20,
        signal_noise: 20,
        originality: 20,
        lasting_impact: 20,
    };

    function loadWeights() {
        try {
            const saved = localStorage.getItem("cqi_weights");
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed && typeof parsed.research_depth === "number") return parsed;
            }
        } catch (_) { /* corrupt data, use defaults */ }
        return { ...DEFAULT_WEIGHTS };
    }

    // --- State ---
    const state = {
        channels: [],
        categories: [],
        stats: null,
        filters: {
            category: "",
            tier: "",
            lang: "",
            sort: "composite_score",
            order: "desc",
            search: "",
        },
        total: 0,
        offset: 0,
        limit: 200,
        loading: false,
        methodologyLoaded: false,
        customWeights: loadWeights(),
        isCustom: false,
    };

    // --- DOM refs ---
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dom = {
        grid: $("#channel-grid"),
        rankingRows: $("#ranking-rows"),
        searchInput: $("#search-input"),
        categoryPills: $("#category-pills"),
        tierPills: $("#tier-pills"),
        langPills: $("#lang-pills"),
        sortPills: $("#sort-pills"),
        resultsCount: $("#results-count"),
        loadMoreWrap: $("#load-more-wrap"),
        btnLoadMore: $("#btn-load-more"),
        emptyState: $("#empty-state"),
        modalOverlay: $("#modal-overlay"),
        modalBody: $("#modal-body"),
        modalClose: $("#modal-close"),
        viewIndex: $("#view-index"),
        viewMethodology: $("#view-methodology"),
        methodologyContent: $("#methodology-content"),
        statTotal: $("#stat-total"),
        statAvgScore: $("#stat-avg-score"),
        statSTier: $("#stat-s-tier"),
        statCategories: $("#stat-categories"),
    };

    // --- Criteria config ---
    const CRITERIA = [
        { key: "score_research_depth", label: "Research", short: "Research" },
        { key: "score_production", label: "Production", short: "Production" },
        { key: "score_signal_noise", label: "Signal/Noise", short: "Signal" },
        { key: "score_originality", label: "Originality", short: "Original." },
        { key: "score_lasting_impact", label: "Impact", short: "Impact" },
    ];

    // --- Category colors for avatars ---
    const CATEGORY_AVATAR_CLASS = {
        science: "avatar-science",
        "tech-dev": "avatar-tech-dev",
        engineering: "avatar-engineering",
        finance: "avatar-finance",
        history: "avatar-history",
        geopolitics: "avatar-geopolitics",
        productivity: "avatar-productivity",
        "philosophy-essays": "avatar-philosophy-essays",
        "design-art": "avatar-design-art",
        education: "avatar-education",
        environment: "avatar-environment",
        making: "avatar-making",
        entertainment: "avatar-entertainment",
        music: "avatar-music",
        "kids-family": "avatar-kids-family",
        "sports-media": "avatar-sports-media",
        gaming: "avatar-gaming",
        lifestyle: "avatar-lifestyle",
    };

    // --- Helpers ---

    function tierClass(tier) {
        return tier ? `tier-${tier}` : "";
    }

    function scoreTierClass(tier) {
        return tier ? `score-tier-${tier}` : "";
    }

    function barTierClass(tier) {
        return tier ? `bar-tier-${tier}` : "bar-tier-B";
    }

    function avatarClass(category) {
        return CATEGORY_AVATAR_CLASS[category] || "avatar-science";
    }

    function firstLetter(name) {
        return name ? name.charAt(0).toUpperCase() : "?";
    }

    function formatNumber(n) {
        if (n == null) return "--";
        if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
        if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
        return n.toLocaleString();
    }

    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function escapeHtml(str) {
        if (!str) return "";
        const d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }

    // --- Weight customizer logic ---

    function checkIsCustom() {
        state.isCustom = Object.keys(DEFAULT_WEIGHTS).some(
            (k) => state.customWeights[k] !== DEFAULT_WEIGHTS[k]
        );
    }

    function computeCustomComposite(ch) {
        const w = state.customWeights;
        const total = Object.values(w).reduce((a, b) => a + b, 0) || 1;
        return (
            ((ch.score_research_depth || 0) * w.research_depth +
             (ch.score_production || 0) * w.production +
             (ch.score_signal_noise || 0) * w.signal_noise +
             (ch.score_originality || 0) * w.originality +
             (ch.score_lasting_impact || 0) * w.lasting_impact) / total
        );
    }

    function computeCustomTier(score) {
        if (score >= 8.5) return "S";
        if (score >= 7.0) return "A";
        if (score >= 5.5) return "B";
        if (score >= 4.0) return "C";
        return "D";
    }

    function applyCustomScores() {
        checkIsCustom();
        state.channels.forEach((ch) => {
            ch._customScore = computeCustomComposite(ch);
            ch._customTier = computeCustomTier(ch._customScore);
        });
    }

    function recalcAndRender() {
        applyCustomScores();
        renderCustomRanking();
    }

    function renderCustomRanking() {
        const container = document.getElementById("customizer-ranking");
        if (!container) return;
        container.innerHTML = "";

        // Sort a copy by custom score descending
        const sorted = [...state.channels].sort((a, b) => (b._customScore || 0) - (a._customScore || 0));

        const fragment = document.createDocumentFragment();

        // Header row
        const header = document.createElement("div");
        header.className = "cr-row cr-header";
        header.innerHTML = `
            <span class="cr-rank">#</span>
            <span class="cr-name">Channel</span>
            <span class="cr-official">Official</span>
            <span class="cr-custom">Custom</span>
            <span class="cr-tier">Tier</span>
            <span class="cr-diff">Diff</span>
        `;
        fragment.appendChild(header);

        sorted.forEach((ch, i) => {
            const tier = ch._customTier || ch.tier || "B";
            const score = ch._customScore != null ? ch._customScore.toFixed(1) : "--";
            const officialScore = ch.composite_score != null ? ch.composite_score.toFixed(1) : "--";
            const officialTier = ch.tier || "B";
            const diff = ch._customScore != null && ch.composite_score != null
                ? (ch._customScore - ch.composite_score).toFixed(1) : null;
            const diffVal = diff !== null ? parseFloat(diff) : 0;
            const diffContent = Math.abs(diffVal) >= 0.1
                ? `<span class="${diffVal > 0 ? "cr-diff-up" : "cr-diff-down"}">${diffVal > 0 ? "+" : ""}${diff}</span>`
                : "";

            const row = document.createElement("div");
            row.className = "cr-row";
            row.innerHTML = `
                <span class="cr-rank">${i + 1}</span>
                <span class="cr-name">${escapeHtml(ch.name)}</span>
                <span class="cr-official">${officialScore} <span class="tier-badge-sm ${tierClass(officialTier)}">${officialTier}</span></span>
                <span class="cr-custom ${scoreTierClass(tier)}">${score}</span>
                <span class="cr-tier"><span class="tier-badge-sm ${tierClass(tier)}">${tier}</span></span>
                <span class="cr-diff">${diffContent}</span>
            `;
            fragment.appendChild(row);
        });
        container.appendChild(fragment);
    }

    function openCustomizer() {
        applyCustomScores();
        renderCustomRanking();
        document.getElementById("customizer-overlay").classList.add("open");
        document.body.classList.add("modal-open");
    }

    function closeCustomizer() {
        document.getElementById("customizer-overlay").classList.remove("open");
        document.body.classList.remove("modal-open");
    }

    const CRITERIA_ORDER = ["research_depth", "production", "signal_noise", "originality", "lasting_impact"];

    function syncSliderUI() {
        const rows = document.querySelectorAll(".weight-slider-row");
        rows.forEach((row, i) => {
            const slider = row.querySelector(".weight-slider-input");
            const valueSpan = row.querySelector(".weight-slider-value");
            const key = CRITERIA_ORDER[i];

            slider.value = Math.round(state.customWeights[key]);
            valueSpan.textContent = state.customWeights[key].toFixed(1) + "%";

            row.classList.remove("active", "locked");

            if (i === state.activeSlider) {
                row.classList.add("active");
                slider.disabled = false;
            } else if (state.lockedSliders.has(i)) {
                row.classList.add("locked");
                slider.disabled = true;
            } else {
                // Idle — keep enabled so clicks register, input handler guards against non-active
                slider.disabled = false;
            }
        });

        // Footer total
        const totalEl = document.getElementById("weight-total");
        if (totalEl) {
            const total = Object.values(state.customWeights).reduce((a, b) => a + b, 0);
            totalEl.textContent = `Total: ${total.toFixed(1)}%`;
            totalEl.classList.toggle("warn", Math.abs(total - 100) > 0.5);
        }

        const resetBtn = document.getElementById("weight-reset");
        if (resetBtn) {
            checkIsCustom();
            resetBtn.disabled = !state.isCustom;
        }
    }

    /**
     * Recompute flex sliders so they split equally whatever is left
     * after the active slider + locked sliders are accounted for.
     * The +1 remainder rotates so no single slider is always higher.
     */
    function redistributeFromActive(activeIdx) {
        const activeVal = state.customWeights[CRITERIA_ORDER[activeIdx]];

        const lockedTotal = [...state.lockedSliders].reduce(
            (s, i) => s + state.customWeights[CRITERIA_ORDER[i]], 0
        );

        const flexIndices = CRITERIA_ORDER
            .map((_, i) => i)
            .filter(i => i !== activeIdx && !state.lockedSliders.has(i));

        if (flexIndices.length === 0) return;

        const remaining = Math.max(0, 100 - activeVal - lockedTotal);

        // Sum of current flex slider values (before adjustment)
        const flexTotal = flexIndices.reduce(
            (s, i) => s + state.customWeights[CRITERIA_ORDER[i]], 0
        );

        if (flexTotal > 0) {
            // Proportional: each flex slider keeps its relative weight
            flexIndices.forEach((idx) => {
                const key = CRITERIA_ORDER[idx];
                state.customWeights[key] = Math.round(
                    (state.customWeights[key] / flexTotal) * remaining * 10
                ) / 10;
            });
        } else {
            // All flex at 0 — split equally
            const share = remaining / flexIndices.length;
            flexIndices.forEach((idx) => {
                state.customWeights[CRITERIA_ORDER[idx]] = Math.round(share * 10) / 10;
            });
        }
    }

    function initWeightSliders() {
        state.activeSlider = null;
        state.lockedSliders = new Set();
        checkIsCustom();
        syncSliderUI();

        const container = document.getElementById("weight-sliders");
        if (!container) return;

        // Click/mousedown on a row or slider → activate that slider (lock previous if any)
        function activateSlider(e) {
            const row = e.target.closest(".weight-slider-row");
            if (!row) return;
            const rows = [...container.querySelectorAll(".weight-slider-row")];
            const idx = rows.indexOf(row);
            if (idx < 0 || state.lockedSliders.has(idx)) return;
            if (idx === state.activeSlider) return;

            // Lock the previously active slider
            if (state.activeSlider !== null) {
                state.lockedSliders.add(state.activeSlider);
            }
            state.activeSlider = idx;
            syncSliderUI();
        }
        container.addEventListener("click", activateSlider);
        container.addEventListener("mousedown", activateSlider);

        // Slider drag → redistribute proportionally (ranking effect disabled for now)
        container.addEventListener("input", (e) => {
            const slider = e.target.closest(".weight-slider-input");
            if (!slider) return;
            const row = slider.closest(".weight-slider-row");
            const rows = [...container.querySelectorAll(".weight-slider-row")];
            const idx = rows.indexOf(row);
            if (idx < 0 || idx !== state.activeSlider) return;

            const key = CRITERIA_ORDER[idx];
            // Cap: active slider cannot exceed 100 minus locked sliders' total
            const lockedTotal = [...state.lockedSliders].reduce(
                (s, i) => s + state.customWeights[CRITERIA_ORDER[i]], 0
            );
            const maxAllowed = 100 - lockedTotal;
            state.customWeights[key] = Math.min(parseInt(slider.value, 10), maxAllowed);
            redistributeFromActive(idx);

            syncSliderUI();
            localStorage.setItem("cqi_weights", JSON.stringify(state.customWeights));
            recalcAndRender();
        });

        // Reset
        const resetBtn = document.getElementById("weight-reset");
        if (resetBtn) {
            resetBtn.addEventListener("click", () => {
                Object.assign(state.customWeights, DEFAULT_WEIGHTS);
                state.activeSlider = null;
                state.lockedSliders = new Set();
                localStorage.removeItem("cqi_weights");
                checkIsCustom();
                syncSliderUI();
                recalcAndRender();
            });
        }
    }

    // --- API ---

    async function apiFetch(url) {
        const res = await fetch(url, { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const json = await res.json();
        if (!json.ok) throw new Error(json.message || "API error");
        return json.data;
    }

    async function fetchChannels(append) {
        if (state.loading) return;
        state.loading = true;

        const f = state.filters;
        const params = new URLSearchParams();
        if (f.category) params.set("category", f.category);
        if (f.tier) params.set("tier", f.tier);
        if (f.lang) params.set("lang", f.lang);
        if (f.search) params.set("search", f.search);
        params.set("sort", f.sort);
        params.set("order", f.order);
        params.set("limit", state.limit);
        params.set("offset", append ? state.offset : 0);

        try {
            const data = await apiFetch(`/api/channels?${params}`);
            if (append) {
                state.channels = state.channels.concat(data.channels);
            } else {
                state.channels = data.channels;
                state.offset = 0;
            }
            state.total = data.total;
            state.offset = state.channels.length;
            renderList();
            renderResultsCount();
            updateLoadMore();
        } catch (e) {
            console.error("fetchChannels:", e);
        } finally {
            state.loading = false;
        }
    }

    async function fetchCategories() {
        try {
            const data = await apiFetch("/api/categories");
            state.categories = data;
            renderCategoryPills();
        } catch (e) {
            console.error("fetchCategories:", e);
        }
    }

    async function fetchStats() {
        try {
            const data = await apiFetch("/api/stats");
            state.stats = data;
            renderStats();
        } catch (e) {
            console.error("fetchStats:", e);
        }
    }

    async function fetchChannel(id) {
        try {
            return await apiFetch(`/api/channels/${id}`);
        } catch (e) {
            console.error("fetchChannel:", e);
            return null;
        }
    }

    async function fetchMethodology() {
        try {
            const data = await apiFetch("/api/methodology");
            return data.content || "";
        } catch (e) {
            console.error("fetchMethodology:", e);
            return "Failed to load methodology.";
        }
    }

    // --- Community API ---

    async function fetchComments(channelId, offset) {
        try {
            return await apiFetch(`/api/channels/${channelId}/comments?limit=20&offset=${offset || 0}`);
        } catch (e) {
            console.error("fetchComments:", e);
            return null;
        }
    }

    async function postComment(channelId, name, content) {
        const res = await fetch(`/api/channels/${channelId}/comments`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ name: name || "Anonymous", content }),
        });
        const json = await res.json();
        if (!json.ok) throw new Error(json.message || "Comment failed");
        return json.data;
    }

    async function upvoteComment(commentId) {
        const res = await fetch(`/api/comments/${commentId}/upvote`, {
            method: "POST",
            headers: { Accept: "application/json" },
        });
        const json = await res.json();
        if (!json.ok) throw new Error(json.message || "Upvote failed");
        return json.data;
    }

    // --- Render: Stats ---

    function renderStats() {
        const s = state.stats;
        if (!s) return;

        dom.statTotal.textContent = s.total_channels || 0;
        dom.statAvgScore.textContent =
            s.averages && s.averages.avg_score != null
                ? s.averages.avg_score.toFixed(1)
                : "--";

        const sTierCount =
            (s.tier_distribution || []).find((t) => t.tier === "S");
        dom.statSTier.textContent = sTierCount ? sTierCount.count : 0;

        dom.statCategories.textContent =
            (s.category_distribution || []).length || 0;
    }

    // --- Render: Category Pills ---

    function renderCategoryPills() {
        // Keep the "All" pill, add dynamic ones
        const existing = dom.categoryPills.querySelectorAll("[data-category]");
        existing.forEach((el) => {
            if (el.dataset.category !== "") el.remove();
        });

        state.categories.forEach((cat) => {
            if (cat.channel_count === 0) return;
            const btn = document.createElement("button");
            btn.className = "pill";
            btn.dataset.category = cat.slug;
            btn.textContent = `${cat.icon || ""} ${cat.name}`;
            dom.categoryPills.appendChild(btn);
        });
    }

    // --- Render: Results Count ---

    function renderResultsCount() {
        const shown = state.channels.length;
        const total = state.total;
        if (total === 0) {
            dom.resultsCount.textContent = "No channels found";
        } else if (shown >= total) {
            dom.resultsCount.textContent = `${total} channel${total !== 1 ? "s" : ""}`;
        } else {
            dom.resultsCount.textContent = `${shown} of ${total} channels`;
        }
    }

    // --- Render: List ---

    function renderList() {
        dom.rankingRows.innerHTML = "";

        if (state.channels.length === 0) {
            dom.emptyState.style.display = "block";
            return;
        }
        dom.emptyState.style.display = "none";

        const fragment = document.createDocumentFragment();
        state.channels.forEach((ch, i) => {
            const row = document.createElement("div");
            row.className = "ranking-row";
            row.dataset.id = ch.id;

            const tier = ch.tier || "B";
            const score = ch.composite_score != null ? ch.composite_score.toFixed(1) : "--";
            const catName = ch.category_name || ch.primary_category || "";
            const catIcon = ch.category_icon || "";
            const lang = (ch.language || "").toUpperCase();

            const subs = ch.subscriber_count ? formatNumber(ch.subscriber_count) : "";
            const avatarHtml = ch.thumbnail_url
                ? `<img class="ranking-avatar ranking-avatar-img" src="${ch.thumbnail_url}" alt="" loading="lazy">`
                : `<span class="ranking-avatar ${avatarClass(ch.primary_category)}">${firstLetter(ch.name)}</span>`;

            row.innerHTML = `
                <span class="ranking-col-rank">${i + 1}</span>
                <span class="ranking-col-name">
                    ${avatarHtml}
                    <span class="ranking-channel-info">
                        <span class="ranking-channel-name">${escapeHtml(ch.name)}</span>
                        <span class="ranking-channel-lang">${lang}</span>
                    </span>
                </span>
                <span class="ranking-col-category">${catIcon} ${escapeHtml(catName)}</span>
                <span class="ranking-col-subs">${subs}</span>
                <span class="ranking-col-score ${scoreTierClass(tier)}">${score}</span>
                <span class="ranking-col-tier"><span class="tier-badge ${tierClass(tier)}">${tier}</span></span>
            `;

            row.addEventListener("click", () => openModal(ch.id));
            fragment.appendChild(row);
        });
        dom.rankingRows.appendChild(fragment);
    }

    // --- Render: Grid (preserved for future reuse) ---

    function renderGrid(append) {
        if (!append) {
            dom.grid.innerHTML = "";
        }

        const startIdx = append ? state.channels.length - (state.offset - (state.channels.length - (state.offset - state.limit > 0 ? state.offset - state.limit : 0))) : 0;
        const channels = append ? state.channels.slice(state.channels.length - state.limit) : state.channels;

        if (state.channels.length === 0) {
            dom.emptyState.style.display = "block";
            dom.grid.style.display = "none";
            return;
        }

        dom.emptyState.style.display = "none";
        dom.grid.style.display = "grid";

        const fragment = document.createDocumentFragment();
        channels.forEach((ch) => {
            fragment.appendChild(createCard(ch));
        });

        if (append) {
            dom.grid.appendChild(fragment);
        } else {
            dom.grid.innerHTML = "";
            const allFragment = document.createDocumentFragment();
            state.channels.forEach((ch) => {
                allFragment.appendChild(createCard(ch));
            });
            dom.grid.appendChild(allFragment);
        }
    }

    function createCard(ch) {
        const card = document.createElement("div");
        card.className = "card";
        card.dataset.id = ch.id;

        const tier = ch.tier || "B";
        const score = ch.composite_score != null ? ch.composite_score.toFixed(1) : "--";
        const catName = ch.category_name || ch.primary_category || "";
        const catIcon = ch.category_icon || "";
        card.innerHTML = `
            <div class="card-header">
                <div class="card-avatar ${avatarClass(ch.primary_category)}">${firstLetter(ch.name)}</div>
                <div class="card-header-info">
                    <div class="card-name" title="${escapeHtml(ch.name)}">${escapeHtml(ch.name)}</div>
                    <div class="card-meta">
                        <span class="card-category-badge">${catIcon} ${escapeHtml(catName)}</span>
                        <span class="card-platform">${escapeHtml(ch.platform || "youtube")}</span>
                        <span class="card-lang">${escapeHtml((ch.language || "").toUpperCase())}</span>
                    </div>
                </div>
            </div>
            <div class="card-score-area">
                <div class="card-composite">
                    <span class="card-score-value ${scoreTierClass(tier)}">${score}</span>
                    <span class="card-score-max">/10</span>
                </div>
                <div class="card-tier ${tierClass(tier)}">${tier}</div>
            </div>
            <div class="card-criteria">
                ${CRITERIA.map((c) => {
                    const val = ch[c.key] != null ? ch[c.key] : 0;
                    const pct = (val / 10) * 100;
                    return `
                        <div class="criteria-row">
                            <span class="criteria-label">${c.short}</span>
                            <div class="criteria-bar-track">
                                <div class="criteria-bar-fill ${barTierClass(tier)}" style="width:${pct}%"></div>
                            </div>
                            <span class="criteria-value">${val || "--"}</span>
                        </div>`;
                }).join("")}
            </div>
        `;

        card.addEventListener("click", () => openModal(ch.id));
        return card;
    }

    // --- Load More ---

    function updateLoadMore() {
        if (state.channels.length < state.total) {
            dom.loadMoreWrap.style.display = "block";
        } else {
            dom.loadMoreWrap.style.display = "none";
        }
    }

    // --- Modal ---

    async function openModal(channelId) {
        const ch = await fetchChannel(channelId);
        if (!ch) return;

        const tier = ch.tier || "B";
        const score = ch.composite_score != null ? ch.composite_score.toFixed(1) : "--";
        const catName = ch.category_name || ch.primary_category || "";
        const catIcon = ch.category_icon || "";

        let statsHtml = "";
        if (ch.subscriber_count || ch.total_views || ch.video_count) {
            statsHtml = `
                <div class="modal-stats-row">
                    ${ch.subscriber_count != null ? `<div class="modal-stat"><span class="modal-stat-value">${formatNumber(ch.subscriber_count)}</span><span class="modal-stat-label">Subscribers</span></div>` : ""}
                    ${ch.total_views != null ? `<div class="modal-stat"><span class="modal-stat-value">${formatNumber(ch.total_views)}</span><span class="modal-stat-label">Total Views</span></div>` : ""}
                    ${ch.video_count != null ? `<div class="modal-stat"><span class="modal-stat-value">${formatNumber(ch.video_count)}</span><span class="modal-stat-label">Videos</span></div>` : ""}
                </div>`;
        }

        let descriptionHtml = "";
        if (ch.description) {
            descriptionHtml = `
                <div class="modal-section">
                    <div class="modal-section-title">About</div>
                    <div class="modal-description">${escapeHtml(ch.description)}</div>
                </div>`;
        }

        let notesHtml = "";
        if (ch.scoring_notes) {
            notesHtml = `
                <div class="modal-section">
                    <div class="modal-section-title">Scoring Notes</div>
                    <div class="modal-notes">${escapeHtml(ch.scoring_notes)}</div>
                </div>`;
        }

        let videosHtml = "";
        if (ch.sample_videos && ch.sample_videos.length > 0) {
            const links = ch.sample_videos
                .map((v) => {
                    const title = typeof v === "string" ? v : v.title || v.url || v;
                    const url = typeof v === "string" ? v : v.url || v;
                    return `
                        <a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="modal-video-link" onclick="event.stopPropagation()">
                            <span class="modal-video-icon">&#9654;</span>
                            <span class="modal-video-title">${escapeHtml(title)}</span>
                        </a>`;
                })
                .join("");
            videosHtml = `
                <div class="modal-section">
                    <div class="modal-section-title">Sample Videos</div>
                    <div class="modal-videos">${links}</div>
                </div>`;
        }

        dom.modalBody.innerHTML = `
            <div class="modal-header">
                ${ch.thumbnail_url
                    ? `<img class="modal-avatar modal-avatar-img" src="${ch.thumbnail_url}" alt="">`
                    : `<div class="modal-avatar ${avatarClass(ch.primary_category)}">${firstLetter(ch.name)}</div>`}
                <div class="modal-header-info">
                    <div class="modal-name">${escapeHtml(ch.name)}</div>
                    <div class="modal-meta">
                        <span class="modal-badge modal-badge-category">${catIcon} ${escapeHtml(catName)}</span>
                        <span class="modal-badge modal-badge-platform">${escapeHtml(ch.platform || "youtube")}</span>
                        <span class="modal-badge modal-badge-lang">${escapeHtml((ch.language || "").toUpperCase())}</span>
                        ${ch.url ? `<a href="${escapeHtml(ch.url)}" target="_blank" rel="noopener" class="modal-channel-link">&#x2197; Channel</a>` : ""}
                    </div>
                </div>
            </div>

            ${statsHtml}

            <div class="modal-score-section">
                <div class="modal-composite">
                    <div class="modal-score-num ${scoreTierClass(tier)}">${score}</div>
                    <div class="modal-score-label">Composite Score</div>
                </div>
                <div class="modal-tier-badge ${tierClass(tier)}">${tier}</div>
                <div class="modal-criteria-list">
                    ${CRITERIA.map((c) => {
                        const val = ch[c.key] != null ? ch[c.key] : 0;
                        const pct = (val / 10) * 100;
                        return `
                            <div class="modal-criteria-row">
                                <span class="modal-criteria-label">${c.label}</span>
                                <div class="modal-criteria-bar-track">
                                    <div class="modal-criteria-bar-fill ${barTierClass(tier)}" style="width:${pct}%"></div>
                                </div>
                                <span class="modal-criteria-value">${val || "--"}</span>
                            </div>`;
                    }).join("")}
                </div>
            </div>

            ${descriptionHtml}
            ${notesHtml}
            ${videosHtml}

            <div class="modal-section community-section">
                <div id="community-ratings"></div>
                <div id="community-comments"></div>
            </div>

            ${ch.url ? `
                <div class="modal-section">
                    <a href="${escapeHtml(ch.url)}" target="_blank" rel="noopener" class="modal-channel-link" onclick="event.stopPropagation()">
                        &#8594; Visit Channel
                    </a>
                </div>` : ""}
        `;

        dom.modalOverlay.classList.add("open");
        document.body.classList.add("modal-open");

        // Load community data asynchronously
        loadCommunityData(ch.id);
    }

    function closeModal() {
        dom.modalOverlay.classList.remove("open");
        document.body.classList.remove("modal-open");
    }

    // --- Community Render ---

    async function loadCommunityData(channelId) {
        const ratingsEl = document.getElementById("community-ratings");
        const commentsEl = document.getElementById("community-comments");
        if (!ratingsEl || !commentsEl) return;

        renderCommunityRatings(ratingsEl);

        commentsEl.innerHTML = '<div class="community-loading">Loading comments...</div>';
        const comments = await fetchComments(channelId, 0);
        renderCommunityComments(commentsEl, comments, channelId);
    }

    function renderCommunityRatings(container) {
        container.innerHTML = `
            <div class="community-section-header">
                <span class="community-section-title">Scoring</span>
            </div>
            <div class="community-empty" style="text-align:center;padding:1rem 0">
                <p>Adjust the global criterion weights on the homepage to see how scores change.</p>
                <button class="community-vote-btn" id="btn-scroll-weights" style="margin-top:0.5rem">
                    Customize Weights
                </button>
            </div>`;
        const scrollBtn = container.querySelector("#btn-scroll-weights");
        if (scrollBtn) {
            scrollBtn.addEventListener("click", () => {
                closeModal();
                openCustomizer();
            });
        }
    }

    function renderCommunityComments(container, data, channelId) {
        if (!data) {
            container.innerHTML = '<div class="community-empty">Could not load comments.</div>';
            return;
        }

        const comments = data.comments || [];
        const total = data.total || 0;

        let html = `<div class="community-section-header">
            <span class="community-section-title">Comments</span>
            <span class="community-voters">${total} comment${total !== 1 ? "s" : ""}</span>
        </div>`;

        // Post form
        html += `<div class="community-comment-form">
            <input type="text" class="community-input" id="comment-name"
                   placeholder="Name (optional)" maxlength="50">
            <textarea class="community-textarea" id="comment-content"
                      placeholder="Share your thoughts..." maxlength="2000" rows="3"></textarea>
            <button class="community-vote-btn" id="btn-post-comment">Post Comment</button>
        </div>`;

        // Comments list
        if (comments.length === 0) {
            html += '<div class="community-empty">No comments yet. Be the first!</div>';
        } else {
            html += '<div class="community-comments-list">';
            comments.forEach((c) => {
                const date = c.created_at ? new Date(c.created_at).toLocaleDateString() : "";
                html += `
                    <div class="community-comment">
                        <div class="community-comment-header">
                            <span class="community-comment-author">${escapeHtml(c.visitor_name || "Anonymous")}</span>
                            <span class="community-comment-date">${date}</span>
                        </div>
                        <div class="community-comment-body">${escapeHtml(c.content)}</div>
                        <button class="community-upvote-btn" data-comment-id="${c.id}">&#9650; ${c.upvotes || 0}</button>
                    </div>`;
            });
            html += "</div>";
        }

        container.innerHTML = html;

        // Post handler
        const postBtn = container.querySelector("#btn-post-comment");
        postBtn.addEventListener("click", async () => {
            const name = container.querySelector("#comment-name").value.trim();
            const content = container.querySelector("#comment-content").value.trim();
            if (!content) return;
            postBtn.disabled = true;
            postBtn.textContent = "Posting...";
            try {
                await postComment(channelId, name, content);
                loadCommunityData(channelId);
            } catch (e) {
                postBtn.textContent = "Error - Retry";
                postBtn.disabled = false;
                console.error("postComment:", e);
            }
        });

        // Upvote handlers
        container.querySelectorAll(".community-upvote-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const cid = btn.dataset.commentId;
                btn.disabled = true;
                try {
                    const result = await upvoteComment(cid);
                    btn.innerHTML = `&#9650; ${result.upvotes}`;
                } catch (e) {
                    console.error("upvote:", e);
                    btn.disabled = false;
                }
            });
        });
    }

    // --- Methodology ---

    async function showMethodology() {
        dom.viewIndex.style.display = "none";
        dom.viewMethodology.style.display = "block";

        // Update nav
        $$(".nav-link").forEach((l) => l.classList.remove("active"));
        $$('[data-nav="methodology"]').forEach((l) => l.classList.add("active"));

        if (!state.methodologyLoaded) {
            const md = await fetchMethodology();
            dom.methodologyContent.innerHTML = `<div class="methodology-rendered">${renderMarkdown(md)}</div>`;
            state.methodologyLoaded = true;
        }
    }

    function showIndex() {
        dom.viewIndex.style.display = "block";
        dom.viewMethodology.style.display = "none";

        $$(".nav-link").forEach((l) => l.classList.remove("active"));
        $$('[data-nav="index"]').forEach((l) => l.classList.add("active"));
    }

    /**
     * Minimal markdown-to-HTML renderer.
     * Handles headings, bold, italic, code, lists, blockquotes, tables, links, paragraphs.
     */
    function renderMarkdown(md) {
        if (!md) return "";
        const lines = md.split("\n");
        let html = "";
        let inList = false;
        let inTable = false;
        let listType = "";

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];

            // Table detection
            if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
                if (!inTable) {
                    if (inList) { html += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
                    inTable = true;
                    html += "<table>";
                    // Header row
                    const cells = line.split("|").filter((c) => c.trim());
                    html += "<tr>" + cells.map((c) => `<th>${inlineMarkdown(c.trim())}</th>`).join("") + "</tr>";
                    // Skip separator row
                    if (i + 1 < lines.length && lines[i + 1].match(/^\|[\s\-:|]+\|$/)) {
                        i++;
                    }
                    continue;
                } else {
                    const cells = line.split("|").filter((c) => c.trim());
                    html += "<tr>" + cells.map((c) => `<td>${inlineMarkdown(c.trim())}</td>`).join("") + "</tr>";
                    continue;
                }
            } else if (inTable) {
                html += "</table>";
                inTable = false;
            }

            // Headings
            const hMatch = line.match(/^(#{1,6})\s+(.*)/);
            if (hMatch) {
                if (inList) { html += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
                const level = hMatch[1].length;
                html += `<h${level}>${inlineMarkdown(hMatch[2])}</h${level}>`;
                continue;
            }

            // Blockquote
            if (line.startsWith("> ")) {
                if (inList) { html += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
                html += `<blockquote>${inlineMarkdown(line.slice(2))}</blockquote>`;
                continue;
            }

            // Unordered list
            const ulMatch = line.match(/^(\s*)[-*]\s+(.*)/);
            if (ulMatch) {
                if (!inList || listType !== "ul") {
                    if (inList) html += listType === "ul" ? "</ul>" : "</ol>";
                    html += "<ul>";
                    inList = true;
                    listType = "ul";
                }
                html += `<li>${inlineMarkdown(ulMatch[2])}</li>`;
                continue;
            }

            // Ordered list
            const olMatch = line.match(/^(\s*)\d+\.\s+(.*)/);
            if (olMatch) {
                if (!inList || listType !== "ol") {
                    if (inList) html += listType === "ul" ? "</ul>" : "</ol>";
                    html += "<ol>";
                    inList = true;
                    listType = "ol";
                }
                html += `<li>${inlineMarkdown(olMatch[2])}</li>`;
                continue;
            }

            // Close list if not matching
            if (inList && line.trim() === "") {
                html += listType === "ul" ? "</ul>" : "</ol>";
                inList = false;
            }

            // Empty line
            if (line.trim() === "") continue;

            // Paragraph
            if (inList) { html += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
            html += `<p>${inlineMarkdown(line)}</p>`;
        }

        if (inList) html += listType === "ul" ? "</ul>" : "</ol>";
        if (inTable) html += "</table>";
        return html;
    }

    function inlineMarkdown(text) {
        // Code
        text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
        // Bold
        text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        text = text.replace(/__([^_]+)__/g, "<strong>$1</strong>");
        // Italic
        text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
        text = text.replace(/_([^_]+)_/g, "<em>$1</em>");
        // Links
        text = text.replace(
            /\[([^\]]+)\]\(([^)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener">$1</a>'
        );
        return text;
    }

    // --- Routing ---

    function handleHash() {
        const hash = window.location.hash;
        if (hash === "#methodology") {
            showMethodology();
        } else {
            showIndex();
        }
    }

    // --- Filter Handlers ---

    function setupPillGroup(container, dataAttr, filterKey, serverSide) {
        container.addEventListener("click", (e) => {
            const pill = e.target.closest(".pill");
            if (!pill) return;

            // Toggle active
            container.querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
            pill.classList.add("active");

            const value = pill.dataset[dataAttr] || "";
            state.filters[filterKey] = value;
            fetchChannels(false);
        });
    }

    function setupSortPills() {
        dom.sortPills.addEventListener("click", (e) => {
            const pill = e.target.closest(".pill");
            if (!pill) return;

            dom.sortPills.querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
            pill.classList.add("active");

            state.filters.sort = pill.dataset.sort || "composite_score";
            state.filters.order = pill.dataset.order || "desc";
            fetchChannels(false);
        });
    }

    // --- Events ---

    function setupEvents() {
        // Pill filters
        setupPillGroup(dom.categoryPills, "category", "category", true);
        setupPillGroup(dom.tierPills, "tier", "tier", false);
        setupPillGroup(dom.langPills, "lang", "lang", false);
        setupSortPills();

        // Search with debounce
        dom.searchInput.addEventListener(
            "input",
            debounce(() => {
                state.filters.search = dom.searchInput.value.trim();
                fetchChannels(false);
            }, 300)
        );

        // Load more
        dom.btnLoadMore.addEventListener("click", () => {
            fetchChannels(true);
        });

        // Modal close
        dom.modalClose.addEventListener("click", closeModal);
        dom.modalOverlay.addEventListener("click", (e) => {
            if (e.target === dom.modalOverlay) closeModal();
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                closeModal();
                closeCustomizer();
            }
        });

        // Customizer modal
        const openBtn = document.getElementById("open-customizer");
        if (openBtn) openBtn.addEventListener("click", openCustomizer);
        const closeBtn = document.getElementById("customizer-close");
        if (closeBtn) closeBtn.addEventListener("click", closeCustomizer);
        const overlay = document.getElementById("customizer-overlay");
        if (overlay) overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeCustomizer();
        });

        // Navigation
        $$("[data-nav]").forEach((link) => {
            link.addEventListener("click", (e) => {
                e.preventDefault();
                const target = link.dataset.nav;
                if (target === "methodology") {
                    window.location.hash = "methodology";
                } else {
                    history.pushState(null, "", window.location.pathname);
                    showIndex();
                }
            });
        });

        // Hash changes
        window.addEventListener("hashchange", handleHash);
    }

    // --- Init ---

    async function init() {
        setupEvents();

        // Load data in parallel
        await Promise.all([fetchCategories(), fetchStats(), fetchChannels(false)]);

        // Init weight customizer after data is loaded
        initWeightSliders();

        // Check initial hash
        handleHash();
    }

    // Boot
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
