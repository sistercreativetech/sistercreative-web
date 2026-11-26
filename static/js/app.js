(() => {
  "use strict";

  // --- Menu navigasi mobile -------------------------------------------------
  const menuButton = document.querySelector("[data-menu-button]");
  const nav = document.querySelector("[data-menu]");

  if (menuButton && nav) {
    const iconOpen = menuButton.querySelector("[data-icon-open]");
    const iconClose = menuButton.querySelector("[data-icon-close]");

    const setOpen = (open) => {
      nav.classList.toggle("hidden", !open);
      nav.classList.toggle("flex", open);
      menuButton.setAttribute("aria-expanded", String(open));
      menuButton.setAttribute("aria-label", open ? "Tutup menu" : "Buka menu");
      iconOpen?.classList.toggle("hidden", open);
      iconClose?.classList.toggle("hidden", !open);
    };

    menuButton.addEventListener("click", () => {
      setOpen(menuButton.getAttribute("aria-expanded") !== "true");
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setOpen(false));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        menuButton.focus();
      }
    });
  }

  // --- Sesi WhatsApp: perbarui QR & muat ulang saat status berubah ---------
  const waSession = document.querySelector("[data-wa-session]");
  const waitingStatuses = ["STARTING", "SCAN_QR_CODE"];

  if (waSession && waitingStatuses.includes(waSession.dataset.status)) {
    const qrImage = waSession.querySelector("[data-wa-qr]");
    let ticks = 0;

    const pollSession = async () => {
      ticks += 1;
      try {
        const response = await fetch(waSession.dataset.statusUrl, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (response.ok) {
          const data = await response.json();
          if (data.status !== waSession.dataset.status) {
            window.location.reload();
            return;
          }
        }
      } catch (error) {
        // Jaringan putus sesaat: coba lagi di putaran berikutnya.
      }
      // QR WhatsApp berganti sekitar tiap 20 detik.
      if (qrImage && ticks % 4 === 0) {
        qrImage.src = `${waSession.dataset.qrUrl}?t=${Date.now()}`;
      }
      if (ticks < 120) window.setTimeout(pollSession, 5000);
    };
    window.setTimeout(pollSession, 5000);
  }

  // --- Progres kampanye ---------------------------------------------------
  const setProgress = (root, data) => {
    const fill = root.querySelector("[data-progress-fill]");
    const bar = root.querySelector("[data-progress-bar]");
    const percent = Math.max(0, Math.min(100, Number(data.percent) || 0));
    if (fill) fill.style.scale = `${percent / 100} 1`;
    if (bar) bar.setAttribute("aria-valuenow", String(percent));
    ["total", "sent", "failed", "pending"].forEach((key) => {
      const el = root.querySelector(`[data-progress="${key}"]`);
      if (el && data[key] !== undefined) el.textContent = data[key];
    });
  };

  document.querySelectorAll("[data-progress-fill]").forEach((fill) => {
    const percent = Math.max(0, Math.min(100, Number(fill.dataset.percent) || 0));
    fill.style.scale = `${percent / 100} 1`;
  });

  const progressRoot = document.querySelector("[data-campaign-progress]");
  if (progressRoot) {
    const pollProgress = async () => {
      try {
        const response = await fetch(progressRoot.dataset.campaignProgress, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (response.ok) {
          const data = await response.json();
          setProgress(progressRoot, data);
          if (!["queued", "running"].includes(data.status)) {
            window.location.reload();
            return;
          }
        }
      } catch (error) {
        // Abaikan; coba lagi.
      }
      window.setTimeout(pollProgress, 5000);
    };
    window.setTimeout(pollProgress, 5000);
  }

  // --- Animasi reveal (Motion) ----------------------------------------------
  const revealItems = document.querySelectorAll("[data-reveal]");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const showAll = () => revealItems.forEach((el) => el.classList.add("is-revealed"));

  if (reduceMotion || !window.Motion) {
    showAll();
    return;
  }

  const { animate, inView } = window.Motion;

  revealItems.forEach((el) => {
    inView(
      el,
      () => {
        el.classList.add("is-revealed");
        animate(
          el,
          { opacity: [0, 1], y: [22, 0] },
          { duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: Number(el.dataset.revealDelay || 0) }
        );
      },
      { amount: 0.12 }
    );
  });
})();
