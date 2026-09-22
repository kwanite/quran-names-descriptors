(() => {
  const PAGE_SIZE = 40;

  const state = {
    descriptors: [],
    occurrenceByIdentity: new Map(),
    rootByOccurrence: new Map(),
    selected: null,
    visibleOccurrences: PAGE_SIZE,
  };

  const $ = (id) => document.getElementById(id);

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[c]));

  function foldSearch(s) {
    let x = String(s ?? "").toLowerCase();

    const translitMap = {
      "ʿ": "", "ʾ": "", "‘": "", "’": "", "ʻ": "", "ʼ": "", "`": "", "'": "",
      "ħ": "h", "ḫ": "kh", "ġ": "gh", "š": "sh", "č": "ch", "ǧ": "j",
      "ṯ": "th", "ḏ": "dh"
    };
    x = Array.from(x).map(ch => translitMap[ch] ?? ch).join("");
    x = x.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

    x = x
      .replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]/g, "")
      .replace(/[أإآٱ]/g, "ا")
      .replace(/ى/g, "ي")
      .replace(/ؤ/g, "و")
      .replace(/ئ/g, "ي")
      .replace(/ة/g, "ه")
      .replace(/ـ/g, "")
      .replace(/[^a-z0-9\u0600-\u06ff]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    return x;
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;

    const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    const cur = new Array(b.length + 1);

    for (let i = 1; i <= a.length; i++) {
      cur[0] = i;
      for (let j = 1; j <= b.length; j++) {
        cur[j] = Math.min(
          cur[j - 1] + 1,
          prev[j] + 1,
          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
        );
      }
      for (let j = 0; j <= b.length; j++) prev[j] = cur[j];
    }

    return prev[b.length];
  }

  function similarity(a, b) {
    const maxLen = Math.max(a.length, b.length);
    if (!maxLen) return 1;
    return 1 - levenshtein(a, b) / maxLen;
  }

  function searchScore(query, d) {
    if (!query) return 1;

    const fields = [
      d.lexical_identity_arabic,
      d.preferred_quran_surface,
      d.transliteration,
      d.english_gloss,
      ...(d.numbered_member_surfaces || []),
    ].map(foldSearch).filter(Boolean);

    let best = -1;

    for (const field of fields) {
      if (field === query) best = Math.max(best, 120);
      if (field.startsWith(query)) best = Math.max(best, 110);
      if (field.includes(query)) best = Math.max(best, 100);

      const compact = field.replace(/\s+/g, "");
      const qCompact = query.replace(/\s+/g, "");
      if (compact.includes(qCompact)) best = Math.max(best, 95);

      for (const token of field.split(" ")) {
        if (token.startsWith(query)) best = Math.max(best, 90);
        if (query.length >= 3 && token.length >= 3) {
          const sim = similarity(query, token);
          if (sim >= 0.67) best = Math.max(best, 55 + sim * 30);
        }
      }

      if (query.length >= 4 && field.length <= 40) {
        const sim = similarity(query, field);
        if (sim >= 0.72) best = Math.max(best, 50 + sim * 25);
      }
    }

    return best;
  }

  function isMulti(d) {
    return String(d.lexical_identity_arabic || "").trim().split(/\s+/).length > 1;
  }

  function highlightVerse(o) {
    const text = String(o.verse_text || "");
    const start = Number(o.start_offset);
    const end = Number(o.end_offset);

    if (
      Number.isInteger(start) &&
      Number.isInteger(end) &&
      start >= 0 &&
      end > start &&
      end <= text.length
    ) {
      return (
        esc(text.slice(0, start)) +
        "<mark>" + esc(text.slice(start, end)) + "</mark>" +
        esc(text.slice(end))
      );
    }

    return esc(text);
  }

  function filtered() {
    const q = foldSearch($("search").value);
    const type = $("typeFilter").value;

    const scored = [];

    for (const d of state.descriptors) {
      if (type === "one" && isMulti(d)) continue;
      if (type === "multi" && !isMulti(d)) continue;

      const score = searchScore(q, d);
      if (score < 0) continue;
      scored.push({ d, score });
    }

    if (q) {
      scored.sort((a, b) =>
        b.score - a.score ||
        Number(b.d.combined_occurrence_count || 0) - Number(a.d.combined_occurrence_count || 0) ||
        String(a.d.transliteration || a.d.lexical_identity_arabic).localeCompare(
          String(b.d.transliteration || b.d.lexical_identity_arabic)
        )
      );
    }

    return scored.map(x => x.d);
  }

  function renderList() {
    const list = filtered();
    $("listCount").textContent = `${list.length} / ${state.descriptors.length}`;

    $("descriptorList").innerHTML = list.length
      ? list.map(d => `
          <button
            class="descriptor-item ${state.selected === d.lexical_identity_arabic ? "active" : ""}"
            data-id="${esc(d.lexical_identity_arabic)}"
            type="button">
            <span class="descriptor-copy">
              <span class="descriptor-ar">${esc(d.preferred_quran_surface || d.lexical_identity_arabic)}</span>
              <span class="descriptor-tr">${esc(d.transliteration || "")}</span>
              <span class="descriptor-meaning">${esc(d.english_gloss || "")}</span>
            </span>
            <span class="count-pill">${Number(d.combined_occurrence_count || 0).toLocaleString()}</span>
          </button>
        `).join("")
      : '<div class="empty-state">No matches.</div>';

    document.querySelectorAll(".descriptor-item").forEach(btn => {
      btn.addEventListener("click", () => {
        select(btn.dataset.id);
        closeSidebar();
      });
    });
  }

  function formArabic(f) {
    return f?.display_arabic || f?.form_arabic || f?.headword_arabic || f?.qac_lemma_arabic || "";
  }

  function formDescription(f) {
    return f?.public_pos_label || f?.public_morphology_hint || f?.lexical_class || f?.part_of_speech || f?.form_label || "";
  }

  function descriptorRootSummary(d, occs) {
    const links = occs
      .map(o => state.rootByOccurrence.get(o.occurrence_id))
      .filter(Boolean);

    if (!links.length) return "";

    if (!isMulti(d)) {
      const unique = new Map();

      for (const link of links) {
        if (link.scope !== "one_word") continue;

        for (const f of link.public_forms || []) {
          const rootId = f?.root_id || "";
          const publicFormId = f?.public_form_id || f?.form_id || "";
          const key = `${rootId}|${publicFormId}`;
          if (!unique.has(key)) unique.set(key, f);
        }
      }

      if (!unique.size) return "";

      const cards = [...unique.values()].map(f => {
        const url = f?.pray_for_the_truth_root_url ||
          (f?.root_id ? `https://prayforthetruth.com/root/${encodeURIComponent(f.root_id)}` : "");
        const rootAr = f?.root_arabic || "";
        const head = formArabic(f);
        const pos = formDescription(f);
        const count = f?.root_dictionary_occurrence_count;

        return `
          <div class="descriptor-root-card">
            <div class="descriptor-root-head">
              ${rootAr ? `<span class="descriptor-root-arabic">${esc(rootAr)}</span>` : ""}
              ${head ? `<span class="root-word">${esc(head)}</span>` : ""}
            </div>
            <div class="descriptor-root-meta">
              ${pos ? `<div><strong>Form:</strong> ${esc(pos)}</div>` : ""}
              ${Number.isFinite(Number(count))
                ? `<div><strong>Occurrences of this form in the root dictionary:</strong> ${Number(count).toLocaleString()}</div>`
                : ""}
            </div>
            ${url
              ? `<a class="btn primary root-dictionary-link" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Open full root dictionary ↗</a>`
              : ""}
          </div>
        `;
      }).join("");

      return `
        <section class="section">
          <div class="section-head">
            <h2>Root dictionary</h2>
            <div class="section-sub">Exact one-word Quran Roots linkage</div>
          </div>
          <div class="section-body">
            <div class="descriptor-root-grid">${cards}</div>
          </div>
        </section>
      `;
    }

    const uniqueRoots = new Map();

    for (const link of links) {
      if (link.scope !== "multiword") continue;

      for (const word of link.constituent_words || []) {
        for (const r of word.roots || []) {
          const rootId = r?.root_id || "";
          const key = rootId || r?.root || r?.root_arabic || "";
          if (!key || uniqueRoots.has(key)) continue;

          const descriptions = [];
          for (const fg of r?.form_groups || []) {
            const label =
              fg?.public_pos_label ||
              fg?.public_morphology_hint ||
              fg?.lexical_class ||
              "";
            if (label && !descriptions.includes(label)) descriptions.push(label);
          }

          uniqueRoots.set(key, {
            root_id: rootId,
            root_arabic: r?.root_arabic || "",
            root_code: r?.root || "",
            descriptions,
          });
        }
      }
    }

    if (!uniqueRoots.size) return "";

    const cards = [...uniqueRoots.values()].map(r => {
      const url = r.root_id
        ? `https://prayforthetruth.com/root/${encodeURIComponent(r.root_id)}`
        : "";
      const rootLabel = r.root_arabic || r.root_code || "Root";

      return `
        <div class="descriptor-root-card">
          <div class="descriptor-root-head">
            <span class="descriptor-root-arabic">${esc(rootLabel)}</span>
          </div>
          <div class="descriptor-root-meta">
            ${r.descriptions.length
              ? `<div><strong>Forms represented in this phrase:</strong> ${r.descriptions.map(esc).join(" · ")}</div>`
              : ""}
          </div>
          ${url
            ? `<a class="btn primary root-dictionary-link" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Open this root in the Quran Roots Dictionary ↗</a>`
            : ""}
        </div>
      `;
    }).join("");

    return `
      <section class="section">
        <div class="section-head">
          <h2>Roots in this phrase</h2>
          <div class="section-sub">Constituent roots; the phrase remains one descriptor</div>
        </div>
        <div class="section-body">
          <div class="descriptor-root-grid">${cards}</div>
        </div>
      </section>
    `;
  }

  function occurrenceHtml(o) {
    const loc = o.record_type === "opening_basmala_unnumbered"
      ? o.source_key
      : o.verse_key;

    const quranLink = o.record_type === "opening_basmala_unnumbered"
      ? ""
      : `<a class="btn primary" target="_blank" rel="noopener noreferrer"
            href="https://prayforthetruth.com/quran/${esc(String(o.verse_key || "").replace(":", "/"))}">
           Read verse with English translation ↗
         </a>`;

    return `
      <article class="occ">
        <div class="occ-head">
          <div class="verse-key">${esc(loc)}</div>
          <div class="surface-hit">${esc(o.surface_arabic)}</div>
          <div class="occ-id">${esc(o.occurrence_id)}</div>
        </div>
        <div class="verse-panel">
          <div class="verse-ar">${highlightVerse(o)}</div>
          ${quranLink ? `<div style="margin-top:12px">${quranLink}</div>` : ""}
        </div>
      </article>
    `;
  }

  function renderDetail() {
    const d = state.descriptors.find(x => x.lexical_identity_arabic === state.selected);
    if (!d) {
      $("detail").innerHTML = '<div class="empty-state">Select a descriptor to inspect its Quran evidence.</div>';
      return;
    }

    const occs = state.occurrenceByIdentity.get(d.lexical_identity_arabic) || [];
    const visible = occs.slice(0, state.visibleOccurrences);

    const surfaces = (d.numbered_member_surfaces || [])
      .map(s => `<span class="surface">${esc(s)}</span>`)
      .join("");

    $("detail").innerHTML = `
      <header class="descriptor-header">
        <h2 class="title-ar">${esc(d.preferred_quran_surface || d.lexical_identity_arabic)}</h2>
        <div class="title-tr">${esc(d.transliteration || "")}</div>
        <div class="title-meaning"><span class="title-meaning-label">English meaning</span>${esc(d.english_gloss || "")}</div>
      </header>

      <section class="stats" aria-label="Descriptor statistics">
        <div class="stat">
          <div class="k">In numbered verses</div>
          <div class="v">${Number(d.numbered_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Opening basmalas</div>
          <div class="v">${Number(d.basmala_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Total occurrences</div>
          <div class="v">${Number(d.combined_occurrence_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Arabic forms</div>
          <div class="v">${Number(d.exact_numbered_surface_count || 0).toLocaleString()}</div>
        </div>
        <div class="stat">
          <div class="k">Expression type</div>
          <div class="v">${isMulti(d) ? "Multiword phrase" : "Single word"}</div>
        </div>
      </section>

      ${descriptorRootSummary(d, occs)}

      <section class="section">
        <div class="section-head">
          <h2>Arabic forms found in the Quran</h2>
          <div class="section-sub">Exact forms of this descriptor in numbered verses</div>
        </div>
        <div class="section-body">
          <div class="surface-wrap">${surfaces || '<span class="small">No numbered-verse forms.</span>'}</div>
          <div class="surface-explainer">These chips preserve the exact Arabic form used in the Quran. The same descriptor can appear with different case endings, attached particles, or orthographic forms.</div>
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <h2>Where it occurs in the Quran</h2>
          <div class="section-sub">${occs.length.toLocaleString()} occurrences, including preserved opening basmalas</div>
        </div>
        <div class="section-body">
          <div class="occ-list">${visible.map(occurrenceHtml).join("")}</div>
          ${visible.length < occs.length ? `
            <div class="more-row">
              <button id="showMore" class="btn" type="button">
                Show ${Math.min(PAGE_SIZE, occs.length - visible.length)} more
              </button>
            </div>
          ` : ""}
        </div>
      </section>
    `;

    const more = $("showMore");
    if (more) {
      more.addEventListener("click", () => {
        state.visibleOccurrences += PAGE_SIZE;
        renderDetail();
      });
    }
  }

  function select(identity) {
    state.selected = identity;
    state.visibleOccurrences = PAGE_SIZE;
    renderList();
    renderDetail();
  }

  function openSidebar() {
    $("sidebar").classList.add("open");
  }

  function closeSidebar() {
    $("sidebar").classList.remove("open");
  }

  async function load() {
    const [d, o, r, v] = await Promise.all([
      fetch("./data/descriptors.json").then(x => x.json()),
      fetch("./data/occurrence_ledger.json").then(x => x.json()),
      fetch("./data/root_links.json").then(x => x.json()),
      fetch("./data/validation_report.json").then(x => x.json()),
    ]);

    state.descriptors = d.descriptors || [];

    for (const row of o.occurrences || []) {
      const key = row.lexical_identity_arabic;
      if (!state.occurrenceByIdentity.has(key)) {
        state.occurrenceByIdentity.set(key, []);
      }
      state.occurrenceByIdentity.get(key).push(row);
    }

    for (const link of r.links || []) {
      state.rootByOccurrence.set(link.occurrence_id, link);
    }

    const expected = Number(v?.counts?.lexical_identities || 0);
    if (expected && state.descriptors.length !== expected) {
      throw new Error(
        `Descriptor count mismatch: viewer loaded ${state.descriptors.length}, validation expects ${expected}.`
      );
    }

    $("loading").hidden = true;
    $("app").hidden = false;

    renderList();

    if (state.descriptors.length) {
      select(state.descriptors[0].lexical_identity_arabic);
    }
  }

  $("search").addEventListener("input", renderList);
  $("typeFilter").addEventListener("change", renderList);
  $("openSidebar").addEventListener("click", openSidebar);
  $("closeSidebar").addEventListener("click", closeSidebar);

  load().catch(err => {
    console.error(err);
    $("loading").innerHTML = `
      <div class="fatal">
        <strong>Could not load publication data.</strong>
        <div class="small" style="margin-top:8px">${esc(err.message)}</div>
      </div>
    `;
  });
})();
