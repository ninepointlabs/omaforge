// omaforge.ninepointlabs.com: quest log, loot, toasts and other small joys.

(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* private window */ } },
  };

  // --- Achievements ---------------------------------------------------------
  const earned = new Set();
  const toasts = $("#toasts");

  function achieve(id, name, text, icon, points = 10) {
    if (earned.has(id)) return;
    earned.add(id);
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `<img alt=""><div><small>Achievement Earned</small><strong></strong><span></span></div><div class="points"></div>`;
    el.querySelector("img").src = icon;
    el.querySelector("strong").textContent = name;
    el.querySelector("span").textContent = text;
    el.querySelector(".points").textContent = points;
    toasts.append(el);
    setTimeout(() => el.remove(), 5200);
  }

  const zone = $("#zone-text");
  function announce(text) {
    zone.textContent = text;
    zone.classList.remove("show");
    void zone.offsetWidth; // restart the animation
    zone.classList.add("show");
    clearTimeout(announce.timer);
    announce.timer = setTimeout(() => zone.classList.remove("show"), 2700);
  }

  // --- Loading screen tips --------------------------------------------------
  const tips = [
    "omaforge backs up your WTF folder before every bulk update.",
    "Addons spread over many folders, like DBM or ElvUI, show as one entry and uninstall cleanly.",
    "Addons you installed by hand are recognized by their CurseForge fingerprint.",
    "Press Ctrl+K to search CurseForge, WoWInterface and GitHub at once.",
    "Pin an addon to keep its version. Ignore one to stop checking it for updates.",
    "Click any addon to read its description and see its screenshots before you install it.",
    "omaforge follows your Omarchy theme. Change themes and it changes with you.",
    "Paste a GitHub URL into Search to install straight from a repository's releases.",
    "Forever gets its own Explore lists, so you only see addons built for it.",
    "systemctl --user enable --now omaforge-update.timer keeps your addons current every day.",
  ];
  const tip = $("#tip");
  let tipIndex = 0;
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setInterval(() => {
      if (document.hidden) return;
      const box = tip.parentElement;
      box.classList.add("fade");
      setTimeout(() => {
        tipIndex = (tipIndex + 1) % tips.length;
        tip.textContent = tips[tipIndex];
        box.classList.remove("fade");
      }, 400);
    }, 6500);
  }

  // --- Faction --------------------------------------------------------------
  const factions = {
    alliance: { cry: "For the Alliance!", icon: "assets/art/alliance-crest.webp" },
    horde: { cry: "For the Horde!", icon: "assets/art/horde-sigil.webp" },
  };
  function setFaction(name, cheer) {
    const pick = factions[name] ? name : "neutral";
    document.documentElement.dataset.faction = pick;
    $$(".faction button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pick === pick)));
    store.set("omaforge-faction", pick);
    if (cheer && factions[pick]) {
      announce(factions[pick].cry);
      achieve(`faction-${pick}`, factions[pick].cry, "Chose a side. The addons don't mind either way.", factions[pick].icon, 5);
    }
  }
  setFaction(store.get("omaforge-faction"), false);
  $$(".faction button").forEach((b) =>
    b.addEventListener("click", () => {
      const current = document.documentElement.dataset.faction;
      setFaction(current === b.dataset.pick ? "neutral" : b.dataset.pick, current !== b.dataset.pick);
    }),
  );

  // --- Quest log ------------------------------------------------------------
  const quests = $$(".quest");
  const list = $("#ql-list");
  const accepted = new Set();
  let current = 0;

  function levelClass(level) {
    if (level >= 45) return "lvl-red";
    if (level >= 30) return "lvl-orange";
    if (level >= 20) return "lvl-yellow";
    return "lvl-green";
  }

  let lastZone = "";
  quests.forEach((q, i) => {
    if (q.dataset.zone !== lastZone) {
      lastZone = q.dataset.zone;
      const z = document.createElement("li");
      z.className = "ql-zone";
      z.textContent = lastZone;
      z.setAttribute("aria-hidden", "true");
      list.append(z);
    }
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.id = `tab-${q.id}`;
    b.className = levelClass(Number(q.dataset.level));
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", q.id);
    b.innerHTML = `<span class="lvl">[${q.dataset.level}]</span><span class="qname"></span>`;
    b.querySelector(".qname").textContent = $("h3", q).textContent;
    if (q.hasAttribute("data-new")) b.insertAdjacentHTML("beforeend", `<span class="new-mark">NEW</span>`);
    b.addEventListener("click", () => show(i));
    li.append(b);
    list.append(li);
    q.setAttribute("role", "tabpanel");
    q.setAttribute("aria-labelledby", b.id);
  });
  list.setAttribute("role", "tablist");
  list.setAttribute("aria-orientation", "vertical");

  function tabs() { return $$("button[role=tab]", list); }

  function show(i, focus = false) {
    current = (i + quests.length) % quests.length;
    quests.forEach((q, j) => q.classList.toggle("active", j === current));
    tabs().forEach((t, j) => {
      t.setAttribute("aria-selected", String(j === current));
      t.tabIndex = j === current ? 0 : -1;
    });
    if (focus) tabs()[current].focus();
    syncAccept();
  }

  list.addEventListener("keydown", (e) => {
    const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (step) { e.preventDefault(); show(current + step, true); }
  });

  const acceptBtn = $("#accept");
  function syncAccept() {
    const done = accepted.has(quests[current].id);
    acceptBtn.textContent = done ? "Accepted" : "Accept";
    acceptBtn.disabled = done;
    acceptBtn.style.opacity = done ? 0.6 : 1;
  }

  acceptBtn.addEventListener("click", () => {
    const q = quests[current];
    if (accepted.has(q.id)) return;
    accepted.add(q.id);
    q.classList.add("completed");
    const tab = tabs()[current];
    tab.querySelector(".new-mark")?.remove();
    tab.insertAdjacentHTML("beforeend", `<span class="done-mark" aria-label="accepted">✓</span>`);
    $("#ql-done").textContent = accepted.size;
    announce(`Quest accepted: ${$("h3", q).textContent}`);
    if (accepted.size === quests.length) {
      achieve("loremaster", "Loremaster of omaforge", "Accepted every quest in the log.",
        "assets/icons/achievement_quests_completed_08.jpg", 25);
    }
    syncAccept();
  });
  $("#next").addEventListener("click", () => show(current + 1));

  const deep = quests.findIndex((q) => `#${q.id}` === location.hash);
  show(deep >= 0 ? deep : 0);

  // --- Screenshot lightbox ---------------------------------------------------
  const box = $("#lightbox");
  if (box && typeof box.showModal === "function") {
    $$("[data-zoom]").forEach((b) =>
      b.addEventListener("click", () => {
        const img = $("img", b);
        $("img", box).src = img.currentSrc || img.src;
        $("img", box).alt = img.alt;
        box.showModal();
      }),
    );
    box.addEventListener("click", () => box.close());
  }

  // --- Loot -----------------------------------------------------------------
  $$("[data-copy]").forEach((b) =>
    b.addEventListener("click", async () => {
      const text = $("pre", b.closest(".loot-item")).innerText.trim();
      try {
        await navigator.clipboard.writeText(text);
        b.textContent = "Copied";
        setTimeout(() => (b.textContent = "Copy"), 1600);
        achieve("loot", "Loot Acquired", "Copied an install command. Now paste it.", "assets/icons/inv_misc_bag_10.jpg");
      } catch {
        b.textContent = "Select it";
      }
    }),
  );

  $("#trailer")?.addEventListener("play", () =>
    achieve("cinematic", "Don't Skip the Cinematic", "Watched the omaforge cinematic.", "assets/icons/inv_misc_spyglass_03.jpg"),
  );

  $(".gossip-bye")?.addEventListener("click", () =>
    achieve("farewell", "Well Met", "Talked to Innkeeper Forgewell.", "assets/icons/inv_misc_note_01.jpg", 5),
  );

  // The latest release: version and download links, when GitHub answers.
  fetch("https://api.github.com/repos/ninepointlabs/omaforge/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((rel) => {
      const match = {
        arch: (n) => n.endsWith(".pkg.tar.zst"),
        deb: (n) => n.endsWith(".deb"),
        rpm: (n) => n.endsWith(".rpm"),
      };
      $$("[data-version]").forEach((el) => (el.textContent = rel.tag_name));
      for (const [key, test] of Object.entries(match)) {
        const asset = (rel.assets || []).find((a) => test(a.name));
        if (!asset) continue;
        $$(`[data-asset="${key}"]`).forEach((el) => (el.textContent = asset.name));
        $$(`[data-download="${key}"]`).forEach((el) => (el.href = asset.browser_download_url));
      }
    })
    .catch(() => { /* keep the built-in version and the releases page link */ });
})();
